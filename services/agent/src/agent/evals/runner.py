"""Eval runner — execute pipeline for each case, apply all checks, print report, save JSON.

Usage:
    python -m agent.evals.runner                      # all cases, all checks
    python -m agent.evals.runner s3_engineers         # single case by ID
    python -m agent.evals.runner --no-judge           # skip LLM judge evals
    python -m agent.evals.runner --baseline           # include baseline comparison
    python -m agent.evals.runner --no-regression      # skip regression diff
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agent.evals.baseline import BaselineComparison, run_baseline_comparison
from agent.evals.brand_rules import BrandCheckResult, run_brand_checks
from agent.evals.cases import CASES, EvalCase
from agent.evals.deterministic import CheckResult, run_deterministic_checks
from agent.evals.judge import JudgeResult, run_judge_checks
from agent.evals.regression import compare_to_previous, load_previous_results
from agent.evals.trace_checks import TraceCheckResult, run_trace_checks
from agent.models.brief import CampaignBrief
from agent.orchestrator import graph
from agent.tracing import finish_run, start_run

_RESULTS_DIR = Path(__file__).parents[4] / "eval_results"


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

async def _run_case(case: EvalCase) -> tuple[dict, str | None]:
    """Execute the pipeline for a single eval case. Returns (state, trace_path)."""
    start_run(case.brief)
    brief = CampaignBrief(raw_text=case.brief)
    result = await graph.ainvoke({"brief": brief})
    trace_path = finish_run()
    return result, str(trace_path) if trace_path else None


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt_check(c: CheckResult | BrandCheckResult | TraceCheckResult) -> str:
    icon = "PASS" if c.passed else "FAIL"
    return f"    [{icon}] {c.name}: {c.detail}"


def _fmt_judge(j: JudgeResult) -> str:
    icon = "PASS" if j.passed else "FAIL"
    label = f"{j.name}[{j.audience_id}]" if j.audience_id else j.name
    return f"    [{icon}] {label} ({j.score}/5): {j.reasoning[:120]}"


def _fmt_baseline(b: BaselineComparison) -> list[str]:
    if not b.deltas:
        return []
    lines = [f"  Baseline comparison (system vs vanilla LLM):"]
    lines.append(
        f"    avg system {b.avg_system_score:.1f}/5  vs  "
        f"baseline {b.avg_baseline_score:.1f}/5  →  "
        f"delta {b.avg_delta:+.1f}"
    )
    by_criterion: dict[str, list] = {}
    for d in b.deltas:
        by_criterion.setdefault(d.check_name, []).append(d)
    for criterion, deltas in sorted(by_criterion.items()):
        avg_sys = sum(d.system_score for d in deltas) / len(deltas)
        avg_base = sum(d.baseline_score for d in deltas) / len(deltas)
        sign = "+" if avg_sys >= avg_base else ""
        lines.append(f"    {criterion}: sys {avg_sys:.1f} / base {avg_base:.1f}  ({sign}{avg_sys - avg_base:.1f})")
    return lines


def _print_case_report(
    case: EvalCase,
    det_checks: list[CheckResult],
    brand_checks: list[BrandCheckResult],
    trace_checks: list[TraceCheckResult],
    judge_checks: list[JudgeResult],
    baseline: BaselineComparison | None,
) -> None:
    all_det = [*det_checks, *brand_checks, *trace_checks]
    det_pass = sum(1 for c in all_det if c.passed)
    det_total = len(all_det)
    judge_pass = sum(1 for j in judge_checks if j.passed)
    judge_total = len(judge_checks)

    overall = det_pass == det_total and (judge_total == 0 or judge_pass == judge_total)
    status = "PASS" if overall else "FAIL"

    print(f"\n{'='*70}")
    print(f"[{status}] {case.id}")
    print(f"  {case.description}")
    print(f"  Brief: {case.brief[:90]}{'...' if len(case.brief) > 90 else ''}")
    print(f"{'='*70}")

    if det_checks:
        dp = sum(1 for c in det_checks if c.passed)
        print(f"  Pipeline ({dp}/{len(det_checks)} passed):")
        for c in det_checks:
            print(_fmt_check(c))

    if brand_checks:
        bp = sum(1 for c in brand_checks if c.passed)
        print(f"  Brand compliance ({bp}/{len(brand_checks)} passed):")
        for c in brand_checks:
            print(_fmt_check(c))

    if trace_checks:
        tp = sum(1 for c in trace_checks if c.passed)
        print(f"  Explainability / trace ({tp}/{len(trace_checks)} passed):")
        for c in trace_checks:
            print(_fmt_check(c))

    if judge_checks:
        print(f"  Judge ({judge_pass}/{judge_total} passed):")
        for j in judge_checks:
            print(_fmt_judge(j))

    if baseline:
        for line in _fmt_baseline(baseline):
            print(line)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_evals(
    case_ids: list[str] | None = None,
    run_judge: bool = True,
    run_baseline: bool = False,
    run_regression: bool = True,
) -> None:
    cases = CASES
    if case_ids:
        cases = [c for c in CASES if c.id in case_ids]
        if not cases:
            print(f"No cases found for IDs: {case_ids}")
            return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    flags = " | ".join(filter(None, [
        "judge" if run_judge else None,
        "baseline" if run_baseline else None,
        "regression" if run_regression else None,
    ]))
    print(f"\nRunning {len(cases)} eval case(s)  [{flags}]")

    all_results: list[dict] = []

    for case in cases:
        print(f"\n  Running: {case.id} ...", end="", flush=True)
        try:
            result, trace_path = await _run_case(case)
        except Exception as exc:
            print(f" ERROR: {exc}")
            all_results.append({
                "case_id": case.id,
                "error": str(exc),
                "det_checks": [],
                "brand_checks": [],
                "trace_checks": [],
                "judge_checks": [],
            })
            continue

        print(" done")

        det_checks = run_deterministic_checks(case, result)
        brand_checks = run_brand_checks(case, result)
        trace_chks = run_trace_checks(case, result, trace_path)
        judge_checks = await run_judge_checks(case, result) if run_judge else []
        baseline = await run_baseline_comparison(case, result) if run_baseline else None

        _print_case_report(case, det_checks, brand_checks, trace_chks, judge_checks, baseline)

        all_results.append({
            "case_id": case.id,
            "description": case.description,
            "trace_path": trace_path,
            "det_checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in det_checks
            ],
            "brand_checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in brand_checks
            ],
            "trace_checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in trace_chks
            ],
            "judge_checks": [
                {
                    "name": j.name,
                    "audience_id": j.audience_id,
                    "passed": j.passed,
                    "score": j.score,
                    "reasoning": j.reasoning,
                }
                for j in judge_checks
            ],
            "baseline": (
                {
                    "avg_system": baseline.avg_system_score,
                    "avg_baseline": baseline.avg_baseline_score,
                    "avg_delta": baseline.avg_delta,
                    "deltas": [
                        {
                            "audience_id": d.audience_id,
                            "check": d.check_name,
                            "system": d.system_score,
                            "baseline": d.baseline_score,
                            "delta": d.delta,
                        }
                        for d in baseline.deltas
                    ],
                }
                if baseline else None
            ),
        })

    # --- Summary ---
    def _count(key: str) -> tuple[int, int]:
        total = sum(len(r.get(key, [])) for r in all_results)
        passed = sum(
            sum(1 for c in r.get(key, []) if c["passed"])
            for r in all_results
        )
        return passed, total

    det_p, det_t = _count("det_checks")
    brand_p, brand_t = _count("brand_checks")
    trace_p, trace_t = _count("trace_checks")
    judge_p, judge_t = _count("judge_checks")

    cases_passed = sum(
        1 for r in all_results
        if not r.get("error")
        and all(c["passed"] for c in r.get("det_checks", []))
        and all(c["passed"] for c in r.get("brand_checks", []))
        and all(c["passed"] for c in r.get("trace_checks", []))
        and all(j["passed"] for j in r.get("judge_checks", []))
    )

    print(f"\n{'='*70}")
    print(f"SUMMARY  {cases_passed}/{len(cases)} cases fully passed")
    print(f"  Pipeline:      {det_p}/{det_t}")
    print(f"  Brand:         {brand_p}/{brand_t}")
    print(f"  Explainability:{trace_p}/{trace_t}")
    if run_judge:
        print(f"  Judge:         {judge_p}/{judge_t}")

    if run_baseline:
        all_deltas = [
            d
            for r in all_results
            if r.get("baseline")
            for d in r["baseline"].get("deltas", [])
        ]
        if all_deltas:
            overall_delta = sum(d["delta"] for d in all_deltas) / len(all_deltas)
            print(f"  Baseline delta:{overall_delta:+.2f} avg score improvement over vanilla LLM")

    # --- Regression report ---
    if run_regression:
        previous = load_previous_results()
        regressions = compare_to_previous(all_results, previous)
        if regressions:
            print(f"\n  REGRESSIONS ({len(regressions)} detected):")
            for reg in regressions:
                print(f"    [{reg.case_id}] {reg.check_name}  {reg.previous} → {reg.current}  {reg.description[:80]}")
        elif previous:
            print(f"  No regressions vs previous run.")

    print(f"{'='*70}\n")

    # --- Save JSON ---
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _RESULTS_DIR / f"eval_{timestamp}.json"
    out_path.write_text(
        json.dumps({"timestamp": timestamp, "cases": all_results}, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Results saved to: {out_path}")


def main() -> None:
    args = sys.argv[1:]
    run_judge = "--no-judge" not in args
    run_baseline = "--baseline" in args
    run_regression = "--no-regression" not in args
    args = [a for a in args if not a.startswith("--")]
    case_ids = args if args else None
    asyncio.run(run_evals(
        case_ids=case_ids,
        run_judge=run_judge,
        run_baseline=run_baseline,
        run_regression=run_regression,
    ))


if __name__ == "__main__":
    main()
