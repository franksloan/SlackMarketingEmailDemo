"""Explainability checks — verify that every LLM node left an auditable reasoning trail.

These checks answer: "How do we ensure all agent actions are explainable?"
For each run, the trace JSON must show that:
  1. The trace file exists and is well-formed.
  2. Every LLM node recorded thinking_and_reasoning (not empty or boilerplate).
  3. The planning node's reasoning explicitly mentions the audiences it selected.
  4. Each drafting node's reasoning references the audience's pain points or themes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agent.evals.cases import EvalCase

# LLM nodes that must record thinking_and_reasoning in the trace.
_LLM_NODES = {"product_lookup", "planning", "drafting", "review", "image_selector"}

# Minimum character count to consider a reasoning field non-trivial.
_MIN_REASONING_CHARS = 50


@dataclass
class TraceCheckResult:
    name: str
    passed: bool
    detail: str


def run_trace_checks(case: EvalCase, result: dict, trace_path: str | None) -> list[TraceCheckResult]:
    """Load the trace for this run and verify its completeness."""
    checks: list[TraceCheckResult] = []

    if case.expect_clarification:
        # Clarification cases are short-circuited — trace may be minimal
        return checks

    # --- Trace file exists ---
    if not trace_path or not Path(trace_path).exists():
        checks.append(TraceCheckResult(
            name="trace:file_exists",
            passed=False,
            detail=f"Trace file not found: {trace_path}",
        ))
        return checks

    checks.append(TraceCheckResult(
        name="trace:file_exists",
        passed=True,
        detail=f"Trace written to {Path(trace_path).name}",
    ))

    try:
        trace = json.loads(Path(trace_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        checks.append(TraceCheckResult(
            name="trace:parseable",
            passed=False,
            detail=f"Could not parse trace: {exc}",
        ))
        return checks

    nodes: list[dict] = trace.get("nodes", [])
    nodes_called: list[str] = [n.get("node", "") for n in nodes]

    # --- All expected LLM nodes are present ---
    expected_in_run = {"product_lookup", "planning"}
    if result.get("drafts"):
        expected_in_run.add("drafting")

    missing_nodes = [n for n in expected_in_run if n not in nodes_called]
    checks.append(TraceCheckResult(
        name="trace:llm_nodes_present",
        passed=len(missing_nodes) == 0,
        detail=(
            f"All expected LLM nodes traced: {sorted(expected_in_run)}"
            if not missing_nodes
            else f"Missing from trace: {missing_nodes}"
        ),
    ))

    # --- Every LLM node has substantive reasoning ---
    thin_reasoning: list[str] = []
    for entry in nodes:
        node_name = entry.get("node", "")
        if node_name not in _LLM_NODES:
            continue
        label = entry.get("label") or node_name
        reasoning = entry.get("thinking_and_reasoning", "") or ""
        if len(reasoning.strip()) < _MIN_REASONING_CHARS:
            thin_reasoning.append(label)

    checks.append(TraceCheckResult(
        name="trace:reasoning_populated",
        passed=len(thin_reasoning) == 0,
        detail=(
            f"All LLM nodes have substantive reasoning (≥{_MIN_REASONING_CHARS} chars)"
            if not thin_reasoning
            else f"Thin or missing reasoning in: {thin_reasoning}"
        ),
    ))

    # --- Planning reasoning mentions the selected audience IDs ---
    plan = result.get("plan")
    if plan and plan.matched_audiences:
        planning_entries = [n for n in nodes if n.get("node") == "planning"]
        if planning_entries:
            planning_reasoning = (planning_entries[0].get("thinking_and_reasoning") or "").lower()
            audience_ids = [a.id for a in plan.matched_audiences]
            mentioned = [aid for aid in audience_ids if aid.lower() in planning_reasoning]
            checks.append(TraceCheckResult(
                name="trace:planning_explains_audiences",
                passed=len(mentioned) == len(audience_ids),
                detail=(
                    f"Planning reasoning references all selected audiences: {audience_ids}"
                    if len(mentioned) == len(audience_ids)
                    else f"Planning reasoning doesn't mention: {[a for a in audience_ids if a not in mentioned]}"
                ),
            ))

    # --- Each drafting node's reasoning references audience characteristics ---
    drafting_entries = [n for n in nodes if n.get("node") == "drafting"]
    playbook_terms = [
        "pain point", "audience", "objective", "tone", "cta", "headline",
        "research", "insight", "messaging",
    ]
    for entry in drafting_entries:
        label = entry.get("label") or "unknown"
        reasoning = (entry.get("thinking_and_reasoning") or "").lower()
        terms_found = [t for t in playbook_terms if t in reasoning]
        checks.append(TraceCheckResult(
            name=f"trace:drafting_reasoning[{label}]",
            passed=len(terms_found) >= 2,
            detail=(
                f"Drafting reasoning references audience context ({', '.join(terms_found[:4])})"
                if len(terms_found) >= 2
                else f"Drafting reasoning for '{label}' is generic — references only: {terms_found}"
            ),
        ))

    return checks
