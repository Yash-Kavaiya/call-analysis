"""Alembic migration management script."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys

from call_analysis.config import get_settings
from call_analysis.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def run_alembic(args: list[str]) -> int:
    """Run alembic command."""
    try:
        result = subprocess.run(
            ["alembic"] + args,
            cwd=__file__,
            check=False,
        )
        return result.returncode
    except FileNotFoundError:
        logger.error("alembic not found. Install with: pip install alembic")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Database migration management")
    parser.add_argument("command", choices=["upgrade", "downgrade", "revision", "history", "current", "stamp"])
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to alembic")
    parsed = parser.parse_args(argv)

    alembic_args = [parsed.command] + parsed.args

    # For revision, add message flag if not present
    if parsed.command == "revision" and "-m" not in parsed.args and "--message" not in parsed.args:
        alembic_args.extend(["-m", "Auto-generated revision"])

    return run_alembic(alembic_args)


if __name__ == "__main__":
    sys.exit(main())