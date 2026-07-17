#!/usr/bin/env python3
"""Manual smoke test for CoursePlanningAgent with TencentTokenHubModel.

This script is for **manual local testing only**.  It is not part of the
pytest suite and should not be run automatically.

Requirements:
    TOKENHUB_API_KEY  — your TokenHub API key
    TOKENHUB_BASE_URL — the TokenHub endpoint base URL
    TOKENHUB_MODEL    — the model name to use (e.g. deepseek-chat)

Usage:
    python3 scripts/smoke_test_agent_tokenhub.py
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
        completed_courses=["CSC108H1", "CSC148H1", "STA237H1"],
        model=model,
    )

    request = (
        "I am interested in AI and machine learning courses for the "
        "Computational Cognition Stream. What should I consider?"
    )

    print("Running agent with TokenHub model ...")
    print(f"Request: {request}")
    print("-" * 60)

    # --- run agent -------------------------------------------------------
    try:
        result = agent.handle_request(request)
    except RuntimeError as exc:
        print(f"ERROR: API call failed — {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Agent execution failed — {exc}")
        sys.exit(1)

    # --- print results ---------------------------------------------------
    print(f"thought:\n{result['thought']}")
    print("-" * 60)
    print(f"tool_called: {result['tool_called']}")
    print("-" * 60)
    print(f"observation:\n{result['observation']}")
    print("-" * 60)
    print(f"final_answer:\n{result['final_answer']}")


if __name__ == "__main__":
    main()
