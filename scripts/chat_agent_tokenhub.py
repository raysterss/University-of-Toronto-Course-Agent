#!/usr/bin/env python3
"""Interactive chat with the UofT Course Planning Agent using TokenHub.

This script is for **manual local testing only**.

Usage:
    python3 scripts/chat_agent_tokenhub.py
    python3 scripts/chat_agent_tokenhub.py --debug-tools
"""

import argparse
import os
import sys

# --- optional .env support ------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv(".env")
except ImportError:
    pass

# --- path setup ----------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.model import TencentTokenHubModel  # noqa: E402
from src.agent import CoursePlanningAgent  # noqa: E402


def print_tools(result: dict) -> None:
    """Print a compact tool-call summary (debug mode only)."""
    steps = result.get("steps", [])
    if not steps:
        return
    print("[debug] Tools called:")
    for i, s in enumerate(steps, start=1):
        tool = s.get("tool_called", "?")
        args = s.get("arguments", {})
        args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
        print(f"  {i}. {tool}({args_str})")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="UofT Course Planning Agent — interactive chat",
    )
    parser.add_argument(
        "--debug-tools",
        action="store_true",
        help="Print tool calls after each response.",
    )
    args = parser.parse_args()
    debug = args.debug_tools

    # --- validate environment --------------------------------------------
    missing = []
    for var in ("TOKENHUB_API_KEY", "TOKENHUB_BASE_URL", "TOKENHUB_MODEL"):
        if not os.environ.get(var, "").strip():
            missing.append(var)
    if missing:
        print("ERROR: Missing environment variables:")
        for v in missing:
            print(f"  - {v}")
        print(
            "\nSet them via a .env file "
            "(python-dotenv required for .env support)."
        )
        sys.exit(1)

    # --- instantiate model + agent ---------------------------------------
    try:
        model = TencentTokenHubModel()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    agent = CoursePlanningAgent(model=model)

    # --- friendly startup -------------------------------------------------
    print("=" * 62)
    print("  UofT Cognitive Science")
    print("  Computational Cognition Stream course-planning assistant")
    print("  (ASMAJ1446A)")
    print("=" * 62)
    print()
    print("⚠️  This is a student-built prototype — not official UofT advising.")
    print()
    print("To begin, tell me which courses you have completed or are")
    print("currently taking, for example:")
    print()
    print("  COG100H1, CSC108H1, CSC148H1, MAT135H1, MAT136H1, STA237H1")
    print()
    print("Once I know your completed courses I can audit your requirements,")
    print("check prerequisites, and explore stream-pool options.")
    print()
    print("Type 'q' or 'exit' to quit.")
    print()

    while True:
        try:
            user_input = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        # --- run agent ---------------------------------------------------
        try:
            result = agent.handle_request(user_input, max_tool_steps=2)
        except RuntimeError as exc:
            print(f"ERROR: API call failed — {exc}")
            continue
        except Exception as exc:
            print(f"ERROR: Agent execution failed — {exc}")
            continue

        # --- print results -----------------------------------------------
        print()
        final = result.get("final_answer", "")
        print(final)
        print()

        if debug:
            print_tools(result)


if __name__ == "__main__":
    main()
