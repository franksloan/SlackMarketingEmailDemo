from typing import TypedDict

from agent.llm import llm
from langgraph.types import Command
from pydantic import BaseModel, Field

from agent.models.draft import ContentDraft
from agent.models.plan import CampaignPlan
from agent.models.review import JUDGE_CRITERIA, ReviewResult
from agent.tracing import elapsed_ms, save_trace, start_timer

_llm = llm


class _ReviewOutput(BaseModel):
    thinking_and_reasoning: str = Field(
        description="Step-by-step reasoning: what was evaluated, what aligns well with the audience and campaign objective, what needs improvement"
    )
    approved: bool
    overall_score: int = Field(ge=1, le=10)
    text_feedback: str
    visual_feedback: str
    layout_feedback: str
    issues: list[str]
    suggestions: list[str]
    # Judge criteria scores (1-5 each)
    pain_point_coverage: int = Field(ge=1, le=5, description="How directly and specifically the email addresses this audience's documented pain points. 5=each pain point has a concrete AWS solution, 1=generic cloud benefits with no role-specific concerns")
    brand_voice: int = Field(ge=1, le=5, description="Consistency with AWS brand voice: professional, outcome-focused, specific, customer-obsessed, no jargon. 5=throughout, 1=off-brand agency-speak")
    cta_quality: int = Field(ge=1, le=5, description="How compelling and audience-specific the CTA is. 5=clear value proposition and role-specific action, 1=weak or generic")
    subject_line_quality: int = Field(ge=1, le=5, description="Effectiveness of the subject line at earning an open. 5=specific, under 60 chars, audience-relevant, 1=generic or too long")
    audience_specificity: int = Field(ge=1, le=5, description="How tailored the email is to this specific role vs generic B2B. 5=deeply role-specific KPIs and priorities, 1=could apply to any buyer")
    factual_grounding: int = Field(ge=1, le=5, description="Whether claims stay within verifiable AWS capabilities. 5=all claims plausible and attributable to real features, 1=invented stats or hallucinated features")


_structured = _llm.with_structured_output(_ReviewOutput)


# Payload dispatched via Send from drafting_node
class ReviewTask(TypedDict):
    plan: CampaignPlan
    draft: ContentDraft


async def review_node(task: ReviewTask) -> dict:
    t0 = start_timer()
    plan = task["plan"]
    draft = task["draft"]

    audience = next(
        (a for a in plan.matched_audiences if a.id == draft.audience_id), None
    )
    audience_context = (
        f"Audience role: {audience.title}\n"
        f"Documented pain points: {', '.join(audience.pain_points)}\n"
        f"What AWS offers them: {audience.what_aws_offers}\n"
        f"Approved messaging themes: {', '.join(audience.messaging.body_themes)}"
        if audience
        else f"Audience ID: {draft.audience_id}"
    )

    prompt = (
        f"You are a rigorous marketing quality reviewer for AWS for Software and Technology.\n"
        f"Evaluate this draft against the campaign plan, its target audience, and the AWS brand playbook.\n\n"
        f"Campaign plan:\n{plan.model_dump_json(indent=2)}\n\n"
        f"Audience profile:\n{audience_context}\n\n"
        f"Draft (audience: {draft.audience_id}):\n{draft.model_dump_json(indent=2)}\n\n"
        f"Provide both editorial feedback (approved, overall_score, text/visual/layout feedback, issues, "
        f"suggestions) and rubric scores for the six quality criteria."
    )
    output: _ReviewOutput = await _structured.ainvoke(prompt)

    judge_scores = {criterion: getattr(output, criterion) for criterion in JUDGE_CRITERIA}

    result = ReviewResult(
        audience_id=draft.audience_id,
        **{
            k: v for k, v in output.model_dump().items()
            if k not in ("thinking_and_reasoning", *JUDGE_CRITERIA)
        },
        judge_scores=judge_scores,
    )
    save_trace(
        node="review",
        inputs={"audience_id": draft.audience_id, "plan_objective": plan.primary_objective},
        thinking_and_reasoning=output.thinking_and_reasoning,
        outputs={"review": result},
        duration_ms=elapsed_ms(t0),
        label=draft.audience_id,
    )
    # Command(goto="html_generator") — NOT Send — so html_generator receives the full
    # accumulated graph state, which includes selected_image from image_selector.
    return Command(
        update={"reviews": [result]},
        goto="html_generator",
    )
