"""Celery worker entry point."""

from __future__ import annotations

import logging
import sys

from call_analysis.celery_app import celery_app
from call_analysis.config import get_settings
from call_analysis.logging_config import setup_logging

# Setup logging before anything else
setup_logging()

logger = logging.getLogger(__name__)
settings = get_settings()


def main() -> int:
    """Run Celery worker."""
    logger.info("Starting Celery worker", version=settings.app_version)

    # prefork is not available on Windows; fall back to the solo pool there.
    import sys as _sys

    pool = "prefork" if _sys.platform != "win32" else "solo"

    # Worker arguments
    argv = [
        "worker",
        "--loglevel=INFO",
        "--concurrency=4",
        f"--pool={pool}",
        "--queues=default,analysis,batch,webhooks,maintenance",
        "--hostname=call-analysis@%h",
    ]

    try:
        celery_app.worker_main(argv)
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
        return 0
    except Exception as e:
        logger.exception("Worker failed", error=str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
