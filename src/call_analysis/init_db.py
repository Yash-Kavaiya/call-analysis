"""Database initialization script."""

from __future__ import annotations

import asyncio
import logging
import sys

from call_analysis.config import get_settings
from call_analysis.database import check_db_connection, init_db
from call_analysis.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


async def main() -> int:
    """Initialize database tables."""
    settings = get_settings()
    logger.info("Initializing database", environment=settings.environment)

    try:
        # Check connection first
        connected = await check_db_connection()
        if not connected:
            logger.error("Cannot connect to database. Check DB_* environment variables.")
            return 1
    except Exception as e:
        logger.exception("Database initialization failed", error=str(e))
        return 1
    else:
        # Create tables
        await init_db()
        logger.info("Database initialized successfully")
        return 0
    finally:
        from call_analysis.database import close_db

        await close_db()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
