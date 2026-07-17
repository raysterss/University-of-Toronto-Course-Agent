"""Tool registry for the UofT Course Planning Agent.

This module provides a centralised registry of available tools, their
required arguments, and descriptions.  It separates tool metadata from
agent logic so that tools can be added or modified without changing the
agent implementation.
"""

from src.tools import (
    check_exclusions,
    check_prerequisites,
    check_term_availability,
    get_course_details,
    get_course_metadata_status,
    recommend_courses_for_requirement,
)

# ------------------------------------------------------------------
# registry — each entry maps tool metadata to a callable function
# ------------------------------------------------------------------
TOOL_REGISTRY = {
    "get_course_details": {
        "function": get_course_details,
        "required_args": ["course_code"],
        "description": (
            "Look up a course by its course code and return its "
            "catalog details."
        ),
    },
    "check_prerequisites": {
        "function": check_prerequisites,
        "required_args": ["course_code", "completed_courses"],
        "description": (
            "Check whether a student's completed courses satisfy a "
            "course's listed prerequisites, returning eligible, "
            "not_eligible, or manual_review_needed."
        ),
    },
    "check_exclusions": {
        "function": check_exclusions,
        "required_args": ["course_code", "completed_courses"],
        "description": (
            "Check whether any completed course conflicts with the "
            "target course's exclusions.  Use for exclusion "
            "questions, overlapping-credit questions, or whether a "
            "previously completed course conflicts with a target "
            "course."
        ),
    },
    "check_term_availability": {
        "function": check_term_availability,
        "required_args": ["course_code", "target_term"],
        "description": (
            "Check whether a course is available in a requested term "
            "such as Fall or Winter.  Returns available, "
            "not_available, unknown, or course_not_found."
        ),
    },
    "get_course_metadata_status": {
        "function": get_course_metadata_status,
        "required_args": ["course_code"],
        "description": (
            "Return verification and safety metadata for a course, "
            "including calendar verification status, UNKNOWN fields, "
            "and whether manual review is needed."
        ),
    },
    "recommend_courses_for_requirement": {
        "function": recommend_courses_for_requirement,
        "required_args": ["requirement_tag", "completed_courses"],
        "description": (
            "Return candidate courses for a program requirement tag "
            "with basic prerequisite eligibility checks.  Accepts an "
            "optional ``interests`` argument (list of strings) to "
            "rank matching courses first."
        ),
    },
}


def get_tool(name: str) -> dict | None:
    """Look up a tool by name in the registry.

    Args:
        name: The tool name (e.g., ``"check_prerequisites"``).

    Returns:
        The tool metadata dict, or ``None`` if the name is not
        registered.
    """
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[str]:
    """Return the names of all registered tools."""
    return list(TOOL_REGISTRY.keys())
