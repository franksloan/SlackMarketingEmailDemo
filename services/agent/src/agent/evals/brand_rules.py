"""Deterministic brand compliance checks derived from the AWS for Software & Technology playbook.

These rules are intentionally model-free: any failing check is a hard, auditable
signal that the output violates a stated brand principle — not a matter of LLM opinion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from agent.evals.cases import EvalCase
from agent.models.draft import ContentDraft

# ---------------------------------------------------------------------------
# Brand rules reference
# ---------------------------------------------------------------------------

# Words the AWS brand voice explicitly discourages — vague, clichéd, or
# agency-speak that dilutes specificity and trust.
BANNED_WORDS: list[str] = [
    "leverage",
    "utilize",
    "synergy",
    "synergize",
    "holistic",
    "robust",
    "seamless",
    "seamlessly",
    "innovative",
    "innovation",
    "cutting-edge",
    "state-of-the-art",
    "best-in-class",
    "world-class",
    "game-changing",
    "game changer",
    "disruptive",
    "disrupt",
    "empower",
    "empowering",
    "unlock",
    "unlocking",
    "supercharge",
    "revolutionary",
    "transformative",
    "next-generation",
    "next generation",
    "paradigm",
]

# Every CTA URL must point to the official AWS domain.
REQUIRED_CTA_DOMAIN = "aws.amazon.com"

# Industry-standard email subject line length cap.
SUBJECT_LINE_MAX_CHARS = 60

# Customer-centric voice: "you/your" mentions should exceed "we/our/us" mentions.
# A ratio below 1.0 suggests the copy is brand-led rather than customer-led.
MIN_YOU_TO_WE_RATIO = 1.0

# Each body section should be substantive — a single throwaway sentence is a signal
# that the LLM padded structure without filling it.
MIN_BODY_SECTION_WORDS = 20


# ---------------------------------------------------------------------------
# Check result
# ---------------------------------------------------------------------------

@dataclass
class BrandCheckResult:
    name: str
    passed: bool
    detail: str


# ---------------------------------------------------------------------------
# Per-draft checks
# ---------------------------------------------------------------------------

def _all_text(draft: ContentDraft) -> str:
    parts = [
        draft.subject_line,
        draft.headline,
        draft.subheadline,
        *(s.heading + " " + s.body for s in draft.body_sections),
        draft.primary_cta_text,
        draft.secondary_cta_text or "",
        draft.sign_off or "",
    ]
    return " ".join(parts)


def check_banned_words(draft: ContentDraft) -> BrandCheckResult:
    text_lower = _all_text(draft).lower()
    found = [w for w in BANNED_WORDS if re.search(r"\b" + re.escape(w) + r"\b", text_lower)]
    return BrandCheckResult(
        name=f"brand:no_banned_words[{draft.audience_id}]",
        passed=len(found) == 0,
        detail=(
            f"No banned words found"
            if not found
            else f"Banned words present: {', '.join(repr(w) for w in found)}"
        ),
    )


def check_cta_domain(draft: ContentDraft) -> BrandCheckResult:
    bad_urls = []
    for url in filter(None, [draft.primary_cta_url, draft.secondary_cta_url]):
        if REQUIRED_CTA_DOMAIN not in url:
            bad_urls.append(url)
    return BrandCheckResult(
        name=f"brand:cta_domain[{draft.audience_id}]",
        passed=len(bad_urls) == 0,
        detail=(
            f"All CTA URLs on {REQUIRED_CTA_DOMAIN}"
            if not bad_urls
            else f"CTA URLs not on {REQUIRED_CTA_DOMAIN}: {bad_urls}"
        ),
    )


def check_subject_line_length(draft: ContentDraft) -> BrandCheckResult:
    length = len(draft.subject_line)
    return BrandCheckResult(
        name=f"brand:subject_length[{draft.audience_id}]",
        passed=length <= SUBJECT_LINE_MAX_CHARS,
        detail=(
            f"Subject line is {length} chars (≤{SUBJECT_LINE_MAX_CHARS})"
            if length <= SUBJECT_LINE_MAX_CHARS
            else f"Subject line is {length} chars — exceeds {SUBJECT_LINE_MAX_CHARS} char recommendation"
        ),
    )


def check_customer_first_voice(draft: ContentDraft) -> BrandCheckResult:
    """AWS brand voice is customer-obsessed: 'you/your' should outweigh 'we/our/us'."""
    text_lower = _all_text(draft).lower()
    you_count = len(re.findall(r"\b(you|your)\b", text_lower))
    we_count = len(re.findall(r"\b(we|our|us)\b", text_lower))
    ratio = you_count / max(we_count, 1)
    passed = ratio >= MIN_YOU_TO_WE_RATIO
    return BrandCheckResult(
        name=f"brand:customer_first_voice[{draft.audience_id}]",
        passed=passed,
        detail=(
            f"Customer-first voice: {you_count} you/your vs {we_count} we/our/us (ratio {ratio:.1f})"
            if passed
            else f"Brand-centric voice detected: {you_count} you/your vs {we_count} we/our/us (ratio {ratio:.1f}, need ≥{MIN_YOU_TO_WE_RATIO})"
        ),
    )


def check_body_section_substance(draft: ContentDraft) -> BrandCheckResult:
    thin_sections = [
        s.heading or f"section {i+1}"
        for i, s in enumerate(draft.body_sections)
        if len(s.body.split()) < MIN_BODY_SECTION_WORDS
    ]
    return BrandCheckResult(
        name=f"brand:body_substance[{draft.audience_id}]",
        passed=len(thin_sections) == 0,
        detail=(
            f"All body sections have ≥{MIN_BODY_SECTION_WORDS} words"
            if not thin_sections
            else f"Thin sections (< {MIN_BODY_SECTION_WORDS} words): {thin_sections}"
        ),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_brand_checks(case: EvalCase, result: dict) -> list[BrandCheckResult]:
    """Run all brand compliance checks on every draft in the pipeline result."""
    if case.expect_clarification:
        return []

    drafts: list[ContentDraft] = result.get("drafts", [])
    checks: list[BrandCheckResult] = []

    for draft in drafts:
        checks.append(check_banned_words(draft))
        checks.append(check_cta_domain(draft))
        checks.append(check_subject_line_length(draft))
        checks.append(check_customer_first_voice(draft))
        checks.append(check_body_section_substance(draft))

    return checks
