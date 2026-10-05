"""Revision planner — decides whether marketer feedback calls for a targeted edit or a full regeneration."""
from typing import Literal

from agent.llm import llm
from pydantic import BaseModel, Field

from agent.models.state import AgentState
from agent.tracing import elapsed_ms, save_trace, start_timer


class _RevisionDecision(BaseModel):
    thinking: str = Field(
        description=(
            "Step-by-step reasoning: what the feedback is asking for, "
            "whether it targets specific elements (including the image) or requests a fundamentally different approach"
        )
    )
    action: Literal["edit", "regenerate"] = Field(
        description=(
            "edit — feedback asks for targeted changes: specific wording, tone, a CTA, individual sections, or swapping the banner image; "
            "regenerate — feedback asks for a completely different approach, angle, structure, or audience positioning"
        )
    )
    rationale: str = Field(description="One sentence explaining the decision")


_structured = llm.with_structured_output(_RevisionDecision)


async def revision_planner_node(state: AgentState) -> dict:
    t0 = start_timer()
    feedback = state["feedback"]
    existing_draft = state.get("existing_draft")

    draft_summary = (
        f"Subject: {existing_draft.subject_line}\n"
        f"Headline: {existing_draft.headline}\n"
        f"Sections: {', '.join(s.heading for s in existing_draft.body_sections if s.heading)}"
        if existing_draft
        else "(draft not available)"
    )

    prompt = (
        f"A marketer has rejected a marketing email draft and provided feedback.\n"
        f"Decide the best revision action.\n\n"
        f"Draft summary:\n{draft_summary}\n\n"
        f"Marketer feedback:\n{feedback}\n\n"
        f"Choose 'edit' if the feedback targets specific elements — wording, a headline, a section, the CTA, "
        f"tone adjustments, or the banner image. "
        f"Choose 'regenerate' if the feedback asks for a fundamentally different angle, structure, or message."
    )

    output: _RevisionDecision = await _structured.ainvoke(prompt)

    save_trace(
        node="revision_planner",
        inputs={"feedback": feedback, "draft_summary": draft_summary},
        thinking_and_reasoning=output.thinking,
        outputs={"action": output.action, "rationale": output.rationale},
        duration_ms=elapsed_ms(t0),
    )
    return {"revision_action": output.action}
