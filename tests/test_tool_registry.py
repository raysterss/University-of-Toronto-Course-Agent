"""Tests for src/tool_registry.py — centralised tool metadata."""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.tool_registry import TOOL_REGISTRY, get_tool, list_tools


# ---------------------------------------------------------------------------
# registry structure
# ---------------------------------------------------------------------------

def test_registry_contains_existing_tools():
    """Registry includes the four core tools."""
    names = list_tools()
    assert "get_course_details" in names
    assert "check_prerequisites" in names
    assert "check_term_availability" in names
    assert "recommend_courses_for_requirement" in names


def test_registry_entry_has_required_fields():
    """Each tool entry has function, required_args, and description."""
    for name, meta in TOOL_REGISTRY.items():
        assert "function" in meta, f"Missing 'function' in {name}"
        assert "required_args" in meta, f"Missing 'required_args' in {name}"
        assert "description" in meta, f"Missing 'description' in {name}"
        assert callable(meta["function"]), (
            f"'function' in {name} is not callable"
        )


# ---------------------------------------------------------------------------
# get_tool
# ---------------------------------------------------------------------------

def test_get_tool_known():
    """get_tool returns metadata for a registered tool."""
    meta = get_tool("check_prerequisites")
    assert meta is not None
    assert meta["required_args"] == ["course_code", "completed_courses"]


def test_get_tool_unknown():
    """get_tool returns None for an unregistered tool."""
    assert get_tool("nonexistent_tool") is None


# ---------------------------------------------------------------------------
# tool dispatch
# ---------------------------------------------------------------------------

def test_valid_action_dispatches_correctly():
    """A registered tool can be called dynamically via the registry."""
    meta = get_tool("get_course_details")
    result = meta["function"]("CSC108H1")
    assert result is not None
    assert result["course_code"] == "CSC108H1"


def test_unknown_tool_returns_clear_error():
    """An unregistered tool name is handled gracefully."""
    assert get_tool("imaginary_tool") is None


# ---------------------------------------------------------------------------
# missing arguments handling
# ---------------------------------------------------------------------------

def test_missing_arguments_detected():
    """Required args are validated — missing args can be detected."""
    meta = get_tool("check_prerequisites")
    required = meta["required_args"]
    assert "course_code" in required
    assert "completed_courses" in required
    assert len(required) == 2


def test_recommend_interests_not_required():
    """interests is NOT in recommend_courses_for_requirement required_args."""
    meta = get_tool("recommend_courses_for_requirement")
    assert "interests" not in meta["required_args"]
    assert meta["required_args"] == ["requirement_tag", "completed_courses"]


# ---------------------------------------------------------------------------
# check_term_availability registry entry
# ---------------------------------------------------------------------------


class TestCheckTermAvailabilityRegistry:
    """Verify check_term_availability is properly registered."""

    def test_registry_contains_check_term_availability(self):
        """check_term_availability is in the registry."""
        meta = get_tool("check_term_availability")
        assert meta is not None
        assert callable(meta["function"])

    def test_required_args_are_course_code_and_target_term(self):
        """Required args are exactly course_code and target_term."""
        meta = get_tool("check_term_availability")
        assert meta["required_args"] == ["course_code", "target_term"]

    def test_dynamic_dispatch_works(self):
        """Calling via registry returns correct result."""
        meta = get_tool("check_term_availability")
        result = meta["function"]("CSC384H1", "Winter")
        assert result["course_code"] == "CSC384H1"
        assert result["target_term"] == "Winter"
        assert result["status"] == "available"
        assert result["message"] is not None

    def test_course_not_found(self):
        """Unknown course returns course_not_found status."""
        meta = get_tool("check_term_availability")
        result = meta["function"]("ZZZ999H1", "Fall")
        assert result["course_found"] is False
        assert result["status"] == "course_not_found"


# ---------------------------------------------------------------------------
# parse_tool_action with check_term_availability
# ---------------------------------------------------------------------------


class TestParseCheckTermAvailability:
    """Verify parse_tool_action handles check_term_availability correctly."""

    def test_valid_check_term_availability_action_parses(self):
        """A valid check_term_availability action passes parsing."""
        from src.agent import parse_tool_action

        result = parse_tool_action(
            '{"action": "tool", '
            '"tool_name": "check_term_availability", '
            '"arguments": {"course_code": "CSC384H1", '
            '"target_term": "Winter"}}'
        )
        assert result["action"] == "tool"
        assert result["valid"] is True
        assert result["tool_name"] == "check_term_availability"
        assert result["arguments"]["course_code"] == "CSC384H1"
        assert result["arguments"]["target_term"] == "Winter"

    def test_missing_target_term_is_rejected(self):
        """Missing target_term returns valid=False."""
        from src.agent import parse_tool_action

        result = parse_tool_action(
            '{"action": "tool", '
            '"tool_name": "check_term_availability", '
            '"arguments": {"course_code": "CSC384H1"}}'
        )
        assert result["valid"] is False
        assert "target_term" in result["error"]

    def test_missing_course_code_is_rejected(self):
        """Missing course_code returns valid=False."""
        from src.agent import parse_tool_action

        result = parse_tool_action(
            '{"action": "tool", '
            '"tool_name": "check_term_availability", '
            '"arguments": {"target_term": "Fall"}}'
        )
        assert result["valid"] is False
        assert "course_code" in result["error"]

    def test_unknown_tool_still_rejected(self):
        """Unregistered tools are still rejected."""
        from src.agent import parse_tool_action

        result = parse_tool_action(
            '{"tool_name": "nonexistent_tool", '
            '"arguments": {"x": 1}}'
        )
        assert result["valid"] is False
        assert "Unknown tool" in result["error"]


# ---------------------------------------------------------------------------
# check_exclusions registry entry
# ---------------------------------------------------------------------------


class TestCheckExclusionsRegistry:
    """Verify check_exclusions is properly registered."""

    def test_registry_contains_check_exclusions(self):
        """check_exclusions is in the registry."""
        meta = get_tool("check_exclusions")
        assert meta is not None
        assert callable(meta["function"])

    def test_required_args(self):
        """Required args are course_code and completed_courses."""
        meta = get_tool("check_exclusions")
        assert meta["required_args"] == ["course_code", "completed_courses"]

    def test_dynamic_dispatch_works(self):
        """Calling via registry returns correct result."""
        meta = get_tool("check_exclusions")
        result = meta["function"]("CSC108H1", ["CSC148H1"])
        assert result["course_found"] is True
        assert "has_conflict" in result


# ---------------------------------------------------------------------------
# get_course_metadata_status registry entry
# ---------------------------------------------------------------------------


class TestGetCourseMetadataStatusRegistry:
    """Verify get_course_metadata_status is properly registered."""

    def test_registry_contains_get_course_metadata_status(self):
        """get_course_metadata_status is in the registry."""
        meta = get_tool("get_course_metadata_status")
        assert meta is not None
        assert callable(meta["function"])

    def test_required_args(self):
        """Required arg is course_code."""
        meta = get_tool("get_course_metadata_status")
        assert meta["required_args"] == ["course_code"]

    def test_dynamic_dispatch_works(self):
        """Calling via registry returns verification metadata."""
        meta = get_tool("get_course_metadata_status")
        result = meta["function"]("MAT137Y1")
        assert result["course_code"] == "MAT137Y1"
        assert result["course_found"] is True
        assert "verification_status" in result
        assert "needs_manual_review" in result


# ---------------------------------------------------------------------------
# parse_tool_action with new tools
# ---------------------------------------------------------------------------


class TestParseNewTools:
    """Verify parse_tool_action handles the new tools correctly."""

    def test_valid_check_exclusions_action_parses(self):
        from src.agent import parse_tool_action

        result = parse_tool_action(
            '{"action": "tool", '
            '"tool_name": "check_exclusions", '
            '"arguments": {"course_code": "CSC108H1", '
            '"completed_courses": ["CSC148H1"]}}'
        )
        assert result["valid"] is True
        assert result["tool_name"] == "check_exclusions"

    def test_check_exclusions_missing_completed_courses_rejected(self):
        from src.agent import parse_tool_action

        result = parse_tool_action(
            '{"tool_name": "check_exclusions", '
            '"arguments": {"course_code": "CSC108H1"}}'
        )
        assert result["valid"] is False
        assert "completed_courses" in result["error"]

    def test_valid_get_course_metadata_status_action_parses(self):
        from src.agent import parse_tool_action

        result = parse_tool_action(
            '{"action": "tool", '
            '"tool_name": "get_course_metadata_status", '
            '"arguments": {"course_code": "MAT137Y1"}}'
        )
        assert result["valid"] is True
        assert result["tool_name"] == "get_course_metadata_status"

    def test_get_course_metadata_status_missing_course_code_rejected(self):
        from src.agent import parse_tool_action

        result = parse_tool_action(
            '{"tool_name": "get_course_metadata_status", '
            '"arguments": {}}'
        )
        assert result["valid"] is False
        assert "course_code" in result["error"]
