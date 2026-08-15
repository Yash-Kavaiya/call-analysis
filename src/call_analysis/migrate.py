"""Alembic migration management script."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from call_analysis.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def run_alembic(args: list[str]) -> int:
    """Run alembic command from the project root (so alembic.ini is found)."""
    try:
        result = subprocess.run(
            ["alembic", *args],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
        )
    except FileNotFoundError:
        logger.exception("alembic not found. Install with: pip install alembic")
        return 1
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Database migration management")
    parser.add_argument(
        "command", choices=["upgrade", "downgrade", "revision", "history", "current", "stamp"]
    )
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to alembic")
    parsed = parser.parse_args(argv)

    alembic_args = [parsed.command, *parsed.args]

    # For revision, add message flag if not present
    if parsed.command == "revision" and "-m" not in parsed.args and "--message" not in parsed.args:
        alembic_args.extend(["-m", "Auto-generated revision"])

    return run_alembic(alembic_args)


if __name__ == "__main__":
    sys.exit(main())
