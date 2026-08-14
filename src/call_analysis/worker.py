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

    # Worker arguments
    argv = [
        "worker",
        "--loglevel=INFO",
        "--concurrency=4",
        "--pool=prefork",
        "--queues=default,analysis,batch,webhooks,maintenance",
        "--hostname=call-analysis@%h",
    ]

    if settings.is_development:
        argv.extend(["--reload", "--autoreload"])

    try:
        celery_app.worker_main(argv)
        return 0
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
        return 0
    except Exception as e:
        logger.exception("Worker failed", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())