#!/usr/bin/env python3
"""LLM Judge for the UofT Course Planning Agent.

Evaluates the semantic quality of the agent's final answer using an
independent LLM call.  Works alongside the deterministic rule-based
evaluator — this judges *what the agent said*, not just what tools
it called.

Usage::

    python3 eval/run_llm_judge.py --case multistep_csc384h1_winter
    python3 eval/run_llm_judge.py --case multistep_csc384h1_winter \\
        --output eval/reports/llm_judge_report.md

This script calls the real TokenHub API and is NOT collected by pytest.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- path setup ----------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.agent import CoursePlanningAgent  # noqa: E402
from src.model import TencentTokenHubModel  # noqa: E402

from eval.judge_prompt import JUDGE_SYSTEM_PROMPT, JUDGE_USER_PREFIX  # noqa: E402
from eval.run_evaluation import evaluate_case, extract_signals  # noqa: E402
from eval.run_full_evaluation import load_cases  # noqa: E402

# =========================================================================
# Batch definitions
# =========================================================================

BATCHES: dict[str, list[str]] = {
    "core5": [
        "multistep_csc384h1_winter",
        "recommend_ai_ml",
        "exclusion_csc108_csc148",
        "verify_mat137_unverified",
        "insufficient_no_completed",
    ],
}


def get_batch_case_ids(batch_name: str) -> list[str]:
    """Return a copy of the case ID list for *batch_name*.

    Args:
        batch_name: A key in :data:`BATCHES`.

    Returns:
        A new list of case IDs.

    Raises:
        ValueError: If *batch_name* is not a known batch.
    """
    if batch_name not in BATCHES:
        raise ValueError(
            f"Unknown batch: '{batch_name}'. "
            f"Available: {sorted(BATCHES.keys())}"
        )
    return list(BATCHES[batch_name])


# =========================================================================
# Constants
# =========================================================================

VALID_SEVERITIES = {"critical", "major", "minor"}
VALID_CATEGORIES = {
    "hallucination", "omission", "contradiction", "vagueness", "overclaim",
}
VALID_HALLUCINATION_RISK = {"none", "low", "medium", "high"}
SCORE_DIMENSIONS = [
    "groundedness", "correctness", "helpfulness", "clarity",
    "uncertainty_handling",
]

# =========================================================================
# Judge message construction
# =========================================================================


def build_judge_messages(
    case: dict[str, Any],
    agent_result: dict[str, Any],
    rule_result: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build [system, user] messages for the judge model.

    Only includes tool-call data, observations, and the final answer.
    Agent thought/reasoning text is excluded to prevent the judge
    from being influenced by the agent's internal monologue.

    Args:
        case: An evaluation case dict from ``evaluation_cases.json``.
        agent_result: The dict from ``handle_request()``.
        rule_result: Optional rule-based evaluation result.

    Returns:
        A list of chat messages ready for ``model.generate_response()``.
    """
    # Build compact case data — no thought fields.
    steps_data: list[dict[str, Any]] = []
    for s in agent_result.get("steps", []):
        steps_data.append({
            "tool_called": s.get("tool_called"),
            "arguments": s.get("arguments", {}),
            "observation": s.get("observation", ""),
        })

    case_data: dict[str, Any] = {
        "case_id": case.get("case_id", ""),
        "user_query": case.get("user_query", ""),
        "completed_courses": case.get("completed_courses", []),
        "expected_behaviors": case.get("expected_behaviors", []),
        "tool_steps": steps_data,
        "final_answer": agent_result.get("final_answer", ""),
        "stop_reason": agent_result.get("stop_reason", ""),
    }

    if rule_result is not None:
        # rule_result is a dataclass (EvalResult), not a dict.
        behaviors = getattr(rule_result, "behavior_results", [])
        case_data["rule_evaluation"] = {
            "tool_pass": getattr(rule_result, "tool_pass", None),
            "sequence_pass": getattr(rule_result, "sequence_pass", None),
            "behavior_pass_count": sum(
                1 for br in behaviors if getattr(br, "passed", False)
            ),
            "behavior_total_count": len(behaviors),
        }

    user_content = (
        JUDGE_USER_PREFIX
        + json.dumps(case_data, ensure_ascii=False, indent=2)
    )

    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# =========================================================================
# Judge response parsing
# =========================================================================


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` fences if present."""
    text = text.strip()
    # Try fenced block.
    m = re.match(r"```(?:json)?\s*\n?(.*)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def parse_judge_response(raw_response: str) -> dict[str, Any]:
    """Parse and validate the judge model's JSON response.

    Accepts pure JSON or JSON inside ```json fences.

    Args:
        raw_response: Raw text from the judge model.

    Returns:
        A validated judge result dict.

    Raises:
        ValueError: If the response is malformed, missing required
            fields, or contains invalid values.
    """
    cleaned = _strip_markdown_fences(raw_response)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Judge response is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Judge response must be a JSON object, got {type(data).__name__}"
        )

    # --- validate scores -------------------------------------------------
    scores = data.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("Judge response missing 'scores' dict")

    for dim in SCORE_DIMENSIONS:
        dim_data = scores.get(dim)
        if not isinstance(dim_data, dict):
            raise ValueError(f"scores.{dim} is missing or not a dict")
        score_val = dim_data.get("score")
        if not isinstance(score_val, (int, float)):
            raise ValueError(
                f"scores.{dim}.score must be a number, got {type(score_val).__name__}"
            )
        if not (1 <= score_val <= 5):
            raise ValueError(
                f"scores.{dim}.score is {score_val}, must be 1–5"
            )
        applicable = dim_data.get("applicable", True)
        if not isinstance(applicable, bool):
            raise ValueError(
                f"scores.{dim}.applicable must be bool, got {type(applicable).__name__}"
            )
        if "reason" not in dim_data:
            raise ValueError(f"scores.{dim} missing 'reason' field")

    # --- validate issues -------------------------------------------------
    issues = data.get("issues")
    if not isinstance(issues, list):
        raise ValueError("Judge response missing 'issues' list")

    for i, issue in enumerate(issues):
        if not isinstance(issue, dict):
            raise ValueError(f"issues[{i}] is not a dict")
        severity = issue.get("severity", "")
        if severity not in VALID_SEVERITIES:
            raise ValueError(
                f"issues[{i}].severity is '{severity}', "
                f"must be one of {sorted(VALID_SEVERITIES)}"
            )
        category = issue.get("category", "")
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"issues[{i}].category is '{category}', "
                f"must be one of {sorted(VALID_CATEGORIES)}"
            )

    # --- validate hallucination_risk --------------------------------------
    risk = data.get("hallucination_risk", "")
    if risk not in VALID_HALLUCINATION_RISK:
        raise ValueError(
            f"hallucination_risk is '{risk}', "
            f"must be one of {sorted(VALID_HALLUCINATION_RISK)}"
        )

    # --- validate strengths + summary ------------------------------------
    if not isinstance(data.get("strengths"), list):
        raise ValueError("Judge response missing 'strengths' list")
    if not isinstance(data.get("summary"), str):
        raise ValueError("Judge response missing 'summary' string")

    return data


# =========================================================================
# Deterministic verdict calculation
# =========================================================================


@dataclass
class JudgeVerdict:
    """Deterministic verdict computed from judge scores."""

    verdict: str  # "PASS" or "FAIL"
    overall_score: float
    applicable_dimensions: list[str]
    fail_reasons: list[str]


def calculate_judge_verdict(judge_result: dict[str, Any]) -> JudgeVerdict:
    """Compute a deterministic PASS/FAIL verdict from judge scores.

    FAIL if any of these conditions are true:
        - groundedness score < 4
        - correctness score < 4
        - any issue has severity "critical"
        - hallucination_risk is "high"

    Overall score is the average of applicable dimension scores.
    Non-applicable dimensions do not reduce the average.

    Args:
        judge_result: Parsed and validated judge response dict.

    Returns:
        A :class:`JudgeVerdict` with the verdict and score.
    """
    scores = judge_result["scores"]
    issues = judge_result.get("issues", [])
    risk = judge_result.get("hallucination_risk", "none")

    fail_reasons: list[str] = []

    # Collect applicable scores for averaging.
    applicable_scores: list[float] = []
    applicable_dims: list[str] = []

    for dim in SCORE_DIMENSIONS:
        dim_data = scores[dim]
        if dim_data.get("applicable", True):
            applicable_scores.append(float(dim_data["score"]))
            applicable_dims.append(dim)

    # Groundedness < 4 (only when applicable).
    g_data = scores["groundedness"]
    if g_data.get("applicable", True) and g_data["score"] < 4:
        fail_reasons.append(
            f"groundedness={g_data['score']} < 4"
        )

    # Correctness < 4 (only when applicable).
    c_data = scores["correctness"]
    if c_data.get("applicable", True) and c_data["score"] < 4:
        fail_reasons.append(
            f"correctness={c_data['score']} < 4"
        )

    # Critical issues.
    critical_issues = [
        i for i in issues if i.get("severity") == "critical"
    ]
    if critical_issues:
        fail_reasons.append(
            f"{len(critical_issues)} critical issue(s)"
        )

    # High hallucination risk.
    if risk == "high":
        fail_reasons.append("hallucination_risk=high")

    verdict = "FAIL" if fail_reasons else "PASS"
    overall = (
        sum(applicable_scores) / len(applicable_scores)
        if applicable_scores
        else 0.0
    )

    return JudgeVerdict(
        verdict=verdict,
        overall_score=round(overall, 1),
        applicable_dimensions=applicable_dims,
        fail_reasons=fail_reasons,
    )


# =========================================================================
# Report formatting
# =========================================================================


def format_judge_report(
    case: dict[str, Any],
    agent_result: dict[str, Any],
    rule_result: Any,
    judge_result: dict[str, Any],
    verdict: JudgeVerdict,
    model_name: str,
) -> str:
    """Format a combined rule-based + LLM Judge markdown report.

    Args:
        case: The evaluation case dict.
        agent_result: Output from ``handle_request()``.
        rule_result: :class:`EvalResult` from the rule-based evaluator.
        judge_result: Parsed judge JSON response.
        verdict: Computed :class:`JudgeVerdict`.
        model_name: Human-readable judge model name.

    Returns:
        A markdown report string.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    steps = agent_result.get("steps", [])
    scores = judge_result["scores"]
    issues = judge_result.get("issues", [])

    lines: list[str] = []
    lines.append("# LLM Judge Evaluation Report")
    lines.append("")
    lines.append(f"**Generated:** {now}  ")
    lines.append(f"**Judge model:** {model_name}  ")
    lines.append(f"**Case:** `{case.get('case_id', '?')}`  ")
    lines.append("")

    # --- user query ------------------------------------------------------
    lines.append("## User Query")
    lines.append("")
    lines.append(f"> {case.get('user_query', '')}")
    lines.append("")

    # --- tools called ----------------------------------------------------
    lines.append("## Tools Called")
    lines.append("")
    if steps:
        for i, s in enumerate(steps, start=1):
            lines.append(
                f"**Step {i}:** `{s.get('tool_called', '?')}` — "
                f"`{json.dumps(s.get('arguments', {}))}`"
            )
            lines.append("")
            lines.append(f"{s.get('observation', '')}")
            lines.append("")
    else:
        lines.append("(no tools called)")
        lines.append("")

    # --- final answer ----------------------------------------------------
    lines.append("## Final Answer")
    lines.append("")
    lines.append(f"> {agent_result.get('final_answer', '')}")
    lines.append("")

    # --- rule-based result -----------------------------------------------
    rule_tool = "✅" if rule_result.tool_pass else "❌"
    lines.append("## Rule-Based Evaluation")
    lines.append("")
    lines.append(f"- **Tool usage:** {rule_tool}")
    lines.append(
        f"- **Behavior pass rate:** "
        f"{sum(1 for b in rule_result.behavior_results if b.passed)}"
        f"/{len(rule_result.behavior_results)}"
    )
    lines.append("")

    # --- LLM Judge scores ------------------------------------------------
    judge_icon = "✅" if verdict.verdict == "PASS" else "❌"
    lines.append("## LLM Judge Assessment")
    lines.append("")
    lines.append(
        f"**Verdict:** {judge_icon} {verdict.verdict}  "
    )
    lines.append(f"**Overall score:** {verdict.overall_score}/5  ")
    if verdict.fail_reasons:
        lines.append(f"**Fail reasons:** {', '.join(verdict.fail_reasons)}  ")
    lines.append("")
    lines.append("| Dimension | Score | Applicable | Reason |")
    lines.append("|-----------|-------|------------|--------|")
    for dim in SCORE_DIMENSIONS:
        d = scores[dim]
        app = "✅" if d.get("applicable", True) else "—"
        reason = d.get("reason", "").replace("\n", " ")
        lines.append(
            f"| {dim} | {d['score']}/5 | {app} | {reason[:120]} |"
        )
    lines.append("")

    # --- strengths -------------------------------------------------------
    strengths = judge_result.get("strengths", [])
    if strengths:
        lines.append("### Strengths")
        lines.append("")
        for s in strengths:
            lines.append(f"- {s}")
        lines.append("")

    # --- issues ----------------------------------------------------------
    if issues:
        lines.append("### Issues")
        lines.append("")
        for i, iss in enumerate(issues, start=1):
            lines.append(
                f"**{i}. [{iss.get('severity', '?')}] "
                f"{iss.get('category', '?')}**"
            )
            lines.append(f"- {iss.get('description', '')}")
            evidence_ans = iss.get("evidence_from_answer", "")
            evidence_obs = iss.get("evidence_from_observations", "")
            if evidence_ans:
                lines.append(f"- From answer: _{evidence_ans}_")
            if evidence_obs:
                lines.append(f"- From observations: _{evidence_obs}_")
            lines.append("")

    # --- hallucination risk ----------------------------------------------
    lines.append(f"**Hallucination risk:** {judge_result.get('hallucination_risk', '?')}")
    lines.append("")

    # --- summary ---------------------------------------------------------
    lines.append(f"**Summary:** {judge_result.get('summary', '')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "*Report generated by `eval/run_llm_judge.py`. "
        "LLM judge scores are heuristic and may vary between runs.*"
    )
    lines.append("")

    return "\n".join(lines)


# =========================================================================
# Batch runner
# =========================================================================


def format_batch_report(
    batch_name: str,
    results: list[dict[str, Any]],
    model_name: str,
) -> str:
    """Format a batch summary + individual case reports.

    Args:
        batch_name: The batch key (e.g., ``"core5"``).
        results: List of per-case result dicts from :func:`run_batch`.
        model_name: Judge model name.

    Returns:
        A complete markdown batch report string.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = len(results)
    rule_pass = sum(1 for r in results if r.get("rule_verdict") == "PASS")
    rule_fail = sum(1 for r in results if r.get("rule_verdict") == "FAIL")
    rule_error = sum(1 for r in results if r.get("rule_verdict") == "ERROR")
    judge_pass = sum(1 for r in results if r.get("judge_verdict") == "PASS")
    judge_fail = sum(1 for r in results if r.get("judge_verdict") == "FAIL")
    judge_error = sum(1 for r in results if r.get("judge_verdict") == "ERROR")

    lines: list[str] = []
    lines.append(f"# Core-5 Batch Evaluation Report")
    lines.append("")
    lines.append(f"**Batch:** `{batch_name}`  ")
    lines.append(f"**Generated:** {now}  ")
    lines.append(f"**Judge model:** {model_name}  ")
    lines.append(f"**Cases:** {total}  ")
    lines.append("")

    # Summary.
    lines.append("## Summary")
    lines.append("")
    lines.append("| | Rule-Based | Judge |")
    lines.append("|---|---|---|")
    lines.append(f"| PASS | {rule_pass} | {judge_pass} |")
    lines.append(f"| FAIL | {rule_fail} | {judge_fail} |")
    lines.append(f"| ERROR | {rule_error} | {judge_error} |")
    lines.append("")

    # Per-case table.
    lines.append("## Case Summary Table")
    lines.append("")
    lines.append(
        "| case_id | category | tools | rule | judge | "
        "score | risk | issues |"
    )
    lines.append(
        "|---------|----------|-------|------|-------|"
        "-------|------|--------|"
    )
    for r in results:
        cid = r.get("case_id", "?")
        cat = r.get("category", "?")
        tools = r.get("tools_called", [])
        tools_str = " → ".join(tools) if tools else "(none)"
        rv = r.get("rule_verdict", "?")
        jv = r.get("judge_verdict", "?")
        score = r.get("overall_score", "—")
        risk = r.get("hallucination_risk", "?")
        issue_count = len(r.get("issues", []))
        lines.append(
            f"| {cid} | {cat} | {tools_str} | {rv} | {jv} | "
            f"{score} | {risk} | {issue_count} |"
        )
    lines.append("")

    # Per-case details.
    lines.append("## Per-Case Reports")
    lines.append("")
    for r in results:
        cid = r.get("case_id", "?")
        case_report = r.get("case_report", "")
        if case_report:
            lines.append(case_report)
            lines.append("")
        elif r.get("error"):
            lines.append(f"### {cid} — ERROR")
            lines.append("")
            lines.append(f"**Error:** {r['error']}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "*Batch report generated by `eval/run_llm_judge.py`. "
        "LLM judge scores are heuristic and may vary between runs.*"
    )
    lines.append("")

    return "\n".join(lines)


def run_batch(
    batch_name: str,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Run all cases in a batch through the full evaluation pipeline.

    Each case is agent-executed, rule-evaluated, and LLM-judged.
    Errors on individual cases are recorded but do not stop the batch.

    Args:
        batch_name: A key in :data:`BATCHES`.
        output_path: Optional path for the combined report.

    Returns:
        A dict with keys ``batch_name``, ``results``, ``report``.
    """
    case_ids = get_batch_case_ids(batch_name)
    all_cases = load_cases()
    case_map = {c["case_id"]: c for c in all_cases}

    # --- model -----------------------------------------------------------
    try:
        model = TencentTokenHubModel()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
    model_label = getattr(model, "model_name", "TencentTokenHubModel")

    results: list[dict[str, Any]] = []

    for case_id in case_ids:
        print(f"\n{'='*60}")
        print(f"Case: {case_id}")
        print(f"{'='*60}")

        case = case_map.get(case_id)
        if case is None:
            results.append({
                "case_id": case_id,
                "category": "?",
                "rule_verdict": "ERROR",
                "judge_verdict": "ERROR",
                "error": f"Case '{case_id}' not found in evaluation cases.",
            })
            continue

        result_entry: dict[str, Any] = {
            "case_id": case_id,
            "category": case.get("category", "?"),
        }

        try:
            # --- run agent ------------------------------------------------
            agent = CoursePlanningAgent(
                completed_courses=case.get("completed_courses", []),
                model=model,
            )
            agent_result = agent.handle_request(
                case["user_query"], max_tool_steps=2
            )

            # Collect tools called.
            steps = agent_result.get("steps", [])
            tools_called = [s["tool_called"] for s in steps]
            result_entry["tools_called"] = tools_called

            # --- rule-based evaluation (re-uses the same agent_result) ---
            rule_result = evaluate_case(case, agent, agent_result=agent_result)
            from eval.run_full_evaluation import _case_passed  # noqa: E402
            rule_verdict = "PASS" if _case_passed(rule_result) else "FAIL"
            result_entry["rule_verdict"] = rule_verdict

            # --- judge ----------------------------------------------------
            messages = build_judge_messages(case, agent_result, rule_result)
            raw = model.generate_response(messages)

            try:
                judge_result = parse_judge_response(raw)
            except ValueError as exc:
                result_entry["rule_verdict"] = result_entry.get(
                    "rule_verdict", "ERROR"
                )
                result_entry["judge_verdict"] = "ERROR"
                result_entry["error"] = f"Judge parse error: {exc}"
                results.append(result_entry)
                continue

            verdict = calculate_judge_verdict(judge_result)
            result_entry["judge_verdict"] = verdict.verdict
            result_entry["overall_score"] = verdict.overall_score
            result_entry["hallucination_risk"] = judge_result.get(
                "hallucination_risk", "?"
            )
            result_entry["issues"] = judge_result.get("issues", [])

            # Per-case report.
            case_report = format_judge_report(
                case, agent_result, rule_result,
                judge_result, verdict, model_label,
            )
            result_entry["case_report"] = case_report

        except Exception as exc:
            result_entry["rule_verdict"] = result_entry.get(
                "rule_verdict", "ERROR"
            )
            result_entry["judge_verdict"] = "ERROR"
            result_entry["error"] = str(exc)

        results.append(result_entry)

    # --- batch report ----------------------------------------------------
    report = format_batch_report(batch_name, results, model_label)

    out = Path(output_path) if output_path else (
        _PROJECT_ROOT / "eval" / "reports" / f"llm_judge_{batch_name}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    # Console summary.
    rule_p = sum(1 for r in results if r.get("rule_verdict") == "PASS")
    judge_p = sum(1 for r in results if r.get("judge_verdict") == "PASS")
    total = len(results)
    print(f"\nBatch '{batch_name}' complete. "
          f"Rule: {rule_p}/{total} PASS. "
          f"Judge: {judge_p}/{total} PASS.")
    print(f"Report: {out}")

    return {"batch_name": batch_name, "results": results, "report": report}


# =========================================================================
# Single-case runner
# =========================================================================


def run_single_case(
    case_id: str,
    output_path: str | None = None,
) -> None:
    """Run the judge on a single evaluation case.

    Executes the agent with TokenHub, runs rule-based evaluation, sends
    the result to the judge model, and writes a combined report.

    Args:
        case_id: The ``case_id`` to evaluate.
        output_path: Optional path to write the markdown report.
            Defaults to ``eval/reports/llm_judge_{case_id}.md``.
    """
    # --- load case -------------------------------------------------------
    all_cases = load_cases()
    matching = [c for c in all_cases if c["case_id"] == case_id]
    if not matching:
        print(f"ERROR: No case found with case_id='{case_id}'")
        available = sorted(c["case_id"] for c in all_cases)
        print(f"Available: {available}")
        sys.exit(1)
    case = matching[0]

    # --- instantiate model -----------------------------------------------
    try:
        model = TencentTokenHubModel()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
    model_label = getattr(model, "model_name", "TencentTokenHubModel")

    # --- run agent -------------------------------------------------------
    print(f"Running agent for case: {case_id} ...")
    agent = CoursePlanningAgent(
        completed_courses=case.get("completed_courses", []),
        model=model,
    )
    try:
        agent_result = agent.handle_request(
            case["user_query"], max_tool_steps=2
        )
    except RuntimeError as exc:
        print(f"ERROR: Agent API call failed — {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Agent execution failed — {exc}")
        sys.exit(1)

    # --- rule-based evaluation (re-uses the same agent_result) -----------
    print("Running rule-based evaluation ...")
    rule_result = evaluate_case(case, agent, agent_result=agent_result)

    # --- judge ------------------------------------------------------------
    print("Sending to LLM judge ...")
    messages = build_judge_messages(case, agent_result, rule_result)
    try:
        raw = model.generate_response(messages)
    except RuntimeError as exc:
        print(f"ERROR: Judge API call failed — {exc}")
        sys.exit(1)

    try:
        judge_result = parse_judge_response(raw)
    except ValueError as exc:
        print(f"ERROR: Failed to parse judge response: {exc}")
        print(f"Raw response was:\n{raw[:500]}")
        sys.exit(1)

    verdict = calculate_judge_verdict(judge_result)

    # --- report -----------------------------------------------------------
    report = format_judge_report(
        case, agent_result, rule_result, judge_result, verdict, model_label,
    )

    out = Path(output_path) if output_path else (
        _PROJECT_ROOT / "eval" / "reports" / f"llm_judge_{case_id}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    # --- console summary -------------------------------------------------
    print()
    print(f"Judge verdict: {verdict.verdict}  "
          f"(overall: {verdict.overall_score}/5)")
    print(f"Report written to: {out}")


# =========================================================================
# CLI
# =========================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM Judge for the UofT Course Planning Agent."
    )
    parser.add_argument(
        "--case",
        type=str,
        default=None,
        help="case_id to evaluate.",
    )
    parser.add_argument(
        "--batch",
        type=str,
        default=None,
        help="Batch name to evaluate (e.g., core5).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write report to a custom path.",
    )
    args = parser.parse_args()

    # --- validate mutually exclusive flags -------------------------------
    if not args.case and not args.batch:
        print("ERROR: Specify --case or --batch.")
        sys.exit(1)
    if args.case and args.batch:
        print("ERROR: Specify only one of --case or --batch, not both.")
        sys.exit(1)

    # --- load .env -------------------------------------------------------
    try:
        from dotenv import load_dotenv
        load_dotenv(".env")
    except ImportError:
        pass

    # --- validate env ----------------------------------------------------
    missing = []
    for var in ("TOKENHUB_API_KEY", "TOKENHUB_BASE_URL", "TOKENHUB_MODEL"):
        if not os.environ.get(var, "").strip():
            missing.append(var)
    if missing:
        print("ERROR: Missing environment variables for TokenHub:")
        for v in missing:
            print(f"  - {v}")
        sys.exit(1)

    if args.case:
        run_single_case(args.case, output_path=args.output)
    else:
        try:
            run_batch(args.batch, output_path=args.output)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)


if __name__ == "__main__":
    main()
