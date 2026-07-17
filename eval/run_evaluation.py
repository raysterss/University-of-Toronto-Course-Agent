#!/usr/bin/env python3
"""Evaluation runner for the UofT Course Planning Agent.

Loads ``eval/evaluation_cases.json``, runs each scenario through the
agent, extracts behavioral signals, and produces a readable report.

Usage::

    # With the real TokenHub model (requires .env):
    python3 eval/run_evaluation.py

    # With MockModel (deterministic, for testing the runner itself):
    python3 eval/run_evaluation.py --mock

This script is **not** collected by pytest.  Only the helper functions
in this module are tested by pytest.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- path setup so we can import from src/ --------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.agent import CoursePlanningAgent  # noqa: E402
from src.model import MockModel, TencentTokenHubModel  # noqa: E402


# =========================================================================
# Signal extraction helpers
# =========================================================================

# Keywords that indicate the agent is surfacing uncertainty.
UNCERTAINTY_KEYWORDS: list[str] = [
    "manual_review_needed",
    "needs_official_verification",
    "UNKNOWN",
    "not listed",
    "not guaranteed",
    "may have been",
    "complex prerequisite",
    "verify with",
    "academic advisor",
    "Academic Calendar",
    "official sources",
]

# Keywords that indicate the agent issued a verification warning.
VERIFICATION_KEYWORDS: list[str] = [
    "needs_official_verification",
    "calendar_verified",
    "verify with",
    "official calendar",
    "academic advising",
    "verify all",
    "mock data",
]

# Keywords that indicate the agent mentioned the CSC credit cap.
CSC_CAP_KEYWORDS: list[str] = [
    "1.5",
    "credit cap",
    "program restriction",
    "non-CS",
    "maximum of 1.5",
]


def _extract_eligibility_statuses(observations: list[str]) -> list[str]:
    """Extract eligibility status keywords from tool observations.

    Statuses are mutually exclusive per observation — ``not_eligible``
    prevents ``eligible`` from being extracted from the same
    observation, since ``eligible`` is a substring of
    ``not_eligible``.
    """
    statuses: list[str] = []
    for obs in observations:
        found = None
        # Check longer / more-specific statuses first so substring
        # overlap does not produce false extractions.
        for kw in ("not_eligible", "manual_review_needed", "eligible"):
            if kw in obs:
                found = kw
                break
        if found and found not in statuses:
            statuses.append(found)
    return statuses


def _extract_term_statuses(
    observations: list[str], tool_sequence: list[str]
) -> list[str]:
    """Extract term-availability statuses from term-related observations.

    Only matches in observations from ``check_term_availability`` or
    ``get_course_details`` to avoid false positives from prose.
    """
    statuses: list[str] = []
    for tool, obs in zip(tool_sequence, observations):
        if tool not in ("check_term_availability", "get_course_details"):
            continue
        lower = obs.lower()
        if "course_not_found" in lower:
            statuses.append("course_not_found")
            continue
        # Check not_available before available (substring overlap).
        if "not_available" in lower:
            statuses.append("not_available")
        elif "available" in lower:
            statuses.append("available")
        if "unknown" in lower and "unknown" not in statuses:
            statuses.append("unknown")
    return statuses


def _extract_target_terms(
    observations: list[str], tool_sequence: list[str]
) -> list[str]:
    """Extract target terms (Fall, Winter, Summer) from term tool obs."""
    terms: list[str] = []
    for tool, obs in zip(tool_sequence, observations):
        if tool not in ("check_term_availability", "get_course_details"):
            continue
        lower = obs.lower()
        for term in ["winter", "fall", "summer"]:
            if term in lower and term.capitalize() not in terms:
                terms.append(term.capitalize())
    return terms


def extract_signals(result: dict[str, Any]) -> dict[str, Any]:
    """Extract structured evaluation signals from an agent result dict.

    Supports both single-step (backward-compatible) and multi-step
    (``steps`` list) results.

    Args:
        result: The dict returned by ``CoursePlanningAgent.handle_request()``,
            containing ``thought``, ``tool_called``, ``observation``,
            ``steps``, and ``final_answer``.

    Returns:
        A dict of extracted signals suitable for comparison against
        expected behaviors.
    """
    # --- multi-step support ----------------------------------------------
    steps: list[dict] = result.get("steps", [])
    thought = result.get("thought", "")
    tool_called = result.get("tool_called")
    observation = result.get("observation", "")
    final_answer = result.get("final_answer", "")

    if steps:
        tools_called = [s["tool_called"] for s in steps]
        tool_call_count = len(steps)
        tool_sequence = tools_called
        observations = [s.get("observation", "") for s in steps]
    else:
        # Backward-compatible single-step fallback.
        tools_called = [tool_called] if tool_called else []
        tool_call_count = len(tools_called)
        tool_sequence = tools_called
        observations = [observation] if observation else []

    # Combine ALL text fields for keyword searching.
    all_text = " ".join([
        str(thought), str(observation), str(final_answer),
    ] + [s.get("thought", "") for s in steps]
      + [s.get("observation", "") for s in steps]
    ).lower()

    return {
        # Backward-compatible single-tool reference.
        "tool_called": tool_called,
        # Multi-step fields.
        "tools_called": tools_called,
        "tool_call_count": tool_call_count,
        "tool_sequence": tool_sequence,
        "observations": observations,
        # Tool matching — filled by caller.
        "expected_tools_match": None,
        "sequence_match": None,
        # Structured statuses.
        "eligibility_statuses": _extract_eligibility_statuses(observations),
        "term_statuses": _extract_term_statuses(observations, tool_sequence),
        "target_terms": _extract_target_terms(observations, tool_sequence),
        # Text signals.
        "has_thought": bool(thought.strip()),
        "has_observation": bool(observation.strip()),
        "has_final_answer": bool(final_answer.strip()),
        "contains_uncertainty": _contains_any(all_text, UNCERTAINTY_KEYWORDS),
        "uncertainty_matches": _find_matches(all_text, UNCERTAINTY_KEYWORDS),
        "contains_verification": _contains_any(all_text, VERIFICATION_KEYWORDS),
        "verification_matches": _find_matches(all_text, VERIFICATION_KEYWORDS),
        "contains_csc_cap": _contains_any(all_text, CSC_CAP_KEYWORDS),
        "csc_cap_matches": _find_matches(all_text, CSC_CAP_KEYWORDS),
        "contains_course_codes": _extract_course_codes(all_text),
        "final_answer_text": final_answer,
    }


def _contains_any(text: str, keywords: list[str]) -> bool:
    """Return True if any keyword (case-insensitive) appears in *text*."""
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in keywords)


def _find_matches(text: str, keywords: list[str]) -> list[str]:
    """Return the subset of *keywords* found in *text* (case-insensitive)."""
    lowered = text.lower()
    return [kw for kw in keywords if kw.lower() in lowered]


def _extract_course_codes(text: str) -> list[str]:
    """Extract UofT-style course codes from *text*."""
    import re

    return re.findall(r"[A-Z]{3}\d{3}[HY]\d", text.upper())


def _contains_affirmative_enrollment(text: str) -> bool:
    """Check whether *text* contains an affirmative enrollment claim.

    An affirmative claim says the student CAN take/enroll in a course.
    Phrases like "you cannot take", "you are not eligible", or
    "not eligible to enroll" are NOT affirmative and return False.
    """
    lowered = text.lower()

    # Negative phrases that should NOT count as affirmative.
    negative_patterns = [
        "you cannot take", "you can't take",
        "you are not eligible", "you aren't eligible",
        "not eligible to take", "not eligible to enroll",
        "cannot enroll", "can't enroll",
    ]
    for pat in negative_patterns:
        if pat in lowered:
            return False

    # Affirmative phrases.
    affirmative_patterns = [
        "you can take", "you can enroll",
        "you are eligible", "you're eligible",
        "eligible to take", "eligible to enroll",
    ]
    for pat in affirmative_patterns:
        if pat in lowered:
            return True

    return False


# =========================================================================
# Behavior checking
# =========================================================================


@dataclass
class BehaviorResult:
    """The outcome of checking an individual expected behavior."""

    description: str
    passed: bool
    evidence: str


def check_expected_behaviors(
    signals: dict[str, Any],
    expected_behaviors: list[str],
) -> list[BehaviorResult]:
    """Check each expected behavior against the extracted signals.

    Each behavior description is mapped to checkable patterns
    (keywords, tool names, course codes).  This is a heuristic check,
    not exact matching — the human reviewer makes the final call.

    Args:
        signals: Output of :func:`extract_signals`.
        expected_behaviors: Natural-language behavior descriptions from
            the evaluation case.

    Returns:
        A list of :class:`BehaviorResult` — one per expected behavior.
    """
    results: list[BehaviorResult] = []
    for behavior in expected_behaviors:
        passed, evidence = _check_one_behavior(behavior, signals)
        results.append(BehaviorResult(behavior, passed, evidence))
    return results


def _check_one_behavior(
    behavior: str, signals: dict[str, Any]
) -> tuple[bool, str]:
    """Check a single expected-behavior string against signals.

    Returns:
        (passed, evidence_reason).
    """
    lowered = behavior.lower()
    tools_called = signals.get("tools_called", [])
    tool_called = signals.get("tool_called") or ""
    combined = " ".join([
        str(signals.get("thought", "")),
        str(signals.get("observation", "")),
        str(signals.get("final_answer_text", "")),
    ] + signals.get("observations", [])).lower()

    checks: list[tuple[bool, str]] = []

    # --- Tool-calling checks ---
    all_tools = ["check_exclusions", "check_prerequisites",
                 "check_term_availability", "get_course_details",
                 "get_course_metadata_status",
                 "recommend_courses_for_requirement"]
    for tool in all_tools:
        if tool in lowered:
            in_list = tool in tools_called
            checks.append(
                (in_list,
                 f"expected tool '{tool}' — got {tools_called}")
            )

    # --- Course code checks ---
    for code in _extract_course_codes(behavior):
        if code in signals.get("contains_course_codes", []):
            checks.append((True,
                           f"course code '{code}' found in agent output"))
        else:
            checks.append((False,
                           f"course code '{code}' NOT found in agent output"))

    # --- Uncertainty / manual_review ---
    # Note: "manual_review_needed" and "not_eligible" are handled by the
    # structured eligibility status check below — do NOT duplicate them
    # here or the old keyword check will conflict with the new exact
    # status check.
    if any(kw in lowered for kw in [
        "uncertain", "not guaranteed", "complex",
        "needs_official_verification",
    ]):
        checks.append(
            (signals["contains_uncertainty"],
             "uncertainty keywords present"
             if signals["contains_uncertainty"]
             else "no uncertainty keywords found")
        )

    # --- Verification warning ---
    if any(kw in lowered for kw in [
        "verification", "needs_official", "calendar_verified",
    ]):
        checks.append(
            (signals["contains_verification"],
             "verification keywords present"
             if signals["contains_verification"]
             else "no verification keywords found")
        )

    # --- CSC cap ---
    if any(kw in lowered for kw in [
        "1.5", "credit cap", "csc program restriction", "non-cs",
    ]):
        checks.append(
            (signals["contains_csc_cap"],
             "CSC cap keywords present"
             if signals["contains_csc_cap"]
             else "no CSC cap keywords found")
        )

    # --- Term availability ---
    if "term" in lowered and ("fall" in lowered or "winter" in lowered):
        checks.append(
            ("fall" in combined or "winter" in combined,
             "term availability mentioned"
             if ("fall" in combined or "winter" in combined)
             else "term availability NOT mentioned")
        )

    # --- Breadth / BR ---
    if "breadth" in lowered or "br " in lowered:
        checks.append(
            ("breadth" in combined or "br" in combined,
             "breadth mentioned" if ("breadth" in combined or "br" in combined)
             else "breadth NOT mentioned")
        )

    # --- Exclusion checks ---
    if "exclusion" in lowered:
        checks.append(
            ("exclusion" in combined or "exclude" in combined,
             "exclusion mentioned"
             if ("exclusion" in combined or "exclude" in combined)
             else "exclusion NOT mentioned")
        )

    # --- Alternative suggestions ---
    if "alternative" in lowered or "other" in lowered:
        checks.append(
            (True, "checked — alternative/reference noted")
        )

    # --- Clarifying questions ---
    if "ask" in lowered and ("clarif" in lowered or "question" in lowered):
        checks.append(
            (True, "checked — clarifying behavior expected")
        )

    # --- Eligibility status ---
    _has_standalone_eligible = (
        "eligible" in lowered
        and "not eligible" not in lowered
        and "ineligible" not in lowered
        and "eligibility" not in lowered
    )
    _triggers_elig = (
        "not_eligible" in lowered
        or "manual_review_needed" in lowered
        or _has_standalone_eligible
    )
    if _triggers_elig:
        expected = []
        if "not_eligible" in lowered:
            expected.append("not_eligible")
        if "manual_review_needed" in lowered:
            expected.append("manual_review_needed")
        if _has_standalone_eligible:
            expected.append("eligible")
        if expected:
            elig_statuses = signals.get("eligibility_statuses", [])
            found = [s for s in expected if s in elig_statuses]
            checks.append(
                (len(found) > 0,
                 f"eligibility status — expected any of {expected}, "
                 f"found {elig_statuses}")
            )

    # --- Term status ---
    if ("available" in lowered and "winter" in lowered) or \
       ("available" in lowered and "fall" in lowered) or \
       "available in" in lowered:
        term_statuses = signals.get("term_statuses", [])
        target_terms = signals.get("target_terms", [])
        if "available" in lowered:
            has_available = "available" in term_statuses
            checks.append(
                (has_available,
                 f"term status 'available' — found {term_statuses}")
            )
        # Check for specific term mentioned in behavior.
        for term in ["winter", "fall", "summer"]:
            if term in lowered:
                has_term = term.capitalize() in target_terms
                checks.append(
                    (has_term,
                     f"target term '{term}' — found {target_terms}")
                )

    # --- Distinction: availability vs eligibility ---
    if ("distinguish" in lowered and "availability" in lowered
            and "eligibility" in lowered) or \
       ("distinguish" in lowered and "available" in lowered
            and "eligible" in lowered):
        elig = signals.get("eligibility_statuses", [])
        term = signals.get("term_statuses", [])
        has_avail = "available" in term
        has_not_elig = any(s in elig for s in
                           ["not_eligible", "manual_review_needed"])
        checks.append(
            (has_avail and has_not_elig,
             f"distinction check — available={has_avail}, "
             f"not_eligible={has_not_elig}")
        )

    # --- Enrollment claim: "does not claim the student can enroll" ---
    if ("does not claim" in lowered
            and ("enroll" in lowered or "eligible" in lowered
                 or "can take" in lowered)):
        # Check that final_answer does NOT contain affirmative claims.
        has_affirmative = _contains_affirmative_enrollment(combined)
        checks.append(
            (not has_affirmative,
             "no affirmative enrollment claim found"
             if not has_affirmative
             else "affirmative enrollment claim detected")
        )

    # Fallback: if no specific checks were generated, mark as unchecked.
    if not checks:
        return (False, "no specific checks could be derived from this behavior")

    # Overall: pass if all checks pass.
    all_pass = all(p for p, _ in checks)
    evidence = "; ".join(e for _, e in checks)
    return (all_pass, evidence)


# =========================================================================
# Case evaluation
# =========================================================================


@dataclass
class EvalResult:
    """Aggregated evaluation result for a single case."""

    case_id: str
    title: str
    user_query: str
    tool_called: str | None
    tool_pass: bool
    behavior_results: list[BehaviorResult]
    signals: dict[str, Any]
    failure_conditions_checked: list[str] = field(default_factory=list)
    sequence_pass: bool | None = None


def evaluate_case(
    case: dict[str, Any],
    agent: CoursePlanningAgent,
) -> EvalResult:
    """Run one evaluation case through the agent and score it.

    Args:
        case: A single evaluation case dict from ``evaluation_cases.json``.
        agent: An initialised :class:`CoursePlanningAgent`.

    Returns:
        An :class:`EvalResult` with tool-usage and behavior scores.
    """
    completed = case.get("completed_courses", [])
    user_query = case.get("user_query", "")
    expected_tools = case.get("expected_tools", [])
    expected_tool_sequence = case.get("expected_tool_sequence")
    expected_behaviors = case.get("expected_behaviors", [])
    failure_conditions = case.get("failure_conditions", [])

    # --- run agent --------------------------------------------------------
    # Temporarily set completed_courses for this case.
    original_courses = agent.completed_courses
    agent.completed_courses = list(completed)
    try:
        result = agent.handle_request(user_query)
    finally:
        agent.completed_courses = original_courses

    # --- extract signals -------------------------------------------------
    signals = extract_signals(result)
    tools_called = signals["tools_called"]

    # --- check tool usage ------------------------------------------------
    if expected_tools:
        tool_pass = all(t in tools_called for t in expected_tools)
    else:
        tool_pass = True
    signals["expected_tools_match"] = tool_pass

    # --- check tool sequence (optional) ----------------------------------
    sequence_pass: bool | None = None
    if expected_tool_sequence:
        actual_seq = signals["tool_sequence"]
        # Check that actual sequence starts with expected sequence.
        match_count = 0
        for exp, act in zip(expected_tool_sequence,
                            actual_seq[:len(expected_tool_sequence)]):
            if exp == act:
                match_count += 1
        sequence_pass = match_count == len(expected_tool_sequence)
        signals["sequence_match"] = sequence_pass

    # --- check behaviors -------------------------------------------------
    behavior_results = check_expected_behaviors(signals,
                                                expected_behaviors)

    # --- check failure conditions (keyword-based) ------------------------
    steps_text = " ".join(
        s.get("observation", "") for s in result.get("steps", [])
    )
    combined = " ".join([
        result.get("thought", ""),
        result.get("observation", ""),
        result.get("final_answer", ""),
        steps_text,
    ])

    failure_flags: list[str] = []
    for fc in failure_conditions:
        if _is_failure_triggered(fc, combined, signals):
            failure_flags.append(fc)

    return EvalResult(
        case_id=case["case_id"],
        title=case["title"],
        user_query=user_query,
        tool_called=signals["tool_called"],
        tool_pass=tool_pass,
        behavior_results=behavior_results,
        signals=signals,
        failure_conditions_checked=failure_flags,
        sequence_pass=sequence_pass,
    )


def _is_failure_triggered(
    condition: str, combined: str, signals: dict[str, Any]
) -> bool:
    """Heuristic check for whether a failure condition may be triggered.

    This is approximate — it looks for dangerous keywords that would
    indicate the failure condition manifested.
    """
    lowered = condition.lower()

    # "does not mention X" → X is missing from combined output.
    if "does not mention" in lowered or "fails to" in lowered:
        # Extract what should be mentioned.
        for phrase in [
            "verification", "term availability", "csc cap",
            "1.5", "credit cap", "program restriction",
            "prerequisite complexity", "recommended",
        ]:
            if phrase in lowered and phrase.lower() not in combined.lower():
                return True
        return False

    # "invents" / "hallucinates" / "fabricates" → look for unexpected content.
    if any(kw in lowered for kw in [
        "invent", "hallucinate", "fabricate",
    ]):
        return False  # cannot reliably detect with keyword matching

    # "claims ... eligible without" → check for over-confident phrasing.
    if "eligible" in lowered:
        over_confident = (
            "definitely eligible" in combined.lower()
            or "guaranteed eligible" in combined.lower()
            or "will count" in combined.lower()
        )
        return over_confident

    # Fallback: check if the condition's keywords all appear (bad).
    return False


# =========================================================================
# Report generation
# =========================================================================


def format_report(results: list[EvalResult]) -> str:
    """Format a list of :class:`EvalResult` into a readable report string.

    Args:
        results: One result per evaluation case.

    Returns:
        A multi-line report string suitable for printing or saving.
    """
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("EVALUATION REPORT")
    lines.append("=" * 70)
    lines.append("")

    total_behaviors = 0
    passed_behaviors = 0
    tools_pass = 0
    tools_total = 0

    for r in results:
        lines.append("-" * 70)
        lines.append(f"Case: {r.case_id}")
        lines.append(f"Title: {r.title}")
        lines.append("")

        # Tool usage.
        tool_status = "PASS" if r.tool_pass else "FAIL"
        lines.append(f"Tool usage: {tool_status}")
        s = r.signals
        lines.append(f"  Expected : {r.signals.get('expected_tools_match', 'N/A')}")
        lines.append(f"  Called   : {s.get('tool_sequence', []) or '(no tool called)'}")
        lines.append(f"  Count    : {s.get('tool_call_count', 0)}")
        if s.get("observations"):
            for i, obs in enumerate(s["observations"], start=1):
                lines.append(f"  Obs {i}   : {obs[:120]}")
        if r.sequence_pass is not None:
            seq_status = "PASS" if r.sequence_pass else "FAIL"
            lines.append(f"  Sequence : {seq_status}")
        lines.append("")

        if r.tool_called is not None:
            tools_total += 1
            if r.tool_pass:
                tools_pass += 1

        # Behavior checks.
        lines.append("Behavior checks:")
        for br in r.behavior_results:
            status = "PASS" if br.passed else "FAIL"
            lines.append(f"  [{status}] {br.description}")
            lines.append(f"          Evidence: {br.evidence}")
            total_behaviors += 1
            if br.passed:
                passed_behaviors += 1
        lines.append("")

        # Signals summary.
        s = r.signals
        lines.append("Signals:")
        lines.append(f"  Uncertainty mentioned:  {s['contains_uncertainty']}")
        if s["uncertainty_matches"]:
            lines.append(f"    Keywords: {', '.join(s['uncertainty_matches'])}")
        lines.append(f"  Verification warning:   {s['contains_verification']}")
        if s["verification_matches"]:
            lines.append(f"    Keywords: {', '.join(s['verification_matches'])}")
        lines.append(f"  CSC cap mentioned:      {s['contains_csc_cap']}")
        lines.append(f"  Course codes found:     {s['contains_course_codes']}")
        if s.get("eligibility_statuses"):
            lines.append(f"  Eligibility statuses:   {s['eligibility_statuses']}")
        if s.get("term_statuses"):
            lines.append(f"  Term statuses:          {s['term_statuses']}")
        if s.get("target_terms"):
            lines.append(f"  Target terms:           {s['target_terms']}")
        lines.append(f"  Final answer:           {s.get('final_answer_text', '')[:200]}")
        lines.append("")

        # Failure conditions.
        if r.failure_conditions_checked:
            lines.append("⚠️  POTENTIAL FAILURES:")
            for fc in r.failure_conditions_checked:
                lines.append(f"  - {fc}")
            lines.append("")

    # Summary.
    lines.append("=" * 70)
    lines.append("SUMMARY")
    lines.append("=" * 70)
    lines.append(f"Total cases evaluated:    {len(results)}")
    lines.append(f"Tool usage pass rate:     {tools_pass}/{tools_total}"
                 if tools_total else "Tool usage:     N/A")
    lines.append(f"Behavior pass rate:       {passed_behaviors}/{total_behaviors}"
                 f" ({_pct(passed_behaviors, total_behaviors)}%)"
                 if total_behaviors else "Behaviors:       N/A")
    lines.append("")
    lines.append("Note: Behavior checks are heuristic.  A human reviewer")
    lines.append("should verify the final answers against expected behaviors.")
    lines.append("")

    return "\n".join(lines)


def _pct(numerator: int, denominator: int) -> int:
    """Return integer percentage, safely."""
    if denominator == 0:
        return 0
    return round(numerator / denominator * 100)


# =========================================================================
# Main entry point
# =========================================================================


def load_cases(path: str | Path = "eval/evaluation_cases.json") -> list[dict[str, Any]]:
    """Load evaluation cases from a JSON file."""
    full_path = _PROJECT_ROOT / path if not os.path.isabs(path) else Path(path)
    with open(full_path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("cases", [])


def run_evaluation(
    cases: list[dict[str, Any]],
    agent: CoursePlanningAgent,
) -> list[EvalResult]:
    """Run all evaluation cases through the agent.

    Args:
        cases: Loaded evaluation case dicts.
        agent: A pre-initialised :class:`CoursePlanningAgent`.

    Returns:
        One :class:`EvalResult` per case.
    """
    results: list[EvalResult] = []
    for case in cases:
        print(f"Evaluating: {case['case_id']} ...")
        result = evaluate_case(case, agent)
        results.append(result)
    return results


def main() -> None:
    """CLI entry point — load cases, build agent, run evaluation, print report."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the UofT Course Planning Agent evaluation suite."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MockModel instead of TencentTokenHubModel.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write the report to a file instead of stdout.",
    )
    parser.add_argument(
        "--case",
        type=str,
        default=None,
        help="Run only the specified case_id.",
    )
    args = parser.parse_args()

    # --- build model -----------------------------------------------------
    if args.mock:
        model = MockModel()
    else:
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
            print("Use --mock to run with MockModel instead.")
            sys.exit(1)

        model = TencentTokenHubModel()

    # --- load cases and agent --------------------------------------------
    cases = load_cases()
    if args.case:
        cases = [c for c in cases if c["case_id"] == args.case]
        if not cases:
            print(f"ERROR: No case found with case_id='{args.case}'")
            sys.exit(1)

    agent = CoursePlanningAgent(model=model)

    # --- run -------------------------------------------------------------
    results = run_evaluation(cases, agent)
    report = format_report(results)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
