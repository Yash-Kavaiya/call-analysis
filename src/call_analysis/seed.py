"""Bootstrap default organization and admin user."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from sqlalchemy import select

from call_analysis.auth import hash_password
from call_analysis.config import get_settings
from call_analysis.database import SyncSessionLocal, check_db_connection, init_db
from call_analysis.logging_config import setup_logging
from call_analysis.models import Organization, User, UserRole

setup_logging()
logger = logging.getLogger(__name__)


def seed_sync() -> int:
    settings = get_settings()
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "admin@call-analysis.local")
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "changeme-change-in-production")

    with SyncSessionLocal() as db:
        org = db.execute(select(Organization).where(Organization.slug == "default")).scalar_one_or_none()
        if org is None:
            org = Organization(name="Default Organization", slug="default", settings={})
            db.add(org)
            db.flush()
            logger.info("Created default organization id=%s", org.id)

        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(
                organization_id=org.id,
                email=email,
                hashed_password=hash_password(password),
                full_name="Administrator",
                role=UserRole.ADMIN,
                is_active=True,
                is_superuser=True,
            )
            db.add(user)
            logger.info("Created bootstrap admin user email=%s", email)
        else:
            logger.info("Bootstrap admin already exists email=%s", email)

        db.commit()

    return 0


async def main() -> int:
    connected = await check_db_connection()
    if not connected:
        logger.error("Cannot connect to database for seed")
        return 1
    await init_db()
    return seed_sync()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
