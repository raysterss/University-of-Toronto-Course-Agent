"""Course and program data tools for the UofT Course Planning Agent.

This module provides low-level data loading and lookup functions.
All course and program data is read from the data/ directory.
"""

import json
import re
from pathlib import Path

# Project root is the parent directory of src/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_courses() -> list[dict]:
    """Load the course catalog from data/mock_courses.json.

    Returns:
        A list of course dicts from the "courses" key.

    Raises:
        FileNotFoundError: If the data file does not exist.
        json.JSONDecodeError: If the data file is malformed JSON.
        KeyError: If the "courses" key is missing from the JSON.
    """
    path = _PROJECT_ROOT / "data" / "mock_courses.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if "courses" not in data:
        raise KeyError(
            f"mock_courses.json is missing the 'courses' key. "
            f"Found keys: {list(data.keys())}"
        )

    return data["courses"]


def load_programs() -> list[dict]:
    """Load program data from data/mock_programs.json.

    Returns:
        A list of program dicts from the "programs" key.

    Raises:
        FileNotFoundError: If the data file does not exist.
        json.JSONDecodeError: If the data file is malformed JSON.
        KeyError: If the "programs" key is missing from the JSON.
    """
    path = _PROJECT_ROOT / "data" / "mock_programs.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if "programs" not in data:
        raise KeyError(
            f"mock_programs.json is missing the 'programs' key. "
            f"Found keys: {list(data.keys())}"
        )

    return data["programs"]


def load_default_program() -> dict:
    """Load the default program (ASMAJ1446A).

    Returns:
        The program dict for program_code "ASMAJ1446A".

    Raises:
        ValueError: If no program with program_code "ASMAJ1446A" is found.
    """
    programs = load_programs()
    default_code = "ASMAJ1446A"

    for program in programs:
        if program.get("program_code") == default_code:
            return program

    available = [p.get("program_code", "?") for p in programs]
    raise ValueError(
        f"Default program {default_code!r} not found. "
        f"Available programs: {available}"
    )


def normalize_course_code(course_code: str) -> str:
    """Normalize a course code for consistent lookup.

    Strips whitespace and converts to uppercase.

    Args:
        course_code: A raw course code string (e.g., " csc384h1 ").

    Returns:
        The normalized course code (e.g., "CSC384H1").

    Examples:
        >>> normalize_course_code(" csc384h1 ")
        'CSC384H1'
        >>> normalize_course_code("CSC384H1")
        'CSC384H1'
    """
    return course_code.strip().upper()


def summarize_catalog_quality() -> dict:
    """Produce a developer-facing summary of catalog data quality.

    Returns a dictionary with counts of verified vs unverified courses,
    and lists of courses missing key metadata.

    Returns:
        dict with keys:
            - total_courses (int)
            - calendar_verified_count (int)
            - needs_official_verification_count (int)
            - unknown_breadth_courses (list[str])
            - unknown_term_courses (list[str])
            - courses_with_prerequisite_note (list[str])
            - courses_with_corequisite_note (list[str])
    """
    courses = load_courses()

    total = len(courses)
    verified = 0
    unverified = 0
    unknown_breadth = []
    unknown_term = []
    has_prereq_note = []
    has_coreq_note = []

    for course in courses:
        status = course.get("verification_status", "")
        if status == "calendar_verified":
            verified += 1
        elif status == "needs_official_verification":
            unverified += 1

        if course.get("breadth_code") == "UNKNOWN":
            unknown_breadth.append(course["course_code"])

        if "UNKNOWN" in course.get("term_availability", []):
            unknown_term.append(course["course_code"])

        prereq_note = course.get("prerequisite_note", "")
        if prereq_note:
            has_prereq_note.append(course["course_code"])

        coreq_note = course.get("corequisite_note", "")
        if coreq_note:
            has_coreq_note.append(course["course_code"])

    return {
        "total_courses": total,
        "calendar_verified_count": verified,
        "needs_official_verification_count": unverified,
        "unknown_breadth_courses": unknown_breadth,
        "unknown_term_courses": unknown_term,
        "courses_with_prerequisite_note": has_prereq_note,
        "courses_with_corequisite_note": has_coreq_note,
    }


def get_course_details(course_code: str) -> dict | None:
    """Look up a course by its course code.

    Matching is case-insensitive. The course code is normalized before lookup.

    Args:
        course_code: The course code to look up (e.g., "CSC384H1" or "csc384h1").

    Returns:
        The course dict if found, or None if not found.

    Examples:
        >>> get_course_details("CSC384H1")  # Returns the CSC384H1 course dict
        >>> get_course_details("csc384h1")  # Same result (case-insensitive)
        >>> get_course_details("FAKE100H1")  # Returns None
    """
    courses = load_courses()
    normalized = normalize_course_code(course_code)

    for course in courses:
        if normalize_course_code(course["course_code"]) == normalized:
            return course

    return None


def get_course_metadata_status(course_code: str) -> dict:
    """Return a structured metadata quality summary for a single course.

    Args:
        course_code: The course code to check (e.g., "CSC384H1").

    Returns:
        A dict with keys:
            - course_code (str): The normalized course code.
            - course_found (bool): Whether the course exists in the catalog.
            - verification_status (str): The course's verification status, or
              "not_found" if the course is not in the catalog.
            - has_unknown_breadth (bool)
            - has_unknown_term (bool)
            - has_prerequisite_note (bool)
            - has_corequisite_note (bool)
            - needs_manual_review (bool): True if any metadata concern exists
              that prevents automatic eligibility determination.
            - notes (list[str]): Human-readable explanations for each concern.
    """
    normalized = normalize_course_code(course_code)
    course = get_course_details(course_code)

    if course is None:
        return {
            "course_code": normalized,
            "course_found": False,
            "verification_status": "not_found",
            "has_unknown_breadth": False,
            "has_unknown_term": False,
            "has_prerequisite_note": False,
            "has_corequisite_note": False,
            "needs_manual_review": True,
            "notes": ["Course not found in course catalog."],
        }

    verification_status = course.get("verification_status", "unknown")
    has_unknown_breadth = course.get("breadth_code") == "UNKNOWN"
    has_unknown_term = "UNKNOWN" in course.get("term_availability", [])
    has_prerequisite_note = bool(course.get("prerequisite_note"))
    has_corequisite_note = bool(course.get("corequisite_note"))

    notes = []
    if verification_status != "calendar_verified":
        notes.append("Course metadata is not fully calendar verified.")
    if has_unknown_breadth:
        notes.append("Breadth Requirement is unknown or not listed.")
    if has_unknown_term:
        notes.append("Term availability is unknown.")
    if has_prerequisite_note:
        notes.append(
            "Prerequisite information contains complex conditions or notes."
        )
    if has_corequisite_note:
        notes.append(
            "Corequisite information contains complex conditions or notes."
        )

    needs_manual_review = (
        verification_status != "calendar_verified"
        or has_unknown_breadth
        or has_prerequisite_note
        or has_corequisite_note
    )

    return {
        "course_code": normalized,
        "course_found": True,
        "verification_status": verification_status,
        "has_unknown_breadth": has_unknown_breadth,
        "has_unknown_term": has_unknown_term,
        "has_prerequisite_note": has_prerequisite_note,
        "has_corequisite_note": has_corequisite_note,
        "needs_manual_review": needs_manual_review,
        "notes": notes,
    }


def check_term_availability(course_code: str, target_term: str) -> dict:
    """Check whether a course is available in a given target term.

    Args:
        course_code: The course code to check (e.g., "CSC384H1").
        target_term: The target term (e.g., "Fall", "Winter", "Summer").

    Returns:
        A dict with keys:
            - course_code (str): The normalized course code.
            - course_found (bool): Whether the course exists in the catalog.
            - target_term (str): The normalized target term.
            - status (str): One of "available", "not_available", "unknown",
              or "course_not_found".
            - term_availability (list[str]): The course's listed terms.
            - message (str): A human-readable explanation.
    """
    normalized_code = normalize_course_code(course_code)
    normalized_term = target_term.strip().capitalize()
    course = get_course_details(course_code)

    if course is None:
        return {
            "course_code": normalized_code,
            "course_found": False,
            "target_term": normalized_term,
            "status": "course_not_found",
            "term_availability": [],
            "message": "Course not found in course catalog.",
        }

    term_availability = course.get("term_availability", [])

    if "UNKNOWN" in term_availability:
        return {
            "course_code": normalized_code,
            "course_found": True,
            "target_term": normalized_term,
            "status": "unknown",
            "term_availability": term_availability,
            "message": (
                f"Term availability for {normalized_code} is unknown "
                f"and should be verified with the official timetable."
            ),
        }

    if normalized_term in term_availability:
        return {
            "course_code": normalized_code,
            "course_found": True,
            "target_term": normalized_term,
            "status": "available",
            "term_availability": term_availability,
            "message": (
                f"{normalized_code} is listed as available in "
                f"{normalized_term}."
            ),
        }

    return {
        "course_code": normalized_code,
        "course_found": True,
        "target_term": normalized_term,
        "status": "not_available",
        "term_availability": term_availability,
        "message": (
            f"{normalized_code} is not listed as available in "
            f"{normalized_term}."
        ),
    }


def check_exclusions(
    course_code: str, completed_courses: list[str]
) -> dict:
    """Check whether any completed courses conflict with a course's exclusions.

    Args:
        course_code: The course code to check (e.g., "STA238H1").
        completed_courses: A list of course codes the student has completed.

    Returns:
        A dict with keys:
            - course_code (str): The normalized course code.
            - course_found (bool): Whether the course exists in the catalog.
            - has_conflict (bool): True if any completed course is listed
              as an exclusion.
            - conflicting_courses (list[str]): Normalized course codes
              that appear in both completed_courses and exclusions.
            - listed_exclusions (list[str]): The course's exclusion list.
            - message (str): A human-readable explanation.
    """
    normalized_code = normalize_course_code(course_code)
    normalized_completed = [
        normalize_course_code(c) for c in completed_courses
    ]
    course = get_course_details(course_code)

    if course is None:
        return {
            "course_code": normalized_code,
            "course_found": False,
            "has_conflict": False,
            "conflicting_courses": [],
            "listed_exclusions": [],
            "message": "Course not found in course catalog.",
        }

    exclusions = course.get("exclusions", [])
    normalized_exclusions = [
        normalize_course_code(e) for e in exclusions
    ]
    conflicting = [
        c for c in normalized_completed if c in normalized_exclusions
    ]

    if conflicting:
        return {
            "course_code": normalized_code,
            "course_found": True,
            "has_conflict": True,
            "conflicting_courses": conflicting,
            "listed_exclusions": normalized_exclusions,
            "message": (
                f"{normalized_code} lists completed course(s) as "
                f"exclusions. Credit or program-counting may be affected; "
                f"verify with the official Academic Calendar or academic "
                f"advising."
            ),
        }

    if exclusions:
        return {
            "course_code": normalized_code,
            "course_found": True,
            "has_conflict": False,
            "conflicting_courses": [],
            "listed_exclusions": normalized_exclusions,
            "message": "No completed courses match the listed exclusions.",
        }

    return {
        "course_code": normalized_code,
        "course_found": True,
        "has_conflict": False,
        "conflicting_courses": [],
        "listed_exclusions": [],
        "message": "This course has no listed exclusions in the catalog.",
    }


def check_prerequisites(
    course_code: str, completed_courses: list[str]
) -> dict:
    """Check whether a student's completed courses satisfy a course's
    listed prerequisites.

    If the course has a non-empty ``prerequisite_note``, the prerequisites
    are considered complex and the function returns
    ``"manual_review_needed"`` rather than claiming definite eligibility.

    Args:
        course_code: The course code to check (e.g., "COG200H1").
        completed_courses: A list of course codes the student has completed.

    Returns:
        A dict with keys:
            - course_code (str)
            - course_found (bool)
            - status (str): "eligible", "not_eligible",
              "manual_review_needed", or "course_not_found"
            - satisfied_prerequisites (list[str])
            - missing_prerequisites (list[str])
            - listed_prerequisites (list[str])
            - prerequisite_note (str)
            - message (str)
    """
    normalized_code = normalize_course_code(course_code)
    normalized_completed = [
        normalize_course_code(c) for c in completed_courses
    ]
    course = get_course_details(course_code)

    if course is None:
        return {
            "course_code": normalized_code,
            "course_found": False,
            "status": "course_not_found",
            "satisfied_prerequisites": [],
            "missing_prerequisites": [],
            "listed_prerequisites": [],
            "prerequisite_note": "",
            "message": "Course not found in course catalog.",
        }

    listed = [normalize_course_code(p) for p in course.get("prerequisites", [])]
    prereq_note = course.get("prerequisite_note", "")

    satisfied = [p for p in listed if p in normalized_completed]
    missing = [p for p in listed if p not in normalized_completed]

    # Complex prerequisites — cannot determine eligibility automatically.
    if prereq_note:
        return {
            "course_code": normalized_code,
            "course_found": True,
            "status": "manual_review_needed",
            "satisfied_prerequisites": satisfied,
            "missing_prerequisites": missing,
            "listed_prerequisites": listed,
            "prerequisite_note": prereq_note,
            "message": (
                "This course has complex prerequisite information "
                "and needs manual review."
            ),
        }

    # Simple prerequisites — can evaluate directly.
    if not listed:
        return {
            "course_code": normalized_code,
            "course_found": True,
            "status": "eligible",
            "satisfied_prerequisites": [],
            "missing_prerequisites": [],
            "listed_prerequisites": [],
            "prerequisite_note": "",
            "message": "This course has no listed prerequisites.",
        }

    if not missing:
        return {
            "course_code": normalized_code,
            "course_found": True,
            "status": "eligible",
            "satisfied_prerequisites": satisfied,
            "missing_prerequisites": [],
            "listed_prerequisites": listed,
            "prerequisite_note": "",
            "message": "All listed prerequisites are satisfied.",
        }

    return {
        "course_code": normalized_code,
        "course_found": True,
        "status": "not_eligible",
        "satisfied_prerequisites": satisfied,
        "missing_prerequisites": missing,
        "listed_prerequisites": listed,
        "prerequisite_note": "",
        "message": "Missing listed prerequisites.",
    }


def find_courses_by_requirement_tag(tag: str) -> list[dict]:
    """Retrieve courses that contain the given requirement tag.

    Args:
        tag: A requirement tag to search for (e.g.,
            "computational_cognition_stream_pool").
            Whitespace is stripped and case is ignored.

    Returns:
        A list of course dicts whose ``requirement_tags`` includes the
        given tag.  Returns an empty list if no courses match.
    """
    normalized_tag = tag.strip().lower()
    courses = load_courses()

    return [
        c for c in courses
        if normalized_tag in (
            t.lower() for t in c.get("requirement_tags", [])
        )
    ]


def recommend_courses_for_requirement(
    requirement_tag: str,
    completed_courses: list[str],
    interests: list[str] | None = None,
) -> list[dict]:
    """Return candidate courses for a program requirement with basic
    eligibility checks.

    Uses :func:`find_courses_by_requirement_tag` to discover candidates,
    then calls :func:`check_prerequisites` on each to include a
    prerequisite status.

    When *interests* is provided, courses are ranked so that those
    matching any interest keyword appear first.  Matching is
    deterministic — it checks the course code, title, description, and
    interest_tags against each keyword case-insensitively.

    Args:
        requirement_tag: A requirement tag (e.g.,
            ``"computational_cognition_stream_pool"``).
        completed_courses: A list of course codes the student has
            completed.
        interests: Optional list of interest keywords (e.g.,
            ``["AI", "machine learning"]``).  When ``None`` or empty,
            courses are returned in catalog order.

    Returns:
        A list of recommendation dicts, each containing:

        * ``course_code``, ``title``, ``department``, ``level``,
          ``credits``, ``breadth_name``, ``term_availability``,
          ``verification_status``
        * ``prerequisite_status`` (from :func:`check_prerequisites`)
        * ``interest_match`` — ``bool``, always present
        * ``matched_interests`` — ``list[str]``, always present
          (empty when no interests matched)
    """
    candidates = find_courses_by_requirement_tag(requirement_tag)

    # --- normalise interests once ---------------------------------------
    interest_keywords: list[str] = []
    if interests:
        interest_keywords = [kw.strip().lower() for kw in interests
                             if kw.strip()]

    results = []
    for idx, course in enumerate(candidates):
        code = course["course_code"]
        prereq_result = check_prerequisites(code, completed_courses)

        # Deterministic interest matching.
        matched = _match_interests(course, interest_keywords)

        results.append({
            "course_code": code,
            "title": course.get("title", ""),
            "department": course.get("department", ""),
            "level": course.get("level"),
            "credits": course.get("credits"),
            "breadth_name": course.get("breadth_name", ""),
            "term_availability": course.get("term_availability", []),
            "verification_status": course.get("verification_status", ""),
            "prerequisite_status": prereq_result["status"],
            "interest_match": bool(matched),
            "matched_interests": matched,
            "_sort_idx": idx,
        })

    # --- sort: matched first, preserving original order in each group ---
    if interest_keywords:
        results.sort(key=lambda r: (not r["interest_match"],
                                    r["_sort_idx"]))

    # Remove the internal sort key before returning.
    for r in results:
        del r["_sort_idx"]

    return results


def _match_interests(course: dict, keywords: list[str]) -> list[str]:
    """Return the subset of *keywords* that match *course*.

    Matching is case-insensitive.  For multi-word keywords and
    single-word keywords longer than 2 characters, substring matching is
    used.  For short keywords (len ≤ 2), standalone-word matching via
    regex ``\\b`` boundaries is applied to avoid false positives from
    those letters appearing inside longer, unrelated words.

    ``"ai"`` (``"AI"``) is additionally expanded to match
    ``"artificial intelligence"``.
    """
    if not keywords:
        return []

    searchable = " ".join([
        course.get("course_code", ""),
        course.get("title", ""),
        course.get("description", ""),
        " ".join(course.get("interest_tags", [])),
    ]).lower()

    matched = []
    for kw in keywords:
        if kw in matched:
            continue

        if len(kw) <= 2:
            # Short keyword — must appear as a standalone word.
            if re.search(r"\b" + re.escape(kw) + r"\b", searchable):
                matched.append(kw)
            elif _match_known_synonym(kw, searchable):
                matched.append(kw)
        else:
            # Longer keyword — substring matching is acceptable.
            if kw in searchable:
                matched.append(kw)

    return matched


def _match_known_synonym(keyword: str, searchable: str) -> bool:
    """Check whether *searchable* contains a known synonym or expansion
    of *keyword*.

    This exists to handle edge cases like ``"ai"`` → ``"artificial
    intelligence"`` where the short form might not appear as a
    standalone word in the course text.
    """
    _SYNONYMS: dict[str, list[str]] = {
        "ai": ["artificial intelligence"],
    }
    for synonym in _SYNONYMS.get(keyword, []):
        if synonym in searchable:
            return True
    return False
