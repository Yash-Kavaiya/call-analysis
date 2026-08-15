"""CLI entry: validate NVIDIA_API_KEY against a hosted NIM endpoint."""

from __future__ import annotations

import argparse
import sys
import traceback

# Robust UTF-8 console output on Windows (cp1252 default can't print emoji).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except (AttributeError, ValueError):
    pass

from call_analysis.config import MissingAPIKeyError, load_nvidia_config
from call_analysis.nim_client import (
    NimAuthError,
    NimError,
    NimHTTPError,
    NimResponseError,
    validate_nim_completion,
)


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911 — exit-code protocol
    parser = argparse.ArgumentParser(
        prog="nim-validate",
        description=(
            "Validate NVIDIA_API_KEY with a simple chat completion against "
            "the hosted NIM catalog (https://integrate.api.nvidia.com/v1)."
        ),
    )
    parser.add_argument(
        "--prompt",
        default="Reply with exactly one word: pong",
        help="User prompt for the smoke completion (default: ping/pong)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds (default: 60)",
    )
    args = parser.parse_args(argv)

    try:
        config = load_nvidia_config(require_key=True)
    except MissingAPIKeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("=== NVIDIA NIM validation ===")
    print(config.redacted_summary())
    print(f"endpoint={config.base_url}/chat/completions")
    print("sending chat completion request...")

    try:
        result = validate_nim_completion(
            config,
            prompt=args.prompt,
            timeout=args.timeout,
        )
    except NimAuthError as exc:
        print(f"AUTH_ERROR: {exc}", file=sys.stderr)
        return 3
    except NimHTTPError as exc:
        print(f"HTTP_ERROR: {exc}", file=sys.stderr)
        return 4
    except NimResponseError as exc:
        print(f"RESPONSE_ERROR: {exc}", file=sys.stderr)
        return 5
    except NimError as exc:
        print(f"NIM_ERROR: {exc}", file=sys.stderr)
        return 6
    except Exception as exc:
        print(f"UNEXPECTED_ERROR: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1

    # Success: non-empty completion body required
    snippet = result.text.replace("\n", " ").strip()
    if len(snippet) > 200:
        snippet = snippet[:200] + "..."

    print(f"status={result.status_code}")
    print(f"model={result.model or config.model}")
    print(f"completion_len={len(result.text)}")
    print(f"completion={snippet}")
    print("SUCCESS: hosted NIM returned a non-empty completion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
