"""Filesystem persistence for active campaigns.

Each campaign gets a UUID directory under campaign_states/.
The state.json within records everything needed to:
  - Post Slack messages back to the right thread
  - Reconstruct pipeline state for a revision run
  - Track per-draft approval status
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from agent.models.plan import CampaignPlan
from agent.models.product import ProductLookupResult

_STORE_DIR = Path(__file__).parents[2] / "campaign_states"


def _state_path(campaign_id: str) -> Path:
    d = _STORE_DIR / campaign_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "state.json"


def new_campaign_id() -> str:
    return str(uuid.uuid4())


def save_campaign(
    campaign_id: str,
    *,
    channel: str,
    user: str,
    brief_text: str,
    product_lookup: ProductLookupResult,
    plan: CampaignPlan,
    trace_path: str | None,
    drafts: dict[str, dict],
    selected_image: dict | None = None,
    image_alternatives: list[dict] | None = None,
) -> None:
    """
    Persist a completed campaign run.

    drafts: mapping of audience_id ->
        {subject_line, html_file_path, status, thread_ts, draft_content}
    thread_ts: ts of the top-level Slack message for that draft's thread
    draft_content: serialized ContentDraft dict for use by the editor node
    Status values: "pending" | "approved" | "rejected"
    """
    data = {
        "campaign_id": campaign_id,
        "channel": channel,
        "user": user,
        "brief_text": brief_text,
        "trace_path": trace_path,
        "product_lookup": product_lookup.model_dump(),
        "plan": plan.model_dump(),
        "selected_image": selected_image,
        "image_alternatives": image_alternatives or [],
        "drafts": drafts,
    }
    _state_path(campaign_id).write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )


def load_campaign(campaign_id: str) -> dict:
    return json.loads(_state_path(campaign_id).read_text(encoding="utf-8"))


def update_draft_status(
    campaign_id: str,
    audience_id: str,
    status: str,
    feedback: str | None = None,
) -> None:
    data = load_campaign(campaign_id)
    draft = data["drafts"].get(audience_id, {})
    draft["status"] = status
    if feedback is not None:
        draft["feedback"] = feedback
    data["drafts"][audience_id] = draft
    _state_path(campaign_id).write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )


def update_draft_button_ts(
    campaign_id: str, audience_id: str, message_ts: str
) -> None:
    """Store the ts of the button message so we can update it later."""
    data = load_campaign(campaign_id)
    draft = data["drafts"].get(audience_id, {})
    draft["button_message_ts"] = message_ts
    data["drafts"][audience_id] = draft
    _state_path(campaign_id).write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )


def update_draft_after_revision(
    campaign_id: str,
    audience_id: str,
    html_file_path: str,
    draft_content: dict,
) -> None:
    """Update HTML path and draft content after a successful revision; reset status to pending."""
    data = load_campaign(campaign_id)
    draft = data["drafts"].get(audience_id, {})
    draft["html_file_path"] = html_file_path
    draft["draft_content"] = draft_content
    draft["status"] = "pending"
    data["drafts"][audience_id] = draft
    _state_path(campaign_id).write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )


def update_image_after_swap(
    campaign_id: str, new_selected: dict, old_selected: dict | None
) -> None:
    """After an image swap: update selected_image. The old image moves to alternatives if not already there."""
    data = load_campaign(campaign_id)
    data["selected_image"] = new_selected
    # Remove the newly selected image from alternatives, add the old one back if it's not already there
    alts: list[dict] = data.get("image_alternatives", [])
    alts = [a for a in alts if a["filename"] != new_selected["filename"]]
    if old_selected and not any(a["filename"] == old_selected["filename"] for a in alts):
        alts.append(old_selected)
    data["image_alternatives"] = alts
    _state_path(campaign_id).write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )


def update_trace_path(campaign_id: str, trace_path: str) -> None:
    data = load_campaign(campaign_id)
    data["trace_path"] = trace_path
    _state_path(campaign_id).write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )
