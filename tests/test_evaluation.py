"""Tests for eval/run_evaluation.py — signal extraction and behavior checking.

These tests verify the evaluation helper functions using synthetic agent
results.  No real APIs are called.
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.model import BaseModelInterface  # noqa: E402

from eval.run_evaluation import (
    BehaviorResult,
    EvalResult,
    _contains_affirmative_enrollment,
    _extract_eligibility_statuses,
    _extract_target_terms,
    _extract_term_statuses,
    check_expected_behaviors,
    evaluate_case,
    extract_signals,
    format_report,
    _check_one_behavior,
    _contains_any,
    _extract_course_codes,
    _find_matches,
    _is_failure_triggered,
)


# =========================================================================
# _contains_any
# =========================================================================


def test_contains_any_true():
    assert _contains_any("hello world", ["hello"]) is True


def test_contains_any_false():
    assert _contains_any("hello world", ["goodbye"]) is False


def test_contains_any_case_insensitive():
    assert _contains_any("Hello World", ["hello"]) is True


def test_contains_any_multiple():
    assert _contains_any("foo bar baz", ["bar"]) is True


# =========================================================================
# _find_matches
# =========================================================================


def test_find_matches():
    assert _find_matches("hello world", ["hello", "goodbye"]) == ["hello"]


def test_find_matches_none():
    assert _find_matches("hello world", ["goodbye", "farewell"]) == []


def test_find_matches_case_insensitive():
    assert _find_matches("Hello World", ["hello", "world"]) == [
        "hello",
        "world",
    ]


# =========================================================================
# _extract_course_codes
# =========================================================================


def test_extract_course_codes():
    codes = _extract_course_codes(
        "Consider taking CSC311H1 or COG260H1 in Fall."
    )
    assert "CSC311H1" in codes
    assert "COG260H1" in codes


def test_extract_course_codes_lowercase():
    codes = _extract_course_codes("try csc108h1 or mat137y1")
    assert "CSC108H1" in codes
    assert "MAT137Y1" in codes


def test_extract_course_codes_none():
    assert _extract_course_codes("No courses mentioned here.") == []


# =========================================================================
# extract_signals
# =========================================================================


def _make_result(
    thought: str = "Thinking...",
    tool_called: str | None = "check_prerequisites",
    observation: str = "Course found.",
    final_answer: str = "You can take this course.",
) -> dict:
    return {
        "thought": thought,
        "tool_called": tool_called,
        "observation": observation,
        "final_answer": final_answer,
    }


def test_extract_signals_basic():
    signals = extract_signals(_make_result())
    assert signals["tool_called"] == "check_prerequisites"
    assert signals["has_thought"] is True
    assert signals["has_observation"] is True
    assert signals["has_final_answer"] is True


def test_extract_signals_detects_uncertainty():
    signals = extract_signals(
        _make_result(
            observation="Prerequisites: manual_review_needed."
        )
    )
    assert signals["contains_uncertainty"] is True
    assert "manual_review_needed" in signals["uncertainty_matches"]


def test_extract_signals_detects_verification():
    signals = extract_signals(
        _make_result(
            final_answer="This course needs_official_verification. "
            "Please verify with the academic calendar."
        )
    )
    assert signals["contains_verification"] is True


def test_extract_signals_detects_csc_cap():
    signals = extract_signals(
        _make_result(
            final_answer="Non-CS majors are limited to a maximum "
            "of 1.5 credits in upper-year CSC courses."
        )
    )
    assert signals["contains_csc_cap"] is True


def test_extract_signals_no_uncertainty():
    signals = extract_signals(
        _make_result(final_answer="You are eligible. Enroll now.")
    )
    assert signals["contains_uncertainty"] is False


def test_extract_signals_empty_tool():
    signals = extract_signals(
        _make_result(tool_called=None,
                     observation="No action found.")
    )
    assert signals["tool_called"] is None


# =========================================================================
# _check_one_behavior
# =========================================================================


def test_check_behavior_tool_match():
    signals = extract_signals(
        _make_result(
            tool_called="check_prerequisites",
            final_answer="You can take CSC311H1 after completing prerequisites.",
        )
    )
    passed, evidence = _check_one_behavior(
        "Calls check_prerequisites for CSC311H1.",
        signals,
    )
    assert passed is True
    assert "check_prerequisites" in evidence


def test_check_behavior_tool_mismatch():
    signals = extract_signals(
        _make_result(tool_called="get_course_details")
    )
    passed, evidence = _check_one_behavior(
        "Calls check_prerequisites for CSC311H1.",
        signals,
    )
    assert passed is False


def test_check_behavior_course_code_found():
    signals = extract_signals(
        _make_result(final_answer="CSC311H1 requires CSC148H1.")
    )
    passed, evidence = _check_one_behavior(
        "Mentions CSC311H1 prerequisites.",
        signals,
    )
    assert passed is True


def test_check_behavior_course_code_missing():
    signals = extract_signals(
        _make_result(final_answer="Some course requires prerequisites.")
    )
    passed, evidence = _check_one_behavior(
        "Mentions CSC311H1 prerequisites.",
        signals,
    )
    assert passed is False


def test_check_behavior_manual_review():
    signals = extract_signals(
        _make_result(
            observation="status: manual_review_needed."
        )
    )
    passed, evidence = _check_one_behavior(
        "Reports that prerequisite status may be manual_review_needed.",
        signals,
    )
    assert passed is True


def test_check_behavior_verification():
    signals = extract_signals(
        _make_result(
            final_answer="Please verify with academic advising."
        )
    )
    passed, evidence = _check_one_behavior(
        "Mentions verification with official sources.",
        signals,
    )
    assert passed is True


def test_check_behavior_csc_cap():
    signals = extract_signals(
        _make_result(
            final_answer="Remember the 1.5 credit cap for non-CS majors."
        )
    )
    passed, evidence = _check_one_behavior(
        "Warns about the 1.5 credit cap for non-CS students.",
        signals,
    )
    assert passed is True


def test_check_behavior_no_specific_checks():
    """A behavior with no checkable patterns returns False."""
    signals = extract_signals(_make_result())
    passed, evidence = _check_one_behavior(
        "This is too vague to check automatically.",
        signals,
    )
    assert passed is False
    assert "no specific checks" in evidence.lower()


# =========================================================================
# check_expected_behaviors
# =========================================================================


def test_check_expected_behaviors_returns_list():
    results = check_expected_behaviors(
        extract_signals(
            _make_result(
                final_answer="CSC311H1 is available to eligible students.",
            )
        ),
        ["Calls check_prerequisites for CSC311H1."],
    )
    assert len(results) == 1
    assert isinstance(results[0], BehaviorResult)
    assert results[0].passed is True


# =========================================================================
# _is_failure_triggered
# =========================================================================


def test_failure_condition_does_not_mention():
    signals = extract_signals(_make_result())
    # "Does not mention 1.5 credit cap" — if output lacks "1.5", triggered.
    triggered = _is_failure_triggered(
        "Does not mention the 1.5 credit cap at all.",
        "Some final answer text.",
        signals,
    )
    assert triggered is True  # "1.5" is not in the text


def test_failure_condition_does_not_mention_ok():
    signals = extract_signals(_make_result())
    triggered = _is_failure_triggered(
        "Does not mention the 1.5 credit cap at all.",
        "Remember the 1.5 credit cap for non-CS majors.",
        signals,
    )
    assert triggered is False  # "1.5" IS in the text


def test_failure_condition_over_confident():
    signals = extract_signals(_make_result())
    triggered = _is_failure_triggered(
        "Claims the student is definitely eligible without qualification.",
        "You are definitely eligible for this course.",
        signals,
    )
    assert triggered is True


def test_failure_condition_not_over_confident():
    signals = extract_signals(_make_result())
    triggered = _is_failure_triggered(
        "Claims the student is definitely eligible without qualification.",
        "You may be eligible but please verify with your advisor.",
        signals,
    )
    assert triggered is False


# =========================================================================
# format_report
# =========================================================================


def test_format_report_produces_output():
    signals = extract_signals(_make_result())
    br = BehaviorResult("Test behavior", True, "matched keyword")
    result = EvalResult(
        case_id="test_case",
        title="Test Case",
        user_query="Test query",
        tool_called="check_prerequisites",
        tool_pass=True,
        behavior_results=[br],
        signals=signals,
        failure_conditions_checked=[],
    )
    report = format_report([result])
    assert "EVALUATION REPORT" in report
    assert "test_case" in report
    assert "PASS" in report


def test_format_report_handles_empty():
    report = format_report([])
    assert "EVALUATION REPORT" in report
    assert "0" in report  # total cases


def test_format_report_includes_summary():
    signals = extract_signals(_make_result())
    br = BehaviorResult("Behavior A", True, "ok")
    result = EvalResult(
        case_id="c1",
        title="T1",
        user_query="Q1",
        tool_called="get_course_details",
        tool_pass=True,
        behavior_results=[br],
        signals=signals,
    )
    report = format_report([result])
    assert "SUMMARY" in report
    assert "1/1" in report
    assert "100%" in report


# =========================================================================
# evaluate_case (uses MockModel, no real API)
# =========================================================================


def test_evaluate_case_with_mock_model():
    """evaluate_case runs through with MockModel without errors."""
    from src.agent import CoursePlanningAgent
    from src.model import MockModel

    agent = CoursePlanningAgent(model=MockModel())
    case = {
        "case_id": "test_case",
        "title": "Test",
        "completed_courses": ["CSC108H1"],
        "user_query": "Can I take CSC148H1?",
        "expected_tools": [],
        "expected_behaviors": [],
        "failure_conditions": [],
    }
    result = evaluate_case(case, agent)
    assert isinstance(result, EvalResult)
    assert result.case_id == "test_case"
    assert result.tool_pass is True  # no expected tools → always passes
    assert isinstance(result.behavior_results, list)


def test_evaluate_case_restores_completed_courses():
    """evaluate_case does not permanently mutate the agent's completed_courses."""
    from src.agent import CoursePlanningAgent
    from src.model import MockModel

    agent = CoursePlanningAgent(
        completed_courses=["COG100H1"],
        model=MockModel(),
    )
    case = {
        "case_id": "tc",
        "title": "T",
        "completed_courses": ["CSC108H1", "CSC148H1"],
        "user_query": "What courses?",
        "expected_tools": [],
        "expected_behaviors": [],
        "failure_conditions": [],
    }
    evaluate_case(case, agent)
    assert agent.completed_courses == ["COG100H1"]


# =========================================================================
# run_full_evaluation.py helpers
# =========================================================================

from eval.run_full_evaluation import (  # noqa: E402
    CategorySummary,
    _case_passed,
    aggregate_by_category,
    format_markdown_report,
)


def _make_eval_result(
    case_id: str = "test",
    tool_pass: bool = True,
    tool_called: str | None = "check_prerequisites",
    behaviors: list[tuple[str, bool]] | None = None,
    steps: list[dict] | None = None,
    sequence_pass: bool | None = None,
    final_answer: str = "test",
    observation: str = "test",
) -> EvalResult:
    """Build an EvalResult with the given behavior results."""
    if behaviors is None:
        behaviors = [("Test behavior", True)]
    brs = [BehaviorResult(desc, passed, "evidence") for desc, passed in behaviors]
    result_data: dict = {
        "thought": "test",
        "tool_called": tool_called,
        "observation": observation,
        "final_answer": final_answer,
    }
    if steps is not None:
        result_data["steps"] = steps
    signals = extract_signals(result_data)
    return EvalResult(
        case_id=case_id,
        title="Test Case",
        user_query="Test?",
        tool_called=tool_called,
        tool_pass=tool_pass,
        behavior_results=brs,
        signals=signals,
        sequence_pass=sequence_pass,
    )


# --- _case_passed --------------------------------------------------------


def test_case_passed_all_behaviors_pass():
    result = _make_eval_result(behaviors=[("A", True), ("B", True)])
    assert _case_passed(result) is True


def test_case_passed_one_behavior_fails():
    result = _make_eval_result(behaviors=[("A", True), ("B", False)])
    assert _case_passed(result) is False


def test_case_passed_no_behaviors():
    result = _make_eval_result(behaviors=[], tool_pass=True)
    assert _case_passed(result) is True


def test_case_passed_no_behaviors_tool_fails():
    result = _make_eval_result(behaviors=[], tool_pass=False)
    assert _case_passed(result) is False


# --- aggregate_by_category -----------------------------------------------


def test_aggregate_by_category_groups_correctly():
    r1 = _make_eval_result(case_id="c1", behaviors=[("A", True)])
    r2 = _make_eval_result(case_id="c2", behaviors=[("B", True)])
    r3 = _make_eval_result(case_id="c3", behaviors=[("C", False)])

    results = [r1, r2, r3]
    cases = [
        {"case_id": "c1", "category": "prerequisite_reasoning"},
        {"case_id": "c2", "category": "course_recommendation"},
        {"case_id": "c3", "category": "prerequisite_reasoning"},
    ]

    summaries = aggregate_by_category(results, cases)
    assert len(summaries) == 2

    prereq = [s for s in summaries if s.name == "prerequisite_reasoning"][0]
    assert prereq.total == 2
    assert prereq.passed == 1  # c1 passes, c3 fails
    assert prereq.failed == 1

    course = [s for s in summaries if s.name == "course_recommendation"][0]
    assert course.total == 1
    assert course.passed == 1


def test_aggregate_by_category_empty():
    summaries = aggregate_by_category([], [])
    assert summaries == []


# --- format_markdown_report ----------------------------------------------


def test_format_markdown_report_structure():
    r = _make_eval_result(case_id="recommend_ai_ml",
                          behaviors=[("Calls tool", True)])
    cases = [{
        "case_id": "recommend_ai_ml",
        "category": "course_recommendation",
        "title": "AI/ML recommendation",
        "user_query": "What AI courses?",
        "expected_tools": ["recommend_courses_for_requirement"],
    }]
    report = format_markdown_report([r], cases, "MockModel")

    # Header.
    assert "# Evaluation Report" in report
    assert "MockModel" in report

    # Summary table.
    assert "## Summary" in report
    assert "Total scenarios" in report
    assert "Pass rate" in report

    # Category breakdown.
    assert "## Category Breakdown" in report
    assert "course_recommendation" in report

    # Individual results.
    assert "## Individual Results" in report
    assert "recommend_ai_ml" in report
    assert "PASS" in report
    assert "✅" in report


def test_format_markdown_report_with_failure():
    r = _make_eval_result(case_id="fail_case",
                          behaviors=[("Should do X", False)])
    cases = [{
        "case_id": "fail_case",
        "category": "breadth_requirement",
        "title": "Failing test",
        "user_query": "Query?",
        "expected_tools": [],
    }]
    report = format_markdown_report([r], cases, "MockModel")

    assert "FAIL" in report
    assert "Failed behaviors" in report
    assert "❌" in report
    assert "0%" in report or "0 cases passed" in report.lower()


def test_format_markdown_report_includes_timestamp():
    r = _make_eval_result()
    cases = [{"case_id": "test", "category": "test", "title": "T",
              "user_query": "Q?", "expected_tools": []}]
    report = format_markdown_report([r], cases, "MockModel")
    assert "2026" in report  # timestamp contains the year
    assert "UTC" in report


def test_format_markdown_report_includes_footer():
    r = _make_eval_result()
    cases = [{"case_id": "test", "category": "test", "title": "T",
              "user_query": "Q?", "expected_tools": []}]
    report = format_markdown_report([r], cases, "MockModel")
    assert "run_full_evaluation.py" in report
    assert "heuristic" in report.lower()


# =========================================================================
# Multi-step evaluation — signals, tool checking, sequence
# =========================================================================


class _SpyModel(BaseModelInterface):
    """A test model that records messages (same pattern as test_agent.py)."""

    def __init__(self) -> None:
        self.last_messages: list[dict] = []

    def generate_response(self, messages: list[dict]) -> str:
        self.last_messages = messages
        return "Spy model response"


class TestMultiStepSignals:
    """Verify signal extraction from multi-step agent results."""

    def test_two_step_result_extracts_both_tools(self):
        """Two steps → tools_called list has both tool names."""
        signals = extract_signals({
            "thought": "...",
            "tool_called": "check_prerequisites",
            "observation": "not_eligible.",
            "steps": [
                {"thought": "...", "tool_called": "check_prerequisites",
                 "arguments": {}, "observation": "not_eligible."},
                {"thought": "...", "tool_called": "check_term_availability",
                 "arguments": {}, "observation": "available in Winter."},
            ],
            "final_answer": "...",
        })
        assert signals["tools_called"] == [
            "check_prerequisites", "check_term_availability"
        ]
        assert signals["tool_call_count"] == 2
        assert signals["tool_sequence"] == [
            "check_prerequisites", "check_term_availability"
        ]
        assert len(signals["observations"]) == 2

    def test_empty_steps_falls_back_to_single_tool(self):
        """Empty steps → falls back to top-level tool_called."""
        signals = extract_signals({
            "thought": "...",
            "tool_called": "get_course_details",
            "observation": "Found course.",
            "steps": [],
            "final_answer": "...",
        })
        assert signals["tools_called"] == ["get_course_details"]
        assert signals["tool_call_count"] == 1

    def test_no_steps_key_falls_back(self):
        """Missing steps key → backward compatible."""
        signals = extract_signals({
            "thought": "...",
            "tool_called": "check_prerequisites",
            "observation": "eligible.",
            "final_answer": "...",
        })
        assert signals["tools_called"] == ["check_prerequisites"]
        assert signals["tool_call_count"] == 1

    def test_no_tool_called_and_no_steps(self):
        """Neither tool_called nor steps → empty lists."""
        signals = extract_signals({
            "thought": "...",
            "tool_called": None,
            "observation": "...",
            "final_answer": "...",
        })
        assert signals["tools_called"] == []
        assert signals["tool_call_count"] == 0

    def test_observations_collected_from_steps(self):
        """observations list matches step observations."""
        signals = extract_signals({
            "thought": "...",
            "tool_called": "check_prerequisites",
            "observation": "...",
            "steps": [
                {"thought": "t1", "tool_called": "check_prerequisites",
                 "arguments": {}, "observation": "obs1"},
                {"thought": "t2", "tool_called": "get_course_details",
                 "arguments": {}, "observation": "obs2"},
            ],
            "final_answer": "...",
        })
        assert signals["observations"] == ["obs1", "obs2"]


# =========================================================================
# evaluate_case with multi-step
# =========================================================================


class TestEvaluateCaseMultiStep:
    """Verify tool and sequence checking in evaluate_case."""

    def test_expected_tools_passes_when_all_present(self):
        """all expected tools in steps → tool_pass=True."""
        from src.agent import CoursePlanningAgent

        agent = CoursePlanningAgent(
            model=_SpyModel(),
        )
        # Override handle_request to return a two-step result.
        def fake_handle(req, max_tool_steps=2):
            return {
                "thought": "...",
                "tool_called": "check_prerequisites",
                "observation": "not_eligible.",
                "steps": [
                    {"thought": "...", "tool_called": "check_prerequisites",
                     "arguments": {}, "observation": "not_eligible."},
                    {"thought": "...", "tool_called": "check_term_availability",
                     "arguments": {}, "observation": "available."},
                ],
                "final_answer": "...",
                "stop_reason": "max_steps",
            }
        agent.handle_request = fake_handle  # type: ignore[method-assign]

        case = {
            "case_id": "tc",
            "title": "T",
            "completed_courses": [],
            "user_query": "Q?",
            "expected_tools": ["check_prerequisites", "check_term_availability"],
            "expected_behaviors": [],
            "failure_conditions": [],
        }
        result = evaluate_case(case, agent)
        assert result.tool_pass is True

    def test_expected_tools_fails_when_one_missing(self):
        """One expected tool missing → tool_pass=False."""
        from src.agent import CoursePlanningAgent

        agent = CoursePlanningAgent(model=_SpyModel())
        def fake_handle(req, max_tool_steps=2):
            return {
                "thought": "...",
                "tool_called": "check_prerequisites",
                "observation": "...",
                "steps": [
                    {"thought": "...", "tool_called": "check_prerequisites",
                     "arguments": {}, "observation": "..."},
                ],
                "final_answer": "...",
                "stop_reason": "max_steps",
            }
        agent.handle_request = fake_handle  # type: ignore[method-assign]

        case = {
            "case_id": "tc",
            "title": "T",
            "completed_courses": [],
            "user_query": "Q?",
            "expected_tools": ["check_prerequisites", "get_course_details"],
            "expected_behaviors": [],
            "failure_conditions": [],
        }
        result = evaluate_case(case, agent)
        assert result.tool_pass is False

    def test_sequence_passes_for_correct_order(self):
        """expected_tool_sequence matches actual sequence."""
        from src.agent import CoursePlanningAgent

        agent = CoursePlanningAgent(model=_SpyModel())
        def fake_handle(req, max_tool_steps=2):
            return {
                "thought": "...",
                "tool_called": "check_prerequisites",
                "observation": "...",
                "steps": [
                    {"thought": "...", "tool_called": "check_prerequisites",
                     "arguments": {}, "observation": "..."},
                    {"thought": "...", "tool_called": "check_term_availability",
                     "arguments": {}, "observation": "..."},
                ],
                "final_answer": "...",
                "stop_reason": "max_steps",
            }
        agent.handle_request = fake_handle  # type: ignore[method-assign]

        case = {
            "case_id": "tc",
            "title": "T",
            "completed_courses": [],
            "user_query": "Q?",
            "expected_tools": [],
            "expected_tool_sequence": ["check_prerequisites",
                                       "check_term_availability"],
            "expected_behaviors": [],
            "failure_conditions": [],
        }
        result = evaluate_case(case, agent)
        assert result.sequence_pass is True

    def test_sequence_fails_for_reversed_order(self):
        """reversed sequence → sequence_pass=False."""
        from src.agent import CoursePlanningAgent

        agent = CoursePlanningAgent(model=_SpyModel())
        def fake_handle(req, max_tool_steps=2):
            return {
                "thought": "...",
                "tool_called": "check_term_availability",
                "observation": "...",
                "steps": [
                    {"thought": "...", "tool_called": "check_term_availability",
                     "arguments": {}, "observation": "..."},
                    {"thought": "...", "tool_called": "check_prerequisites",
                     "arguments": {}, "observation": "..."},
                ],
                "final_answer": "...",
                "stop_reason": "max_steps",
            }
        agent.handle_request = fake_handle  # type: ignore[method-assign]

        case = {
            "case_id": "tc",
            "title": "T",
            "completed_courses": [],
            "user_query": "Q?",
            "expected_tools": [],
            "expected_tool_sequence": ["check_prerequisites",
                                       "check_term_availability"],
            "expected_behaviors": [],
            "failure_conditions": [],
        }
        result = evaluate_case(case, agent)
        assert result.sequence_pass is False

    def test_single_step_old_format_still_works(self):
        """Old single-step result without steps key still evaluates."""
        from src.agent import CoursePlanningAgent

        agent = CoursePlanningAgent(model=_SpyModel())
        def fake_handle(req, max_tool_steps=2):
            return {
                "thought": "...",
                "tool_called": "get_course_details",
                "observation": "Found course.",
                "final_answer": "CSC108H1 is an intro course.",
            }
        agent.handle_request = fake_handle  # type: ignore[method-assign]

        case = {
            "case_id": "tc",
            "title": "T",
            "completed_courses": [],
            "user_query": "What is CSC108H1?",
            "expected_tools": ["get_course_details"],
            "expected_behaviors": [],
            "failure_conditions": [],
        }
        result = evaluate_case(case, agent)
        assert result.tool_pass is True

    def test_markdown_report_shows_tool_sequence(self):
        """Two-step result → report shows the tool sequence."""
        steps = [
            {"thought": "...", "tool_called": "check_prerequisites",
             "arguments": {}, "observation": "not_eligible."},
            {"thought": "...", "tool_called": "check_term_availability",
             "arguments": {}, "observation": "available in Winter."},
        ]
        r = _make_eval_result(
            case_id="multi_case",
            tool_called="check_prerequisites",
            steps=steps,
        )
        cases = [{
            "case_id": "multi_case",
            "category": "prerequisite_reasoning",
            "title": "Multi-step test",
            "user_query": "Can I take CSC384H1?",
            "expected_tools": ["check_prerequisites",
                               "check_term_availability"],
        }]
        report = format_markdown_report([r], cases, "MockModel")
        assert "check_prerequisites" in report
        assert "check_term_availability" in report
        assert "not_eligible" in report
        assert "available in Winter" in report


# =========================================================================
# Structured status extraction
# =========================================================================


class TestStatusExtraction:
    """Verify eligibility, term, and target term extraction."""

    def test_not_eligible_extracted_from_prereq_obs(self):
        """not_eligible in check_prerequisites observation → extracted."""
        statuses = _extract_eligibility_statuses([
            "Prerequisite check for CSC384H1: not_eligible."
        ])
        assert statuses == ["not_eligible"]

    def test_eligible_extracted(self):
        """eligible in observation → extracted (and not not_eligible)."""
        statuses = _extract_eligibility_statuses([
            "Prerequisite check for CSC108H1: eligible."
        ])
        assert statuses == ["eligible"]

    def test_manual_review_extracted(self):
        """manual_review_needed → extracted."""
        statuses = _extract_eligibility_statuses([
            "Prerequisite check for CSC311H1: manual_review_needed."
        ])
        assert "manual_review_needed" in statuses

    def test_available_and_winter_extracted(self):
        """available + Winter from term observation."""
        term_s = _extract_term_statuses(
            ["Tool 'check_term_availability' returned: {...'status': 'available'...}"],
            ["check_term_availability"],
        )
        assert "available" in term_s
        terms = _extract_target_terms(
            ["...target_term': 'Winter'..."],
            ["check_term_availability"],
        )
        assert "Winter" in terms

    def test_not_available_extracted(self):
        """not_available from term observation."""
        term_s = _extract_term_statuses(
            ["status': 'not_available'"],
            ["check_term_availability"],
        )
        assert "not_available" in term_s

    def test_available_not_in_non_term_obs(self):
        """'available' in prose (not term tool) is not extracted."""
        term_s = _extract_term_statuses(
            ["This course is available to all students."],
            ["check_prerequisites"],  # not a term tool
        )
        assert term_s == []

    # -- substring-overlap fix --------------------------------------------

    def test_not_eligible_does_not_produce_eligible(self):
        """not_eligible → only not_eligible, NOT eligible."""
        statuses = _extract_eligibility_statuses([
            "Prerequisite check for CSC384H1: not_eligible."
        ])
        assert statuses == ["not_eligible"], (
            f"Expected ['not_eligible'] but got {statuses}"
        )

    def test_eligible_alone_is_detected(self):
        """eligible alone (no not_eligible) → eligible."""
        statuses = _extract_eligibility_statuses([
            "Prerequisite check for CSC108H1: eligible."
        ])
        assert statuses == ["eligible"]

    def test_manual_review_needed_alone_is_detected(self):
        """manual_review_needed without overlap → detected alone."""
        statuses = _extract_eligibility_statuses([
            "Prerequisite status: manual_review_needed."
        ])
        assert statuses == ["manual_review_needed"]

    def test_multiple_distinct_statuses_preserved(self):
        """Two observations with different statuses → both kept."""
        statuses = _extract_eligibility_statuses([
            "Prerequisite check for CSC384H1: not_eligible.",
            "Prerequisite check for CSC311H1: eligible.",
        ])
        assert "not_eligible" in statuses
        assert "eligible" in statuses
        assert len(statuses) == 2

    def test_duplicate_statuses_deduplicated(self):
        """Same status across two observations → only one entry."""
        statuses = _extract_eligibility_statuses([
            "Prerequisite check: not_eligible.",
            "Another check: not_eligible.",
        ])
        assert statuses == ["not_eligible"]

    def test_term_not_available_does_not_produce_available(self):
        """not_available → not_available alone, NOT available."""
        term_s = _extract_term_statuses(
            ["status': 'not_available'"],
            ["check_term_availability"],
        )
        # not_available is checked before available in the function.
        assert "not_available" in term_s
        assert "available" not in term_s

    def test_term_available_alone_when_exists(self):
        """available alone (no not_available) → available."""
        term_s = _extract_term_statuses(
            ["status': 'available'"],
            ["check_term_availability"],
        )
        assert term_s == ["available"]


# =========================================================================
# Signal integration — multi-step result
# =========================================================================


class TestMultiStepSignalIntegration:
    """Verify signals from a realistic two-step agent result."""

    TWO_STEP_RESULT = {
        "thought": "...",
        "tool_called": "check_prerequisites",
        "observation": "not_eligible.",
        "steps": [
            {"thought": "...", "tool_called": "check_prerequisites",
             "arguments": {}, "observation": "Prerequisite check for CSC384H1: not_eligible."},
            {"thought": "...", "tool_called": "check_term_availability",
             "arguments": {}, "observation": "Tool returned: 'status': 'available', 'target_term': 'Winter'"},
        ],
        "final_answer": "CSC384H1 is available in Winter but you are not eligible to enroll.",
    }

    def test_eligibility_status_in_signals(self):
        signals = extract_signals(self.TWO_STEP_RESULT)
        assert "not_eligible" in signals["eligibility_statuses"]

    def test_term_status_and_target_in_signals(self):
        signals = extract_signals(self.TWO_STEP_RESULT)
        assert "available" in signals["term_statuses"]
        assert "Winter" in signals["target_terms"]

    def test_final_answer_text_in_signals(self):
        signals = extract_signals(self.TWO_STEP_RESULT)
        assert "not eligible to enroll" in signals["final_answer_text"].lower()

    def test_report_shows_final_answer(self):
        steps = self.TWO_STEP_RESULT["steps"]
        r = _make_eval_result(
            case_id="mc", tool_called="check_prerequisites",
            steps=steps,
            final_answer="CSC384H1 is available in Winter but you are not eligible to enroll.",
        )
        cases = [{"case_id": "mc", "category": "test", "title": "T",
                  "user_query": "Q?", "expected_tools": []}]
        report = format_markdown_report([r], cases, "MockModel")
        assert "Final answer" in report
        assert "not eligible to enroll" in report.lower()

    def test_report_shows_structured_statuses(self):
        steps = self.TWO_STEP_RESULT["steps"]
        r = _make_eval_result(case_id="mc", tool_called="check_prerequisites",
                              steps=steps)
        cases = [{"case_id": "mc", "category": "test", "title": "T",
                  "user_query": "Q?", "expected_tools": []}]
        report = format_markdown_report([r], cases, "MockModel")
        assert "Eligibility" in report
        assert "Term Status" in report
        assert "not_eligible" in report
        assert "available" in report


# =========================================================================
# Behavior checks — eligibility + term + distinction + enrollment
# =========================================================================


class TestStatusBehaviorChecks:
    """Verify check_one_behavior handles new check types."""

    TWO_STEP_SIGNALS = extract_signals({
        "thought": "...",
        "tool_called": "check_prerequisites",
        "observation": "...",
        "steps": [
            {"thought": "...", "tool_called": "check_prerequisites",
             "arguments": {}, "observation": "Prerequisite check for CSC384H1: not_eligible."},
            {"thought": "...", "tool_called": "check_term_availability",
             "arguments": {}, "observation": "...'status': 'available'...'target_term': 'Winter'..."},
        ],
        "final_answer": "CSC384H1 is available in Winter but you are not eligible to enroll.",
    })

    def test_not_eligible_behavior_passes(self):
        """Behavior expects not_eligible → passes when observed."""
        passed, ev = _check_one_behavior(
            "Reports that prerequisite eligibility is not_eligible.",
            self.TWO_STEP_SIGNALS,
        )
        assert passed is True, f"Expected PASS, got: {ev}"

    def test_available_in_winter_passes(self):
        """Behavior expects available in Winter → passes."""
        passed, ev = _check_one_behavior(
            "Reports that CSC384H1 is available in Winter.",
            self.TWO_STEP_SIGNALS,
        )
        assert passed is True, f"Expected PASS, got: {ev}"

    def test_distinction_passes_when_both_statuses_present(self):
        """Distinction: available + not_eligible → passes."""
        passed, ev = _check_one_behavior(
            "Distinguishes course availability (available in Winter) "
            "from student eligibility (not_eligible).",
            self.TWO_STEP_SIGNALS,
        )
        assert passed is True, f"Expected PASS, got: {ev}"

    def test_distinction_fails_when_only_availability(self):
        """Only available, no not_eligible → distinction fails."""
        signals_avail_only = extract_signals({
            "thought": "...",
            "tool_called": "check_term_availability",
            "observation": "...",
            "steps": [
                {"thought": "...", "tool_called": "check_term_availability",
                 "arguments": {}, "observation": "...'status': 'available'..."},
            ],
            "final_answer": "CSC384H1 is available in Winter.",
        })
        passed, ev = _check_one_behavior(
            "Distinguishes course availability from student eligibility.",
            signals_avail_only,
        )
        assert passed is False, f"Expected FAIL, got: {ev}"


# =========================================================================
# Affirmative enrollment claim detection
# =========================================================================


class TestEnrollmentClaimDetection:
    """Verify _contains_affirmative_enrollment correctly distinguishes."""

    def test_negative_cannot_take_not_flagged(self):
        """'you cannot take' is NOT affirmative."""
        assert _contains_affirmative_enrollment(
            "You cannot take CSC384H1 because you are not eligible."
        ) is False

    def test_negative_not_eligible_not_flagged(self):
        """'not eligible' → not affirmative."""
        assert _contains_affirmative_enrollment(
            "You are not eligible to enroll in CSC384H1."
        ) is False

    def test_affirmative_can_take_flagged(self):
        """'you can take' → affirmative."""
        assert _contains_affirmative_enrollment(
            "You can take CSC384H1 since you are eligible."
        ) is True

    def test_affirmative_eligible_flagged(self):
        """'you are eligible' → affirmative."""
        assert _contains_affirmative_enrollment(
            "You are eligible to enroll in CSC384H1."
        ) is True

    def test_does_not_claim_behavior_passes_with_negative(self):
        """'does not claim enrollment' passes when answer is negative."""
        signals = extract_signals({
            "thought": "...",
            "tool_called": "check_prerequisites",
            "observation": "...",
            "steps": [
                {"thought": "...", "tool_called": "check_prerequisites",
                 "arguments": {}, "observation": "not_eligible."},
                {"thought": "...", "tool_called": "check_term_availability",
                 "arguments": {}, "observation": "...available...Winter..."},
            ],
            "final_answer": "CSC384H1 is available in Winter but you cannot take it.",
        })
        passed, ev = _check_one_behavior(
            "Does not claim that Winter availability means the student can enroll.",
            signals,
        )
        assert passed is True, f"Expected PASS, got: {ev}"

    def test_does_not_claim_behavior_fails_with_affirmative(self):
        """'does not claim enrollment' fails when answer is affirmative."""
        signals = extract_signals({
            "thought": "...",
            "tool_called": "check_prerequisites",
            "observation": "...",
            "steps": [
                {"thought": "...", "tool_called": "check_prerequisites",
                 "arguments": {}, "observation": "eligible."},
                {"thought": "...", "tool_called": "check_term_availability",
                 "arguments": {}, "observation": "...available...Winter..."},
            ],
            "final_answer": "CSC384H1 is available in Winter and you can take it.",
        })
        passed, ev = _check_one_behavior(
            "Does not claim that Winter availability means the student can enroll.",
            signals,
        )
        assert passed is False, f"Expected FAIL, got: {ev}"


# =========================================================================
# Boolean-logic "or" — any-match semantics for eligibility
# =========================================================================


class TestEligibilityOrLogic:
    """Verify that 'not_eligible or manual_review_needed' means ANY match."""

    def _signals_with_eligibility(self, status: str) -> dict:
        """Build signals with a single eligibility observation."""
        return extract_signals({
            "thought": "...",
            "tool_called": "check_prerequisites",
            "observation": "...",
            "steps": [
                {"thought": "...", "tool_called": "check_prerequisites",
                 "arguments": {},
                 "observation": f"Prerequisite check: {status}."},
            ],
            "final_answer": f"Status is {status}.",
        })

    def test_not_eligible_passes_or_behavior(self):
        """not_eligible satisfies 'not_eligible or manual_review_needed'."""
        signals = self._signals_with_eligibility("not_eligible")
        passed, ev = _check_one_behavior(
            "Reports that prerequisite eligibility is not_eligible "
            "or manual_review_needed.",
            signals,
        )
        assert passed is True, f"Expected PASS, got: {ev}"

    def test_manual_review_passes_or_behavior(self):
        """manual_review_needed satisfies 'not_eligible or manual_review_needed'."""
        signals = self._signals_with_eligibility("manual_review_needed")
        passed, ev = _check_one_behavior(
            "Reports that prerequisite eligibility is not_eligible "
            "or manual_review_needed.",
            signals,
        )
        assert passed is True, f"Expected PASS, got: {ev}"

    def test_eligible_fails_or_behavior(self):
        """eligible does NOT satisfy 'not_eligible or manual_review_needed'."""
        signals = self._signals_with_eligibility("eligible")
        passed, ev = _check_one_behavior(
            "Reports that prerequisite eligibility is not_eligible "
            "or manual_review_needed.",
            signals,
        )
        assert passed is False, f"Expected FAIL, got: {ev}"

    def test_empty_statuses_fails_or_behavior(self):
        """No eligibility statuses → fails 'or' behavior."""
        signals = extract_signals({
            "thought": "...",
            "tool_called": None,
            "observation": "...",
            "final_answer": "No status reported.",
        })
        passed, ev = _check_one_behavior(
            "Reports that prerequisite eligibility is not_eligible "
            "or manual_review_needed.",
            signals,
        )
        assert passed is False, f"Expected FAIL, got: {ev}"

    def test_not_eligible_passes_even_without_uncertainty(self):
        """not_eligible passes even when has_uncertainty is False."""
        signals = self._signals_with_eligibility("not_eligible")
        # Verify contains_uncertainty is False.
        assert signals["contains_uncertainty"] is False
        passed, ev = _check_one_behavior(
            "Reports that prerequisite eligibility is not_eligible "
            "or manual_review_needed.",
            signals,
        )
        assert passed is True, (
            f"Expected PASS but got FAIL with evidence: {ev}"
        )

    def test_single_not_eligible_still_passes(self):
        """Exact 'not_eligible' (not 'or') still passes."""
        signals = self._signals_with_eligibility("not_eligible")
        passed, ev = _check_one_behavior(
            "Reports that prerequisite eligibility is not_eligible.",
            signals,
        )
        assert passed is True, f"Expected PASS, got: {ev}"

    def test_single_manual_review_still_passes(self):
        """Exact 'manual_review_needed' (not 'or') still passes."""
        signals = self._signals_with_eligibility("manual_review_needed")
        passed, ev = _check_one_behavior(
            "Reports that prerequisite status may be manual_review_needed.",
            signals,
        )
        assert passed is True, f"Expected PASS, got: {ev}"


# =========================================================================
# Aggregation consistency — _case_passed vs aggregate_by_category
# =========================================================================

from eval.run_full_evaluation import _case_passed, aggregate_by_category  # noqa: E402


def test_empty_behaviors_tool_fail_case_verdict_fail():
    er = _make_eval_result(behaviors=[], tool_pass=False)
    assert _case_passed(er) is False


def test_empty_behaviors_tool_pass_case_verdict_pass():
    er = _make_eval_result(behaviors=[], tool_pass=True)
    assert _case_passed(er) is True


def test_empty_behaviors_tool_fail_category_aggregate_fail():
    er = _make_eval_result(case_id="c1", behaviors=[], tool_pass=False)
    cases = [{"case_id": "c1", "category": "test"}]
    summaries = aggregate_by_category([er], cases)
    assert summaries[0].passed == 0
    assert summaries[0].failed == 1


def test_empty_behaviors_tool_pass_category_aggregate_pass():
    er = _make_eval_result(case_id="c2", behaviors=[], tool_pass=True)
    cases = [{"case_id": "c2", "category": "test"}]
    summaries = aggregate_by_category([er], cases)
    assert summaries[0].passed == 1


def test_one_behavior_fails_category_aggregate_fail():
    er = _make_eval_result(
        case_id="c3", behaviors=[("Should pass", False)], tool_pass=True,
    )
    cases = [{"case_id": "c3", "category": "test"}]
    summaries = aggregate_by_category([er], cases)
    assert summaries[0].passed == 0
    assert summaries[0].failed == 1


def test_all_behaviors_pass_category_aggregate_pass():
    er = _make_eval_result(
        case_id="c4", behaviors=[("A", True), ("B", True)], tool_pass=True,
    )
    cases = [{"case_id": "c4", "category": "test"}]
    summaries = aggregate_by_category([er], cases)
    assert summaries[0].passed == 1


def test_summary_and_category_agree():
    """Summary table and category breakdown always match."""
    results = [
        _make_eval_result(case_id="p", behaviors=[("A", True)], tool_pass=True),
        _make_eval_result(case_id="f", behaviors=[("B", False)], tool_pass=True),
        _make_eval_result(case_id="e", behaviors=[], tool_pass=False),
    ]
    cases = [
        {"case_id": "p", "category": "cat"},
        {"case_id": "f", "category": "cat"},
        {"case_id": "e", "category": "cat"},
    ]
    summary_passed = sum(1 for r in results if _case_passed(r))
    summaries = aggregate_by_category(results, cases)
    assert summaries[0].passed == summary_passed, (
        f"Category passed={summaries[0].passed} != summary passed={summary_passed}"
    )


# =========================================================================
# evaluate_case with pre-computed agent_result
# =========================================================================


def test_evaluate_case_uses_existing_agent_result():
    """When agent_result is provided, handle_request is NOT called."""
    from src.agent import CoursePlanningAgent
    from src.model import MockModel

    agent = CoursePlanningAgent(model=MockModel())
    precomputed = {
        "thought": "...",
        "tool_called": "check_prerequisites",
        "observation": "not_eligible.",
        "steps": [{
            "thought": "...", "tool_called": "check_prerequisites",
            "arguments": {"course_code": "CSC384H1",
                          "completed_courses": ["CSC148H1"]},
            "observation": "not_eligible.",
        }],
        "final_answer": "You cannot take CSC384H1.",
        "stop_reason": "max_steps",
    }
    case = {
        "case_id": "tc", "title": "T",
        "completed_courses": ["CSC148H1"],
        "user_query": "Can I take CSC384H1?",
        "expected_tools": ["check_prerequisites"],
        "expected_behaviors": [],
        "failure_conditions": [],
    }
    result = evaluate_case(case, agent, agent_result=precomputed)
    assert result.tool_pass is True
    assert result.tool_called == "check_prerequisites"


def test_evaluate_case_backward_compatibility():
    """Without agent_result, agent.handle_request() still runs."""
    from src.agent import CoursePlanningAgent
    from src.model import MockModel

    agent = CoursePlanningAgent(model=MockModel())
    case = {
        "case_id": "tc", "title": "T",
        "completed_courses": [],
        "user_query": "Q?",
        "expected_tools": [],
        "expected_behaviors": [],
        "failure_conditions": [],
    }
    result = evaluate_case(case, agent)
    assert isinstance(result, EvalResult)
    # MockModel returns "Mock model response" → no parseable JSON → no tool.
    assert result.tool_pass is True  # empty expected_tools


# =========================================================================
# completed_courses, interests, prerequisite_status behavior checks
# =========================================================================


def test_completed_courses_arg_check_passes():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": "recommend_courses_for_requirement",
        "observation": "...",
        "steps": [{
            "thought": "...",
            "tool_called": "recommend_courses_for_requirement",
            "arguments": {
                "requirement_tag": "computational_cognition_stream_pool",
                "completed_courses": ["CSC108H1", "CSC148H1", "STA237H1"],
            },
            "observation": "Found 65 courses...",
        }],
        "final_answer": "Consider CSC311H1 and CSC384H1.",
    })
    passed, ev = _check_one_behavior(
        "Passes the student's completed_courses for prerequisite checks.",
        signals,
    )
    assert passed is True, f"Expected PASS, got: {ev}"


def test_completed_courses_arg_check_fails():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": "recommend_courses_for_requirement",
        "observation": "...",
        "steps": [{
            "thought": "...",
            "tool_called": "recommend_courses_for_requirement",
            "arguments": {"requirement_tag": "pool"},
            "observation": "...",
        }],
        "final_answer": "Some courses.",
    })
    passed, ev = _check_one_behavior(
        "Passes the student's completed_courses for prerequisite checks.",
        signals,
    )
    assert passed is False, f"Expected FAIL, got: {ev}"


def test_interests_arg_check_passes_ai():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": "recommend_courses_for_requirement",
        "observation": "...",
        "steps": [{
            "thought": "...",
            "tool_called": "recommend_courses_for_requirement",
            "arguments": {
                "requirement_tag": "pool",
                "completed_courses": [],
                "interests": ["AI", "machine learning"],
            },
            "observation": "...",
        }],
        "final_answer": "...",
    })
    passed, ev = _check_one_behavior(
        "Passes interests=['AI', 'machine learning'] or similar to rank AI/ML courses first.",
        signals,
    )
    assert passed is True, f"Expected PASS, got: {ev}"


def test_interests_arg_check_fails():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": "recommend_courses_for_requirement",
        "observation": "...",
        "steps": [{
            "thought": "...",
            "tool_called": "recommend_courses_for_requirement",
            "arguments": {"requirement_tag": "pool", "completed_courses": []},
            "observation": "...",
        }],
        "final_answer": "...",
    })
    passed, ev = _check_one_behavior(
        "Passes interests=['AI', 'machine learning'] or similar.",
        signals,
    )
    assert passed is False, f"Expected FAIL, got: {ev}"


def test_prerequisite_status_mention_passes():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": "recommend_courses_for_requirement",
        "observation": "...",
        "final_answer": "CSC311H1 requires prerequisite check. CSC384H1 is manual_review_needed.",
    })
    passed, ev = _check_one_behavior(
        "Notes prerequisite_status for the courses explicitly recommended in the final answer.",
        signals,
    )
    assert passed is True, f"Expected PASS, got: {ev}"


def test_prerequisite_status_mention_fails():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": "recommend_courses_for_requirement",
        "observation": "...",
        "final_answer": "Here are some AI courses: CSC311H1, CSC384H1.",
    })
    passed, ev = _check_one_behavior(
        "Notes prerequisite_status for the courses explicitly recommended in the final answer.",
        signals,
    )
    assert passed is False, f"Expected FAIL, got: {ev}"


# =========================================================================
# advising + credit implication behavior check
# =========================================================================


def test_advising_credit_check_passes():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": "check_exclusions",
        "observation": "...",
        "final_answer": "Check with academic advising about credit implications.",
    })
    passed, ev = _check_one_behavior(
        "Advises checking with academic advising about credit implications.",
        signals,
    )
    assert passed is True, f"Expected PASS, got: {ev}"


def test_advising_exclusion_check_passes():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": "check_exclusions",
        "observation": "...",
        "final_answer": "Ask an advisor how this exclusion affects program counting.",
    })
    passed, ev = _check_one_behavior(
        "Advises checking with academic advising about credit implications.",
        signals,
    )
    assert passed is True, f"Expected PASS, got: {ev}"


def test_advising_check_fails_generic_verification():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": "check_exclusions",
        "observation": "...",
        "final_answer": "Verify with official sources.",
    })
    passed, ev = _check_one_behavior(
        "Advises checking with academic advising about credit implications.",
        signals,
    )
    assert passed is False, f"Expected FAIL, got: {ev}"


def test_advising_check_fails_credit_only():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": "check_exclusions",
        "observation": "...",
        "final_answer": "This may affect credit.",
    })
    passed, ev = _check_one_behavior(
        "Advises checking with academic advising about credit implications.",
        signals,
    )
    assert passed is False, f"Expected FAIL, got: {ev}"


# =========================================================================
# clarification behavior checks
# =========================================================================


def test_completed_courses_clarification_passes():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": None,
        "observation": "Clarification required.",
        "final_answer": "Which courses have you completed so far?",
    })
    passed, ev = _check_one_behavior(
        "Asks specifically about completed courses, which are needed for eligibility.",
        signals,
    )
    assert passed is True, f"Expected PASS, got: {ev}"


def test_completed_courses_clarification_fails():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": None,
        "observation": "Clarification required.",
        "final_answer": "What is your target term?",
    })
    passed, ev = _check_one_behavior(
        "Asks specifically about completed courses, which are needed for eligibility.",
        signals,
    )
    assert passed is False, f"Expected FAIL, got: {ev}"


def test_no_tool_no_determination_passes():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": None,
        "observation": "Clarification required.",
        "steps": [],
        "final_answer": "Please tell me which courses you have completed so I can check eligibility.",
    })
    passed, ev = _check_one_behavior(
        "Does not call any tool or make an eligibility determination.",
        signals,
    )
    assert passed is True, f"Expected PASS, got: {ev}"


def test_no_tool_no_determination_fails_with_claim():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": "check_prerequisites",
        "observation": "...",
        "steps": [{"thought": "...", "tool_called": "check_prerequisites",
                    "arguments": {}, "observation": "eligible."}],
        "final_answer": "You are eligible to take CSC311H1.",
    })
    passed, ev = _check_one_behavior(
        "Does not call any tool or make an eligibility determination.",
        signals,
    )
    assert passed is False, f"Expected FAIL, got: {ev}"


def test_specific_clarification_passes():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": None,
        "observation": "Clarification required.",
        "final_answer": "Which courses have you completed so far?",
    })
    passed, ev = _check_one_behavior(
        "Makes the clarification question specific and actionable.",
        signals,
    )
    assert passed is True, f"Expected PASS, got: {ev}"


def test_specific_clarification_fails_not_a_question():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": None,
        "observation": "Clarification required.",
        "final_answer": "I need more information.",
    })
    passed, ev = _check_one_behavior(
        "Makes the clarification question specific and actionable.",
        signals,
    )
    assert passed is False, f"Expected FAIL, got: {ev}"


def test_no_course_advice_before_info_passes():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": None,
        "observation": "Clarification required.",
        "final_answer": "What courses have you completed? CSC311H1 requires prerequisites.",
    })
    passed, ev = _check_one_behavior(
        "Does not provide course advice before receiving the missing information.",
        signals,
    )
    assert passed is True, f"Expected PASS, got: {ev}"


def test_no_course_advice_before_info_fails_with_recommendation():
    from eval.run_evaluation import _check_one_behavior

    signals = extract_signals({
        "thought": "...",
        "tool_called": None,
        "observation": "Clarification required.",
        "final_answer": "I recommend taking CSC311H1. What courses have you completed?",
    })
    passed, ev = _check_one_behavior(
        "Does not provide course advice before receiving the missing information.",
        signals,
    )
    assert passed is False, f"Expected FAIL, got: {ev}"
