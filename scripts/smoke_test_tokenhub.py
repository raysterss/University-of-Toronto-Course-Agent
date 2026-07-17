#!/usr/bin/env python3
"""Manual smoke test for Tencent TokenHub connectivity.

This script is for **manual local testing only**.  It is not part of the
pytest suite and should not be run automatically.

Requirements:
    TOKENHUB_API_KEY  — your TokenHub API key
    TOKENHUB_BASE_URL — the TokenHub endpoint base URL
    TOKENHUB_MODEL    — the model name to use (e.g. deepseek-chat)

Usage:
    python3 scripts/smoke_test_tokenhub.py
"""

import os
import sys

# --- optional .env support ------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env vars must already be set

# --- path setup so we can import from src/ --------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.model import TencentTokenHubModel  # noqa: E402


def main() -> None:
    # Validate environment before constructing the model.
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

    try:
        model = TencentTokenHubModel()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    messages = [
        {"role": "user", "content": "Reply with exactly: TokenHub connection OK"}
    ]

    print("Sending test message to TokenHub ...")
    try:
        response = model.generate_response(messages)
        print(f"Model response: {response}")
    except RuntimeError as exc:
        print(f"ERROR: API call failed — {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
