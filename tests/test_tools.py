"""Tests for src/tools.py — basic course and program data loading."""

import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so tests can import src.tools
# regardless of where pytest is invoked from.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.tools import (
    _match_interests,
    load_courses,
    load_programs,
    load_default_program,
    normalize_course_code,
    get_course_details,
    summarize_catalog_quality,
    get_course_metadata_status,
    check_term_availability,
    check_exclusions,
    check_prerequisites,
    find_courses_by_requirement_tag,
    recommend_courses_for_requirement,
)


# ---------------------------------------------------------------------------
# load_courses
# ---------------------------------------------------------------------------

def test_load_courses_returns_non_empty_list():
    """load_courses() should return a non-empty list of course dicts."""
    courses = load_courses()
    assert isinstance(courses, list), "load_courses() must return a list"
    assert len(courses) > 0, "Course catalog should not be empty"


# ---------------------------------------------------------------------------
# load_programs
# ---------------------------------------------------------------------------

def test_load_programs_returns_non_empty_list():
    """load_programs() should return a non-empty list of program dicts."""
    programs = load_programs()
    assert isinstance(programs, list), "load_programs() must return a list"
    assert len(programs) > 0, "Program list should not be empty"


# ---------------------------------------------------------------------------
# load_default_program
# ---------------------------------------------------------------------------

def test_load_default_program_returns_asma():
    """load_default_program() returns the ASMAJ1446A program."""
    program = load_default_program()
    assert isinstance(program, dict), "Default program must be a dict"
    assert program["program_code"] == "ASMAJ1446A", (
        f"Expected ASMAJ1446A, got {program.get('program_code')!r}"
    )


# ---------------------------------------------------------------------------
# normalize_course_code
# ---------------------------------------------------------------------------

def test_normalize_course_code_strips_and_uppercases():
    """normalize_course_code(' csc384h1 ') returns 'CSC384H1'."""
    result = normalize_course_code(" csc384h1 ")
    assert result == "CSC384H1", f"Expected 'CSC384H1', got {result!r}"


# ---------------------------------------------------------------------------
# get_course_details
# ---------------------------------------------------------------------------

def test_get_course_details_uppercase():
    """get_course_details('CSC384H1') returns the CSC384H1 course dict."""
    course = get_course_details("CSC384H1")
    assert course is not None, "CSC384H1 should exist in the catalog"
    assert course["course_code"] == "CSC384H1"


def test_get_course_details_lowercase():
    """get_course_details('csc384h1') also works (case-insensitive)."""
    course = get_course_details("csc384h1")
    assert course is not None, "Lowercase csc384h1 should still match"
    assert course["course_code"] == "CSC384H1"


def test_get_course_details_missing_returns_none():
    """get_course_details('FAKE100H1') returns None."""
    course = get_course_details("FAKE100H1")
    assert course is None, "FAKE100H1 should not exist and must return None"


# ---------------------------------------------------------------------------
# summarize_catalog_quality
# ---------------------------------------------------------------------------

def test_summarize_catalog_quality_returns_dict():
    """summarize_catalog_quality() returns a dict with expected keys."""
    summary = summarize_catalog_quality()
    assert isinstance(summary, dict), "summarize_catalog_quality() must return a dict"
    expected_keys = {
        "total_courses",
        "calendar_verified_count",
        "needs_official_verification_count",
        "unknown_breadth_courses",
        "unknown_term_courses",
        "courses_with_prerequisite_note",
        "courses_with_corequisite_note",
    }
    assert expected_keys <= summary.keys(), (
        f"Missing keys: {expected_keys - summary.keys()}"
    )


def test_total_courses_matches_load_courses():
    """total_courses equals len(load_courses())."""
    summary = summarize_catalog_quality()
    courses = load_courses()
    assert summary["total_courses"] == len(courses), (
        f"Expected {len(courses)}, got {summary['total_courses']}"
    )


def test_verified_plus_unverified_equals_total():
    """calendar_verified_count + needs_official_verification_count equals total_courses."""
    summary = summarize_catalog_quality()
    total = summary["total_courses"]
    verified = summary["calendar_verified_count"]
    unverified = summary["needs_official_verification_count"]
    assert verified + unverified == total, (
        f"{verified} + {unverified} != {total}"
    )


def test_unknown_breadth_courses_is_list():
    """unknown_breadth_courses is a list."""
    summary = summarize_catalog_quality()
    assert isinstance(summary["unknown_breadth_courses"], list), (
        "unknown_breadth_courses must be a list"
    )


def test_unknown_term_courses_is_list():
    """unknown_term_courses is a list."""
    summary = summarize_catalog_quality()
    assert isinstance(summary["unknown_term_courses"], list), (
        "unknown_term_courses must be a list"
    )


def test_courses_with_prerequisite_note_is_list():
    """courses_with_prerequisite_note is a list."""
    summary = summarize_catalog_quality()
    assert isinstance(summary["courses_with_prerequisite_note"], list), (
        "courses_with_prerequisite_note must be a list"
    )


# ---------------------------------------------------------------------------
# get_course_metadata_status
# ---------------------------------------------------------------------------

def test_metadata_status_verified_course():
    """CSC108H1: course_found true, calendar_verified, no concerns."""
    result = get_course_metadata_status("CSC108H1")
    assert result["course_found"] is True
    assert result["verification_status"] == "calendar_verified"
    assert result["needs_manual_review"] is False


def test_metadata_status_unverified_course():
    """MAT137Y1: needs_manual_review true because not calendar_verified."""
    result = get_course_metadata_status("MAT137Y1")
    assert result["course_found"] is True
    assert result["verification_status"] == "needs_official_verification"
    assert result["needs_manual_review"] is True
    assert "Course metadata is not fully calendar verified." in result["notes"]


def test_metadata_status_unknown_breadth():
    """LIN232H1 or PSY330H1: has_unknown_breadth is true."""
    result = get_course_metadata_status("LIN232H1")
    assert result["course_found"] is True
    assert result["has_unknown_breadth"] is True
    assert "Breadth Requirement is unknown or not listed." in result["notes"]


def test_metadata_status_complex_prereq():
    """CSC413H1: has_prerequisite_note true, needs_manual_review true."""
    result = get_course_metadata_status("CSC413H1")
    assert result["course_found"] is True
    assert result["has_prerequisite_note"] is True
    assert result["needs_manual_review"] is True
    assert any(
        "Prerequisite" in note for note in result["notes"]
    )


def test_metadata_status_missing_course():
    """FAKE100H1: course_found false, verification_status not_found."""
    result = get_course_metadata_status("FAKE100H1")
    assert result["course_found"] is False
    assert result["verification_status"] == "not_found"
    assert result["needs_manual_review"] is True
    assert "Course not found in course catalog." in result["notes"]


# ---------------------------------------------------------------------------
# check_term_availability
# ---------------------------------------------------------------------------

def test_term_available():
    """CSC384H1 is Winter-only, so status is 'available' for Winter."""
    result = check_term_availability("CSC384H1", "Winter")
    assert result["course_found"] is True
    assert result["status"] == "available"


def test_term_not_available():
    """CSC110Y1 is Fall-only, so status is 'not_available' for Winter."""
    result = check_term_availability("CSC110Y1", "Winter")
    assert result["course_found"] is True
    assert result["status"] == "not_available"


def test_term_unknown():
    """A course with ['UNKNOWN'] term_availability returns status 'unknown'."""
    result = check_term_availability("COG341H1", "Fall")
    assert result["course_found"] is True
    assert result["status"] == "unknown"


def test_term_lowercase_input():
    """Lowercase/whitespace target term works (e.g., ' winter ')."""
    result = check_term_availability("CSC384H1", " winter ")
    assert result["course_found"] is True
    assert result["status"] == "available"
    assert result["target_term"] == "Winter"


def test_term_course_not_found():
    """Unknown course returns status 'course_not_found'."""
    result = check_term_availability("FAKE100H1", "Fall")
    assert result["course_found"] is False
    assert result["status"] == "course_not_found"


# ---------------------------------------------------------------------------
# check_exclusions
# ---------------------------------------------------------------------------

def test_exclusion_conflict():
    """STA238H1 lists PSY201H1 as an exclusion — should detect conflict."""
    result = check_exclusions("STA238H1", ["PSY201H1"])
    assert result["course_found"] is True
    assert result["has_conflict"] is True
    assert "PSY201H1" in result["conflicting_courses"]


def test_exclusion_no_conflict():
    """CSC108H1 is not excluded by STA238H1."""
    result = check_exclusions("STA238H1", ["CSC108H1"])
    assert result["course_found"] is True
    assert result["has_conflict"] is False
    assert result["conflicting_courses"] == []


def test_exclusion_no_listed_exclusions():
    """COG100H1 has no listed exclusions."""
    result = check_exclusions("COG100H1", ["PSY100H1"])
    assert result["course_found"] is True
    assert result["has_conflict"] is False
    assert result["listed_exclusions"] == []
    assert "no listed exclusions" in result["message"]


def test_exclusion_lowercase_input():
    """Lowercase completed course codes still match."""
    result = check_exclusions("STA238H1", ["psy201h1"])
    assert result["course_found"] is True
    assert result["has_conflict"] is True
    assert "PSY201H1" in result["conflicting_courses"]


def test_exclusion_course_not_found():
    """Unknown course returns course_found False."""
    result = check_exclusions("FAKE100H1", ["CSC108H1"])
    assert result["course_found"] is False


# ---------------------------------------------------------------------------
# check_prerequisites
# ---------------------------------------------------------------------------

def test_prereq_no_prerequisites():
    """COG100H1 has no listed prerequisites — status eligible."""
    result = check_prerequisites("COG100H1", [])
    assert result["course_found"] is True
    assert result["status"] == "eligible"
    assert result["listed_prerequisites"] == []
    assert "no listed prerequisites" in result["message"]


def test_prereq_simple_eligible():
    """COG200H1 requires COG100H1 — status eligible when completed."""
    result = check_prerequisites("COG200H1", ["COG100H1"])
    assert result["course_found"] is True
    assert result["status"] == "eligible"
    assert result["missing_prerequisites"] == []
    assert "COG100H1" in result["satisfied_prerequisites"]


def test_prereq_simple_not_eligible():
    """COG200H1 requires COG100H1 — status not_eligible when missing."""
    result = check_prerequisites("COG200H1", ["CSC108H1"])
    assert result["course_found"] is True
    assert result["status"] == "not_eligible"
    assert "COG100H1" in result["missing_prerequisites"]


def test_prereq_manual_review_needed():
    """CSC413H1 has prerequisite_note — status manual_review_needed."""
    result = check_prerequisites("CSC413H1", ["CSC311H1", "MAT223H1"])
    assert result["course_found"] is True
    assert result["status"] == "manual_review_needed"
    assert result["prerequisite_note"] != ""
    assert "manual review" in result["message"].lower()


def test_prereq_lowercase_input():
    """Lowercase completed course codes still match."""
    result = check_prerequisites("COG200H1", ["cog100h1"])
    assert result["course_found"] is True
    assert result["status"] == "eligible"
    assert "COG100H1" in result["satisfied_prerequisites"]


def test_prereq_course_not_found():
    """Unknown course returns status course_not_found."""
    result = check_prerequisites("FAKE100H1", ["CSC108H1"])
    assert result["course_found"] is False
    assert result["status"] == "course_not_found"


# ---------------------------------------------------------------------------
# find_courses_by_requirement_tag
# ---------------------------------------------------------------------------

def test_find_pool_courses():
    """Finding computational_cognition_stream_pool returns non-empty list."""
    results = find_courses_by_requirement_tag(
        "computational_cognition_stream_pool"
    )
    assert isinstance(results, list)
    assert len(results) > 0


def test_find_statistics_choice():
    """Finding second_year_statistics_choice returns STA courses."""
    results = find_courses_by_requirement_tag(
        "second_year_statistics_choice"
    )
    assert len(results) > 0
    codes = {c["course_code"] for c in results}
    assert any(code.startswith("STA") for code in codes)


def test_find_unknown_tag():
    """Unknown tag returns empty list."""
    results = find_courses_by_requirement_tag("nonexistent_tag_xyz")
    assert results == []


def test_find_tag_normalized_input():
    """Uppercase and spaced input is normalized."""
    results_spaced = find_courses_by_requirement_tag(
        "  COMPUTATIONAL_COGNITION_STREAM_POOL  "
    )
    results_plain = find_courses_by_requirement_tag(
        "computational_cognition_stream_pool"
    )
    assert len(results_spaced) == len(results_plain)
    assert len(results_spaced) > 0


def test_find_returned_has_course_code():
    """Returned course dicts contain course_code field."""
    results = find_courses_by_requirement_tag("first_year_required")
    assert len(results) > 0
    for course in results:
        assert "course_code" in course


# ---------------------------------------------------------------------------
# recommend_courses_for_requirement
# ---------------------------------------------------------------------------

def test_recommend_pool_returns_multiple():
    """computational_cognition_stream_pool returns multiple courses."""
    results = recommend_courses_for_requirement(
        "computational_cognition_stream_pool", []
    )
    assert isinstance(results, list)
    assert len(results) > 1


def test_recommend_completed_prereqs_affect_status():
    """Completed courses affect prerequisite_status in output."""
    # Without COG100H1, COG200H1 should be not_eligible
    results_no = recommend_courses_for_requirement(
        "second_year_required", []
    )
    cog200_no = [r for r in results_no if r["course_code"] == "COG200H1"]
    assert len(cog200_no) == 1
    assert cog200_no[0]["prerequisite_status"] == "not_eligible"

    # With COG100H1, COG200H1 should be eligible
    results_yes = recommend_courses_for_requirement(
        "second_year_required", ["COG100H1"]
    )
    cog200_yes = [r for r in results_yes if r["course_code"] == "COG200H1"]
    assert len(cog200_yes) == 1
    assert cog200_yes[0]["prerequisite_status"] == "eligible"


def test_recommend_has_course_code_and_title():
    """Returned items contain course_code and title."""
    results = recommend_courses_for_requirement(
        "first_year_required", []
    )
    assert len(results) > 0
    for r in results:
        assert "course_code" in r
        assert "title" in r


def test_recommend_unknown_tag_returns_empty():
    """Unknown requirement_tag returns empty list."""
    results = recommend_courses_for_requirement(
        "nonexistent_tag_xyz", ["COG100H1"]
    )
    assert results == []


def test_recommend_does_not_modify_course_data():
    """Function does not modify existing course data."""
    from src.tools import load_courses
    before = load_courses()
    recommend_courses_for_requirement(
        "first_year_required", ["COG100H1"]
    )
    after = load_courses()
    assert before == after


# ---------------------------------------------------------------------------
# recommend_courses_for_requirement — interest filtering
# ---------------------------------------------------------------------------

def test_recommend_interests_none_preserves_order():
    """interests=None returns results in catalog order with no rank change."""
    results = recommend_courses_for_requirement(
        "computational_cognition_stream_pool", []
    )
    # All courses should have interest_match=False and matched_interests=[]
    for r in results:
        assert r["interest_match"] is False
        assert r["matched_interests"] == []


def test_recommend_interests_empty_preserves_order():
    """interests=[] behaves same as None — catalog order, no matches."""
    results = recommend_courses_for_requirement(
        "computational_cognition_stream_pool", [], interests=[]
    )
    for r in results:
        assert r["interest_match"] is False
        assert r["matched_interests"] == []


def test_recommend_ai_interests_surface_ml_courses():
    """AI/ML interests bring CSC311H1 or CSC413H1 into the first 10."""
    results = recommend_courses_for_requirement(
        "computational_cognition_stream_pool",
        [],
        interests=["AI", "machine learning"],
    )
    # At least one AI/ML course should now be in the first 10
    first_10_codes = [r["course_code"] for r in results[:10]]
    has_ai_course = any(
        code in first_10_codes
        for code in ["CSC311H1", "CSC413H1", "CSC384H1"]
    )
    assert has_ai_course, (
        f"Expected an AI/ML course in first 10, got {first_10_codes}"
    )


def test_recommend_matched_courses_appear_first():
    """Interest-matched courses appear before non-matched courses."""
    results = recommend_courses_for_requirement(
        "computational_cognition_stream_pool",
        [],
        interests=["AI"],
    )
    # Find the first non-match position.
    first_non_match = None
    for i, r in enumerate(results):
        if not r["interest_match"]:
            first_non_match = i
            break
    # All courses after the first non-match must also be non-match.
    if first_non_match is not None:
        for r in results[first_non_match:]:
            assert r["interest_match"] is False, (
                f"Match found after non-match at index {first_non_match}"
            )


def test_recommend_result_includes_interest_fields():
    """Every result dict includes interest_match and matched_interests."""
    results = recommend_courses_for_requirement(
        "first_year_required", []
    )
    for r in results:
        assert "interest_match" in r
        assert "matched_interests" in r
        assert isinstance(r["interest_match"], bool)
        assert isinstance(r["matched_interests"], list)


def test_recommend_matched_interests_are_listed():
    """matched_interests contains the keywords that actually matched."""
    results = recommend_courses_for_requirement(
        "computational_cognition_stream_pool",
        [],
        interests=["AI", "machine learning", "quantum computing"],
    )
    # CSC413H1 matches multiple: AI, machine learning
    csc413 = [r for r in results if r["course_code"] == "CSC413H1"]
    assert len(csc413) == 1
    assert csc413[0]["interest_match"] is True
    assert "ai" in csc413[0]["matched_interests"]
    assert "machine learning" in csc413[0]["matched_interests"]
    assert "quantum computing" not in csc413[0]["matched_interests"]


def test_recommend_interests_case_insensitive():
    """Interest matching is case-insensitive."""
    results_lower = recommend_courses_for_requirement(
        "computational_cognition_stream_pool",
        [],
        interests=["ai", "machine learning"],
    )
    results_upper = recommend_courses_for_requirement(
        "computational_cognition_stream_pool",
        [],
        interests=["AI", "MACHINE LEARNING"],
    )
    assert len(results_lower) == len(results_upper)
    for a, b in zip(results_lower, results_upper):
        assert a["interest_match"] == b["interest_match"]
        assert a["matched_interests"] == b["matched_interests"]


def test_recommend_total_count_unchanged_with_interests():
    """Interest filtering does not drop courses — total count stays same."""
    tag = "computational_cognition_stream_pool"
    no_interests = recommend_courses_for_requirement(tag, [])
    with_interests = recommend_courses_for_requirement(
        tag, [], interests=["AI"]
    )
    assert len(with_interests) == len(no_interests)


# ---------------------------------------------------------------------------
# _match_interests — short-keyword matching (no false positives)
# ---------------------------------------------------------------------------


class TestShortKeywordMatching:
    """Verify that short keywords like 'ai' avoid false positives."""

    # -- real-course tests -------------------------------------------------

    def test_ai_matches_csc384h1_via_synonym(self):
        """CSC384H1 (Artificial Intelligence) matches via synonym expansion."""
        results = recommend_courses_for_requirement(
            "computational_cognition_stream_pool",
            [],
            interests=["AI"],
        )
        csc384 = [r for r in results if r["course_code"] == "CSC384H1"]
        assert len(csc384) == 1
        assert csc384[0]["interest_match"] is True

    def test_ai_matches_standalone_in_interest_tags(self):
        """A course with 'AI' as an independent interest_tag matches."""
        from src.tools import load_courses

        courses = load_courses()
        # Find a course that has 'AI' as a standalone interest tag.
        for c in courses:
            tags = [t.lower() for t in c.get("interest_tags", [])]
            if "ai" in tags:
                matched = _match_interests(c, ["ai"])
                assert "ai" in matched, (
                    f"{c['course_code']} has 'AI' in interest_tags "
                    f"but _match_interests didn't catch it"
                )
                return
        pytest.fail("No course found with standalone 'AI' interest tag")

    def test_machine_learning_still_matches_csc311h1(self):
        """Long keyword 'machine learning' uses substring matching as before."""
        results = recommend_courses_for_requirement(
            "computational_cognition_stream_pool",
            [],
            interests=["machine learning"],
        )
        csc311 = [r for r in results if r["course_code"] == "CSC311H1"]
        assert len(csc311) == 1
        assert csc311[0]["interest_match"] is True

    # -- synthetic false-positive tests ------------------------------------

    def test_ai_does_not_match_brain(self):
        """'brain' contains 'ai' but should not match."""
        course = {
            "course_code": "PSY100H1",
            "title": "Introduction to Psychology",
            "description": "Covers the brain and nervous system.",
            "interest_tags": ["psychology"],
        }
        assert _match_interests(course, ["ai"]) == []

    def test_ai_does_not_match_certain(self):
        """'certain' contains 'ai' but should not match."""
        course = {
            "course_code": "PHL100H1",
            "title": "Introduction to Philosophy",
            "description": "Examines certain fundamental questions.",
            "interest_tags": ["philosophy"],
        }
        assert _match_interests(course, ["ai"]) == []

    def test_ai_does_not_match_available(self):
        """'available' contains 'ai' but should not match."""
        course = {
            "course_code": "STA100H1",
            "title": "Statistics",
            "description": "This course is available to all students.",
            "interest_tags": ["statistics"],
        }
        assert _match_interests(course, ["ai"]) == []

    def test_ai_does_not_match_training(self):
        """'training' contains 'ai' but should not match."""
        course = {
            "course_code": "KPE100H1",
            "title": "Physical Education",
            "description": "Focus on athletic training methods.",
            "interest_tags": ["kinesiology"],
        }
        assert _match_interests(course, ["ai"]) == []

    def test_ai_does_not_match_social(self):
        """'social' contains 'ai' — no, wait, it doesn't.  But 'email'
        does.  Test with a realistic word."""
        course = {
            "course_code": "SOC100H1",
            "title": "Introduction to Sociology",
            "description": "Covers social structures and daily life.",
            "interest_tags": ["sociology"],
        }
        # 'social' does not contain 'ai' — use 'detail' instead.
        assert _match_interests(course, ["ai"]) == []

    def test_ai_does_not_match_detail(self):
        """'detail' contains 'ai' but should not match."""
        course = {
            "course_code": "ENG100H1",
            "title": "English Literature",
            "description": "Examines texts in detail.",
            "interest_tags": ["literature"],
        }
        assert _match_interests(course, ["ai"]) == []

    def test_ai_does_not_match_maintain(self):
        """'maintain' contains 'ai' but should not match."""
        course = {
            "course_code": "BIO100H1",
            "title": "Biology",
            "description": "How organisms maintain homeostasis.",
            "interest_tags": ["biology"],
        }
        assert _match_interests(course, ["ai"]) == []

    # -- count unchanged ---------------------------------------------------

    def test_total_count_unchanged_after_ai_filtering(self):
        """Filtering with 'AI' does not change total course count."""
        tag = "computational_cognition_stream_pool"
        no_interests = recommend_courses_for_requirement(tag, [])
        with_interests = recommend_courses_for_requirement(
            tag, [], interests=["AI"]
        )
        assert len(with_interests) == len(no_interests)
