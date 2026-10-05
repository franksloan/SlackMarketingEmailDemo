"""Regression detection — compare the current eval run to the most recent previous run.

Answers: "How do you catch regressions when prompts or models change?"

A regression is:
  - A deterministic, brand, or trace check that previously passed and now fails.
  - A judge score that dropped by more than SCORE_REGRESSION_THRESHOLD points.

Usage:
    from agent.evals.regression import compare_to_previous, load_previous_results
    previous = load_previous_results()
    regressions = compare_to_previous(current_results, previous)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_RESULTS_DIR = Path(__file__).parents[4] / "eval_results"

# A judge score drop of more than this triggers a regression flag.
SCORE_REGRESSION_THRESHOLD = 1


@dataclass
class Regression:
    case_id: str
    check_name: str
    check_type: str       # "deterministic" | "brand" | "trace" | "judge"
    previous: str         # "pass" | "fail" | score string
    current: str
    description: str


def load_previous_results() -> dict | None:
    """Return the second-most-recent eval_*.json, or None if fewer than 2 runs exist."""
    files = sorted(_RESULTS_DIR.glob("eval_*.json"), reverse=True)
    if len(files) < 2:
        return None
    try:
        return json.loads(files[1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _check_type(name: str) -> str:
    if name.startswith("brand:"):
        return "brand"
    if name.startswith("trace:"):
        return "trace"
    return "deterministic"


def compare_to_previous(
    current_cases: list[dict],
    previous_data: dict | None,
) -> list[Regression]:
    """Diff current results against previous, returning any regressions found."""
    if not previous_data:
        return []

    previous_cases: list[dict] = previous_data.get("cases", [])
    prev_by_id = {c["case_id"]: c for c in previous_cases}

    regressions: list[Regression] = []

    for case_result in current_cases:
        case_id = case_result["case_id"]
        prev = prev_by_id.get(case_id)
        if not prev:
            continue

        # --- Deterministic / brand / trace checks ---
        prev_checks = {c["name"]: c for c in prev.get("det_checks", [])}
        curr_checks = {c["name"]: c for c in case_result.get("det_checks", [])}

        for name, curr in curr_checks.items():
            p = prev_checks.get(name)
            if p and p["passed"] and not curr["passed"]:
                regressions.append(Regression(
                    case_id=case_id,
                    check_name=name,
                    check_type=_check_type(name),
                    previous="pass",
                    current="fail",
                    description=f"Was passing, now failing: {curr['detail']}",
                ))

        # --- Judge checks ---
        prev_judge: dict[str, dict] = {}
        for j in prev.get("judge_checks", []):
            key = f"{j['name']}[{j['audience_id']}]" if j.get("audience_id") else j["name"]
            prev_judge[key] = j

        for j in case_result.get("judge_checks", []):
            key = f"{j['name']}[{j['audience_id']}]" if j.get("audience_id") else j["name"]
            pj = prev_judge.get(key)
            if pj:
                drop = pj["score"] - j["score"]
                if drop > SCORE_REGRESSION_THRESHOLD:
                    regressions.append(Regression(
                        case_id=case_id,
                        check_name=key,
                        check_type="judge",
                        previous=str(pj["score"]),
                        current=str(j["score"]),
                        description=f"Score dropped {drop} point(s): {j['reasoning'][:120]}",
                    ))

    return regressions
