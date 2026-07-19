"""Deterministic program-progress audit engine — Phase 1.

Evaluates fixed required-course groups and choice groups against the
real structured program data in ``data/mock_programs.json``.

Not yet registered as an agent tool — callable from tests and scripts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# =========================================================================
# Course index
# =========================================================================


def build_course_index() -> dict[str, dict[str, Any]]:
    """Load all courses from ``data/mock_courses.json`` into a dict keyed
    by uppercase course code.

    Returns:
        ``{code: course_dict, ...}``
    """
    path = _PROJECT_ROOT / "data" / "mock_courses.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    courses: list[dict[str, Any]] = data.get("courses", [])
    return {c["course_code"].upper(): c for c in courses}


# =========================================================================
# Program loading
# =========================================================================


def load_program_by_code(program_code: str) -> dict[str, Any]:
    """Load a program definition by its program_code.

    Args:
        program_code: e.g. ``"ASMAJ1446A"``.

    Returns:
        The program dict.

    Raises:
        ValueError: If *program_code* is not found.
    """
    path = _PROJECT_ROOT / "data" / "mock_programs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    programs: list[dict[str, Any]] = data.get("programs", [])
    for prog in programs:
        if prog.get("program_code") == program_code:
            return prog
    raise ValueError(f"Program '{program_code}' not found in program data.")


# =========================================================================
# Normalisation
# =========================================================================


def normalize_completed_courses(
    completed_courses: list[str],
) -> dict[str, Any]:
    """Normalise a list of course codes.

    - Strips whitespace and uppercases.
    - Removes duplicates (preserving first-seen order).
    - Classifies courses as known, unknown, or unverified.

    Args:
        completed_courses: Raw course-code strings.

    Returns:
        A dict with keys ``raw_completed_courses``,
        ``normalized_courses``, ``duplicates_removed``,
        ``unknown_courses``, ``unverified_courses``.
    """
    course_index = build_course_index()
    raw = list(completed_courses)

    # Normalise: strip + uppercase, keep first-seen order.
    seen: set[str] = set()
    normalized: list[str] = []
    duplicates: list[str] = []
    for code in completed_courses:
        nc = code.strip().upper()
        if nc in seen:
            duplicates.append(nc)
        else:
            seen.add(nc)
            normalized.append(nc)

    unknown: list[str] = []
    unverified: list[str] = []
    for nc in normalized:
        course = course_index.get(nc)
        if course is None:
            unknown.append(nc)
        elif course.get("verification_status") != "calendar_verified":
            unverified.append(nc)

    return {
        "raw_completed_courses": raw,
        "normalized_courses": normalized,
        "duplicates_removed": duplicates,
        "unknown_courses": unknown,
        "unverified_courses": unverified,
    }


# =========================================================================
# Credit helpers
# =========================================================================


def _course_credits(code: str, course_index: dict[str, Any]) -> float:
    """Return the credit value of *code*, or 0.0 if unknown."""
    course = course_index.get(code)
    if course is None:
        return 0.0
    return float(course.get("credits", 0.0))


def _course_is_unverified(code: str, course_index: dict[str, Any]) -> bool:
    """Return True if *code* needs_official_verification."""
    course = course_index.get(code)
    if course is None:
        return False
    return course.get("verification_status") != "calendar_verified"


def _sum_credits(codes: list[str], course_index: dict[str, Any]) -> float:
    return sum(_course_credits(c, course_index) for c in codes)


# =========================================================================
# Fixed required-course group
# =========================================================================


def evaluate_required_course_group(
    completed_courses: list[str],
    group_definition: dict[str, Any],
    course_index: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate a fixed required-course group.

    Args:
        completed_courses: Normalised course codes.
        group_definition: A required-courses block from program data,
            e.g. ``completion_requirements.first_year.required_courses``.
        course_index: Output of :func:`build_course_index`.

    Returns:
        A result dict with ``progress_status`` and ``review_status``.
    """
    required_codes = [
        rc["course_code"].upper() for rc in group_definition.get("required_courses", [])
    ]
    credits_required = sum(
        float(rc.get("credits", 0)) for rc in group_definition.get("required_courses", [])
    )

    completed = [c for c in completed_courses if c in required_codes]
    missing = [c for c in required_codes if c not in completed_courses]
    credits_completed = _sum_credits(completed, course_index)

    # Progress status.
    if len(completed) == len(required_codes) and required_codes:
        progress = "completed"
    elif completed:
        progress = "partially_completed"
    else:
        progress = "not_started"

    # Review status.
    warnings: list[str] = []
    review = "clear"
    for c in completed:
        if _course_is_unverified(c, course_index):
            review = "needs_official_verification"
            warnings.append(
                f"{c} is marked needs_official_verification."
            )

    return {
        "requirement_id": group_definition.get("description", "required_courses"),
        "type": "required_course_group",
        "progress_status": progress,
        "review_status": review,
        "credits_completed": credits_completed,
        "credits_required": credits_required,
        "completed_courses": completed,
        "missing_courses": missing,
        "warnings": warnings,
    }


# =========================================================================
# Choice group
# =========================================================================


def normalize_choice_options(
    group_definition: dict[str, Any],
) -> dict[str, Any]:
    """Validate and normalise explicit program options.

    Each option must have ``required_courses`` and ``credits_required``
    already set in the program data.  This function performs validation
    only — no semantic inference, credit math, or course-count
    heuristics are applied.  Invalid options are NOT silently skipped;
    they are reported with structured error information.

    Args:
        group_definition: A choice-group block from program data.

    Returns:
        A dict with keys ``valid_options``, ``invalid_options``,
        and ``warnings``.
    """
    completion_logic = group_definition.get("completion_logic", "")
    if completion_logic != "complete_one_option":
        return {"valid_options": [], "invalid_options": [], "warnings": []}

    raw_options = group_definition.get("options", [])
    if not raw_options:
        return {"valid_options": [], "invalid_options": [], "warnings": []}

    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    validation_warnings: list[str] = []

    for order, opt in enumerate(raw_options):
        errors: list[str] = []
        opt_id = opt.get("option_id", "")
        required = opt.get("required_courses")
        credits = opt.get("credits_required")

        # --- validate option_id ---
        if not isinstance(opt_id, str) or not opt_id.strip():
            errors.append("option_id is missing or blank")

        # --- validate required_courses ---
        if required is None:
            errors.append("required_courses is missing")
        elif not isinstance(required, list):
            errors.append("required_courses must be a list")
        elif len(required) == 0:
            errors.append("required_courses is empty")
        else:
            # Validate each course code.
            for ci, code in enumerate(required):
                if not isinstance(code, str) or not code.strip():
                    errors.append(
                        f"required_courses[{ci}] is blank or invalid"
                    )

        # --- validate credits_required ---
        if credits is None:
            errors.append("credits_required is missing")
        elif not isinstance(credits, (int, float)):
            errors.append(
                f"credits_required must be numeric, got {type(credits).__name__}"
            )
        elif isinstance(credits, bool):
            errors.append("credits_required must be numeric, got bool")
        elif credits <= 0:
            errors.append(
                f"credits_required is {credits}, must be positive"
            )

        if errors:
            invalid.append({
                "source_order": order,
                "option_id": opt_id if isinstance(opt_id, str) and opt_id.strip() else f"<invalid>",
                "errors": errors,
            })
            continue

        # Valid — normalise.
        valid.append({
            "option_id": opt_id.strip(),
            "description": opt.get("description", ""),
            "required_courses": [c.strip().upper() for c in required],
            "credits_required": float(credits),
            "source_order": order,
        })

    if invalid:
        for inv in invalid:
            validation_warnings.append(
                f"Option '{inv['option_id']}' (source_order={inv['source_order']}) "
                f"could not be validated: {'; '.join(inv['errors'])}"
            )

    return {
        "valid_options": valid,
        "invalid_options": invalid,
        "warnings": validation_warnings,
    }


def evaluate_choice_group(
    completed_courses: list[str],
    group_definition: dict[str, Any],
    course_index: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate a choice group with ``complete_one_option`` logic.

    Options are first normalised via :func:`normalize_choice_options`,
    then each is evaluated independently.  An option is complete when
    ALL its required courses are in *completed_courses*.

    Args:
        completed_courses: Normalised course codes.
        group_definition: A choice-group block from program data.
        course_index: Output of :func:`build_course_index`.

    Returns:
        A result dict with ``progress_status``, ``review_status``,
        ``completed_options``, ``best_partial_option``,
        ``option_results``, and ``warnings``.
    """
    completion_logic = group_definition.get("completion_logic", "")
    # Read explicit ambiguous_expression field (no note/prose heuristics).
    ambig_raw = group_definition.get("ambiguous_expression")
    if isinstance(ambig_raw, bool):
        ambiguous = ambig_raw
    else:
        ambiguous = None  # missing or invalid — handled below

    # Handle unsupported or missing logic.
    if completion_logic != "complete_one_option":
        if not completion_logic:
            return _unsupported_choice_result(
                group_definition,
                "Missing completion_logic field — cannot determine completion semantics.",
            )
        return _unsupported_choice_result(
            group_definition,
            f"Unsupported completion_logic '{completion_logic}'.",
        )

    norm_result = normalize_choice_options(group_definition)
    valid_options = norm_result["valid_options"]
    invalid_options = norm_result["invalid_options"]
    validation_warnings = norm_result["warnings"]

    if not valid_options and not invalid_options:
        return _unsupported_choice_result(
            group_definition,
            "No structured options could be derived from this choice group.",
        )

    if not valid_options:
        # All options invalid — cannot evaluate.
        result = _unsupported_choice_result(
            group_definition,
            "All options in this choice group are structurally invalid.",
        )
        result["invalid_options"] = invalid_options
        result["valid_option_count"] = 0
        result["invalid_option_count"] = len(invalid_options)
        result["warnings"].extend(validation_warnings)
        return result

    option_results: list[dict[str, Any]] = []
    completed_options: list[dict[str, Any]] = []
    best_partial: dict[str, Any] | None = None
    best_partial_score = -1
    best_partial_credits = 0.0

    for opt in valid_options:
        req_courses = opt["required_courses"]
        completed_in_opt = [c for c in completed_courses if c in req_courses]
        credits_in_opt = _sum_credits(completed_in_opt, course_index)
        all_done = set(req_courses).issubset(set(completed_courses))

        opt_result = {
            "option_id": opt["option_id"],
            "description": opt["description"],
            "required_courses": req_courses,
            "courses_completed": completed_in_opt,
            "credits_completed": credits_in_opt,
            "credits_required": opt["credits_required"],
            "is_complete": all_done,
        }
        option_results.append(opt_result)

        if all_done:
            completed_options.append(opt_result)

        if not all_done:
            score = len(completed_in_opt)
            if score > 0 and (
                score > best_partial_score
                or (score == best_partial_score
                    and credits_in_opt > best_partial_credits)
            ):
                best_partial_score = score
                best_partial_credits = credits_in_opt
                best_partial = opt_result

    # Progress status.
    if completed_options:
        progress = "completed"
    elif best_partial and best_partial_score > 0:
        progress = "partially_completed"
    else:
        progress = "not_started"

    # Review status.
    warnings: list[str] = []
    review = "clear"

    # Invalid options force manual review.
    if invalid_options:
        review = "manual_review_needed"
        warnings.append(
            f"{len(invalid_options)} option(s) could not be validated. "
            "Progress is provisional."
        )

    if ambiguous is None:
        # Missing or non-boolean ambiguous_expression.
        review = "manual_review_needed"
        warnings.append(
            "ambiguous_expression metadata is missing or invalid — "
            "cannot determine whether this requirement's official "
            "expression is ambiguous."
        )
    elif ambiguous:
        review = "manual_review_needed"
        note = group_definition.get("note", "")
        if note:
            warnings.append(note[:200])

    # Check for unverified counted courses.
    all_completed_codes: set[str] = set()
    for co in completed_options:
        all_completed_codes.update(co["courses_completed"])
    for c in all_completed_codes:
        if _course_is_unverified(c, course_index):
            if review != "manual_review_needed":
                review = "needs_official_verification"
            warnings.append(
                f"{c} is marked needs_official_verification."
            )

    # Include validation warnings.
    warnings.extend(validation_warnings)

    return {
        "requirement_id": group_definition.get("group_id",
                                               group_definition.get("description", "choice_group")),
        "type": "choice_group",
        "progress_status": progress,
        "review_status": review,
        "completed_options": completed_options,
        "best_partial_option": best_partial,
        "option_results": option_results,
        "invalid_options": invalid_options,
        "valid_option_count": len(valid_options),
        "invalid_option_count": len(invalid_options),
        "ambiguous_expression": ambiguous,
        "warnings": warnings,
    }


def _unsupported_choice_result(
    group_definition: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    """Return a result for an unsupported or unparseable choice group."""
    return {
        "requirement_id": group_definition.get("group_id",
                                               group_definition.get("description", "choice_group")),
        "type": "choice_group",
        "progress_status": "not_started",
        "review_status": "manual_review_needed",
        "completed_options": [],
        "best_partial_option": None,
        "option_results": [],
        "invalid_options": [],
        "valid_option_count": 0,
        "invalid_option_count": 0,
        "ambiguous_expression": True,
        "warnings": [reason],
    }


# =========================================================================
# Core-requirements audit (Phase 1)
# =========================================================================


def audit_core_requirements(
    completed_courses: list[str],
    program_code: str = "ASMAJ1446A",
) -> dict[str, Any]:
    """Evaluate all fixed required-course groups and choice groups
    for a program.

    Phase 1 does NOT include pool credit counting, special rules,
    exclusion conflicts, or double-counting allocation.

    Args:
        completed_courses: Raw course-code strings.
        program_code: Program identifier.

    Returns:
        A structured audit result dict.
    """
    norm = normalize_completed_courses(completed_courses)
    normalized = norm["normalized_courses"]
    course_index = build_course_index()
    program = load_program_by_code(program_code)
    reqs = program.get("completion_requirements", {})

    requirement_results: dict[str, Any] = {}
    all_warnings: list[str] = []

    # Walk all requirement sections.
    for section_key in ["first_year", "second_year",
                         "second_year_and_higher", "fourth_year"]:
        section = reqs.get(section_key)
        if section is None:
            continue
        section_desc = section.get("description", section_key)

        # --- required courses in this section ---
        if section.get("required_courses"):
            result = evaluate_required_course_group(
                normalized, section, course_index,
            )
            result["requirement_id"] = f"{section_key}_required"
            result["section_description"] = section_desc
            requirement_results[result["requirement_id"]] = result
            all_warnings.extend(result.get("warnings", []))

        # --- choice groups in this section ---
        for cg in section.get("choice_groups", []):
            result = evaluate_choice_group(
                normalized, cg, course_index,
            )
            gid = cg.get("group_id", "unknown")
            result["requirement_id"] = gid
            result["section_description"] = section_desc
            requirement_results[gid] = result
            all_warnings.extend(result.get("warnings", []))

    # Deduplicate warnings.
    unique_warnings: list[str] = []
    seen_w = set()
    for w in all_warnings:
        if w not in seen_w:
            seen_w.add(w)
            unique_warnings.append(w)

    # Handle unknown / unverified from normalisation.
    for uc in norm["unknown_courses"]:
        unique_warnings.append(
            f"Unknown course code '{uc}' — not found in course catalog."
        )

    return {
        "audit_version": "1.0-phase1",
        "program_code": program_code,
        "program_name": program.get("program_name", ""),
        "normalized_input": norm,
        "requirement_results": requirement_results,
        "warnings": unique_warnings,
        "assumptions": [
            "Grades are not considered.",
            "Transfer credits are not considered.",
            "This is not an official Degree Explorer audit.",
        ],
        "limitations": [
            "Pool credit counting is not implemented in Phase 1.",
            "Special program rules are not implemented in Phase 1.",
            "Exclusion conflicts are not resolved in Phase 1.",
            "Double-counting allocation is not implemented in Phase 1.",
        ],
    }


# =========================================================================
# Phase 2A — Pool credit counting
# =========================================================================


def evaluate_credit_pool(
    completed_courses: list[str],
    pool_definition: dict[str, Any],
    course_index: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate a credit-pool requirement against completed courses.

    A course counts only when its normalised code appears in the
    pool's explicit course list.  Credits, levels, and designators
    are read from the course catalog, not inferred from code strings.

    Args:
        completed_courses: Normalised course codes.
        pool_definition: A pool block from program data
            (``approved_pools`` entry).
        course_index: Output of :func:`build_course_index`.

    Returns:
        A pool result dict.
    """
    pool_id = pool_definition.get("pool_id", "unknown_pool")
    pool_name = pool_definition.get("pool_name", pool_id)
    pool_courses: list[str] = [
        c.upper() for c in pool_definition.get("courses", [])
    ]
    credits_needed_raw = pool_definition.get("credits_needed")

    # --- review: validate pool definition ---
    warnings: list[str] = []
    review = "clear"

    if not isinstance(credits_needed_raw, (int, float)) or credits_needed_raw <= 0:
        return {
            "requirement_id": pool_id,
            "type": "credit_pool",
            "description": pool_name,
            "progress_status": "not_started",
            "review_status": "manual_review_needed",
            "credits_completed": 0.0,
            "credits_required": None,
            "credits_remaining": None,
            "completed_courses": [],
            "course_count": 0,
            "counts_by_level": {},
            "credits_at_300_plus": 0.0,
            "counts_by_designator": {},
            "unverified_counted_courses": [],
            "warnings": [
                "Pool definition missing or invalid credits_needed field."
            ],
        }

    credits_required = float(credits_needed_raw)

    # --- count completed pool courses ---
    completed_pool: list[str] = []
    seen: set[str] = set()
    for c in completed_courses:
        if c in pool_courses and c not in seen:
            completed_pool.append(c)
            seen.add(c)

    # --- compute credits and breakdowns ---
    credits_completed = _sum_credits(completed_pool, course_index)
    counts_by_level: dict[str, float] = {}
    counts_by_designator: dict[str, float] = {}
    credits_at_300_plus = 0.0
    unverified: list[str] = []

    for code in completed_pool:
        course = course_index.get(code, {})
        level = course.get("level", 0) or 0
        dept = code[:3]  # 3-letter designator
        cred = course.get("credits", 0) or 0

        level_key = str(int(level)) if level else "unknown"
        counts_by_level[level_key] = counts_by_level.get(level_key, 0.0) + cred
        counts_by_designator[dept] = counts_by_designator.get(dept, 0.0) + cred
        if level >= 300:
            credits_at_300_plus += cred
        if _course_is_unverified(code, course_index):
            unverified.append(code)

    # --- progress status ---
    if credits_completed == 0.0:
        progress = "not_started"
    elif credits_completed >= credits_required:
        progress = "completed"
    else:
        progress = "partially_completed"

    # --- review status ---
    if unverified:
        review = "needs_official_verification"
        for uv in unverified:
            warnings.append(
                f"{uv} (pool course) is marked needs_official_verification."
            )

    return {
        "requirement_id": pool_id,
        "type": "credit_pool",
        "description": pool_name,
        "progress_status": progress,
        "review_status": review,
        "credits_completed": credits_completed,
        "credits_required": credits_required,
        "credits_remaining": max(0.0, credits_required - credits_completed),
        "completed_courses": completed_pool,
        "course_count": len(completed_pool),
        "counts_by_level": dict(sorted(counts_by_level.items())),
        "credits_at_300_plus": credits_at_300_plus,
        "counts_by_designator": dict(sorted(counts_by_designator.items())),
        "unverified_counted_courses": unverified,
        "warnings": warnings,
    }


# =========================================================================
# Phase 2A — Special rules
# =========================================================================


def _read_structured_rules(
    requirements: dict[str, Any],
) -> dict[str, Any]:
    """Read and validate structured special-rule values from program data.

    All numeric rule values come from
    ``completion_requirements.structured_special_rules``.
    No hard-coded constants, no prose parsing, no regex.

    Args:
        requirements: The ``completion_requirements`` dict from
            the program definition.

    Returns:
        A dict of validated rule values and any validation errors.
        Keys: ``values``, ``errors``.
    """
    BASE_PATH = "completion_requirements.structured_special_rules"
    rules = requirements.get("structured_special_rules")
    errors: dict[str, str] = {}
    values: dict[str, Any] = {}

    if not isinstance(rules, dict):
        return {
            "values": {},
            "errors": {"_all": f"{BASE_PATH} is missing or not an object"},
        }

    def _path(field: str) -> str:
        return f"{BASE_PATH}.{field}"

    # --- minimum_300_level_credits ---
    v = rules.get("minimum_300_level_credits")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        values["minimum_300_level_credits"] = float(v)
    else:
        errors["minimum_300_level_credits"] = (
            f"{_path('minimum_300_level_credits')} must be a positive number"
        )

    # --- csc_credit_minimum ---
    v = rules.get("csc_credit_minimum")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
        values["csc_credit_minimum"] = float(v)
    else:
        errors["csc_credit_minimum"] = (
            f"{_path('csc_credit_minimum')} must be a non-negative number"
        )

    # --- csc_credit_maximum ---
    v = rules.get("csc_credit_maximum")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        values["csc_credit_maximum"] = float(v)
    else:
        errors["csc_credit_maximum"] = (
            f"{_path('csc_credit_maximum')} must be a positive number"
        )

    # Cross-field: csc_max must be >= csc_min (only when both valid).
    if "csc_credit_minimum" in values and "csc_credit_maximum" in values:
        if values["csc_credit_maximum"] < values["csc_credit_minimum"]:
            errors["csc_credit_maximum"] = (
                f"{_path('csc_credit_maximum')} ({values['csc_credit_maximum']}) "
                f"is less than csc_credit_minimum ({values['csc_credit_minimum']})"
            )
            del values["csc_credit_maximum"]

    # --- designator_credit_maximum ---
    v = rules.get("designator_credit_maximum")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        values["designator_credit_maximum"] = float(v)
    else:
        errors["designator_credit_maximum"] = (
            f"{_path('designator_credit_maximum')} must be a positive number"
        )

    # --- designator_exceptions ---
    v = rules.get("designator_exceptions")
    if isinstance(v, list) and all(
        isinstance(x, str) and len(x.strip()) == 3 and x.strip().isalpha()
        and x.strip().isupper()
        for x in v
    ):
        values["designator_exceptions"] = [x.strip() for x in v]
    else:
        errors["designator_exceptions"] = (
            f"{_path('designator_exceptions')} must be a list of "
            "3-letter uppercase designators"
        )

    return {"values": values, "errors": errors}


def evaluate_special_rules(
    pool_result: dict[str, Any],
    pool_definition: dict[str, Any],
    requirements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate program special rules against pool counting results.

    All rule values are read from the program's
    ``structured_special_rules`` — no hard-coded constants.

    Args:
        pool_result: Output of :func:`evaluate_credit_pool`.
        pool_definition: The pool block from program data.
        requirements: The ``completion_requirements`` dict (optional —
            used for source metadata).  If omitted, pool_definition is
            used to load the program.

    Returns:
        A dict of special-rule results.
    """
    if requirements is None:
        program = load_program_by_code("ASMAJ1446A")
        requirements = program.get("completion_requirements", {})

    parsed = _read_structured_rules(requirements)
    values = parsed["values"]
    field_errors = parsed["errors"]
    BASE = "completion_requirements.structured_special_rules"

    credits_at_300 = pool_result.get("credits_at_300_plus", 0.0)
    designator_counts = pool_result.get("counts_by_designator", {})
    csc_credits = designator_counts.get("CSC", 0.0)
    excluded = values.get("designator_exceptions", [])

    # --- 300-level minimum ---
    min_300 = values.get("minimum_300_level_credits")
    if min_300 is None:
        rule_300 = _rule_unknown(
            "minimum", credits_at_300,
            field_errors.get("minimum_300_level_credits",
                              "minimum_300_level_credits is missing or invalid"),
            f"{BASE}.minimum_300_level_credits",
        )
    else:
        met = credits_at_300 >= min_300
        rule_300 = {
            "rule_type": "minimum",
            "required": min_300,
            "completed": credits_at_300,
            "remaining": max(0.0, min_300 - credits_at_300),
            "rule_status": "met" if met else "not_met",
            "review_status": "clear",
            "source": {"json_path": f"{BASE}.minimum_300_level_credits",
                       "value": min_300},
        }

    # --- CSC minimum ---
    csc_min = values.get("csc_credit_minimum")
    if csc_min is None:
        rule_csc_min = _rule_unknown(
            "minimum", csc_credits,
            field_errors.get("csc_credit_minimum",
                              "csc_credit_minimum is missing or invalid"),
            f"{BASE}.csc_credit_minimum",
        )
    else:
        met = csc_credits >= csc_min
        rule_csc_min = {
            "rule_type": "minimum",
            "required": csc_min,
            "completed": csc_credits,
            "remaining": max(0.0, csc_min - csc_credits),
            "rule_status": "met" if met else "not_met",
            "review_status": "clear",
            "source": {"json_path": f"{BASE}.csc_credit_minimum",
                       "value": csc_min},
        }

    # --- CSC maximum ---
    csc_max = values.get("csc_credit_maximum")
    if csc_max is None:
        rule_csc_max = _rule_unknown(
            "maximum", csc_credits,
            field_errors.get("csc_credit_maximum",
                              "csc_credit_maximum is missing or invalid"),
            f"{BASE}.csc_credit_maximum",
        )
    else:
        over = max(0.0, csc_credits - csc_max)
        rule_csc_max = {
            "rule_type": "maximum",
            "limit": csc_max,
            "completed": csc_credits,
            "remaining_before_limit": max(0.0, csc_max - csc_credits),
            "amount_over_limit": over,
            "rule_status": "exceeded" if over > 0 else "ok",
            "review_status": "clear",
            "source": {"json_path": f"{BASE}.csc_credit_maximum",
                       "value": csc_max},
        }

    # --- Designator concentration ---
    d_limit = values.get("designator_credit_maximum")
    if d_limit is None:
        rule_dc = _rule_unknown(
            "maximum_per_designator", 0.0,
            field_errors.get("designator_credit_maximum",
                              "designator_credit_maximum is missing or invalid"),
            f"{BASE}.designator_credit_maximum",
        )
        rule_dc["excluded_designators"] = excluded
        rule_dc["counts"] = designator_counts
        rule_dc["violations"] = []
    else:
        violations: list[dict[str, Any]] = []
        for dept, count in designator_counts.items():
            if dept not in excluded and count > d_limit:
                violations.append({
                    "designator": dept,
                    "credits": count,
                    "limit": d_limit,
                    "excess": count - d_limit,
                })
        rule_dc = {
            "rule_type": "maximum_per_designator",
            "limit": d_limit,
            "excluded_designators": excluded,
            "counts": designator_counts,
            "violations": violations,
            "rule_status": "exceeded" if violations else "ok",
            "review_status": "clear",
            "source": {"json_path": f"{BASE}.designator_credit_maximum",
                       "value": d_limit},
        }

    return {
        "rule_300_level_minimum": rule_300,
        "rule_csc_minimum": rule_csc_min,
        "rule_csc_maximum": rule_csc_max,
        "rule_designator_concentration": rule_dc,
    }


def _rule_unknown(
    rule_type: str, completed: float, warning: str, json_path: str,
) -> dict[str, Any]:
    """Build a special-rule result for missing/invalid structured data."""
    return {
        "rule_type": rule_type,
        "required": None,
        "completed": completed,
        "remaining": None,
        "rule_status": "unknown",
        "review_status": "manual_review_needed",
        "warning": warning,
        "source": {"json_path": json_path, "value": None},
    }


# =========================================================================
# Phase 2A — Full audit
# =========================================================================


def audit_program_progress(
    completed_courses: list[str],
    program_code: str = "ASMAJ1446A",
) -> dict[str, Any]:
    """Full program-progress audit — Phase 1 + Phase 2A.

    Composes core requirement evaluation (Phase 1) with pool credit
    counting and special-rule evaluation (Phase 2A).

    Args:
        completed_courses: Raw course-code strings.
        program_code: Program identifier.

    Returns:
        A structured audit result dict.
    """
    # Phase 1: core requirements.
    phase1 = audit_core_requirements(completed_courses, program_code)

    norm = phase1["normalized_input"]
    normalized = norm["normalized_courses"]
    course_index = build_course_index()
    program = load_program_by_code(program_code)
    reqs = program.get("completion_requirements", {})

    # Phase 2A: pool + special rules.
    pool_results: dict[str, Any] = {}
    special_rule_results: dict[str, Any] = {}
    all_warnings: list[str] = list(phase1.get("warnings", []))

    pools = reqs.get("approved_pools", [])
    for pool_def in pools:
        pool_result = evaluate_credit_pool(normalized, pool_def, course_index)
        pid = pool_result["requirement_id"]
        pool_results[pid] = pool_result
        all_warnings.extend(pool_result.get("warnings", []))

        # Evaluate special rules for this pool.
        pool_rules = evaluate_special_rules(
            pool_result, pool_def, requirements=reqs,
        )
        special_rule_results.update(pool_rules)

    # Phase 2B1: category membership, exclusions, allocations.
    category_membership = _build_category_membership(
        program_code, course_index,
    )
    exclusion_conflicts = detect_exclusion_conflicts(
        normalized, course_index, category_membership,
    )
    allocations = build_course_allocations(
        normalized, course_index, category_membership,
        exclusion_conflicts,
    )
    classification = build_course_classification_summaries(
        norm, course_index,
    )

    # Build overlap cases.
    overlap_cases: list[dict[str, Any]] = []
    for entry in allocations["entries"]:
        eligible = entry.get("eligible_categories", [])
        if len(eligible) > 1:
            overlap_cases.append({
                "course_code": entry["course_code"],
                "eligible_categories": eligible,
                "allocation_status": "manual_review_needed",
                "message": (
                    "The course is eligible for multiple categories, "
                    "but official double-counting policy is not encoded."
                ),
            })

    # Apply exclusion conflicts to affected requirement/pool review status.
    for conflict in exclusion_conflicts:
        for cat in conflict.get("affected_categories", []):
            req = phase1["requirement_results"].get(cat)
            if req:
                req["review_status"] = "manual_review_needed"
                req["warnings"].append(
                    f"Exclusion conflict ({conflict['course_a']} / "
                    f"{conflict['course_b']}) may affect this requirement."
                )
            pool = pool_results.get(cat)
            if pool:
                pool["review_status"] = "manual_review_needed"
                pool["warnings"].append(
                    f"Exclusion conflict ({conflict['course_a']} / "
                    f"{conflict['course_b']}) may affect this pool count."
                )

    # Collect all warnings.
    for c in exclusion_conflicts:
        all_warnings.append(c["message"])
    for oc in overlap_cases:
        all_warnings.append(oc["message"])
    for entry in allocations["entries"]:
        for reason in entry.get("review_reasons", []):
            all_warnings.append(
                f"{entry['course_code']}: {reason}"
            )

    # Overall status.
    overall = _compute_overall_status(
        phase1["requirement_results"], pool_results, special_rule_results,
    )
    overall_review = _compute_overall_review_status(
        phase1["requirement_results"], pool_results,
        special_rule_results, exclusion_conflicts,
        allocations, classification["unverified_courses"],
    )

    # Phase 2B2: priority items.
    priority_items = build_priority_items(
        phase1["requirement_results"], pool_results,
        special_rule_results, overall_review,
    )

    # Deduplicate warnings (exact matches only).
    unique_warnings: list[str] = []
    seen_w = set()
    for w in all_warnings:
        if w not in seen_w:
            seen_w.add(w)
            unique_warnings.append(w)

    return {
        "audit_version": "1.0-phase2b2",
        "program_code": program_code,
        "program_name": program.get("program_name", ""),
        "normalized_input": norm,
        "overall_status": overall,
        "overall_review_status": overall_review,
        "requirement_results": phase1["requirement_results"],
        "pool_results": pool_results,
        "special_rule_results": special_rule_results,
        "unknown_courses": classification["unknown_courses"],
        "unverified_courses": classification["unverified_courses"],
        "exclusion_conflicts": exclusion_conflicts,
        "overlap_cases": overlap_cases,
        "course_allocations": allocations,
        "priority_items": priority_items,
        "warnings": unique_warnings,
        "assumptions": list(phase1["assumptions"]),
        "limitations": [
            "Official exclusion-credit decisions are not made.",
            "Official double-count allocation is not implemented.",
            "Program-counted total credits are not calculated.",
            "Enrollment restrictions are not evaluated.",
            "This is not an official Degree Explorer audit.",
        ],
    }


# =========================================================================
# Phase 2B2 — Priority items
# =========================================================================


def _section_order(section_key: str) -> int:
    """Deterministic ordering for requirement sections."""
    _ORDER = {
        "first_year": 0, "second_year": 1,
        "second_year_and_higher": 2, "fourth_year": 10,
    }
    return _ORDER.get(section_key, 5)


def build_priority_items(
    requirement_results: dict[str, Any],
    pool_results: dict[str, Any],
    special_rule_results: dict[str, Any],
    overall_review_status: str,
) -> list[dict[str, Any]]:
    """Build a deterministic priority list from existing audit results.

    Priority items describe unfinished requirements factually, not as
    personalized recommendations.  Review-required items appear first,
    followed by gap items in program structure order.

    Args:
        requirement_results: Phase 1 requirement evaluation results.
        pool_results: Phase 2A pool credit counting results.
        special_rule_results: Phase 2A special-rule evaluation results.
        overall_review_status: Computed overall review status.

    Returns:
        A list of priority item dicts, sorted by rank.
    """
    items: list[dict[str, Any]] = []
    rank = 1

    # --- Collect review-required items first ---
    for key, req in requirement_results.items():
        ps = req.get("progress_status", "not_started")
        rs = req.get("review_status", "clear")
        if ps == "completed" and rs in ("manual_review_needed",
                                         "needs_official_verification"):
            items.append({
                "rank": rank,
                "priority_type": "review_required",
                "category": key,
                "title": "Verify this requirement before relying on the audit result",
                "progress_status": ps,
                "review_status": rs,
                "evidence": {"source": f"requirement_results.{key}"},
            })
            rank += 1

    # Pool review-required.
    for key, pool in pool_results.items():
        ps = pool.get("progress_status", "not_started")
        rs = pool.get("review_status", "clear")
        if ps == "completed" and rs in ("manual_review_needed",
                                         "needs_official_verification"):
            items.append({
                "rank": rank,
                "priority_type": "review_required",
                "category": key,
                "title": "Verify this pool result before relying on the audit",
                "progress_status": ps,
                "review_status": rs,
                "evidence": {"source": f"pool_results.{key}"},
            })
            rank += 1

    # Special-rule unknown → review required.
    for key, sr in special_rule_results.items():
        if not isinstance(sr, dict):
            continue
        if sr.get("rule_status") == "unknown":
            items.append({
                "rank": rank,
                "priority_type": "review_required",
                "category": key,
                "title": "This rule could not be evaluated — verify manually",
                "rule_status": "unknown",
                "review_status": sr.get("review_status", "?"),
                "evidence": {"source": f"special_rule_results.{key}"},
            })
            rank += 1

    # --- Gap items: fixed required courses ---
    # Collect all requirement entries sorted by section order.
    req_entries: list[tuple[str, dict, int]] = []
    for key, req in requirement_results.items():
        if req.get("type") != "required_course_group":
            continue
        order = _section_order(key.split("_")[0])
        req_entries.append((key, req, order))
    req_entries.sort(key=lambda x: x[2])

    for key, req, _order in req_entries:
        ps = req.get("progress_status", "not_started")
        if ps == "completed":
            continue
        credits = req.get("credits_remaining",
                          req.get("credits_required", 0)
                          - req.get("credits_completed", 0))
        items.append({
            "rank": rank,
            "priority_type": "required_course_gap",
            "category": key,
            "title": f"Complete remaining courses for {key}",
            "progress_status": ps,
            "review_status": req.get("review_status", "clear"),
            "credits_remaining": max(0.0, credits),
            "missing_courses": req.get("missing_courses", []),
            "evidence": {"source": f"requirement_results.{key}"},
        })
        rank += 1

    # --- Gap items: choice groups (excluding capstone) ---
    choice_entries: list[tuple[str, dict, int]] = []
    for key, req in requirement_results.items():
        if req.get("type") != "choice_group":
            continue
        if "capstone" in key.lower():
            continue
        order = _section_order(key.split("_")[0])
        choice_entries.append((key, req, order))
    choice_entries.sort(key=lambda x: x[2])

    for key, req, _order in choice_entries:
        ps = req.get("progress_status", "not_started")
        if ps == "completed":
            continue
        items.append({
            "rank": rank,
            "priority_type": "choice_group_gap",
            "category": key,
            "title": "Complete one valid option",
            "progress_status": ps,
            "review_status": req.get("review_status", "clear"),
            "completed_options": req.get("completed_options", []),
            "best_partial_option": req.get("best_partial_option"),
            "evidence": {"source": f"requirement_results.{key}"},
        })
        rank += 1

    # --- Gap items: pool credits ---
    for key, pool in pool_results.items():
        ps = pool.get("progress_status", "not_started")
        if ps == "completed":
            continue
        remaining = pool.get("credits_remaining",
                             pool.get("credits_required", 0)
                             - pool.get("credits_completed", 0))
        if remaining <= 0:
            continue
        items.append({
            "rank": rank,
            "priority_type": "pool_credit_gap",
            "category": key,
            "title": f"Complete {remaining} remaining stream-pool credits",
            "progress_status": ps,
            "review_status": pool.get("review_status", "clear"),
            "credits_remaining": max(0.0, remaining),
            "evidence": {"source": f"pool_results.{key}"},
        })
        rank += 1

    # --- Gap items: special rules ---
    # 300-level minimum.
    r300 = special_rule_results.get("rule_300_level_minimum", {})
    if isinstance(r300, dict) and r300.get("rule_status") == "not_met":
        items.append({
            "rank": rank,
            "priority_type": "special_rule_gap",
            "category": "rule_300_level_minimum",
            "title": "Meet the remaining 300-level credit minimum",
            "rule_status": "not_met",
            "review_status": r300.get("review_status", "clear"),
            "credits_remaining": r300.get("remaining", 0),
            "evidence": {"source": "special_rule_results.rule_300_level_minimum"},
        })
        rank += 1

    # CSC minimum.
    csc_min = special_rule_results.get("rule_csc_minimum", {})
    if isinstance(csc_min, dict) and csc_min.get("rule_status") == "not_met":
        items.append({
            "rank": rank,
            "priority_type": "special_rule_gap",
            "category": "rule_csc_minimum",
            "title": "Meet the CSC credit minimum",
            "rule_status": "not_met",
            "review_status": csc_min.get("review_status", "clear"),
            "credits_remaining": csc_min.get("remaining", 0),
            "evidence": {"source": "special_rule_results.rule_csc_minimum"},
        })
        rank += 1

    # CSC maximum.
    csc_max = special_rule_results.get("rule_csc_maximum", {})
    if isinstance(csc_max, dict):
        status = csc_max.get("rule_status", "?")
        if status == "exceeded":
            items.append({
                "rank": rank,
                "priority_type": "special_rule_gap",
                "category": "rule_csc_maximum",
                "title": "CSC credit maximum exceeded",
                "rule_status": "exceeded",
                "review_status": csc_max.get("review_status", "clear"),
                "credits_remaining": 0.0,
                "amount_over": csc_max.get("amount_over_limit", 0),
                "evidence": {"source": "special_rule_results.rule_csc_maximum"},
            })
            rank += 1
        elif status == "ok":
            remaining = csc_max.get("remaining_before_limit", 0)
            if 0 < remaining <= 0.5:
                items.append({
                    "rank": rank,
                    "priority_type": "special_rule_info",
                    "category": "rule_csc_maximum",
                    "title": "CSC credit maximum is approaching",
                    "rule_status": "ok",
                    "review_status": csc_max.get("review_status", "clear"),
                    "remaining_before_limit": remaining,
                    "evidence": {"source": "special_rule_results.rule_csc_maximum"},
                })
                rank += 1

    # Designator concentration.
    dc = special_rule_results.get("rule_designator_concentration", {})
    if isinstance(dc, dict) and dc.get("violations"):
        items.append({
            "rank": rank,
            "priority_type": "special_rule_gap",
            "category": "rule_designator_concentration",
            "title": "Resolve designator concentration violations",
            "rule_status": "exceeded",
            "review_status": dc.get("review_status", "clear"),
            "violations": dc.get("violations", []),
            "evidence": {
                "source": "special_rule_results.rule_designator_concentration",
            },
        })
        rank += 1

    # --- Gap items: capstone (last) ---
    for key, req in requirement_results.items():
        if req.get("type") != "choice_group":
            continue
        if "capstone" not in key.lower():
            continue
        ps = req.get("progress_status", "not_started")
        if ps == "completed":
            continue
        items.append({
            "rank": rank,
            "priority_type": "choice_group_gap",
            "category": key,
            "title": "Complete one capstone option",
            "progress_status": ps,
            "review_status": req.get("review_status", "clear"),
            "completed_options": req.get("completed_options", []),
            "best_partial_option": req.get("best_partial_option"),
            "evidence": {"source": f"requirement_results.{key}"},
        })
        rank += 1

    # Re-rank consecutively.
    for i, item in enumerate(items):
        item["rank"] = i + 1

    return items


def _build_category_membership(
    program_code: str,
    course_index: dict[str, Any],
) -> dict[str, list[str]]:
    """Build a mapping from course code to the requirement categories
    in which it appears in the program definition.

    Only uses explicit program structures — no inference from
    department, title, or requirement_tags.
    """
    program = load_program_by_code(program_code)
    reqs = program.get("completion_requirements", {})
    membership: dict[str, set[str]] = {}

    def _add(code: str, category: str) -> None:
        if code not in membership:
            membership[code] = set()
        membership[code].add(category)

    # Walk all requirement sections.
    for section_key, section in reqs.items():
        if not isinstance(section, dict):
            continue

        # Fixed required courses.
        for rc in section.get("required_courses", []):
            code = rc.get("course_code", "").upper()
            if code:
                _add(code, f"{section_key}_required")

        # Choice groups — normalize and collect.
        for cg in section.get("choice_groups", []):
            if cg.get("completion_logic") != "complete_one_option":
                continue
            gid = cg.get("group_id", "")
            norm = normalize_choice_options(cg)
            for opt in norm.get("valid_options", []):
                for code in opt.get("required_courses", []):
                    _add(code, gid)

    # Approved pools.
    for pool_def in reqs.get("approved_pools", []):
        pid = pool_def.get("pool_id", "unknown_pool")
        for code in pool_def.get("courses", []):
            _add(code.upper(), pid)

    return {code: sorted(cats) for code, cats in membership.items()}


def detect_exclusion_conflicts(
    completed_courses: list[str],
    course_index: dict[str, Any],
    category_membership: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Detect exclusion conflicts among completed courses.

    A conflict exists when any two completed courses exclude each
    other.  Conflicts are canonicalized so each pair appears once.
    """
    conflicts: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, code_a in enumerate(completed_courses):
        course_a = course_index.get(code_a)
        if not course_a:
            continue
        exclusions_a = [
            e.upper() for e in course_a.get("exclusions", [])
        ]
        for code_b in completed_courses[i + 1:]:
            course_b = course_index.get(code_b)
            if not course_b:
                continue
            exclusions_b = [
                e.upper() for e in course_b.get("exclusions", [])
            ]
            a_excludes_b = code_b in exclusions_a
            b_excludes_a = code_a in exclusions_b

            if not a_excludes_b and not b_excludes_a:
                continue

            pair = tuple(sorted([code_a, code_b]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            sources: list[dict[str, str]] = []
            if a_excludes_b:
                sources.append({
                    "source_course": code_a,
                    "excluded_course": code_b,
                })
            if b_excludes_a:
                sources.append({
                    "source_course": code_b,
                    "excluded_course": code_a,
                })

            cats = (category_membership.get(code_a, [])
                    + category_membership.get(code_b, []))
            affected = sorted(set(cats))

            conflicts.append({
                "course_a": pair[0],
                "course_b": pair[1],
                "relationship_sources": sources,
                "affected_categories": affected,
                "review_status": "manual_review_needed",
                "message": (
                    f"Both {pair[0]} and {pair[1]} appear in "
                    "completed_courses. The audit does not determine "
                    "which course receives official credit."
                ),
            })

    return conflicts


def build_course_allocations(
    completed_courses: list[str],
    course_index: dict[str, Any],
    category_membership: dict[str, list[str]],
    exclusion_conflicts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build per-course allocation entries with eligibility and status.

    Allocates courses to categories based on membership and conflict
    status.  Does not automatically double-count.
    """
    conflict_codes: set[str] = set()
    for c in exclusion_conflicts:
        conflict_codes.add(c["course_a"])
        conflict_codes.add(c["course_b"])

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_credits = 0.0
    multi_count = 0
    conflict_count = 0
    unclear_count = 0

    for code in completed_courses:
        if code in seen:
            continue
        seen.add(code)

        course = course_index.get(code)
        if not course:
            continue
        credits = float(course.get("credits", 0))
        total_credits += credits
        verification = course.get("verification_status", "unknown")
        eligible = category_membership.get(code, [])
        has_conflict = code in conflict_codes
        is_multi = len(eligible) > 1

        allocated: list[str] = []
        provisional: list[str] = []
        status = "unambiguous"
        reasons: list[str] = []

        if has_conflict:
            status = "manual_review_needed"
            provisional = eligible
            conflict_count += 1
            reasons.append(
                "Course involved in exclusion conflict."
            )
        elif is_multi:
            status = "manual_review_needed"
            provisional = eligible
            multi_count += 1
            unclear_count += 1
            reasons.append(
                "Eligible for multiple categories — official "
                "double-counting policy is not encoded."
            )
        elif eligible:
            if verification != "calendar_verified":
                status = "needs_official_verification"
                reasons.append(
                    f"Course is {verification}."
                )
            allocated = eligible
        else:
            status = "not_applicable"

        entries.append({
            "course_code": code,
            "credits": credits,
            "verification_status": verification,
            "eligible_categories": eligible,
            "allocated_categories": allocated,
            "provisional_categories": provisional,
            "allocation_status": status,
            "review_reasons": reasons,
        })

    return {
        "summary": {
            "unique_known_completed_courses": len(entries),
            "unique_catalog_credits_completed": total_credits,
            "courses_in_multiple_categories": multi_count,
            "courses_with_exclusion_conflicts": conflict_count,
            "courses_with_unclear_allocation": unclear_count,
            "program_counted_credits": None,
            "program_counted_credit_status": "not_computed_in_v1",
        },
        "entries": entries,
    }


def build_course_classification_summaries(
    normalized_input: dict[str, Any],
    course_index: dict[str, Any],
) -> dict[str, Any]:
    """Build top-level unknown and unverified course summaries."""
    unknown: list[dict[str, Any]] = []
    for code in normalized_input.get("unknown_courses", []):
        unknown.append({
            "course_code": code,
            "reason": "not_found_in_catalog",
        })

    unverified: list[dict[str, Any]] = []
    seen_uv: set[str] = set()
    for code in normalized_input.get("unverified_courses", []):
        if code in seen_uv:
            continue
        seen_uv.add(code)
        course = course_index.get(code, {})
        unverified.append({
            "course_code": code,
            "verification_status": course.get(
                "verification_status", "unknown"
            ),
            "verification_note": course.get("verification_note", ""),
        })

    return {
        "unknown_courses": unknown,
        "unverified_courses": unverified,
    }


def _compute_overall_review_status(
    requirement_results: dict[str, Any],
    pool_results: dict[str, Any],
    special_rules: dict[str, Any],
    exclusion_conflicts: list[dict[str, Any]],
    allocations: dict[str, Any],
    unverified_list: list[dict[str, Any]],
) -> str:
    """Compute overall review status with precedence:
    manual_review_needed > needs_official_verification > clear.
    """
    # Check for manual review triggers.
    if exclusion_conflicts:
        return "manual_review_needed"

    alloc_summary = allocations.get("summary", {})
    if alloc_summary.get("courses_with_unclear_allocation", 0) > 0:
        return "manual_review_needed"

    # Only consider requirements/pools with actual progress.
    for r in requirement_results.values():
        if r.get("progress_status") != "not_started" and \
           r.get("review_status") == "manual_review_needed":
            return "manual_review_needed"
    for p in pool_results.values():
        if p.get("progress_status") != "not_started" and \
           p.get("review_status") == "manual_review_needed":
            return "manual_review_needed"
    for sr in special_rules.values():
        if isinstance(sr, dict) and sr.get("review_status") == "manual_review_needed":
            return "manual_review_needed"

    if unverified_list:
        return "needs_official_verification"

    for r in requirement_results.values():
        if r.get("progress_status") != "not_started" and \
           r.get("review_status") == "needs_official_verification":
            return "needs_official_verification"
    for p in pool_results.values():
        if p.get("progress_status") != "not_started" and \
           p.get("review_status") == "needs_official_verification":
            return "needs_official_verification"

    return "clear"


def _compute_overall_status(
    requirement_results: dict[str, Any],
    pool_results: dict[str, Any],
    special_rules: dict[str, Any],
) -> str:
    """Compute a conservative overall status.

    Returns one of: ``not_started``, ``in_progress``,
    ``completed_with_review_needed``, ``completed_provisionally``.
    """
    any_progress = False
    all_complete = True
    any_review_issue = False

    for r in requirement_results.values():
        ps = r.get("progress_status", "not_started")
        rs = r.get("review_status", "clear")
        if ps != "not_started":
            any_progress = True
        if ps not in ("completed",):
            all_complete = False
        if rs != "clear":
            any_review_issue = True

    for p in pool_results.values():
        ps = p.get("progress_status", "not_started")
        rs = p.get("review_status", "clear")
        if ps != "not_started":
            any_progress = True
        if ps != "completed":
            all_complete = False
        if rs != "clear":
            any_review_issue = True

    for sr_key in ["rule_300_level_minimum", "rule_csc_minimum"]:
        sr = special_rules.get(sr_key, {})
        if sr.get("rule_status") not in ("met",):
            all_complete = False
    for sr_key in ["rule_csc_maximum", "rule_designator_concentration"]:
        sr = special_rules.get(sr_key, {})
        if sr.get("rule_status") == "exceeded":
            all_complete = False

    if not any_progress:
        return "not_started"
    if all_complete and any_review_issue:
        return "completed_with_review_needed"
    if all_complete:
        return "completed_provisionally"
    return "in_progress"
