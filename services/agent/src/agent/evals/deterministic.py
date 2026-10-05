"""Deterministic (rule-based) eval checks — no LLM required."""
from __future__ import annotations

from dataclasses import dataclass

from agent.evals.cases import EvalCase


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def run_deterministic_checks(case: EvalCase, result: dict) -> list[CheckResult]:
    checks: list[CheckResult] = []

    plan_clarification = result.get("plan_clarification")
    product_lookup = result.get("product_lookup")
    plan = result.get("plan")
    drafts = result.get("drafts", [])
    html_file_paths = result.get("html_file_paths", [])

    # --- Clarification gate ---
    low_confidence = product_lookup and getattr(product_lookup, "confidence", None) == "low"
    clarification_triggered = bool(plan_clarification) or bool(low_confidence)

    if case.expect_clarification:
        checks.append(CheckResult(
            name="clarification_triggered",
            passed=clarification_triggered,
            detail=(
                "Clarification was requested as expected"
                if clarification_triggered
                else f"Expected clarification but pipeline produced plan/drafts (plan_clarification={plan_clarification!r})"
            ),
        ))
        # When clarification is expected, remaining checks are not applicable
        return checks

    # --- Pipeline completed (no clarification expected) ---
    checks.append(CheckResult(
        name="no_unexpected_clarification",
        passed=not clarification_triggered,
        detail=(
            "Pipeline completed without asking for clarification"
            if not clarification_triggered
            else f"Unexpected clarification: {plan_clarification!r}"
        ),
    ))

    # --- Plan present ---
    checks.append(CheckResult(
        name="plan_present",
        passed=plan is not None,
        detail="Plan was produced" if plan else "No plan in result",
    ))

    # --- Expected audience IDs in plan ---
    if plan and case.expected_audience_ids:
        actual_ids = {a.id for a in plan.matched_audiences}
        missing = [aid for aid in case.expected_audience_ids if aid not in actual_ids]
        checks.append(CheckResult(
            name="expected_audiences_in_plan",
            passed=len(missing) == 0,
            detail=(
                f"All expected audiences present: {case.expected_audience_ids}"
                if not missing
                else f"Missing audience IDs: {missing} (got {sorted(actual_ids)})"
            ),
        ))

    # --- At least one draft produced ---
    checks.append(CheckResult(
        name="drafts_produced",
        passed=len(drafts) > 0,
        detail=f"{len(drafts)} draft(s) produced" if drafts else "No drafts in result",
    ))

    # --- Draft completeness ---
    for draft in drafts:
        aid = draft.audience_id
        has_subject = bool(draft.subject_line)
        has_headline = bool(draft.headline)
        has_subheadline = bool(draft.subheadline)
        has_sections = len(draft.body_sections) >= 3
        has_cta = bool(draft.primary_cta_text) and bool(draft.primary_cta_url)

        all_ok = has_subject and has_headline and has_subheadline and has_sections and has_cta
        missing_fields = []
        if not has_subject:
            missing_fields.append("subject_line")
        if not has_headline:
            missing_fields.append("headline")
        if not has_subheadline:
            missing_fields.append("subheadline")
        if not has_sections:
            missing_fields.append(f"body_sections (got {len(draft.body_sections)}, need ≥3)")
        if not has_cta:
            missing_fields.append("primary_cta")

        checks.append(CheckResult(
            name=f"draft_complete[{aid}]",
            passed=all_ok,
            detail=(
                f"Draft for {aid!r} is complete"
                if all_ok
                else f"Draft for {aid!r} missing: {', '.join(missing_fields)}"
            ),
        ))

    # --- Draft-to-plan audience alignment ---
    if plan and drafts:
        plan_ids = {a.id for a in plan.matched_audiences}
        draft_ids = {d.audience_id for d in drafts}
        unmatched = draft_ids - plan_ids
        missing_drafts = plan_ids - draft_ids
        checks.append(CheckResult(
            name="draft_audience_alignment",
            passed=not unmatched and not missing_drafts,
            detail=(
                "Draft audience IDs align with plan"
                if not unmatched and not missing_drafts
                else (
                    f"Unmatched draft IDs: {unmatched}; "
                    f"Plan audiences with no draft: {missing_drafts}"
                )
            ),
        ))

    # --- HTML files generated ---
    if drafts:
        checks.append(CheckResult(
            name="html_files_generated",
            passed=len(html_file_paths) == len(drafts),
            detail=(
                f"{len(html_file_paths)} HTML file(s) generated for {len(drafts)} draft(s)"
                if len(html_file_paths) == len(drafts)
                else f"Expected {len(drafts)} HTML file(s), got {len(html_file_paths)}"
            ),
        ))

    # --- HTML content checks ---
    from pathlib import Path

    for path_str in html_file_paths:
        path = Path(path_str)
        if not path.exists():
            checks.append(CheckResult(
                name=f"html_file_exists[{path.name}]",
                passed=False,
                detail=f"File not found: {path_str}",
            ))
            continue

        html = path.read_text(encoding="utf-8")
        checks.append(CheckResult(
            name=f"html_has_cta_link[{path.name}]",
            passed="<a " in html,
            detail="CTA anchor tag present" if "<a " in html else "No <a> tag found in HTML",
        ))
        checks.append(CheckResult(
            name=f"html_has_aws_branding[{path.name}]",
            passed="Amazon Web Services" in html or "aws" in html.lower(),
            detail="AWS branding present" if ("Amazon Web Services" in html or "aws" in html.lower()) else "No AWS branding found",
        ))

    return checks
