import json
from pathlib import Path
from typing import Any, Literal

from agent.llm import llm
from pydantic import BaseModel, Field

from agent.models.audience import AudienceMessaging, AudienceProfile
from agent.models.plan import CampaignPlan
from agent.models.state import AgentState
from agent.tracing import elapsed_ms, save_trace, start_timer

_PLAYBOOK_PATH = Path(__file__).parents[3] / "assets" / "playbook_knowledge.json"
_llm = llm


# Internal model — LLM returns audience IDs from the known list rather than full objects
class _PlanningOutput(BaseModel):
    thinking_and_reasoning: str = Field(
        description="Step-by-step reasoning: how the brief maps to audiences, why this objective and tone were chosen"
    )
    matched_audience_ids: list[str] = Field(
        description="IDs from the known audience list that match the brief, max 4"
    )
    primary_objective: str
    tone: str
    content_format: Literal["email", "landing_page"]
    suggested_sections: list[str]
    success_criteria: str


_structured = _llm.with_structured_output(_PlanningOutput)


def _load_playbook() -> dict:
    with open(_PLAYBOOK_PATH) as f:
        return json.load(f)


def _load_previous_planning_entry(trace_path: str) -> dict[str, Any] | None:
    """Return the planning node entry from a previous trace file, or None."""
    try:
        trace = json.loads(Path(trace_path).read_text(encoding="utf-8"))
        return next(
            (n for n in trace.get("nodes", []) if n.get("node") == "planning"),
            None,
        )
    except (OSError, json.JSONDecodeError):
        return None


def _keyword_detected_audiences(brief_text: str, detection_hints: dict) -> list[str]:
    """Return audience IDs whose hint keywords appear in the brief (case-insensitive)."""
    text_lower = brief_text.lower()
    return [
        audience_id
        for audience_id, keywords in detection_hints.items()
        if any(kw.lower() in text_lower for kw in keywords)
    ]


async def planning_node(state: AgentState) -> dict:
    t0 = start_timer()
    brief = state["brief"]
    product = state["product_lookup"].product
    playbook = _load_playbook()

    known_audiences = playbook["audiences"]
    detection_hints = playbook["audience_detection_hints"]

    # Hard gate: require at least one audience keyword before proceeding
    detected_ids = _keyword_detected_audiences(brief.raw_text, detection_hints)
    if not detected_ids:
        known_list = "\n".join(f"- *{a['id']}*: {a['title']}" for a in known_audiences)
        clarification = (
            "I need to know which audience(s) this campaign should target. "
            "Could you mention the role(s) in your request?\n\n"
            f"Available audiences:\n{known_list}"
        )
        save_trace(
            node="planning",
            inputs={"brief": brief.raw_text, "product": product.model_dump()},
            thinking_and_reasoning="No audience keywords detected in brief — skipping LLM, returning clarification.",
            outputs={"clarification": clarification},
            duration_ms=elapsed_ms(t0),
        )
        return {"plan_clarification": clarification}

    profile_by_id = {a["id"]: a for a in known_audiences}

    # Build a rich audience reference block so the LLM can reason about each audience fully
    audience_detail = "\n\n".join(
        f"## {a['id']}: {a['title']}\n"
        f"Description: {a['description']}\n"
        f"Pain points: {', '.join(a['pain_points'])}\n"
        f"What AWS offers them: {a['what_aws_offers']}\n"
        f"Primary headline: {a['messaging']['primary_headline']}\n"
        f"Secondary headline: {a['messaging']['secondary_headline']}\n"
        f"Body themes: {', '.join(a['messaging']['body_themes'])}"
        for a in known_audiences
    )
    hints_str = json.dumps(detection_hints, indent=2)

    prompt = (
        f"You are a senior marketing strategist for AWS for Software and Technology.\n\n"
        f"Brief: {brief.raw_text}\n"
        f"Product: {product.name} ({product.url})\n\n"
        f"Known audiences — read each profile carefully before deciding which match the brief:\n\n"
        f"{audience_detail}\n\n"
        f"Audience detection hints (keywords per audience ID):\n{hints_str}\n\n"
        f"Keyword pre-scan identified these audiences as candidates: {detected_ids}\n\n"
        f"Select the appropriate audience IDs from that candidate list (max 4). "
        f"Use the full profiles above to reason about which genuinely fit the brief. "
        f"Then produce a campaign plan covering objective, tone, content format, "
        f"suggested sections, and success criteria.\n\n"
        f"For suggested_sections: write 3-5 outcome-oriented headings specific to this product and audience. "
        f"Each heading should read like a benefit or insight the reader will get from that section — "
        f"not a generic topic label. "
        f"Good: 'Deploy without touching your pipeline', 'How teams like yours cut release cycles by half'. "
        f"Bad: 'Why AWS', 'Key Benefits', 'Get Started'. "
        f"Use the audience pain points and AWS offering above to ground each heading."
    )

    # Revision: append previous reasoning + marketer feedback so the plan adapts
    feedback = state.get("feedback")
    previous_trace_path = state.get("previous_trace_path")
    if feedback and previous_trace_path:
        prev_entry = _load_previous_planning_entry(previous_trace_path)
        prev_reasoning = prev_entry["thinking_and_reasoning"] if prev_entry else "(not available)"
        prompt += (
            f"\n\n--- REVISION RUN ---\n"
            f"A marketer reviewed the previous draft and provided this feedback:\n"
            f"{feedback}\n\n"
            f"Previous planning reasoning:\n{prev_reasoning}\n\n"
            f"Adapt the plan to directly address the feedback. "
            f"Keep the same product and audience; adjust tone, sections, and success criteria as needed."
        )

    output: _PlanningOutput = await _structured.ainvoke(prompt)

    matched_audiences = []
    for aid in output.matched_audience_ids[:4]:
        raw = profile_by_id.get(aid)
        if raw:
            matched_audiences.append(AudienceProfile(
                id=raw["id"],
                title=raw["title"],
                description=raw["description"],
                pain_points=raw["pain_points"],
                what_aws_offers=raw["what_aws_offers"],
                messaging=AudienceMessaging(**raw["messaging"]),
            ))

    plan = CampaignPlan(
        matched_audiences=matched_audiences,
        primary_objective=output.primary_objective,
        tone=output.tone,
        content_format=output.content_format,
        suggested_sections=output.suggested_sections,
        success_criteria=output.success_criteria,
    )
    save_trace(
        node="planning",
        inputs={"brief": brief.raw_text, "product": product.model_dump()},
        thinking_and_reasoning=output.thinking_and_reasoning,
        outputs={"plan": plan},
        duration_ms=elapsed_ms(t0),
    )
    return {"plan": plan}
