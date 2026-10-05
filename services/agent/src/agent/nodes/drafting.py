from typing import TypedDict

from agent.llm import llm
from langgraph.types import Command, Send
from pydantic import Field

from agent.models.audience import AudienceProfile
from agent.models.draft import ContentDraft
from agent.models.plan import CampaignPlan
from agent.models.research import ResearchFindings
from agent.tracing import elapsed_ms, save_trace, start_timer

_llm = llm


class _DraftOutput(ContentDraft):
    thinking_and_reasoning: str = Field(
        description="Step-by-step reasoning: how audience pain points and research shaped the headline, body, and CTAs"
    )


_structured = _llm.with_structured_output(_DraftOutput)


# Payload shape passed via Send from the orchestrator
class DraftTask(TypedDict, total=False):
    plan: CampaignPlan
    audience: AudienceProfile
    research: ResearchFindings
    feedback: str  # set on revision runs


async def drafting_node(task: DraftTask) -> dict:
    t0 = start_timer()
    plan = task["plan"]
    audience = task["audience"]
    research = task["research"]

    prompt = (
        f"You are an expert B2B copywriter for AWS for Software and Technology.\n"
        f"Write compelling {plan.content_format} content tailored specifically to this audience.\n\n"
        f"Audience: {audience.title}\n"
        f"Pain points: {', '.join(audience.pain_points)}\n"
        f"What AWS offers them: {audience.what_aws_offers}\n"
        f"Suggested messaging:\n"
        f"  Primary headline: {audience.messaging.primary_headline}\n"
        f"  Secondary headline: {audience.messaging.secondary_headline}\n"
        f"  Body themes: {', '.join(audience.messaging.body_themes)}\n\n"
        f"Campaign objective: {plan.primary_objective}\n"
        f"Tone: {plan.tone}\n"
        f"Sections to cover: {', '.join(plan.suggested_sections)}\n\n"
        f"Research insights: {', '.join(research.insights)}\n"
        f"Key facts: {', '.join(research.key_facts)}\n"
        f"Talking points: {', '.join(research.suggested_talking_points)}\n\n"
        f"Visual direction: Frame the headline and body sections to match this audience's context. "
        f"Technical audiences (CTOs, engineers) respond to architecture, performance, and control. "
        f"Business audiences (CPOs, CROs) respond to outcomes, speed, and competitive advantage. "
        f"Let this shape your word choices, section structure, and CTA framing.\n\n"
        f"Set audience_id='{audience.id}'."
    )

    feedback = task.get("feedback")
    if feedback:
        prompt += (
            f"\n\n--- REVISION ---\n"
            f"The previous draft was rejected. Marketer feedback:\n{feedback}\n"
            f"Address this feedback directly. Change what was criticised; keep what works."
        )
    output: _DraftOutput = await _structured.ainvoke(prompt)
    draft = ContentDraft(**{k: v for k, v in output.model_dump().items() if k != "thinking_and_reasoning"})
    save_trace(
        node="drafting",
        inputs={"audience_id": audience.id, "plan_objective": plan.primary_objective, "research_insights": research.insights},
        thinking_and_reasoning=output.thinking_and_reasoning,
        outputs={"draft": draft},
        duration_ms=elapsed_ms(t0),
        label=audience.id,
    )
    return Command(
        update={"drafts": [draft]},
        goto=Send("review", {"plan": plan, "draft": draft}),
    )
