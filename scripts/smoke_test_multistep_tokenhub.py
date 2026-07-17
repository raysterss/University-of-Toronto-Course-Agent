#!/usr/bin/env python3
"""Manual smoke test for the bounded multi-step ReAct agent with TokenHub.

This script is for **manual local testing only**.  It is not part of the
pytest suite and should not be run automatically.

The expected tool sequence for the test query is:
    1. check_prerequisites
    2. check_term_availability

but the script prints whatever the TokenHub model actually chooses —
it does not hard-code any tool sequence.

Requirements:
    TOKENHUB_API_KEY  — your TokenHub API key
    TOKENHUB_BASE_URL — the TokenHub endpoint base URL
    TOKENHUB_MODEL    — the model name to use (e.g. deepseek-chat)

Usage:
    python3 scripts/smoke_test_multistep_tokenhub.py
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
        completed_courses=["CSC148H1", "STA237H1"],
        model=model,
    )

    request = (
        "Can I take CSC384H1 in Winter if I have completed "
        "CSC148H1 and STA237H1?"
    )

    print("=" * 70)
    print("Multi-Step ReAct Agent — TokenHub Smoke Test")
    print("=" * 70)
    print(f"Request: {request}")
    print()

    # --- run agent (multi-step) ------------------------------------------
    try:
        result = agent.handle_request(request, max_tool_steps=2)
    except RuntimeError as exc:
        print(f"ERROR: API call failed — {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Agent execution failed — {exc}")
        sys.exit(1)

    # --- print results ---------------------------------------------------
    steps = result.get("steps", [])
    stop_reason = result.get("stop_reason", "unknown")

    print(f"stop_reason: {stop_reason}")
    print(f"number of steps: {len(steps)}")
    print()

    parse_error_msg = result.get("parse_error")
    if parse_error_msg:
        print(f"parse_error: {parse_error_msg}")
        print()

    last_response = result.get("last_model_response", "")
    if last_response:
        print("last_model_response:")
        print(f"  {last_response}")
        print()

    print("-" * 70)

    for i, step in enumerate(steps, start=1):
        print(f"Step {i}:")
        print(f"  tool_called: {step.get('tool_called', '?')}")
        print(f"  arguments:   {step.get('arguments', {})}")
        print(f"  thought:")
        print(f"    {step.get('thought', '')}")
        print(f"  observation:")
        print(f"    {step.get('observation', '')}")
        print("-" * 70)

    print(f"final_answer:")
    print(f"  {result.get('final_answer', '')}")
    print()


if __name__ == "__main__":
    main()
