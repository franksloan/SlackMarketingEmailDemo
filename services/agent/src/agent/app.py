import hashlib
import hmac
import json
import os
import time

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from loguru import logger
from slack_sdk import WebClient

from agent.campaign_store import (
    load_campaign,
    new_campaign_id,
    save_campaign,
    update_draft_after_revision,
    update_draft_button_ts,
    update_draft_status,
    update_image_after_swap,
    update_trace_path,
)
from agent.models.brief import CampaignBrief
from agent.models.draft import ContentDraft
from agent.models.plan import CampaignPlan
from agent.models.product import ProductLookupResult
from agent.orchestrator import graph, revision_graph
from agent.tracing import finish_run, start_run

load_dotenv()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]

slack_client = WebClient(token=SLACK_BOT_TOKEN)

app = FastAPI(title="Slack Marketing Email Agent")


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> None:
    """Raise HTTPException if the request signature is invalid or too old."""
    if abs(time.time() - float(timestamp)) > 300:
        raise HTTPException(status_code=403, detail="Request too old")
    sig_basestring = f"v0:{timestamp}:{body.decode()}"
    expected = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")


# ---------------------------------------------------------------------------
# Block Kit helpers
# ---------------------------------------------------------------------------

def _draft_approval_blocks(
    campaign_id: str, audience_id: str, subject_line: str
) -> list[dict]:
    value = json.dumps({"campaign_id": campaign_id, "audience_id": audience_id})
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{subject_line}*\n"
                    f"Approve to mark this draft ready, or reject to provide feedback and trigger a revision."
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "action_id": "approve_draft",
                    "value": value,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "action_id": "reject_draft",
                    "value": value,
                },
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Initial pipeline run
# ---------------------------------------------------------------------------

async def process_request(
    text: str, channel: str, user: str, campaign_id: str
) -> None:
    """Run the agent pipeline, streaming status updates, then post each draft in its own thread."""
    raw_text = text or "Generate a marketing email for an AWS product."
    start_run(raw_text)
    trace_path_str: str | None = None

    # Post the initial ack here so we return to Slack immediately in the event handler
    ack = slack_client.chat_postMessage(
        channel=channel,
        text=f"<@{user}> Got it, looking up product...",
    )
    status_ts = ack["ts"]

    def update_status(msg: str) -> None:
        slack_client.chat_update(channel=channel, ts=status_ts, text=f"<@{user}> {msg}")

    try:
        brief = CampaignBrief(raw_text=raw_text)

        # Stream the graph so we can post status updates as each node completes
        accumulated: dict = {"brief": brief}
        status_milestones: set[str] = set()

        async for chunk in graph.astream({"brief": brief}, stream_mode="updates"):
            if not chunk:
                continue
            for node_name, node_updates in chunk.items():
                if not node_updates:
                    logger.debug(f"Stream: node '{node_name}' returned empty update — skipping")
                    continue
                # Merge updates — list fields (research_findings, drafts, etc.) are appended
                for k, v in node_updates.items():
                    if isinstance(v, list) and isinstance(accumulated.get(k), list):
                        accumulated[k] = accumulated[k] + v
                    else:
                        accumulated[k] = v

                # Status updates at key milestones (once per milestone, not once per audience)
                if node_name == "product_lookup":
                    lookup = node_updates.get("product_lookup")
                    if lookup and lookup.confidence == "high":
                        update_status(
                            f"Identified *{lookup.product.name}* — planning campaign..."
                        )

                elif node_name == "planning":
                    plan = node_updates.get("plan")
                    if plan:
                        audiences = ", ".join(a.title for a in plan.matched_audiences)
                        update_status(f"Campaign planned — researching: _{audiences}_...")

                elif node_name == "drafting" and "drafting" not in status_milestones:
                    status_milestones.add("drafting")
                    update_status("Research complete — drafting content...")

                elif node_name == "review" and "review" not in status_milestones:
                    status_milestones.add("review")
                    update_status("Drafts complete — reviewing content...")

                elif node_name == "html_check" and "html_check" not in status_milestones:
                    status_milestones.add("html_check")
                    update_status("Drafts ready — posting now...")

        result = accumulated

        lookup = result.get("product_lookup")

        # Product was ambiguous — ask the user to clarify
        if not lookup or lookup.confidence == "low":
            clarification = (
                lookup.clarification_message
                if lookup
                else "I couldn't identify an AWS product from your message. Could you provide more detail?"
            )
            update_status(clarification)
            return

        # No audience identified — ask the user to specify one
        plan_clarification = result.get("plan_clarification")
        if plan_clarification:
            update_status(plan_clarification)
            return

        drafts = result.get("drafts", [])
        plan = result.get("plan")
        html_file_paths = result.get("html_file_paths", [])
        selected_image = result.get("selected_image")
        image_alternatives = result.get("image_alternatives", [])

        # Build lookup maps
        drafts_by_audience = {d.audience_id: d for d in drafts}
        reviews_by_audience = {r.audience_id: r for r in result.get("reviews", [])}
        html_paths_by_audience: dict[str, str] = {}
        for path in html_file_paths:
            audience_id = os.path.basename(path).removeprefix("email_").removesuffix(".html")
            html_paths_by_audience[audience_id] = path

        audience_by_id = {a.id: a for a in plan.matched_audiences} if plan else {}
        draft_store: dict[str, dict] = {}

        # Each draft gets its own top-level thread (no extra summary message)
        for audience_id, draft in drafts_by_audience.items():
            html_path = html_paths_by_audience.get(audience_id)
            audience = audience_by_id.get(audience_id)
            audience_title = audience.title if audience else audience_id

            # Thread-root message for this draft
            root = slack_client.chat_postMessage(
                channel=channel,
                text=f"*{audience_title}* — {draft.subject_line}",
            )
            thread_ts = root["ts"]

            # HTML file as a reply in this draft's thread
            if html_path:
                slack_client.files_upload_v2(
                    channel=channel,
                    thread_ts=thread_ts,
                    file=html_path,
                    filename=os.path.basename(html_path),
                )

            # Review score summary
            review = reviews_by_audience.get(audience_id)
            if review:
                score = review.overall_score
                if score < 7:
                    score_line = f":warning: *Quality score: {score}/10* — this draft may need revision."
                    if review.issues:
                        score_line += f"\n*Issues:* {', '.join(review.issues[:3])}"
                else:
                    score_line = f":white_check_mark: *Quality score: {score}/10*"
                    if review.suggestions:
                        score_line += f"\n*Suggestions:* {', '.join(review.suggestions[:2])}"
                slack_client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=score_line,
                )

            # Approval buttons in the same thread
            btn_response = slack_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"Review draft for {audience_title}",
                blocks=_draft_approval_blocks(campaign_id, audience_id, draft.subject_line),
            )

            draft_store[audience_id] = {
                "subject_line": draft.subject_line,
                "html_file_path": html_path or "",
                "status": "pending",
                "thread_ts": thread_ts,
                "button_message_ts": btn_response["ts"],
                "draft_content": draft.model_dump(),
            }

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        update_status("Something went wrong running the pipeline. Please try again.")
        return
    finally:
        trace_path = finish_run()
        trace_path_str = str(trace_path) if trace_path else None
        if trace_path:
            logger.info(f"Trace written to {trace_path}")

    # Persist campaign state for later approval/revision
    try:
        save_campaign(
            campaign_id,
            channel=channel,
            user=user,
            brief_text=text,
            product_lookup=result["product_lookup"],
            plan=result["plan"],
            trace_path=trace_path_str,
            selected_image=result.get("selected_image"),
            image_alternatives=result.get("image_alternatives", []),
            drafts=draft_store,
        )
    except Exception as e:
        logger.error(f"Failed to save campaign state: {e}")


# ---------------------------------------------------------------------------
# Revision run (after a rejection)
# ---------------------------------------------------------------------------

async def process_revision(
    campaign_id: str,
    audience_id: str,
    feedback: str,
    user: str,
) -> None:
    """Route to edit or regenerate based on feedback, post result in the draft's thread."""
    campaign = load_campaign(campaign_id)
    channel = campaign["channel"]
    draft_entry = campaign["drafts"].get(audience_id, {})
    thread_ts = draft_entry.get("thread_ts")

    # Reconstruct pipeline state from saved campaign
    product_lookup = ProductLookupResult.model_validate(campaign["product_lookup"])
    plan = CampaignPlan.model_validate(campaign["plan"])
    brief = CampaignBrief(raw_text=campaign["brief_text"])
    existing_draft = (
        ContentDraft.model_validate(draft_entry["draft_content"])
        if draft_entry.get("draft_content")
        else None
    )

    slack_client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=f"<@{user}> Working on a revision...",
    )

    current_image = campaign.get("selected_image")
    image_alternatives = campaign.get("image_alternatives", [])

    start_run(f"[REVISION:{audience_id}] {campaign['brief_text']}")
    try:
        revision_state: dict = {
            "brief": brief,
            "product_lookup": product_lookup,
            "plan": plan,
            "feedback": feedback,
            "previous_trace_path": campaign.get("trace_path"),
            "target_audience_ids": [audience_id],
            # Editor reads these to decide whether/how to swap the image
            "selected_image": current_image,
            "image_alternatives": image_alternatives,
        }
        if existing_draft:
            revision_state["existing_draft"] = existing_draft

        result = await revision_graph.ainvoke(revision_state)

        new_drafts = result.get("drafts", [])
        new_html_paths = result.get("html_file_paths", [])
        revision_action = result.get("revision_action", "unknown")

        if not new_drafts:
            slack_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"<@{user}> The revision didn't produce a draft. Please try again.",
            )
            return

        revised_draft = new_drafts[0]
        html_path = new_html_paths[0] if new_html_paths else None
        audience = next(
            (a for a in plan.matched_audiences if a.id == audience_id), None
        )
        audience_title = audience.title if audience else audience_id
        action_label = "Edited" if revision_action == "edit" else "Regenerated"

        # Upload revised HTML in the draft's thread
        if html_path:
            slack_client.files_upload_v2(
                channel=channel,
                thread_ts=thread_ts,
                file=html_path,
                filename=os.path.basename(html_path),
                initial_comment=f"*{action_label}:* {revised_draft.subject_line}",
            )

        # Review score for regenerated drafts (edit path skips review, so reviews may be empty)
        revised_reviews = result.get("reviews", [])
        if revised_reviews:
            rev = revised_reviews[0]
            score = rev.overall_score
            if score < 7:
                score_line = f":warning: *Quality score: {score}/10* — this revision may still need work."
                if rev.issues:
                    score_line += f"\n*Issues:* {', '.join(rev.issues[:3])}"
            else:
                score_line = f":white_check_mark: *Quality score: {score}/10*"
            slack_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=score_line,
            )

        # Post new approval buttons in the thread
        btn_response = slack_client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"Review revised draft for {audience_title}",
            blocks=_draft_approval_blocks(campaign_id, audience_id, revised_draft.subject_line),
        )
        update_draft_button_ts(campaign_id, audience_id, btn_response["ts"])
        update_draft_after_revision(
            campaign_id,
            audience_id,
            html_path or draft_entry.get("html_file_path", ""),
            revised_draft.model_dump(),
        )
        # If the editor swapped the image, rotate selected/alternatives so next revision sees fresh options
        new_image = result.get("selected_image")
        if new_image and current_image and new_image["filename"] != current_image["filename"]:
            update_image_after_swap(campaign_id, new_image, current_image)

    except Exception as e:
        logger.error(f"Revision failed: {e}")
        slack_client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"Sorry <@{user}>, the revision failed. Please try again.",
        )
    finally:
        trace_path = finish_run()
        if trace_path:
            logger.info(f"Revision trace written to {trace_path}")
            update_trace_path(campaign_id, str(trace_path))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def health() -> dict:
    return {"status": "ok"}




@app.post("/slack/events")
async def slack_events(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_request_timestamp: str = Header(...),
    x_slack_signature: str = Header(...),
    x_slack_retry_num: str | None = Header(default=None),
) -> dict:
    # Slack retries if we don't respond within 3s — ignore retries to avoid duplicate runs
    if x_slack_retry_num is not None:
        logger.debug(f"Dropping Slack retry #{x_slack_retry_num}")
        return {"ok": True}

    body = await request.body()
    verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature)

    payload = await request.json()

    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    event = payload.get("event", {})
    if event.get("type") == "app_mention":
        channel = event["channel"]
        user = event["user"]
        text: str = event.get("text", "")

        if ">" in text:
            text = text.split(">", 1)[1].strip()

        logger.info(f"app_mention from {user} in {channel}: {text!r}")

        campaign_id = new_campaign_id()

        background_tasks.add_task(
            process_request, text, channel, user, campaign_id
        )

    return {"ok": True}


@app.post("/slack/actions")
async def slack_actions(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_request_timestamp: str = Header(...),
    x_slack_signature: str = Header(...),
) -> dict:
    """Handle Slack interactive component payloads (button clicks and modal submissions)."""
    body = await request.body()
    verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature)

    form_data = await request.form()
    payload = json.loads(form_data["payload"])
    payload_type = payload.get("type")

    if payload_type == "block_actions":
        action = payload["actions"][0]
        action_id = action["action_id"]
        value = json.loads(action["value"])
        campaign_id = value["campaign_id"]
        audience_id = value["audience_id"]
        channel = payload["channel"]["id"]
        message_ts = payload["message"]["ts"]
        user = payload["user"]["id"]

        if action_id == "approve_draft":
            update_draft_status(campaign_id, audience_id, "approved")
            slack_client.chat_update(
                channel=channel,
                ts=message_ts,
                text=f"*{audience_id}* draft approved by <@{user}>",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{audience_id}* draft approved by <@{user}>",
                        },
                    }
                ],
            )

        elif action_id == "reject_draft":
            # Open feedback modal — must happen synchronously (trigger_id expires in 3s)
            meta = json.dumps({
                "campaign_id": campaign_id,
                "audience_id": audience_id,
                "channel": channel,
                "message_ts": message_ts,
                "user": user,
            })
            slack_client.views_open(
                trigger_id=payload["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "reject_feedback",
                    "private_metadata": meta,
                    "title": {"type": "plain_text", "text": "Reject Draft"},
                    "submit": {"type": "plain_text", "text": "Submit"},
                    "close": {"type": "plain_text", "text": "Cancel"},
                    "blocks": [
                        {
                            "type": "input",
                            "block_id": "feedback_block",
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "feedback_input",
                                "multiline": True,
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "What needs to change in this draft?",
                                },
                            },
                            "label": {"type": "plain_text", "text": "Feedback"},
                        }
                    ],
                },
            )

    elif payload_type == "view_submission":
        if payload["view"]["callback_id"] != "reject_feedback":
            return {"response_action": "clear"}

        meta = json.loads(payload["view"]["private_metadata"])
        campaign_id = meta["campaign_id"]
        audience_id = meta["audience_id"]
        channel = meta["channel"]
        message_ts = meta["message_ts"]
        user = meta["user"]

        feedback = (
            payload["view"]["state"]["values"]["feedback_block"]["feedback_input"]["value"]
        )

        # Update the button message in the draft's thread to show it's been rejected
        slack_client.chat_update(
            channel=channel,
            ts=message_ts,
            text="Draft rejected — revision in progress",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{audience_id}* rejected by <@{user}> — revising...\n> _{feedback}_",
                    },
                }
            ],
        )

        update_draft_status(campaign_id, audience_id, "rejected", feedback=feedback)
        background_tasks.add_task(
            process_revision, campaign_id, audience_id, feedback, user
        )

        return {"response_action": "clear"}

    return {"ok": True}
