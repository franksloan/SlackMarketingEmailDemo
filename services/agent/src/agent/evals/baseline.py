"""Baseline comparison — measures how much better our system is than a vanilla LLM.

Generates a "baseline" draft for each case using only the raw brief and audience title,
with no playbook, no audience profiles, no pain points, no research. Scores it with the
same judge criteria. The delta (our score − baseline score) is the measurable value
our architecture adds.

Usage:
    from agent.evals.baseline import run_baseline_comparison
    delta = await run_baseline_comparison(case, result)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from agent.evals.cases import EvalCase
from agent.llm import llm
from agent.models.draft import BodySection, ContentDraft


@dataclass
class BaselineDelta:
    audience_id: str
    check_name: str
    system_score: int
    baseline_score: int
    delta: int  # positive = system better, negative = system worse


@dataclass
class BaselineComparison:
    case_id: str
    deltas: list[BaselineDelta] = field(default_factory=list)

    @property
    def avg_system_score(self) -> float:
        if not self.deltas:
            return 0.0
        return sum(d.system_score for d in self.deltas) / len(self.deltas)

    @property
    def avg_baseline_score(self) -> float:
        if not self.deltas:
            return 0.0
        return sum(d.baseline_score for d in self.deltas) / len(self.deltas)

    @property
    def avg_delta(self) -> float:
        return self.avg_system_score - self.avg_baseline_score


# ---------------------------------------------------------------------------
# Baseline draft generation — vanilla LLM, no playbook context
# ---------------------------------------------------------------------------

class _BaselineDraftOutput(ContentDraft):
    pass


_baseline_llm = llm.with_structured_output(_BaselineDraftOutput)


async def _generate_baseline_draft(brief: str, audience_title: str, audience_id: str) -> ContentDraft:
    """Generate a draft with only the raw brief and audience label — no playbook context."""
    prompt = (
        f"Write a marketing email for an AWS cloud product.\n\n"
        f"Brief: {brief}\n"
        f"Target audience: {audience_title}\n\n"
        f"Include a compelling subject line, headline, subheadline, 3-5 body sections, "
        f"and a primary call-to-action. Set audience_id='{audience_id}'."
    )
    output: _BaselineDraftOutput = await _baseline_llm.ainvoke(prompt)
    return ContentDraft(**output.model_dump())


# ---------------------------------------------------------------------------
# Shared judge criteria (mirrors judge.py rubrics but self-contained)
# ---------------------------------------------------------------------------

class _JudgeScore(BaseModel):
    score: int = Field(ge=1, le=5)
    reasoning: str
    passed: bool


_judge_llm = llm.with_structured_output(_JudgeScore)


async def _score_draft(draft: ContentDraft, criterion: str, prompt: str) -> tuple[str, int]:
    output: _JudgeScore = await _judge_llm.ainvoke(prompt)
    return criterion, output.score


async def _score_all_criteria(draft: ContentDraft, audience_title: str, product_name: str) -> dict[str, int]:
    body_text = "\n\n".join(
        f"{s.heading}\n{s.body}" if s.heading else s.body
        for s in draft.body_sections
    )

    criteria_prompts = {
        "pain_point_coverage": (
            f"Score 1-5: How specifically does this AWS marketing email address the pain points and "
            f"priorities of a *{audience_title}*?\n"
            f"5=highly specific to this role's concerns, 1=generic.\n\n"
            f"Subject: {draft.subject_line}\nHeadline: {draft.headline}\nBody:\n{body_text}"
        ),
        "brand_voice": (
            f"Score 1-5: How well does this AWS email match the brand voice — "
            f"professional, outcome-focused, specific, customer-obsessed, no jargon?\n"
            f"5=strongly on-brand, 1=off-brand or generic marketing speak.\n\n"
            f"Subject: {draft.subject_line}\nHeadline: {draft.headline}\nBody:\n{body_text}"
        ),
        "cta_quality": (
            f"Score 1-5: How compelling and audience-specific is the CTA for a *{audience_title}*?\n"
            f"5=specific value proposition and clear next step, 1=vague or generic.\n\n"
            f"CTA: {draft.primary_cta_text} → {draft.primary_cta_url}"
        ),
        "subject_line_quality": (
            f"Score 1-5: How effective is this subject line for a *{audience_title}* "
            f"at an AWS campaign?\n"
            f"5=specific, concise, audience-relevant, clear value, 1=generic or too long.\n\n"
            f"Subject: {draft.subject_line}"
        ),
    }

    tasks = [
        _score_draft(draft, criterion, prompt)
        for criterion, prompt in criteria_prompts.items()
    ]
    results = await asyncio.gather(*tasks)
    return dict(results)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_baseline_comparison(case: EvalCase, result: dict) -> BaselineComparison:
    """
    For each draft in result, generate a baseline draft and score both on the same criteria.
    Returns deltas showing the system's improvement over a vanilla LLM.
    """
    comparison = BaselineComparison(case_id=case.id)

    if case.expect_clarification:
        return comparison

    plan = result.get("plan")
    drafts: list[ContentDraft] = result.get("drafts", [])
    product_lookup = result.get("product_lookup")
    product_name = product_lookup.product.name if product_lookup and product_lookup.product else "AWS"

    if not plan or not drafts:
        return comparison

    audience_by_id = {a.id: a for a in plan.matched_audiences}

    for draft in drafts:
        audience = audience_by_id.get(draft.audience_id)
        audience_title = audience.title if audience else draft.audience_id

        # Generate baseline and score in parallel
        baseline_draft, system_scores = await asyncio.gather(
            _generate_baseline_draft(case.brief, audience_title, draft.audience_id),
            _score_all_criteria(draft, audience_title, product_name),
        )
        baseline_scores = await _score_all_criteria(baseline_draft, audience_title, product_name)

        for criterion in system_scores:
            sys_score = system_scores[criterion]
            base_score = baseline_scores.get(criterion, 0)
            comparison.deltas.append(BaselineDelta(
                audience_id=draft.audience_id,
                check_name=criterion,
                system_score=sys_score,
                baseline_score=base_score,
                delta=sys_score - base_score,
            ))

    return comparison
