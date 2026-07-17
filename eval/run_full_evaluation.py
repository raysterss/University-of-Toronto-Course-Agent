#!/usr/bin/env python3
"""Full evaluation runner for the UofT Course Planning Agent.

Loads ``eval/evaluation_cases.json``, runs every scenario through the
agent, and writes a structured markdown report to
``eval/reports/latest_report.md``.

Usage::

    # MockModel evaluation (default):
    python3 eval/run_full_evaluation.py

    # Single category:
    python3 eval/run_full_evaluation.py --category prerequisite_reasoning

    # TokenHub evaluation (requires TOKENHUB_* env vars):
    python3 eval/run_full_evaluation.py --model tokenhub

This script is **not** collected by pytest.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- path setup ----------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.agent import CoursePlanningAgent  # noqa: E402
from src.model import MockModel, TencentTokenHubModel  # noqa: E402

# Reuse the existing evaluation logic.
from eval.run_evaluation import (  # noqa: E402
    BehaviorResult,
    EvalResult,
    check_expected_behaviors,
    evaluate_case,
    extract_signals,
    load_cases,
)


# =========================================================================
# Category-level aggregation
# =========================================================================


@dataclass
class CategorySummary:
    """Aggregated results for one evaluation category."""

    name: str
    total: int
    passed: int
    failed: int
    tool_pass: int
    tool_total: int
    behavior_pass: int
    behavior_total: int


def aggregate_by_category(
    results: list[EvalResult],
    cases: list[dict[str, Any]],
) -> list[CategorySummary]:
    """Group evaluation results by category and compute per-category stats.

    Args:
        results: One :class:`EvalResult` per evaluated case.
        cases: The original case dicts (to look up categories).

    Returns:
        A :class:`CategorySummary` for each category, sorted by name.
    """
    case_map = {c["case_id"]: c.get("category", "unknown") for c in cases}

    # Group results by category.
    by_cat: dict[str, list[EvalResult]] = defaultdict(list)
    for r in results:
        cat = case_map.get(r.case_id, "unknown")
        by_cat[cat].append(r)

    summaries: list[CategorySummary] = []
    for cat_name in sorted(by_cat.keys()):
        cat_results = by_cat[cat_name]
        total = len(cat_results)

        passed_count = 0
        tool_pass_count = 0
        tool_total_count = 0
        behavior_pass_count = 0
        behavior_total_count = 0

        for r in cat_results:
            # A case passes when all behaviors pass.
            all_behaviors_pass = all(br.passed for br in r.behavior_results)
            if all_behaviors_pass:
                passed_count += 1

            if r.tool_called is not None or r.signals.get("expected_tools_match") is not None:
                tool_total_count += 1
                if r.tool_pass:
                    tool_pass_count += 1

            behavior_total_count += len(r.behavior_results)
            behavior_pass_count += sum(1 for br in r.behavior_results if br.passed)

        summaries.append(CategorySummary(
            name=cat_name,
            total=total,
            passed=passed_count,
            failed=total - passed_count,
            tool_pass=tool_pass_count,
            tool_total=tool_total_count,
            behavior_pass=behavior_pass_count,
            behavior_total=behavior_total_count,
        ))

    return summaries


def _case_passed(result: EvalResult) -> bool:
    """A case passes when all behavior checks pass."""
    if not result.behavior_results:
        return result.tool_pass
    return all(br.passed for br in result.behavior_results)


# =========================================================================
# Markdown report generation
# =========================================================================


def format_markdown_report(
    results: list[EvalResult],
    cases: list[dict[str, Any]],
    model_name: str,
) -> str:
    """Generate a markdown evaluation report.

    Args:
        results: One result per evaluated case.
        cases: Original case dicts from ``evaluation_cases.json``.
        model_name: Human-readable model name for the report header.

    Returns:
        A complete markdown report string.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    summaries = aggregate_by_category(results, cases)
    case_map = {c["case_id"]: c for c in cases}

    # --- overall stats ---------------------------------------------------
    total = len(results)
    total_passed = sum(1 for r in results if _case_passed(r))
    total_failed = total - total_passed
    pass_rate = _pct(total_passed, total)

    total_behaviors = sum(len(r.behavior_results) for r in results)
    passed_behaviors = sum(
        sum(1 for br in r.behavior_results if br.passed)
        for r in results
    )

    # --- build report ----------------------------------------------------
    lines: list[str] = []
    lines.append("# Evaluation Report")
    lines.append("")
    lines.append(f"**Generated:** {now}  ")
    lines.append(f"**Model:** {model_name}  ")
    lines.append(f"**Cases evaluated:** {total}  ")
    lines.append("")

    # Summary.
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total scenarios | {total} |")
    lines.append(f"| Passed | {total_passed} |")
    lines.append(f"| Failed | {total_failed} |")
    lines.append(f"| Pass rate | {pass_rate}% |")
    lines.append(f"| Behavior checks passed | {passed_behaviors}/{total_behaviors} |")
    lines.append("")

    # Category breakdown.
    lines.append("## Category Breakdown")
    lines.append("")
    lines.append("| Category | Total | Passed | Failed | Pass Rate |")
    lines.append("|----------|-------|--------|--------|-----------|")
    for s in summaries:
        s_rate = _pct(s.passed, s.total)
        lines.append(
            f"| {s.name} | {s.total} | {s.passed} | {s.failed} | {s_rate}% |"
        )
    lines.append("")

    # Individual results.
    lines.append("## Individual Results")
    lines.append("")

    for r in results:
        case = case_map.get(r.case_id, {})
        cat = case.get("category", "unknown")
        title = case.get("title", r.case_id)
        all_pass = _case_passed(r)
        status = "PASS" if all_pass else "FAIL"

        lines.append(f"### {r.case_id} — {status}")
        lines.append("")
        lines.append(f"- **Category:** `{cat}`")
        lines.append(f"- **Title:** {title}")
        lines.append(f"- **Query:** _{case.get('user_query', 'N/A')}_")
        lines.append("")

        # Tool usage.
        tool_status = "✅" if r.tool_pass else "❌"
        sig = r.signals
        tool_sequence = sig.get("tool_sequence", [])
        tool_label = " → ".join(tool_sequence) if tool_sequence else "(no tool called)"
        expected_tools = case.get("expected_tools", [])
        expected_seq = case.get("expected_tool_sequence")
        lines.append(f"- **Tools called:** {tool_status} `{tool_label}`")
        lines.append(f"- **Tool count:** {sig.get('tool_call_count', 0)}")
        lines.append(f"- **Expected tools:** {expected_tools}")
        if expected_seq:
            seq_status = "✅" if r.sequence_pass else "❌"
            lines.append(f"- **Sequence check:** {seq_status} "
                         f"(expected: {' → '.join(expected_seq)})")
        # Show observations.
        observations = sig.get("observations", [])
        if observations:
            lines.append("- **Observations:**")
            for i, obs in enumerate(observations, start=1):
                lines.append(f"  {i}. {obs[:200]}")

        # Behavior checks.
        lines.append("")
        lines.append("**Behavior checks:**")
        lines.append("")
        for br in r.behavior_results:
            icon = "✅" if br.passed else "❌"
            lines.append(f"- {icon} {br.description}")
            lines.append(f"  - Evidence: {br.evidence}")

        # Failed behaviors summary.
        failed_behaviors = [br for br in r.behavior_results if not br.passed]
        if failed_behaviors:
            lines.append("")
            lines.append("**Failed behaviors:**")
            for fb in failed_behaviors:
                lines.append(f"- {fb.description}")

        # Signals.
        s = r.signals
        lines.append("")
        lines.append("**Signals detected:**")
        lines.append("")
        uncertainty = "✅" if s["contains_uncertainty"] else "❌"
        verification = "✅" if s["contains_verification"] else "❌"
        csc_cap = "✅" if s["contains_csc_cap"] else "❌"
        lines.append("| Uncertainty | Verification | CSC Cap | Course Codes |")
        lines.append("|-------------|--------------|---------|--------------|")
        lines.append(
            f"| {uncertainty} | {verification} | {csc_cap} | "
            f"{', '.join(s['contains_course_codes'][:5]) or 'none'} |"
        )
        lines.append("")

        # Structured statuses.
        elig = s.get("eligibility_statuses", [])
        term_s = s.get("term_statuses", [])
        target = s.get("target_terms", [])
        if elig or term_s or target:
            lines.append("| Eligibility | Term Status | Target Terms |")
            lines.append("|-------------|-------------|--------------|")
            lines.append(
                f"| {', '.join(elig) or '—'} "
                f"| {', '.join(term_s) or '—'} "
                f"| {', '.join(target) or '—'} |"
            )
            lines.append("")

        # Final answer.
        final_answer_text = s.get("final_answer_text", "")
        lines.append("**Final answer:**")
        lines.append("")
        lines.append(f"> {final_answer_text}")
        lines.append("")

        # Failure conditions triggered.
        if r.failure_conditions_checked:
            lines.append("")
            lines.append("**⚠️ Potential failures:**")
            for fc in r.failure_conditions_checked:
                lines.append(f"- {fc}")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Footer.
    lines.append("---")
    lines.append("")
    lines.append(
        "*Report generated by `eval/run_full_evaluation.py`. "
        "Behavior checks are heuristic — human review of final answers "
        "is recommended.*"
    )
    lines.append("")

    return "\n".join(lines)


def _pct(numerator: int, denominator: int) -> int:
    """Return integer percentage, safely."""
    if denominator == 0:
        return 0
    return round(numerator / denominator * 100)


# =========================================================================
# CLI
# =========================================================================


def main() -> None:
    """Parse arguments, run evaluation, write markdown report."""
    parser = argparse.ArgumentParser(
        description="Run the full UofT Course Planning Agent evaluation suite."
    )
    parser.add_argument(
        "--model",
        choices=["mock", "tokenhub"],
        default="mock",
        help="Model backend to use (default: mock).",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Run only cases in the specified category.",
    )
    parser.add_argument(
        "--case",
        type=str,
        default=None,
        help="Run only the specified case_id.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write report to a custom path (default: eval/reports/latest_report.md).",
    )
    args = parser.parse_args()

    # --- build model -----------------------------------------------------
    if args.model == "tokenhub":
        # Optional .env support.
        try:
            from dotenv import load_dotenv
            load_dotenv(".env")
        except ImportError:
            pass

        missing = []
        for var in ("TOKENHUB_API_KEY", "TOKENHUB_BASE_URL", "TOKENHUB_MODEL"):
            if not os.environ.get(var, "").strip():
                missing.append(var)
        if missing:
            print("ERROR: Missing environment variables for TokenHub:")
            for v in missing:
                print(f"  - {v}")
            print("Use --model mock to run with MockModel instead.")
            sys.exit(1)

        model = TencentTokenHubModel()
        model_label = "TencentTokenHubModel"
    else:
        model = MockModel()
        model_label = "MockModel"

    # --- load cases ------------------------------------------------------
    all_cases = load_cases()
    if args.case:
        cases = [c for c in all_cases if c.get("case_id") == args.case]
        if not cases:
            print(f"ERROR: No case found with case_id='{args.case}'.")
            available = sorted(c.get("case_id", "?") for c in all_cases)
            print(f"Available case IDs: {available}")
            sys.exit(1)
        print(f"Running single case: {args.case}")
    elif args.category:
        cases = [c for c in all_cases if c.get("category") == args.category]
        if not cases:
            print(f"ERROR: No cases found for category '{args.category}'.")
            print(f"Available categories: "
                  f"{sorted(set(c.get('category', '?') for c in all_cases))}")
            sys.exit(1)
        print(f"Filtered to category '{args.category}': {len(cases)} cases")
    else:
        cases = all_cases
        print(f"Loaded {len(cases)} cases across "
              f"{len(set(c.get('category', '?') for c in cases))} categories")

    # --- evaluate --------------------------------------------------------
    agent = CoursePlanningAgent(model=model)

    results: list[EvalResult] = []
    for i, case in enumerate(cases, start=1):
        cid = case["case_id"]
        cat = case.get("category", "?")
        print(f"  [{i}/{len(cases)}] {cid} ({cat}) ...")
        result = evaluate_case(case, agent)
        results.append(result)

    # --- report ----------------------------------------------------------
    report = format_markdown_report(results, cases, model_label)

    # Write report.
    output_path = Path(args.output) if args.output else (
        _PROJECT_ROOT / "eval" / "reports" / "latest_report.md"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    # Console summary.
    total_passed = sum(1 for r in results if _case_passed(r))
    print(f"\nDone. {total_passed}/{len(results)} cases passed.")
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
