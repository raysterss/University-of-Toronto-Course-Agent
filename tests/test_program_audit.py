"""Tests for src/program_audit.py — Phase 1 core requirement evaluation."""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.program_audit import (
    _build_category_membership,
    _read_structured_rules,
    audit_core_requirements,
    audit_program_progress,
    build_course_allocations,
    build_course_index,
    build_course_classification_summaries,
    detect_exclusion_conflicts,
    evaluate_choice_group,
    evaluate_credit_pool,
    evaluate_required_course_group,
    evaluate_special_rules,
    load_program_by_code,
    normalize_completed_courses,
)


# =========================================================================
# build_course_index
# =========================================================================


def test_build_course_index_returns_dict():
    idx = build_course_index()
    assert isinstance(idx, dict)
    assert len(idx) == 95
    assert "COG100H1" in idx
    assert idx["COG100H1"]["credits"] == 0.5


# =========================================================================
# load_program_by_code
# =========================================================================


def test_load_program_known():
    prog = load_program_by_code("ASMAJ1446A")
    assert prog["program_name"].startswith("Cognitive Science")


def test_load_program_unknown_raises():
    with pytest.raises(ValueError, match="not found"):
        load_program_by_code("NONEXISTENT")


# =========================================================================
# normalize_completed_courses
# =========================================================================


def test_empty_completed():
    result = normalize_completed_courses([])
    assert result["normalized_courses"] == []
    assert result["duplicates_removed"] == []
    assert result["unknown_courses"] == []
    assert result["unverified_courses"] == []


def test_case_folding_and_stripping():
    result = normalize_completed_courses(["  cog100h1  ", "CSC108H1"])
    assert result["normalized_courses"] == ["COG100H1", "CSC108H1"]


def test_duplicate_removal():
    result = normalize_completed_courses(["COG100H1", "cog100h1", "COG100H1"])
    assert result["normalized_courses"] == ["COG100H1"]
    assert result["duplicates_removed"] == ["COG100H1", "COG100H1"]


def test_unknown_course_classification():
    result = normalize_completed_courses(["ZZZ999H1"])
    assert "ZZZ999H1" in result["unknown_courses"]


def test_mat137y1_unverified_not_unknown():
    """MAT137Y1 is in the catalog but not calendar_verified."""
    result = normalize_completed_courses(["MAT137Y1"])
    assert "MAT137Y1" not in result["unknown_courses"]
    assert "MAT137Y1" in result["unverified_courses"]


def test_known_course_not_unverified():
    """CSC108H1 is calendar_verified."""
    result = normalize_completed_courses(["CSC108H1"])
    assert "CSC108H1" not in result["unverified_courses"]


def test_input_not_mutated():
    original = ["  cog100h1  ", "CSC108H1"]
    normalize_completed_courses(original)
    assert original == ["  cog100h1  ", "CSC108H1"]


# =========================================================================
# evaluate_required_course_group
# =========================================================================


_FIRST_YEAR_COURSES = [
    {"course_code": "COG100H1", "credits": 0.5, "category": "Core"},
]

_GROUP_FIRST_YEAR = {"required_courses": _FIRST_YEAR_COURSES,
                     "description": "First Year required"}


def test_required_group_not_started():
    idx = build_course_index()
    result = evaluate_required_course_group(
        [], _GROUP_FIRST_YEAR, idx,
    )
    assert result["progress_status"] == "not_started"
    assert result["credits_completed"] == 0.0
    assert result["credits_required"] == 0.5
    assert result["completed_courses"] == []
    assert result["missing_courses"] == ["COG100H1"]


def test_required_group_completed():
    idx = build_course_index()
    result = evaluate_required_course_group(
        ["COG100H1"], _GROUP_FIRST_YEAR, idx,
    )
    assert result["progress_status"] == "completed"
    assert result["credits_completed"] == 0.5
    assert result["missing_courses"] == []


def test_required_group_with_unverified_course():
    """MAT137Y1 is unverified — review_status reflects that."""
    idx = build_course_index()
    group = {"required_courses": [
        {"course_code": "MAT137Y1", "credits": 1.0, "category": "Math"},
    ], "description": "Math"}
    result = evaluate_required_course_group(
        ["MAT137Y1"], group, idx,
    )
    assert result["progress_status"] == "completed"
    assert result["review_status"] == "needs_official_verification"


# =========================================================================
# evaluate_choice_group
# =========================================================================


def _get_cs_pathway_group() -> dict:
    prog = load_program_by_code("ASMAJ1446A")
    for cg in prog["completion_requirements"]["first_year"]["choice_groups"]:
        if cg["group_id"] == "first_year_intro_cs_pathway":
            return cg
    raise ValueError("CS pathway not found")


def _get_math_pathway_group() -> dict:
    prog = load_program_by_code("ASMAJ1446A")
    for cg in prog["completion_requirements"]["first_year"]["choice_groups"]:
        if cg["group_id"] == "first_year_math_pathway":
            return cg
    raise ValueError("Math pathway not found")


def _get_statistics_choice_group() -> dict:
    prog = load_program_by_code("ASMAJ1446A")
    for cg in prog["completion_requirements"]["second_year"]["choice_groups"]:
        if cg["group_id"] == "second_year_statistics_choice":
            return cg
    raise ValueError("Statistics choice not found")


def test_choice_one_completed_option():
    idx = build_course_index()
    result = evaluate_choice_group(
        ["CSC108H1", "CSC148H1"], _get_cs_pathway_group(), idx,
    )
    assert result["progress_status"] == "completed"
    assert len(result["completed_options"]) == 1
    assert result["completed_options"][0]["option_id"] == "cs_standard"


def test_choice_not_started():
    idx = build_course_index()
    result = evaluate_choice_group(
        [], _get_cs_pathway_group(), idx,
    )
    assert result["progress_status"] == "not_started"
    assert result["completed_options"] == []
    assert result["best_partial_option"] is None


def test_choice_partial_progress():
    """Only CSC108H1 — not enough for standard option (needs both)."""
    idx = build_course_index()
    result = evaluate_choice_group(
        ["CSC108H1"], _get_cs_pathway_group(), idx,
    )
    assert result["progress_status"] == "partially_completed"
    assert result["best_partial_option"] is not None
    assert result["best_partial_option"]["option_id"] == "cs_standard"


def test_choice_bundle_not_merged_across_options():
    """CSC108H1 from standard + CSC110Y1 from accelerated = NOT merged."""
    idx = build_course_index()
    result = evaluate_choice_group(
        ["CSC108H1", "CSC110Y1"], _get_cs_pathway_group(), idx,
    )
    # Neither option complete.
    assert result["completed_options"] == []
    # Best partial: both have 1 course, accelerated (1.0 cr) > standard (0.5 cr).
    assert result["best_partial_option"]["option_id"] == "cs_accelerated"


def test_choice_statistics_single_course_completes():
    """Any one statistics course completes the requirement."""
    idx = build_course_index()
    result = evaluate_choice_group(
        ["STA237H1"], _get_statistics_choice_group(), idx,
    )
    assert result["progress_status"] == "completed"
    assert len(result["completed_options"]) == 1


def test_choice_statistics_multiple_completed_options():
    """Multiple stats courses → found in completed_options."""
    idx = build_course_index()
    result = evaluate_choice_group(
        ["STA237H1", "STA247H1"], _get_statistics_choice_group(), idx,
    )
    assert result["progress_status"] == "completed"
    # Each course is a separate normalized option (e.g., stat_single_STA237H1).
    assert len(result["completed_options"]) >= 1


def test_choice_ambiguous_expression_manual_review():
    """Math pathway has ambiguous expression → review_status=manual_review."""
    idx = build_course_index()
    result = evaluate_choice_group(
        ["MAT135H1", "MAT136H1"], _get_math_pathway_group(), idx,
    )
    assert result["progress_status"] == "completed"
    assert result["review_status"] == "manual_review_needed"
    assert result["ambiguous_expression"] is True


def test_choice_unverified_course_preserved():
    """MAT137Y1 in math pathway → needs_official_verification warning."""
    idx = build_course_index()
    result = evaluate_choice_group(
        ["MAT137Y1"], _get_math_pathway_group(), idx,
    )
    # Math pathway is ambiguous → review stays manual_review_needed.
    # MAT137Y1 is also unverified → additional warning.
    assert "manual_review" in result["review_status"]
    assert any("MAT137Y1" in w for w in result["warnings"])


# =========================================================================
# audit_core_requirements
# =========================================================================


def test_audit_empty():
    result = audit_core_requirements([])
    assert result["audit_version"] == "1.0-phase1"
    assert result["program_code"] == "ASMAJ1446A"

    reqs = result["requirement_results"]
    # All should be not_started.
    for rid, r in reqs.items():
        assert r["progress_status"] == "not_started", (
            f"{rid} should be not_started but is {r['progress_status']}"
        )


def test_audit_first_year_complete():
    """COG100H1 + CS standard + math standard = completed first year."""
    result = audit_core_requirements([
        "COG100H1", "CSC108H1", "CSC148H1", "MAT135H1", "MAT136H1",
    ])
    reqs = result["requirement_results"]

    assert reqs["first_year_required"]["progress_status"] == "completed"
    assert reqs["first_year_intro_cs_pathway"]["progress_status"] == "completed"
    assert reqs["first_year_math_pathway"]["progress_status"] == "completed"


def test_audit_second_year_not_started():
    """With only first-year courses, second-year should be not_started."""
    result = audit_core_requirements([
        "COG100H1", "CSC108H1", "CSC148H1",
    ])
    reqs = result["requirement_results"]
    assert reqs["second_year_required"]["progress_status"] == "not_started"
    assert reqs["second_year_statistics_choice"]["progress_status"] == "not_started"


def test_audit_unknown_course_warning():
    result = audit_core_requirements(["ZZZ999H1"])
    assert any("ZZZ999H1" in w for w in result["warnings"])


def test_audit_mat137_warning():
    """MAT137Y1 is unverified — warning should appear."""
    result = audit_core_requirements(["MAT137Y1"])
    assert any("MAT137Y1" in w for w in result["warnings"])


def test_audit_internally_consistent_credits():
    """credits_completed equals sum of listed completed course credits."""
    result = audit_core_requirements([
        "COG100H1", "CSC108H1", "CSC148H1", "MAT135H1", "MAT136H1",
    ])
    reqs = result["requirement_results"]
    for rid, r in reqs.items():
        if r["type"] == "required_course_group":
            idx = build_course_index()
            expected = sum(
                idx[c]["credits"] for c in r["completed_courses"]
                if c in idx
            )
            assert abs(r["credits_completed"] - expected) < 0.001, (
                f"{rid}: credits_completed={r['credits_completed']} "
                f"!= sum={expected}"
            )
            assert r["credits_required"] > 0, (
                f"{rid}: credits_required should be > 0"
            )


def test_audit_unknown_program_code_raises():
    with pytest.raises(ValueError, match="not found"):
        audit_core_requirements([], program_code="BOGUS")


def test_audit_assumptions_present():
    result = audit_core_requirements([])
    assert len(result["assumptions"]) >= 2
    assert any("grade" in a.lower() for a in result["assumptions"])


def test_audit_limitations_present():
    result = audit_core_requirements([])
    assert len(result["limitations"]) >= 3


def test_audit_input_not_mutated():
    original = ["COG100H1", "CSC108H1"]
    audit_core_requirements(original)
    assert original == ["COG100H1", "CSC108H1"]


def test_audit_second_year_partially_completed():
    """COG200H1 done but PSY270H1 not → partially_completed."""
    result = audit_core_requirements([
        "COG100H1", "COG200H1",
    ])
    reqs = result["requirement_results"]
    assert reqs["second_year_required"]["progress_status"] == "partially_completed"
    assert "COG200H1" in reqs["second_year_required"]["completed_courses"]
    assert "PSY270H1" in reqs["second_year_required"]["missing_courses"]


def test_audit_multiple_choice_options_completed():
    """Both CS standard AND CS accelerated completed — both in results."""
    result = audit_core_requirements([
        "CSC108H1", "CSC148H1", "CSC110Y1", "CSC111H1",
    ])
    reqs = result["requirement_results"]
    cs = reqs["first_year_intro_cs_pathway"]
    assert cs["progress_status"] == "completed"
    assert len(cs["completed_options"]) == 2


def test_audit_capstone_not_started():
    result = audit_core_requirements(["COG100H1"])
    reqs = result["requirement_results"]
    assert reqs["fourth_year_capstone_choice"]["progress_status"] == "not_started"


# =========================================================================
# normalize_choice_options — credit-math normalization
# =========================================================================

from src.program_audit import normalize_choice_options  # noqa: E402


def _vopts(group):
    """Valid options from normalize_choice_options."""
    return normalize_choice_options(group)["valid_options"]


def test_normalize_cs_standard_is_bundle():
    opts = _vopts(_get_cs_pathway_group())
    cs_std = [o for o in opts if o["option_id"] == "cs_standard"]
    assert len(cs_std) == 1
    assert cs_std[0]["required_courses"] == ["CSC108H1", "CSC148H1"]


def test_normalize_cs_accelerated_is_bundle():
    opts = _vopts(_get_cs_pathway_group())
    cs_acc = [o for o in opts if o["option_id"] == "cs_accelerated"]
    assert len(cs_acc) == 1
    assert cs_acc[0]["required_courses"] == ["CSC110Y1", "CSC111H1"]


def test_normalize_statistics_explicit_individual_options():
    opts = _vopts(_get_statistics_choice_group())
    assert len(opts) == 8
    for o in opts:
        assert len(o["required_courses"]) == 1


def test_normalize_statistics_option_ids():
    opts = _vopts(_get_statistics_choice_group())
    ids = [o["option_id"] for o in opts]
    assert "stat_sta237" in ids
    assert "stat_psy201" in ids


def test_normalize_capstone_explicit_individual_options():
    prog = load_program_by_code("ASMAJ1446A")
    cap = prog["completion_requirements"]["fourth_year"]["choice_groups"][0]
    opts = _vopts(cap)
    assert len(opts) == 6
    for o in opts:
        assert len(o["required_courses"]) == 1


def test_normalize_capstone_option_ids():
    prog = load_program_by_code("ASMAJ1446A")
    cap = prog["completion_requirements"]["fourth_year"]["choice_groups"][0]
    opts = _vopts(cap)
    ids = [o["option_id"] for o in opts]
    assert "capstone_cog402" in ids
    assert "capstone_cog497" in ids  # 1.0 credit option


def test_normalize_math_single_course_options():
    opts = _vopts(_get_math_pathway_group())
    mat137 = [o for o in opts if o["option_id"] == "math_mat137"]
    assert len(mat137) == 1
    assert mat137[0]["required_courses"] == ["MAT137Y1"]


def test_option_length_never_determines_semantics():
    prog = load_program_by_code("ASMAJ1446A")
    cap = prog["completion_requirements"]["fourth_year"]["choice_groups"][0]
    opts = _vopts(cap)
    assert len(opts) == 6
    for o in opts:
        assert len(o["required_courses"]) == 1


def test_math_pathway_requires_both_mat135_mat136():
    """MAT135H1 alone does NOT complete the math_mat135_mat136 option."""
    idx = build_course_index()
    result = evaluate_choice_group(
        ["MAT135H1"], _get_math_pathway_group(), idx,
    )
    assert result["progress_status"] == "partially_completed"
    assert result["completed_options"] == []
    bp = result["best_partial_option"]
    assert bp is not None
    assert "MAT136H1" in bp["required_courses"]


def test_math_pathway_completed_with_both():
    """MAT135H1 + MAT136H1 completes the option."""
    idx = build_course_index()
    result = evaluate_choice_group(
        ["MAT135H1", "MAT136H1"], _get_math_pathway_group(), idx,
    )
    assert result["progress_status"] == "completed"
    completed_ids = [o["option_id"] for o in result["completed_options"]]
    assert "math_mat135_mat136" in completed_ids


def test_unsupported_completion_logic_manual_review():
    """Missing or unsupported completion_logic → manual_review_needed."""
    idx = build_course_index()
    bad_group = {
        "group_id": "test_group",
        "description": "Test",
        "completion_logic": "unknown_logic",
        "credits_needed": 1.0,
        "options": [{"option_id": "opt1", "courses": [
            {"course_code": "CSC108H1", "credits": 0.5}
        ]}],
    }
    result = evaluate_choice_group([], bad_group, idx)
    assert result["progress_status"] == "not_started"
    assert result["review_status"] == "manual_review_needed"


def test_missing_completion_logic_manual_review():
    """No completion_logic field → manual_review_needed."""
    idx = build_course_index()
    bad_group = {
        "group_id": "test_group",
        "description": "Test",
        "credits_needed": 1.0,
        "options": [],
    }
    result = evaluate_choice_group([], bad_group, idx)
    assert result["review_status"] == "manual_review_needed"


def test_missing_options_manual_review():
    """No options and unsupported logic → manual_review_needed."""
    idx = build_course_index()
    bad_group = {
        "group_id": "test_group",
        "description": "Test",
        "completion_logic": "complete_one_option",
        "credits_needed": 1.0,
        "options": [],
    }
    result = evaluate_choice_group([], bad_group, idx)
    assert result["review_status"] == "manual_review_needed"


def test_ambiguous_expression_still_preserved():
    """Math pathway ambiguity survives normalization."""
    idx = build_course_index()
    result = evaluate_choice_group(
        ["MAT135H1", "MAT136H1"], _get_math_pathway_group(), idx,
    )
    assert result["ambiguous_expression"] is True
    assert result["review_status"] == "manual_review_needed"


def test_unverified_course_still_preserved():
    """MAT137Y1 verification warning survives normalization."""
    idx = build_course_index()
    result = evaluate_choice_group(
        ["MAT137Y1"], _get_math_pathway_group(), idx,
    )
    assert any("MAT137Y1" in w for w in result["warnings"])


# =========================================================================
# Explicit structure — no heuristic inference
# =========================================================================


def test_statistics_completion_uses_explicit_option_id():
    """STA237H1 completes the stat_sta237 explicit option."""
    idx = build_course_index()
    result = evaluate_choice_group(
        ["STA237H1"], _get_statistics_choice_group(), idx,
    )
    assert result["progress_status"] == "completed"
    completed_ids = [o["option_id"] for o in result["completed_options"]]
    assert "stat_sta237" in completed_ids


def test_capstone_completion_uses_explicit_option_id():
    """COG402H1 completes the capstone_cog402 explicit option."""
    idx = build_course_index()
    prog = load_program_by_code("ASMAJ1446A")
    cap = prog["completion_requirements"]["fourth_year"]["choice_groups"][0]
    result = evaluate_choice_group(["COG402H1"], cap, idx)
    assert result["progress_status"] == "completed"
    completed_ids = [o["option_id"] for o in result["completed_options"]]
    assert "capstone_cog402" in completed_ids


def test_completion_does_not_depend_on_course_count():
    """A 2-course bundle and a 1-course option are both explicit."""
    idx = build_course_index()
    result2 = evaluate_choice_group(
        ["CSC108H1", "CSC148H1"], _get_cs_pathway_group(), idx,
    )
    assert result2["progress_status"] == "completed"
    result1 = evaluate_choice_group(
        ["MAT137Y1"], _get_math_pathway_group(), idx,
    )
    assert result1["progress_status"] == "completed"


def test_completion_does_not_depend_on_credit_value():
    """COG497Y1 (1.0cr) and COG402H1 (0.5cr) both work — explicit options."""
    idx = build_course_index()
    prog = load_program_by_code("ASMAJ1446A")
    cap = prog["completion_requirements"]["fourth_year"]["choice_groups"][0]
    result1 = evaluate_choice_group(["COG497Y1"], cap, idx)
    assert result1["progress_status"] == "completed"
    result05 = evaluate_choice_group(["COG402H1"], cap, idx)
    assert result05["progress_status"] == "completed"


def test_explicit_three_course_bundle():
    """A 3-course explicit option requires all 3 courses."""
    idx = build_course_index()
    group = {
        "group_id": "test_bundle",
        "completion_logic": "complete_one_option",
        "options": [{
            "option_id": "triple",
            "description": "Three required courses",
            "required_courses": ["CSC108H1", "CSC148H1", "CSC165H1"],
            "credits_required": 1.5,
        }],
    }
    result = evaluate_choice_group(
        ["CSC108H1", "CSC148H1", "CSC165H1"], group, idx,
    )
    assert result["progress_status"] == "completed"

    result_partial = evaluate_choice_group(
        ["CSC108H1", "CSC148H1"], group, idx,
    )
    assert result_partial["progress_status"] == "partially_completed"


def test_two_explicit_single_course_options():
    """Two single-course options — completing one is enough."""
    idx = build_course_index()
    group = {
        "group_id": "test_two_options",
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "opt_a", "description": "A",
             "required_courses": ["CSC108H1"], "credits_required": 0.5},
            {"option_id": "opt_b", "description": "B",
             "required_courses": ["CSC148H1"], "credits_required": 0.5},
        ],
    }
    result = evaluate_choice_group(["CSC108H1"], group, idx)
    assert result["progress_status"] == "completed"


def test_invalid_option_missing_required_courses():
    """Options without required_courses are skipped (not inferred)."""
    idx = build_course_index()
    group = {
        "group_id": "test_bad",
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "bad_opt", "description": "Missing required",
             "credits_required": 0.5},
        ],
    }
    result = evaluate_choice_group(["CSC108H1"], group, idx)
    assert result["progress_status"] == "not_started"
    assert result["review_status"] == "manual_review_needed"


def test_invalid_option_empty_required_courses():
    """Options with empty required_courses are skipped."""
    idx = build_course_index()
    group = {
        "group_id": "test_empty",
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "empty_opt", "description": "Empty",
             "required_courses": [], "credits_required": 0.5},
        ],
    }
    result = evaluate_choice_group(["CSC108H1"], group, idx)
    assert result["review_status"] == "manual_review_needed"


def test_invalid_option_zero_credits():
    """Options with credits_required <= 0 are skipped."""
    idx = build_course_index()
    group = {
        "group_id": "test_zero",
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "zero_opt", "description": "Zero credits",
             "required_courses": ["CSC108H1"], "credits_required": 0},
        ],
    }
    result = evaluate_choice_group(["CSC108H1"], group, idx)
    assert result["review_status"] == "manual_review_needed"


# =========================================================================
# Validation transparency — invalid options reported, not skipped silently
# =========================================================================


def test_one_valid_plus_one_invalid():
    """Valid option evaluated + invalid option reported."""
    idx = build_course_index()
    group = {
        "group_id": "test_mixed",
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "good", "required_courses": ["CSC108H1"],
             "credits_required": 0.5},
            {"option_id": "bad", "description": "bad",
             "credits_required": 0.5},
        ],
    }
    result = evaluate_choice_group(["CSC108H1"], group, idx)
    assert result["valid_option_count"] == 1
    assert result["invalid_option_count"] == 1
    assert len(result["invalid_options"]) == 1
    assert result["invalid_options"][0]["option_id"] == "bad"
    assert result["progress_status"] == "completed"
    assert result["review_status"] == "manual_review_needed"


def test_completed_valid_plus_invalid_manual_review():
    idx = build_course_index()
    group = {
        "group_id": "test_done_but_bad",
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "good", "required_courses": ["MAT137Y1"],
             "credits_required": 1.0},
            {"option_id": "bad", "required_courses": [],
             "credits_required": 0.5},
        ],
    }
    result = evaluate_choice_group(["MAT137Y1"], group, idx)
    assert result["progress_status"] == "completed"
    assert result["review_status"] == "manual_review_needed"
    assert result["invalid_option_count"] == 1


def test_all_options_invalid_not_started():
    idx = build_course_index()
    group = {
        "group_id": "test_all_bad",
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "bad1", "required_courses": [], "credits_required": 0.5},
            {"option_id": "bad2", "credits_required": 0.5},
        ],
    }
    result = evaluate_choice_group(["CSC108H1"], group, idx)
    assert result["progress_status"] == "not_started"
    assert result["review_status"] == "manual_review_needed"
    assert result["valid_option_count"] == 0
    assert result["invalid_option_count"] == 2


def test_missing_option_id_reported():
    result = normalize_choice_options({
        "completion_logic": "complete_one_option",
        "options": [
            {"required_courses": ["CSC108H1"], "credits_required": 0.5},
        ],
    })
    assert len(result["invalid_options"]) == 1
    assert "missing or blank" in result["invalid_options"][0]["errors"][0]


def test_blank_option_id_reported():
    result = normalize_choice_options({
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "  ", "required_courses": ["CSC108H1"],
             "credits_required": 0.5},
        ],
    })
    assert len(result["invalid_options"]) == 1


def test_required_courses_not_list_reported():
    result = normalize_choice_options({
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "bad", "required_courses": "CSC108H1",
             "credits_required": 0.5},
        ],
    })
    assert len(result["invalid_options"]) == 1
    assert any("must be a list" in e
               for e in result["invalid_options"][0]["errors"])


def test_blank_course_code_in_required_reported():
    result = normalize_choice_options({
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "bad", "required_courses": ["CSC108H1", "  "],
             "credits_required": 0.5},
        ],
    })
    assert len(result["invalid_options"]) == 1
    assert any("blank" in e for e in result["invalid_options"][0]["errors"])


def test_non_numeric_credits_reported():
    result = normalize_choice_options({
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "bad", "required_courses": ["CSC108H1"],
             "credits_required": "one"},
        ],
    })
    assert len(result["invalid_options"]) == 1
    assert any("numeric" in e for e in result["invalid_options"][0]["errors"])


def test_negative_credits_reported():
    result = normalize_choice_options({
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "bad", "required_courses": ["CSC108H1"],
             "credits_required": -0.5},
        ],
    })
    assert len(result["invalid_options"]) == 1
    assert any("positive" in e for e in result["invalid_options"][0]["errors"])


def test_valid_option_count_and_invalid_option_count():
    result = normalize_choice_options({
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "good1", "required_courses": ["CSC108H1"],
             "credits_required": 0.5},
            {"option_id": "good2", "required_courses": ["CSC148H1"],
             "credits_required": 0.5},
            {"option_id": "bad", "required_courses": [],
             "credits_required": 0.5},
        ],
    })
    assert len(result["valid_options"]) == 2
    assert len(result["invalid_options"]) == 1


def test_no_invalid_option_omitted_from_output():
    result = normalize_choice_options({
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "bad1", "required_courses": [], "credits_required": 0.5},
            {"option_id": "bad2", "required_courses": [], "credits_required": 0.5},
            {"option_id": "bad3", "credits_required": 0.5},
        ],
    })
    assert len(result["invalid_options"]) == 3


def test_valid_program_groups_have_zero_invalid():
    for getter in [_get_cs_pathway_group, _get_math_pathway_group,
                   _get_statistics_choice_group]:
        r = normalize_choice_options(getter())
        assert r["invalid_options"] == []
        assert len(r["valid_options"]) > 0


def test_validation_warnings_include_option_id():
    result = normalize_choice_options({
        "completion_logic": "complete_one_option",
        "options": [
            {"option_id": "bad_opt", "required_courses": [],
             "credits_required": 0.5},
        ],
    })
    assert len(result["warnings"]) >= 1
    assert "bad_opt" in result["warnings"][0]


# =========================================================================
# Phase 2A — pool credit counting
# =========================================================================


def _get_pool_definition() -> dict:
    prog = load_program_by_code("ASMAJ1446A")
    return prog["completion_requirements"]["approved_pools"][0]


def test_pool_empty_not_started():
    result = evaluate_credit_pool([], _get_pool_definition(), build_course_index())
    assert result["progress_status"] == "not_started"
    assert result["credits_completed"] == 0.0


def test_pool_course_outside_pool_not_counted():
    """Course not in pool list → not counted."""
    result = evaluate_credit_pool(
        ["COG100H1"], _get_pool_definition(), build_course_index(),
    )
    assert result["credits_completed"] == 0.0
    assert result["completed_courses"] == []


def test_pool_member_counted():
    """CSC165H1 IS in the stream pool."""
    result = evaluate_credit_pool(
        ["CSC165H1"], _get_pool_definition(), build_course_index(),
    )
    assert result["credits_completed"] == 0.5
    assert "CSC165H1" in result["completed_courses"]


def test_pool_duplicate_counts_once():
    result = evaluate_credit_pool(
        ["CSC165H1", "CSC165H1"], _get_pool_definition(), build_course_index(),
    )
    assert result["credits_completed"] == 0.5
    assert result["course_count"] == 1


def test_pool_credits_match_catalog():
    idx = build_course_index()
    result = evaluate_credit_pool(
        ["CSC165H1", "CSC207H1"], _get_pool_definition(), idx,
    )
    expected = idx["CSC165H1"]["credits"] + idx["CSC207H1"]["credits"]
    assert result["credits_completed"] == expected


def test_pool_counts_by_level_sum():
    result = evaluate_credit_pool(
        ["CSC165H1", "CSC207H1", "CSC311H1"],
        _get_pool_definition(), build_course_index(),
    )
    assert sum(result["counts_by_level"].values()) == result["credits_completed"]


def test_pool_counts_by_designator_sum():
    result = evaluate_credit_pool(
        ["CSC165H1", "CSC311H1", "COG260H1"],
        _get_pool_definition(), build_course_index(),
    )
    assert sum(result["counts_by_designator"].values()) == result["credits_completed"]


def test_pool_levels_from_catalog():
    """Levels come from catalog metadata, not code strings."""
    idx = build_course_index()
    # CSC165H1 is level 100, CSC311H1 is level 300.
    result = evaluate_credit_pool(
        ["CSC165H1", "CSC311H1"], _get_pool_definition(), idx,
    )
    assert result["counts_by_level"]["100"] == idx["CSC165H1"]["credits"]
    assert result["counts_by_level"]["300"] == idx["CSC311H1"]["credits"]


def test_pool_300_plus():
    """credits_at_300_plus only counts level >= 300."""
    result = evaluate_credit_pool(
        ["CSC165H1", "CSC311H1", "CSC384H1"],
        _get_pool_definition(), build_course_index(),
    )
    assert result["credits_at_300_plus"] == 1.0  # CSC311 (0.5) + CSC384 (0.5)


def test_pool_partially_completed():
    result = evaluate_credit_pool(
        ["CSC165H1"], _get_pool_definition(), build_course_index(),
    )
    assert result["progress_status"] == "partially_completed"
    assert result["credits_remaining"] > 0


def test_pool_completed():
    """Complete 2.5+ credits from pool."""
    result = evaluate_credit_pool(
        ["CSC311H1", "CSC384H1", "CSC413H1", "CSC420H1", "CSC401H1"],
        _get_pool_definition(), build_course_index(),
    )
    assert result["credits_completed"] >= 2.5
    assert result["progress_status"] == "completed"


def test_pool_unverified_course_warning():
    """An unverified pool course produces needs_official_verification."""
    idx = build_course_index()
    # Find an unverified course in the pool.
    pool_courses = _get_pool_definition()["courses"]
    unverified = None
    for c in pool_courses:
        if idx.get(c, {}).get("verification_status") != "calendar_verified":
            unverified = c
            break
    if unverified:
        result = evaluate_credit_pool([unverified], _get_pool_definition(), idx)
        assert result["review_status"] == "needs_official_verification"
        assert unverified in result["unverified_counted_courses"]


def test_pool_malformed_credits_needed():
    """Missing credits_needed → manual_review_needed."""
    bad_pool = {"pool_id": "bad", "courses": ["CSC108H1"]}
    result = evaluate_credit_pool(
        ["CSC108H1"], bad_pool, build_course_index(),
    )
    assert result["review_status"] == "manual_review_needed"
    assert result["credits_required"] is None


def test_pool_csc108_not_in_stream_pool():
    """CSC108H1 is NOT in the Computational Cognition Stream pool."""
    result = evaluate_credit_pool(
        ["CSC108H1"], _get_pool_definition(), build_course_index(),
    )
    assert result["credits_completed"] == 0.0


# =========================================================================
# Phase 2A — special rules
# =========================================================================


def test_300_level_minimum_not_met():
    pool_result = evaluate_credit_pool(
        ["CSC165H1"], _get_pool_definition(), build_course_index(),
    )
    rules = evaluate_special_rules(pool_result, _get_pool_definition())
    assert rules["rule_300_level_minimum"]["rule_status"] == "not_met"
    assert rules["rule_300_level_minimum"]["completed"] == 0.0


def test_300_level_minimum_met():
    pool_result = evaluate_credit_pool(
        ["CSC311H1", "CSC384H1"], _get_pool_definition(), build_course_index(),
    )
    rules = evaluate_special_rules(pool_result, _get_pool_definition())
    assert rules["rule_300_level_minimum"]["rule_status"] == "met"


def test_csc_minimum_not_met():
    pool_result = evaluate_credit_pool(
        ["COG260H1"], _get_pool_definition(), build_course_index(),
    )
    rules = evaluate_special_rules(pool_result, _get_pool_definition())
    assert rules["rule_csc_minimum"]["rule_status"] == "not_met"


def test_csc_minimum_met():
    pool_result = evaluate_credit_pool(
        ["CSC311H1", "CSC384H1"], _get_pool_definition(), build_course_index(),
    )
    rules = evaluate_special_rules(pool_result, _get_pool_definition())
    assert rules["rule_csc_minimum"]["rule_status"] == "met"


def test_csc_maximum_ok():
    pool_result = evaluate_credit_pool(
        ["CSC311H1"], _get_pool_definition(), build_course_index(),
    )
    rules = evaluate_special_rules(pool_result, _get_pool_definition())
    assert rules["rule_csc_maximum"]["rule_status"] == "ok"


def test_csc_maximum_exceeded():
    pool_result = evaluate_credit_pool(
        ["CSC311H1", "CSC384H1", "CSC413H1", "CSC420H1", "CSC401H1"],
        _get_pool_definition(), build_course_index(),
    )
    rules = evaluate_special_rules(pool_result, _get_pool_definition())
    assert rules["rule_csc_maximum"]["rule_status"] == "exceeded"


def test_designator_concentration_ok():
    pool_result = evaluate_credit_pool(
        ["CSC311H1", "COG260H1"], _get_pool_definition(), build_course_index(),
    )
    rules = evaluate_special_rules(pool_result, _get_pool_definition())
    assert rules["rule_designator_concentration"]["rule_status"] == "ok"
    assert rules["rule_designator_concentration"]["violations"] == []


def test_csc_excluded_from_designator_limit():
    """CSC is excluded from designator concentration limit."""
    pool_result = evaluate_credit_pool(
        ["CSC311H1", "CSC384H1", "CSC413H1", "CSC420H1"],
        _get_pool_definition(), build_course_index(),
    )
    rules = evaluate_special_rules(pool_result, _get_pool_definition())
    assert rules["rule_designator_concentration"]["rule_status"] == "ok"
    assert "CSC" in rules["rule_designator_concentration"]["excluded_designators"]


# =========================================================================
# Phase 2A — audit_program_progress integration
# =========================================================================


def test_audit_phase2a_includes_both_phases():
    result = audit_program_progress(["CSC165H1", "CSC311H1", "CSC384H1"])
    assert result["audit_version"] == "1.0-phase2b1"
    assert "requirement_results" in result
    assert "pool_results" in result
    assert "special_rule_results" in result
    assert "computational_cognition_stream_pool" in result["pool_results"]


def test_audit_phase2a_overall_in_progress():
    result = audit_program_progress(["COG100H1"])
    assert result["overall_status"] == "in_progress"


def test_audit_phase2a_overall_not_started():
    result = audit_program_progress([])
    assert result["overall_status"] == "not_started"


def test_audit_phase2a_input_not_mutated():
    original = ["CSC165H1", "CSC311H1"]
    audit_program_progress(original)
    assert original == ["CSC165H1", "CSC311H1"]


def test_audit_phase2a_internally_consistent():
    """Pool credits match catalog credits."""
    result = audit_program_progress(["CSC165H1", "CSC311H1", "CSC384H1"])
    pool = result["pool_results"]["computational_cognition_stream_pool"]
    idx = build_course_index()
    expected = sum(idx[c]["credits"] for c in pool["completed_courses"])
    assert abs(pool["credits_completed"] - expected) < 0.001
    assert pool["course_count"] == len(pool["completed_courses"])
    assert abs(sum(pool["counts_by_level"].values()) - pool["credits_completed"]) < 0.001


# =========================================================================
# Structured special rules — data-driven, no hard-coded constants
# =========================================================================


def _make_synthetic_reqs(**overrides) -> dict:
    """Build a synthetic structured_special_rules for testing."""
    base = {
        "minimum_300_level_credits": 1.0,
        "csc_credit_minimum": 1.0,
        "csc_credit_maximum": 2.0,
        "designator_credit_maximum": 1.5,
        "designator_exceptions": ["CSC"],
    }
    base.update(overrides)
    return {"structured_special_rules": base}


def _make_pool_result(**overrides) -> dict:
    """Build a minimal pool result for rule testing."""
    base = {
        "credits_at_300_plus": 0.5,
        "counts_by_designator": {"CSC": 1.0, "LIN": 1.0},
        "completed_courses": [],
        "credits_completed": 1.5,
        "course_count": 3,
        "counts_by_level": {},
        "unverified_counted_courses": [],
    }
    base.update(overrides)
    return base


def test_json_contains_structured_special_rules():
    prog = load_program_by_code("ASMAJ1446A")
    reqs = prog["completion_requirements"]
    assert "structured_special_rules" in reqs
    sr = reqs["structured_special_rules"]
    assert sr["minimum_300_level_credits"] == 1.0
    assert sr["csc_credit_minimum"] == 1.0
    assert sr["csc_credit_maximum"] == 2.0
    assert sr["designator_credit_maximum"] == 1.5
    assert sr["designator_exceptions"] == ["CSC"]


def test_original_prose_rules_preserved():
    prog = load_program_by_code("ASMAJ1446A")
    reqs = prog["completion_requirements"]
    assert isinstance(reqs["special_rules"], list)
    assert len(reqs["special_rules"]) == 5


def test_no_fallback_constants():
    """_read_structured_rules with empty dict → no values, all error."""
    result = _read_structured_rules({})
    assert result["values"] == {}
    assert len(result["errors"]) >= 1
    assert "_all" in result["errors"]


# --- Data-driven: changing values changes results ---


def test_changing_300_minimum_changes_rule():
    pool = _make_pool_result(credits_at_300_plus=1.0)
    rules1 = evaluate_special_rules(
        pool, {}, requirements=_make_synthetic_reqs(minimum_300_level_credits=1.0),
    )
    assert rules1["rule_300_level_minimum"]["rule_status"] == "met"

    rules2 = evaluate_special_rules(
        pool, {}, requirements=_make_synthetic_reqs(minimum_300_level_credits=1.5),
    )
    assert rules2["rule_300_level_minimum"]["rule_status"] == "not_met"


def test_changing_csc_minimum_changes_rule():
    pool = _make_pool_result(counts_by_designator={"CSC": 0.5})
    rules1 = evaluate_special_rules(
        pool, {}, requirements=_make_synthetic_reqs(csc_credit_minimum=0.5),
    )
    assert rules1["rule_csc_minimum"]["rule_status"] == "met"

    rules2 = evaluate_special_rules(
        pool, {}, requirements=_make_synthetic_reqs(csc_credit_minimum=1.0),
    )
    assert rules2["rule_csc_minimum"]["rule_status"] == "not_met"


def test_changing_csc_maximum_changes_limit():
    pool = _make_pool_result(counts_by_designator={"CSC": 1.5})
    rules1 = evaluate_special_rules(
        pool, {}, requirements=_make_synthetic_reqs(csc_credit_maximum=2.0),
    )
    assert rules1["rule_csc_maximum"]["rule_status"] == "ok"

    rules2 = evaluate_special_rules(
        pool, {}, requirements=_make_synthetic_reqs(csc_credit_maximum=1.0),
    )
    assert rules2["rule_csc_maximum"]["rule_status"] == "exceeded"


def test_changing_designator_maximum_changes_violation():
    pool = _make_pool_result(
        counts_by_designator={"CSC": 1.0, "LIN": 2.0},
    )
    rules1 = evaluate_special_rules(
        pool, {}, requirements=_make_synthetic_reqs(designator_credit_maximum=2.5),
    )
    assert rules1["rule_designator_concentration"]["violations"] == []

    rules2 = evaluate_special_rules(
        pool, {}, requirements=_make_synthetic_reqs(designator_credit_maximum=1.5),
    )
    assert len(rules2["rule_designator_concentration"]["violations"]) >= 1


def test_changing_exceptions_changes_exempt_designators():
    pool = _make_pool_result(
        counts_by_designator={"CSC": 2.0, "LIN": 2.0},
    )
    # CSC excluded → no violation for CSC.
    rules1 = evaluate_special_rules(
        pool, {},
        requirements=_make_synthetic_reqs(
            designator_credit_maximum=1.5, designator_exceptions=["CSC", "LIN"],
        ),
    )
    assert rules1["rule_designator_concentration"]["violations"] == []

    # CSC NOT excluded → violation.
    rules2 = evaluate_special_rules(
        pool, {},
        requirements=_make_synthetic_reqs(
            designator_credit_maximum=1.5, designator_exceptions=[],
        ),
    )
    assert len(rules2["rule_designator_concentration"]["violations"]) >= 2


# --- Validation: missing or malformed fields ---


def test_missing_individual_field_unknown_only_that_rule():
    """Missing minimum_300_level_credits → only that rule unknown."""
    reqs = _make_synthetic_reqs()
    del reqs["structured_special_rules"]["minimum_300_level_credits"]
    rules = evaluate_special_rules(_make_pool_result(), {}, requirements=reqs)
    assert rules["rule_300_level_minimum"]["rule_status"] == "unknown"
    assert rules["rule_csc_minimum"]["rule_status"] != "unknown"
    assert rules["rule_csc_maximum"]["rule_status"] != "unknown"


def test_malformed_numeric_field_manual_review():
    """Non-numeric csc_credit_maximum → manual_review on that rule."""
    reqs = _make_synthetic_reqs(csc_credit_maximum="two")
    rules = evaluate_special_rules(_make_pool_result(), {}, requirements=reqs)
    assert rules["rule_csc_maximum"]["rule_status"] == "unknown"
    assert rules["rule_csc_maximum"]["review_status"] == "manual_review_needed"


def test_csc_max_lower_than_min_invalid():
    """csc_max < csc_min → max becomes unknown."""
    reqs = _make_synthetic_reqs(csc_credit_minimum=2.0, csc_credit_maximum=1.0)
    rules = evaluate_special_rules(_make_pool_result(), {}, requirements=reqs)
    assert rules["rule_csc_maximum"]["rule_status"] == "unknown"
    assert "less than" in rules["rule_csc_maximum"]["warning"]


def test_invalid_designator_exceptions_rejected():
    """designator_exceptions with non-3-letter entries → error."""
    reqs = _make_synthetic_reqs(designator_exceptions=["CSC", "TOOLONG"])
    result = _read_structured_rules(reqs)
    assert "designator_exceptions" in result["errors"]


def test_missing_designator_exceptions_no_csc_assumption():
    """Missing designator_exceptions → all errors, no CSC assumed excluded."""
    reqs = _make_synthetic_reqs()
    del reqs["structured_special_rules"]["designator_exceptions"]
    # Without exceptions, CSC is not excluded → could count in violations.
    result = _read_structured_rules(reqs)
    assert "designator_exceptions" in result["errors"]
    assert "designator_exceptions" not in result["values"]


# --- Source metadata ---


def test_source_json_path_in_each_rule():
    pool = _make_pool_result()
    rules = evaluate_special_rules(
        pool, {}, requirements=_make_synthetic_reqs(),
    )
    for key in ["rule_300_level_minimum", "rule_csc_minimum",
                "rule_csc_maximum", "rule_designator_concentration"]:
        assert "source" in rules[key], f"Missing source in {key}"
        assert "json_path" in rules[key]["source"], f"Missing json_path in {key}"
        assert "structured_special_rules" in rules[key]["source"]["json_path"]


def test_source_value_matches_rule_value():
    pool = _make_pool_result()
    rules = evaluate_special_rules(
        pool, {}, requirements=_make_synthetic_reqs(minimum_300_level_credits=1.0),
    )
    r = rules["rule_300_level_minimum"]
    assert r["source"]["value"] == 1.0
    assert r["required"] == 1.0


def test_existing_phase2a_behavior_unchanged():
    """Real program data still produces correct rule results."""
    pool = _make_pool_result(credits_at_300_plus=1.0,
                             counts_by_designator={"CSC": 1.0})
    # Use real program data.
    prog = load_program_by_code("ASMAJ1446A")
    reqs = prog["completion_requirements"]
    rules = evaluate_special_rules(pool, {}, requirements=reqs)
    assert rules["rule_300_level_minimum"]["rule_status"] == "met"
    assert rules["rule_csc_minimum"]["rule_status"] == "met"
    assert rules["rule_csc_maximum"]["rule_status"] == "ok"
    assert rules["rule_designator_concentration"]["rule_status"] == "ok"


# =========================================================================
# Phase 2B1 — Exclusion conflicts, allocations, review status
# =========================================================================


def test_category_membership_coverage():
    mem = _build_category_membership("ASMAJ1446A", build_course_index())
    assert "COG100H1" in mem
    assert "first_year_required" in mem["COG100H1"]


def test_exclusion_no_conflict():
    idx = build_course_index()
    mem = _build_category_membership("ASMAJ1446A", idx)
    conflicts = detect_exclusion_conflicts(
        ["COG100H1", "CSC108H1"], idx, mem,
    )
    assert conflicts == []


def test_exclusion_conflict_detected():
    idx = build_course_index()
    mem = _build_category_membership("ASMAJ1446A", idx)
    conflicts = detect_exclusion_conflicts(
        ["CSC108H1", "CSC148H1"], idx, mem,
    )
    assert len(conflicts) == 1
    assert conflicts[0]["course_a"] == "CSC108H1"
    assert conflicts[0]["course_b"] == "CSC148H1"


def test_exclusion_no_self_conflict():
    idx = build_course_index()
    mem = _build_category_membership("ASMAJ1446A", idx)
    conflicts = detect_exclusion_conflicts(
        ["CSC108H1", "CSC108H1"], idx, mem,
    )
    assert conflicts == []


def test_allocation_unambiguous_single_category():
    idx = build_course_index()
    mem = _build_category_membership("ASMAJ1446A", idx)
    alloc = build_course_allocations(
        ["COG100H1"], idx, mem, [],
    )
    assert alloc["entries"][0]["allocation_status"] == "unambiguous"


def test_allocation_multi_category_manual_review():
    """CSC108H1 eligible for both CS pathway AND the pool? No — pool doesn't have CSC108H1.
    Use synthetic membership to test multi-category behavior."""
    idx = build_course_index()
    mem = {"CSC108H1": ["first_year_intro_cs_pathway", "test_pool"]}
    alloc = build_course_allocations(
        ["CSC108H1"], idx, mem, [],
    )
    e = alloc["entries"][0]
    assert e["allocation_status"] == "manual_review_needed"
    assert len(e["eligible_categories"]) > 1
    assert e["allocated_categories"] == []


def test_allocation_exclusion_conflict():
    idx = build_course_index()
    mem = _build_category_membership("ASMAJ1446A", idx)
    conflicts = detect_exclusion_conflicts(
        ["CSC108H1", "CSC148H1"], idx, mem,
    )
    alloc = build_course_allocations(
        ["CSC108H1", "CSC148H1"], idx, mem, conflicts,
    )
    for entry in alloc["entries"]:
        assert entry["allocation_status"] == "manual_review_needed"


def test_allocation_not_applicable():
    """Course in catalog with no program membership → not_applicable."""
    idx = build_course_index()
    # Use empty membership to simulate no-category course.
    alloc = build_course_allocations(["COG100H1"], idx, {}, [])
    assert alloc["entries"][0]["allocation_status"] == "not_applicable"


def test_allocation_unknown_excluded():
    idx = build_course_index()
    mem = _build_category_membership("ASMAJ1446A", idx)
    alloc = build_course_allocations(["ZZZ999H1"], idx, mem, [])
    assert alloc["entries"] == []


def test_unverified_not_in_unknown():
    result = audit_program_progress(["MAT137Y1"])
    assert any(u["course_code"] == "MAT137Y1"
               for u in result["unverified_courses"])
    assert not any(u["course_code"] == "MAT137Y1"
                   for u in result["unknown_courses"])


def test_unique_credits_count_once():
    result = audit_program_progress(["CSC165H1", "CSC165H1"])
    s = result["course_allocations"]["summary"]
    assert s["unique_known_completed_courses"] == 1


def test_program_counted_credits_null():
    result = audit_program_progress(["COG100H1"])
    assert result["course_allocations"]["summary"]["program_counted_credits"] is None


def test_overall_review_clear():
    result = audit_program_progress(["COG100H1"])
    assert result["overall_review_status"] == "clear"


def test_overall_review_unverified():
    """MAT137Y1 — math pathway has progress + ambiguous expression → manual_review."""
    result = audit_program_progress(["MAT137Y1"])
    # Math pathway has actual progress (MAT137Y1 counted) AND review is
    # manual_review_needed (ambiguous expression) → overall manual_review.
    assert result["overall_review_status"] == "manual_review_needed"


def test_overall_review_manual():
    result = audit_program_progress(["CSC108H1", "CSC148H1"])
    assert result["overall_review_status"] == "manual_review_needed"


def test_exclusion_does_not_remove_courses():
    result = audit_program_progress(["CSC108H1", "CSC148H1", "COG100H1"])
    codes = [e["course_code"] for e in result["course_allocations"]["entries"]]
    assert "CSC108H1" in codes
    assert "CSC148H1" in codes


def test_input_not_mutated_phase2b1():
    original = ["CSC108H1", "CSC148H1"]
    audit_program_progress(original)
    assert original == ["CSC108H1", "CSC148H1"]


def test_overlap_case_reported():
    """COG498H1 is in both pool and capstone → overlap."""
    result = audit_program_progress(["COG498H1"])
    overlaps = result["overlap_cases"]
    assert any(o["course_code"] == "COG498H1" for o in overlaps)


def test_allocation_summary_counts():
    result = audit_program_progress(["COG100H1", "CSC108H1", "CSC148H1"])
    s = result["course_allocations"]["summary"]
    assert s["unique_known_completed_courses"] == 3
    assert s["unique_catalog_credits_completed"] == 1.5


def test_audit_version_phase2b1():
    assert audit_program_progress([])["audit_version"] == "1.0-phase2b1"
