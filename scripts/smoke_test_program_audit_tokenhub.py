#!/usr/bin/env python3
"""Manual smoke test for the integrated program-progress audit with TokenHub.

This script is for **manual local testing only**.  It is not part of the
pytest suite and should not be run automatically.

Verifies that the agent selects and calls audit_program_progress for a
program-progress question and that the audit result contains expected
structured fields.

Requirements:
    TOKENHUB_API_KEY  — your TokenHub API key
    TOKENHUB_BASE_URL — the TokenHub endpoint base URL
    TOKENHUB_MODEL    — the model name to use (e.g. deepseek-chat)

Usage:
    python3 scripts/smoke_test_program_audit_tokenhub.py
"""

import os
import sys

# --- optional .env support ------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv(".env")
except ImportError:
    pass  # python-dotenv not installed — env vars must already be set

# --- path setup so we can import from src/ --------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.model import TencentTokenHubModel  # noqa: E402
from src.agent import CoursePlanningAgent  # noqa: E402


def main() -> None:
    # --- validate environment variables ----------------------------------
    missing = []
    for var in ("TOKENHUB_API_KEY", "TOKENHUB_BASE_URL", "TOKENHUB_MODEL"):
        if not os.environ.get(var, "").strip():
            missing.append(var)

    if missing:
        print("ERROR: Missing environment variables:")
        for var in missing:
            print(f"  - {var}")
        print(
            "\nSet them directly or via a .env file "
            "(python-dotenv required for .env support)."
        )
        sys.exit(1)

    # --- instantiate model -----------------------------------------------
    try:
        model = TencentTokenHubModel()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    # --- instantiate agent -----------------------------------------------
    agent = CoursePlanningAgent(
        completed_courses=[
            "COG100H1", "CSC108H1", "CSC148H1",
            "MAT135H1", "MAT136H1", "STA237H1",
        ],
        model=model,
    )

    request = (
        "I have completed COG100H1, CSC108H1, CSC148H1, MAT135H1, "
        "MAT136H1, and STA237H1. What requirements have I completed, "
        "what am I still missing, and what factual requirement items "
        "remain for the ASMAJ1446A Computational Cognition Stream?"
    )

    print("=" * 70)
    print("Program Audit — TokenHub Smoke Test")
    print("=" * 70)
    print(f"Request: {request}")
    print()

    # --- run agent -------------------------------------------------------
    try:
        result = agent.handle_request(request, max_tool_steps=2)
    except RuntimeError as exc:
        print(f"ERROR: API call failed — {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Agent execution failed — {exc}")
        sys.exit(1)

    # --- verification assertions -----------------------------------------
    steps = result.get("steps", [])
    stop_reason = result.get("stop_reason", "unknown")
    tools_called = [s.get("tool_called", "") for s in steps]
    final_answer = result.get("final_answer", "")

    # 1. At least one tool was called.
    if not steps:
        print("FAIL: No tool was called.")
        print(f"  stop_reason: {stop_reason}")
        if result.get("parse_error"):
            print(f"  parse_error: {result['parse_error']}")
        if result.get("last_model_response"):
            print(f"  last_model_response: {result['last_model_response']}")
        sys.exit(1)

    # 2. audit_program_progress appears in the tool sequence.
    if "audit_program_progress" not in tools_called:
        print(f"FAIL: audit_program_progress not in tool sequence. "
              f"Got: {tools_called}")
        sys.exit(1)

    # 3. The audit tool arguments contain completed_courses.
    audit_step = next(
        (s for s in steps if s.get("tool_called") == "audit_program_progress"),
        None,
    )
    if audit_step is None:
        print("FAIL: Could not find audit step.")
        sys.exit(1)

    audit_args = audit_step.get("arguments", {})
    if "completed_courses" not in audit_args:
        print(f"FAIL: completed_courses missing from audit arguments. "
              f"Got: {audit_args}")
        sys.exit(1)

    # 4. The observation contains requirement_results.
    observation = audit_step.get("observation", "")
    if "requirement" not in observation.lower():
        print("FAIL: observation does not contain requirement_results.")
        sys.exit(1)

    # 5. The observation contains priority_items.
    if "priority" not in observation.lower():
        print("FAIL: observation does not contain priority_items.")
        sys.exit(1)

    # 6. Non-empty final answer.
    if not final_answer.strip():
        print("FAIL: final_answer is empty.")
        sys.exit(1)

    # 7. Normal stop reason.
    if stop_reason not in ("finish", "max_steps"):
        print(f"FAIL: unexpected stop_reason: {stop_reason}")
        sys.exit(1)

    # --- verification passed — print report ------------------------------
    print("PASS: audit_program_progress was correctly called.")
    print()

    print(f"stop_reason: {stop_reason}")
    print(f"tool sequence: {tools_called}")
    print()

    print("-" * 70)
    for i, step in enumerate(steps, start=1):
        print(f"Step {i}:")
        print(f"  tool_called: {step.get('tool_called', '?')}")
        print(f"  arguments:   {step.get('arguments', {})}")
        print(f"  observation:")
        # Extract key audit fields from the observation.
        obs = step.get("observation", "")
        lines = obs.split("\n")
        for line in lines[:5]:
            print(f"    {line}")
        if len(lines) > 5:
            print(f"    ... ({len(lines)} lines total)")
        print()

    # Extract audit summary from the last tool observation.
    if audit_step:
        obs = audit_step.get("observation", "")
        # Parse overall status from observation.
        overall_status = ""
        overall_review = ""
        for line in obs.split("\n"):
            if line.startswith("Program audit") and "overall=" in line:
                overall_status = line
            if "priority" in line.lower() and "items" in line.lower():
                # Parse count.
                import re
                m = re.search(r"(\d+)", line)
                priority_count = int(m.group(1)) if m else 0

        print(f"  audit overall_status line: {overall_status.strip() if overall_status else '(not found in observation)'}")
        print(f"  priority items count: {priority_count if 'priority_count' in dir() else '?'}")
        print("-" * 70)

    print(f"final_answer:")
    print(f"  {final_answer}")
    print()


if __name__ == "__main__":
    main()
