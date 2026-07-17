"""Tests for eval/run_llm_judge.py — prompt construction, parsing, verdicts.

All tests use fake judge responses.  No real API calls.
"""

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from eval.run_llm_judge import (  # noqa: E402
    BATCHES,
    JudgeVerdict,
    build_judge_messages,
    calculate_judge_verdict,
    format_batch_report,
    format_judge_report,
    get_batch_case_ids,
    parse_judge_response,
)


# =========================================================================
# Helpers
# =========================================================================


def _valid_judge_json(**overrides) -> str:
    """Return a valid judge JSON response string, with optional overrides."""
    data = {
        "scores": {
            "groundedness": {"score": 5, "applicable": True,
                             "reason": "All claims backed by observations."},
            "correctness": {"score": 5, "applicable": True,
                            "reason": "Correct interpretation of statuses."},
            "helpfulness": {"score": 4, "applicable": True,
                            "reason": "Good actionable advice."},
            "clarity": {"score": 5, "applicable": True,
                        "reason": "Well-structured answer."},
            "uncertainty_handling": {"score": 4, "applicable": True,
                                     "reason": "Warns about UNKNOWN terms."},
        },
        "strengths": ["Clear distinction between availability and eligibility."],
        "issues": [],
        "hallucination_risk": "none",
        "summary": "Strong answer grounded in observations.",
    }
    data.update(overrides)
    return json.dumps(data)


def _min_case() -> dict:
    return {
        "case_id": "test_case",
        "user_query": "Can I take CSC384H1?",
        "completed_courses": ["CSC148H1"],
        "expected_behaviors": ["Check prerequisites."],
    }


def _min_agent_result() -> dict:
    return {
        "steps": [
            {
                "thought": "Check prerequisites.",  # should be excluded
                "tool_called": "check_prerequisites",
                "arguments": {"course_code": "CSC384H1",
                              "completed_courses": ["CSC148H1"]},
                "observation": "Prerequisite check for CSC384H1: not_eligible.",
            },
        ],
        "final_answer": "You cannot take CSC384H1.",
        "stop_reason": "max_steps",
    }


# =========================================================================
# Prompt construction
# =========================================================================


class TestBuildJudgeMessages:
    """Verify judge message construction."""

    def test_includes_user_query(self):
        case = _min_case()
        msg = build_judge_messages(case, _min_agent_result())
        user_content = msg[1]["content"]
        assert "Can I take CSC384H1?" in user_content

    def test_includes_tool_steps(self):
        msg = build_judge_messages(_min_case(), _min_agent_result())
        user_content = msg[1]["content"]
        assert "check_prerequisites" in user_content
        assert "not_eligible" in user_content

    def test_includes_final_answer(self):
        msg = build_judge_messages(_min_case(), _min_agent_result())
        user_content = msg[1]["content"]
        assert "You cannot take CSC384H1." in user_content

    def test_includes_stop_reason(self):
        msg = build_judge_messages(_min_case(), _min_agent_result())
        user_content = msg[1]["content"]
        assert "max_steps" in user_content

    def test_excludes_thought_key(self):
        """Agent thought JSON key is NOT sent to judge."""
        msg = build_judge_messages(_min_case(), _min_agent_result())
        user_content = msg[1]["content"]
        assert '"thought"' not in user_content

    def test_includes_expected_behaviors(self):
        msg = build_judge_messages(_min_case(), _min_agent_result())
        user_content = msg[1]["content"]
        assert "Check prerequisites." in user_content

    def test_includes_untrusted_data_instruction(self):
        msg = build_judge_messages(_min_case(), _min_agent_result())
        user_content = msg[1]["content"]
        assert "CASE_DATA" in user_content
        assert "untrusted" in user_content.lower()

    def test_includes_rule_result_when_provided(self):
        from eval.run_evaluation import EvalResult, BehaviorResult
        br = BehaviorResult("Check prereqs", True, "ok")
        signals = {"tool_pass": True}
        rule = EvalResult(
            case_id="t", title="T", user_query="Q",
            tool_called="check_prerequisites", tool_pass=True,
            behavior_results=[br], signals=signals,
        )
        msg = build_judge_messages(_min_case(), _min_agent_result(), rule)
        user_content = msg[1]["content"]
        assert "rule_evaluation" in user_content
        assert "tool_pass" in user_content

    def test_agent_result_without_steps(self):
        """Agent result with no 'steps' key → empty steps in judge input."""
        result = {"final_answer": "No tools.", "stop_reason": "no_action"}
        msg = build_judge_messages(_min_case(), result)
        user_content = msg[1]["content"]
        assert '"tool_steps": []' in user_content


# =========================================================================
# parse_judge_response
# =========================================================================


class TestParseJudgeResponse:
    """Verify JSON parsing and validation."""

    def test_valid_pure_json(self):
        raw = _valid_judge_json()
        result = parse_judge_response(raw)
        assert result["scores"]["groundedness"]["score"] == 5
        assert result["hallucination_risk"] == "none"

    def test_fenced_json(self):
        raw = "```json\n" + _valid_judge_json() + "\n```"
        result = parse_judge_response(raw)
        assert result["scores"]["correctness"]["score"] == 5

    def test_fenced_no_language_tag(self):
        raw = "```\n" + _valid_judge_json() + "\n```"
        result = parse_judge_response(raw)
        assert result["summary"] == "Strong answer grounded in observations."

    def test_whitespace_surrounding(self):
        raw = "  \n" + _valid_judge_json() + "\n  "
        result = parse_judge_response(raw)
        assert result["hallucination_risk"] == "none"

    def test_malformed_json_raises(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            parse_judge_response("not json at all")

    def test_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            parse_judge_response("[1, 2, 3]")

    def test_missing_scores_raises(self):
        with pytest.raises(ValueError, match="missing 'scores'"):
            parse_judge_response('{"strengths": [], "summary": "x"}')

    def test_missing_dimension_raises(self):
        data = json.loads(_valid_judge_json())
        del data["scores"]["groundedness"]
        with pytest.raises(ValueError, match="groundedness"):
            parse_judge_response(json.dumps(data))

    def test_score_below_1_raises(self):
        raw = _valid_judge_json(
            scores={
                "groundedness": {"score": 0, "applicable": True, "reason": "x"},
                "correctness": {"score": 5, "applicable": True, "reason": "x"},
                "helpfulness": {"score": 5, "applicable": True, "reason": "x"},
                "clarity": {"score": 5, "applicable": True, "reason": "x"},
                "uncertainty_handling": {"score": 5, "applicable": True, "reason": "x"},
            },
        )
        with pytest.raises(ValueError, match="must be 1–5"):
            parse_judge_response(raw)

    def test_score_above_5_raises(self):
        raw = _valid_judge_json(
            scores={
                "groundedness": {"score": 6, "applicable": True, "reason": "x"},
                "correctness": {"score": 5, "applicable": True, "reason": "x"},
                "helpfulness": {"score": 5, "applicable": True, "reason": "x"},
                "clarity": {"score": 5, "applicable": True, "reason": "x"},
                "uncertainty_handling": {"score": 5, "applicable": True, "reason": "x"},
            },
        )
        with pytest.raises(ValueError, match="must be 1–5"):
            parse_judge_response(raw)

    def test_missing_reason_raises(self):
        data = json.loads(_valid_judge_json())
        del data["scores"]["groundedness"]["reason"]
        with pytest.raises(ValueError, match="missing 'reason'"):
            parse_judge_response(json.dumps(data))

    def test_invalid_severity_raises(self):
        raw = _valid_judge_json(issues=[
            {"severity": "catastrophic", "category": "hallucination",
             "description": "x"},
        ])
        with pytest.raises(ValueError, match="severity"):
            parse_judge_response(raw)

    def test_invalid_category_raises(self):
        raw = _valid_judge_json(issues=[
            {"severity": "major", "category": "fabrication",
             "description": "x"},
        ])
        with pytest.raises(ValueError, match="category"):
            parse_judge_response(raw)

    def test_invalid_hallucination_risk_raises(self):
        raw = _valid_judge_json(hallucination_risk="extreme")
        with pytest.raises(ValueError, match="hallucination_risk"):
            parse_judge_response(raw)

    def test_missing_strengths_raises(self):
        data = json.loads(_valid_judge_json())
        del data["strengths"]
        with pytest.raises(ValueError, match="missing 'strengths'"):
            parse_judge_response(json.dumps(data))

    def test_missing_summary_raises(self):
        data = json.loads(_valid_judge_json())
        del data["summary"]
        with pytest.raises(ValueError, match="missing 'summary'"):
            parse_judge_response(json.dumps(data))

    def test_extra_fields_accepted(self):
        """Unknown additional fields are silently accepted (forward compat)."""
        data = json.loads(_valid_judge_json())
        data["future_field"] = "some_value"
        data["scores"]["groundedness"]["extra"] = 42
        result = parse_judge_response(json.dumps(data))
        assert result["scores"]["groundedness"]["score"] == 5

    def test_applicable_not_bool_raises(self):
        raw = _valid_judge_json(
            scores={
                "groundedness": {"score": 5, "applicable": "yes", "reason": "x"},
                "correctness": {"score": 5, "applicable": True, "reason": "x"},
                "helpfulness": {"score": 5, "applicable": True, "reason": "x"},
                "clarity": {"score": 5, "applicable": True, "reason": "x"},
                "uncertainty_handling": {"score": 5, "applicable": True, "reason": "x"},
            },
        )
        with pytest.raises(ValueError, match="applicable"):
            parse_judge_response(raw)


# =========================================================================
# calculate_judge_verdict
# =========================================================================


class TestCalculateVerdict:
    """Verify deterministic verdict computation."""

    def _parse_and_judge(self, json_str: str) -> JudgeVerdict:
        return calculate_judge_verdict(parse_judge_response(json_str))

    def test_strong_scores_produce_pass(self):
        v = self._parse_and_judge(_valid_judge_json())
        assert v.verdict == "PASS"
        assert v.overall_score == 4.6  # (5+5+4+5+4)/5

    def test_groundedness_below_4_fails(self):
        raw = _valid_judge_json(
            scores={
                "groundedness": {"score": 3, "applicable": True, "reason": "x"},
                "correctness": {"score": 5, "applicable": True, "reason": "x"},
                "helpfulness": {"score": 5, "applicable": True, "reason": "x"},
                "clarity": {"score": 5, "applicable": True, "reason": "x"},
                "uncertainty_handling": {"score": 5, "applicable": True, "reason": "x"},
            },
        )
        v = self._parse_and_judge(raw)
        assert v.verdict == "FAIL"
        assert "groundedness=3" in v.fail_reasons[0]

    def test_correctness_below_4_fails(self):
        raw = _valid_judge_json(
            scores={
                "groundedness": {"score": 5, "applicable": True, "reason": "x"},
                "correctness": {"score": 2, "applicable": True, "reason": "x"},
                "helpfulness": {"score": 5, "applicable": True, "reason": "x"},
                "clarity": {"score": 5, "applicable": True, "reason": "x"},
                "uncertainty_handling": {"score": 5, "applicable": True, "reason": "x"},
            },
        )
        v = self._parse_and_judge(raw)
        assert v.verdict == "FAIL"
        assert "correctness=2" in v.fail_reasons[0]

    def test_critical_issue_fails(self):
        raw = _valid_judge_json(issues=[
            {"severity": "critical", "category": "hallucination",
             "description": "Fabricated course."},
        ])
        v = self._parse_and_judge(raw)
        assert v.verdict == "FAIL"
        assert "critical issue" in v.fail_reasons[0]

    def test_high_hallucination_risk_fails(self):
        raw = _valid_judge_json(hallucination_risk="high")
        v = self._parse_and_judge(raw)
        assert v.verdict == "FAIL"
        assert "hallucination_risk=high" in v.fail_reasons[0]

    def test_non_applicable_excluded_from_average(self):
        """Non-applicable dimensions don't reduce the overall score."""
        raw = _valid_judge_json(
            scores={
                "groundedness": {"score": 4, "applicable": True, "reason": "x"},
                "correctness": {"score": 4, "applicable": True, "reason": "x"},
                "helpfulness": {"score": 4, "applicable": True, "reason": "x"},
                "clarity": {"score": 4, "applicable": True, "reason": "x"},
                "uncertainty_handling": {"score": 1, "applicable": False,
                                          "reason": "No uncertain data."},
            },
        )
        v = self._parse_and_judge(raw)
        # Average of 4 dimensions (4+4+4+4)/4 = 4.0, not (4+4+4+4+1)/5 = 3.4
        assert v.overall_score == 4.0
        assert "uncertainty_handling" not in v.applicable_dimensions

    def test_all_non_applicable_produces_zero(self):
        raw = _valid_judge_json(
            scores={
                "groundedness": {"score": 1, "applicable": False, "reason": "x"},
                "correctness": {"score": 1, "applicable": False, "reason": "x"},
                "helpfulness": {"score": 1, "applicable": False, "reason": "x"},
                "clarity": {"score": 1, "applicable": False, "reason": "x"},
                "uncertainty_handling": {"score": 1, "applicable": False, "reason": "x"},
            },
        )
        v = self._parse_and_judge(raw)
        assert v.overall_score == 0.0
        assert v.verdict == "PASS"  # no fail conditions triggered (but weird state)


# =========================================================================
# format_judge_report
# =========================================================================


class TestFormatJudgeReport:
    """Verify the combined markdown report."""

    def _make_rule_result(self) -> object:
        from eval.run_evaluation import EvalResult, BehaviorResult
        br = BehaviorResult("Check prereqs", True, "ok")
        signals = {"tool_pass": True}
        return EvalResult(
            case_id="tc", title="T", user_query="Q",
            tool_called="check_prerequisites", tool_pass=True,
            behavior_results=[br], signals=signals,
        )

    def test_report_includes_case_id(self):
        result = parse_judge_response(_valid_judge_json())
        verdict = calculate_judge_verdict(result)
        report = format_judge_report(
            _min_case(), _min_agent_result(),
            self._make_rule_result(), result, verdict, "TestModel",
        )
        assert "test_case" in report

    def test_report_includes_user_query(self):
        result = parse_judge_response(_valid_judge_json())
        verdict = calculate_judge_verdict(result)
        report = format_judge_report(
            _min_case(), _min_agent_result(),
            self._make_rule_result(), result, verdict, "TestModel",
        )
        assert "Can I take CSC384H1?" in report

    def test_report_includes_final_answer(self):
        result = parse_judge_response(_valid_judge_json())
        verdict = calculate_judge_verdict(result)
        report = format_judge_report(
            _min_case(), _min_agent_result(),
            self._make_rule_result(), result, verdict, "TestModel",
        )
        assert "You cannot take CSC384H1." in report

    def test_report_includes_rule_result(self):
        result = parse_judge_response(_valid_judge_json())
        verdict = calculate_judge_verdict(result)
        report = format_judge_report(
            _min_case(), _min_agent_result(),
            self._make_rule_result(), result, verdict, "TestModel",
        )
        assert "Rule-Based Evaluation" in report

    def test_report_includes_score_table(self):
        result = parse_judge_response(_valid_judge_json())
        verdict = calculate_judge_verdict(result)
        report = format_judge_report(
            _min_case(), _min_agent_result(),
            self._make_rule_result(), result, verdict, "TestModel",
        )
        assert "| Dimension | Score |" in report
        assert "groundedness" in report
        assert "5/5" in report

    def test_report_handles_empty_issues(self):
        result = parse_judge_response(_valid_judge_json(issues=[]))
        verdict = calculate_judge_verdict(result)
        report = format_judge_report(
            _min_case(), _min_agent_result(),
            self._make_rule_result(), result, verdict, "TestModel",
        )
        assert "Issues" not in report  # no issues section when empty

    def test_report_handles_issues_with_evidence(self):
        result = parse_judge_response(_valid_judge_json(issues=[
            {
                "severity": "major",
                "category": "hallucination",
                "description": "Claimed available in Fall.",
                "evidence_from_answer": "offered in Fall",
                "evidence_from_observations": "term_availability: ['Winter']",
            },
        ]))
        verdict = calculate_judge_verdict(result)
        report = format_judge_report(
            _min_case(), _min_agent_result(),
            self._make_rule_result(), result, verdict, "TestModel",
        )
        assert "### Issues" in report
        assert "Claimed available in Fall" in report
        assert "offered in Fall" in report

    def test_report_includes_timestamp_and_model(self):
        result = parse_judge_response(_valid_judge_json())
        verdict = calculate_judge_verdict(result)
        report = format_judge_report(
            _min_case(), _min_agent_result(),
            self._make_rule_result(), result, verdict, "TestModel",
        )
        assert "TestModel" in report
        assert "2026" in report or "2025" in report

    def test_report_preserves_unicode(self):
        """Unicode in final_answer is preserved."""
        agent_result = _min_agent_result()
        agent_result["final_answer"] = "CSC384H1 — Introduction to Artificial Intelligence."
        result = parse_judge_response(_valid_judge_json())
        verdict = calculate_judge_verdict(result)
        report = format_judge_report(
            _min_case(), agent_result,
            self._make_rule_result(), result, verdict, "TestModel",
        )
        assert "—" in report
        assert "Artificial Intelligence" in report

    def test_report_handles_no_steps(self):
        agent_result = {"final_answer": "No tools needed.", "steps": []}
        result = parse_judge_response(_valid_judge_json())
        verdict = calculate_judge_verdict(result)
        report = format_judge_report(
            _min_case(), agent_result,
            self._make_rule_result(), result, verdict, "TestModel",
        )
        assert "(no tools called)" in report


# =========================================================================
# Batch definitions and get_batch_case_ids
# =========================================================================


class TestBatchDefinitions:
    """Verify batch definitions and get_batch_case_ids."""

    def test_core5_contains_five_cases(self):
        assert len(BATCHES["core5"]) == 5

    def test_core5_case_ids(self):
        ids = BATCHES["core5"]
        assert "multistep_csc384h1_winter" in ids
        assert "recommend_ai_ml" in ids
        assert "exclusion_csc108_csc148" in ids
        assert "verify_mat137_unverified" in ids
        assert "insufficient_no_completed" in ids

    def test_get_batch_case_ids_returns_copy(self):
        batch_ids = get_batch_case_ids("core5")
        batch_ids.append("extra")
        assert "extra" not in BATCHES["core5"]

    def test_unknown_batch_raises(self):
        import pytest as pt
        with pt.raises(ValueError, match="Unknown batch"):
            get_batch_case_ids("nonexistent_batch")


# =========================================================================
# Batch report formatting
# =========================================================================


class TestBatchReport:
    """Verify batch report structure and content."""

    def _make_batch_result(
        self, case_id: str, category: str = "test",
        rule: str = "PASS", judge: str = "PASS", score: float = 4.5,
        risk: str = "none", issues: list | None = None,
        tools: list | None = None,
        error: str | None = None,
        case_report: str = "",
    ) -> dict:
        return {
            "case_id": case_id,
            "category": category,
            "tools_called": tools or [],
            "rule_verdict": rule,
            "judge_verdict": judge,
            "overall_score": score,
            "hallucination_risk": risk,
            "issues": issues or [],
            "error": error,
            "case_report": case_report,
        }

    def test_batch_report_includes_all_case_ids(self):
        results = [
            self._make_batch_result(f"case_{i}")
            for i in range(5)
        ]
        report = format_batch_report("test", results, "TestModel")
        for i in range(5):
            assert f"case_{i}" in report

    def test_batch_report_includes_summary_table(self):
        results = [
            self._make_batch_result("c1", rule="PASS"),
            self._make_batch_result("c2", rule="FAIL", judge="FAIL"),
        ]
        report = format_batch_report("test", results, "TestModel")
        assert "## Summary" in report
        assert "## Case Summary Table" in report

    def test_batch_report_counts_pass_fail_error(self):
        results = [
            self._make_batch_result("c1", rule="PASS", judge="PASS"),
            self._make_batch_result("c2", rule="FAIL", judge="FAIL"),
            self._make_batch_result("c3", rule="ERROR", judge="ERROR"),
        ]
        report = format_batch_report("test", results, "TestModel")
        assert "| PASS | 1 | 1 |" in report
        assert "| FAIL | 1 | 1 |" in report
        assert "| ERROR | 1 | 1 |" in report

    def test_batch_report_shows_tools(self):
        results = [
            self._make_batch_result(
                "c1", tools=["check_prerequisites", "check_term_availability"],
            ),
        ]
        report = format_batch_report("test", results, "TestModel")
        assert "check_prerequisites" in report
        assert "check_term_availability" in report

    def test_batch_report_includes_per_case_details(self):
        results = [
            self._make_batch_result("c1", case_report="### c1 — PASS\n\nDetails here.\n"),
        ]
        report = format_batch_report("test", results, "TestModel")
        assert "## Per-Case Reports" in report
        assert "### c1 — PASS" in report

    def test_batch_error_case_shows_error(self):
        results = [
            self._make_batch_result(
                "c_err", rule="ERROR", judge="ERROR",
                error="Agent API call failed.",
            ),
        ]
        report = format_batch_report("test", results, "TestModel")
        assert "ERROR" in report
        assert "Agent API call failed" in report

    def test_clarification_case_zero_steps_accepted(self):
        """Zero-step clarification result is valid, not an error."""
        results = [
            self._make_batch_result(
                "clarify_case", tools=[], rule="PASS", judge="PASS",
                case_report="### clarify_case — PASS\n\nClarification asked.\n",
            ),
        ]
        report = format_batch_report("test", results, "TestModel")
        assert "(none)" in report
        assert "PASS" in report

    def test_batch_report_preserves_unicode(self):
        results = [
            self._make_batch_result(
                "c1",
                case_report="CSC384H1 — Introduction to Artificial Intelligence.\n",
            ),
        ]
        report = format_batch_report("test", results, "TestModel")
        assert "—" in report


# =========================================================================
# Core-5 expected tool mappings
# =========================================================================


class TestCore5ExpectedTools:
    """Verify the evaluation cases have correct expected tools."""

    def test_multistep_case_expected_tools(self):
        import json
        data = json.load(open("eval/evaluation_cases.json"))
        case = [c for c in data["cases"]
                if c["case_id"] == "multistep_csc384h1_winter"][0]
        assert case["expected_tools"] == [
            "check_prerequisites", "check_term_availability"
        ]
        assert case["expected_tool_sequence"] == [
            "check_prerequisites", "check_term_availability"
        ]

    def test_recommend_case_expected_tools(self):
        import json
        data = json.load(open("eval/evaluation_cases.json"))
        case = [c for c in data["cases"]
                if c["case_id"] == "recommend_ai_ml"][0]
        assert case["expected_tools"] == ["recommend_courses_for_requirement"]

    def test_exclusion_case_expected_tools(self):
        import json
        data = json.load(open("eval/evaluation_cases.json"))
        case = [c for c in data["cases"]
                if c["case_id"] == "exclusion_csc108_csc148"][0]
        assert case["expected_tools"] == ["check_exclusions"]

    def test_verification_case_expected_tools(self):
        import json
        data = json.load(open("eval/evaluation_cases.json"))
        case = [c for c in data["cases"]
                if c["case_id"] == "verify_mat137_unverified"][0]
        assert case["expected_tools"] == [
            "get_course_metadata_status",
            "recommend_courses_for_requirement",
        ]
        assert case["expected_tool_sequence"] == [
            "get_course_metadata_status",
            "recommend_courses_for_requirement",
        ]

    def test_insufficient_case_expected_tools(self):
        import json
        data = json.load(open("eval/evaluation_cases.json"))
        case = [c for c in data["cases"]
                if c["case_id"] == "insufficient_no_completed"][0]
        assert case["expected_tools"] == []
        behaviors = [b.lower() for b in case["expected_behaviors"]]
        assert any("clarify" in b for b in behaviors)