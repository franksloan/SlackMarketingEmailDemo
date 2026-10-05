"""LLM judge evals — assess content quality for completed (non-clarification) pipeline runs.

The pipeline's review_node now scores each draft on the same six criteria and stores
them in ReviewResult.judge_scores. run_judge_checks reads those scores directly,
avoiding redundant LLM calls. If scores are absent (e.g. results from an older run),
it falls back to scoring the drafts itself.

Criteria (grounded in the AWS for Software & Technology brand playbook):
  pain_point_coverage  — copy directly addresses this audience's documented pain points
  brand_voice          — professional, outcome-focused, specific, customer-obsessed, no jargon
  cta_quality          — compelling, audience-specific action with a clear value proposition
  subject_line_quality — concise, role-relevant, specific enough to earn the open
  audience_specificity — language and concerns are right for this role, not generic B2B
  factual_grounding    — stays within known AWS capabilities; no invented stats or features
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from agent.evals.cases import EvalCase
from agent.llm import llm
from agent.models.review import JUDGE_CRITERIA

PASS_THRESHOLD = 3  # score >= 3 is a pass


@dataclass
class JudgeResult:
    name: str
    passed: bool
    score: int  # 1-5
    reasoning: str
    audience_id: str = ""


class _JudgeOutput(BaseModel):
    score: int = Field(ge=1, le=5, description="Quality score 1 (poor) to 5 (excellent)")
    reasoning: str = Field(description="One-paragraph explanation citing specific evidence from the draft")
    passed: bool = Field(description="True if score >= 3")


_judge_llm = llm.with_structured_output(_JudgeOutput)


async def _judge(prompt: str) -> _JudgeOutput:
    return await _judge_llm.ainvoke(prompt)


def _results_from_reviews(result: dict) -> list[JudgeResult] | None:
    """
    Read judge scores from ReviewResult.judge_scores written by review_node.
    Returns None if no reviews exist or none have judge_scores populated.
    """
    reviews = result.get("reviews", [])
    if not reviews:
        return None

    judge_results = []
    for review in reviews:
        scores = getattr(review, "judge_scores", {}) or {}
        if not scores:
            return None  # fall back to re-scoring if any review is missing scores
        for criterion in JUDGE_CRITERIA:
            score = scores.get(criterion)
            if score is None:
                return None
            judge_results.append(JudgeResult(
                name=criterion,
                passed=score >= PASS_THRESHOLD,
                score=score,
                reasoning="(scored by pipeline review_node)",
                audience_id=review.audience_id,
            ))

    return judge_results if judge_results else None


async def _score_drafts_directly(case: EvalCase, result: dict) -> list[JudgeResult]:
    """Fallback: score drafts with separate LLM calls (used when pipeline scores are absent)."""
    plan = result.get("plan")
    drafts = result.get("drafts", [])
    product_lookup = result.get("product_lookup")
    product_name = product_lookup.product.name if product_lookup and product_lookup.product else "Unknown"

    if not plan or not drafts:
        return []

    judge_results: list[JudgeResult] = []

    for draft in drafts:
        audience = next((a for a in plan.matched_audiences if a.id == draft.audience_id), None)
        audience_context = (
            f"Audience role: {audience.title}\n"
            f"Documented pain points: {', '.join(audience.pain_points)}\n"
            f"What AWS offers them: {audience.what_aws_offers}\n"
            f"Approved messaging themes: {', '.join(audience.messaging.body_themes)}"
            if audience
            else f"Audience ID: {draft.audience_id}"
        )

        body_text = "\n\n".join(
            f"{s.heading}\n{s.body}" if s.heading else s.body
            for s in draft.body_sections
        )
        draft_text = (
            f"Subject: {draft.subject_line}\n"
            f"Headline: {draft.headline}\n"
            f"Subheadline: {draft.subheadline}\n"
            f"Body:\n{body_text}\n"
            f"CTA: {draft.primary_cta_text} → {draft.primary_cta_url}"
        )

        checks = [
            (
                "pain_point_coverage",
                f"You are evaluating a marketing email for AWS '{product_name}'.\n\n"
                f"{audience_context}\n\n{draft_text}\n\n"
                f"Score 1-5: How directly and specifically does this email address the documented pain points above?\n"
                f"5 = each pain point is addressed with a concrete AWS solution\n"
                f"3 = some pain points addressed, others ignored\n"
                f"1 = generic cloud benefits with no connection to this role's actual concerns\n"
                f"Cite specific sentences from the draft in your reasoning.",
            ),
            (
                "brand_voice",
                f"You are evaluating an AWS marketing email against the brand voice guidelines.\n\n"
                f"AWS brand voice: professional, outcome-focused, specific, customer-obsessed.\n"
                f"Avoid: jargon, vague superlatives, passive voice, brand-centric 'we' framing.\n\n"
                f"{draft_text}\n\n"
                f"Score 1-5: How consistently does this email maintain the AWS brand voice?\n"
                f"5 = throughout: specific outcomes, customer-first language, no clichés\n"
                f"3 = mostly on-brand with isolated lapses\n"
                f"1 = off-brand: generic agency-speak, jargon, or empty superlatives\n"
                f"Cite specific phrases as evidence.",
            ),
            (
                "cta_quality",
                f"You are evaluating the call-to-action in an AWS email for a *{audience.title if audience else draft.audience_id}*.\n\n"
                f"CTA text: {draft.primary_cta_text}\n"
                f"CTA URL: {draft.primary_cta_url}\n"
                + (f"Secondary CTA: {draft.secondary_cta_text} → {draft.secondary_cta_url}\n" if draft.secondary_cta_text else "") +
                f"\nScore 1-5: How compelling and audience-specific is this CTA?\n"
                f"5 = clear value proposition, role-specific action, URL is a logical next step\n"
                f"3 = acceptable but generic (e.g. 'Learn more')\n"
                f"1 = weak, irrelevant to this audience, or missing context",
            ),
            (
                "subject_line_quality",
                f"You are evaluating an email subject line for an AWS campaign.\n\n"
                f"Target audience: {audience.title if audience else draft.audience_id}\n"
                f"Product: {product_name}\n"
                f"Subject line: {draft.subject_line}\n\n"
                f"Score 1-5: How effective is this subject line at earning an open?\n"
                f"5 = specific, under 60 chars, audience-relevant, clear value, no clickbait\n"
                f"3 = acceptable but could be more compelling or specific\n"
                f"1 = generic, too long, vague, or uses spam trigger words",
            ),
            (
                "audience_specificity",
                f"You are checking whether a marketing email is truly tailored to its audience.\n\n"
                f"{audience_context}\n\n{draft_text}\n\n"
                f"Score 1-5: Could this email have been written for a *different* audience with minimal changes?\n"
                f"5 = deeply role-specific: references this persona's responsibilities, KPIs, and priorities\n"
                f"3 = some role-specific language but could largely apply to any technical buyer\n"
                f"1 = purely generic — no signal this was written for this role",
            ),
            (
                "factual_grounding",
                f"You are checking whether an AWS marketing email stays within known product capabilities.\n\n"
                f"Product: {product_name}\n\n{draft_text}\n\n"
                f"Score 1-5: Does the copy stay within verifiable AWS product capabilities?\n"
                f"5 = all claims are plausible, specific, and attributable to real AWS features\n"
                f"3 = mostly grounded with one or two vague or unverifiable claims\n"
                f"1 = contains invented statistics, hallucinated features, or unsubstantiated claims",
            ),
        ]

        for check_name, prompt in checks:
            output = await _judge(prompt)
            judge_results.append(JudgeResult(
                name=check_name,
                passed=output.passed,
                score=output.score,
                reasoning=output.reasoning,
                audience_id=draft.audience_id,
            ))

    return judge_results


async def run_judge_checks(case: EvalCase, result: dict) -> list[JudgeResult]:
    """Run judge evals on a completed pipeline result. Returns [] for clarification cases."""
    if case.expect_clarification:
        return []

    # Primary path: read scores already computed by review_node (free, no LLM calls)
    from_reviews = _results_from_reviews(result)
    if from_reviews is not None:
        return from_reviews

    # Fallback: score drafts directly (used for older results or if review_node scores missing)
    return await _score_drafts_directly(case, result)
