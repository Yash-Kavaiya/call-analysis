"""Database engine, session management, and initialization."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from call_analysis.config import get_settings
from call_analysis.models import Base

logger = logging.getLogger(__name__)

_settings = get_settings()

# Async engine for FastAPI
async_engine = create_async_engine(
    _settings.database.async_url,
    pool_size=_settings.database.pool_size,
    max_overflow=_settings.database.max_overflow,
    pool_timeout=_settings.database.pool_timeout,
    pool_recycle=_settings.database.pool_recycle,
    echo=_settings.database.echo,
    echo_pool=_settings.database.echo_pool,
    pool_pre_ping=True,
)

# Sync engine for Alembic and Celery workers
sync_engine = create_engine(
    _settings.database.url,
    pool_size=_settings.database.pool_size,
    max_overflow=_settings.database.max_overflow,
    pool_timeout=_settings.database.pool_timeout,
    pool_recycle=_settings.database.pool_recycle,
    echo=_settings.database.echo,
    echo_pool=_settings.database.echo_pool,
    pool_pre_ping=True,
)

# Session factories
AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)

SyncSessionLocal = sessionmaker(
    sync_engine, class_=Session, expire_on_commit=False, autoflush=False
)


# Connection event listeners for logging
# (SQLAlchemy passes opaque connection objects — Any is intentional)
@event.listens_for(sync_engine, "connect")
def on_connect(dbapi_conn: Any, connection_record: Any) -> None:
    logger.debug("Database connection established")


@event.listens_for(sync_engine, "checkout")
def on_checkout(dbapi_conn: Any, connection_record: Any, connection_proxy: Any) -> None:
    logger.debug("Database connection checked out")


@event.listens_for(sync_engine, "checkin")
def on_checkin(dbapi_conn: Any, connection_record: Any) -> None:
    logger.debug("Database connection checked in")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_session() -> Session:
    """Get synchronous database session for Celery workers."""
    return SyncSessionLocal()


@asynccontextmanager
async def async_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for async session outside of FastAPI."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def sync_session_context() -> Session:
    """Context manager for sync session."""
    return SyncSessionLocal()


async def init_db() -> None:
    """Initialize database tables (development only - use Alembic in production)."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")


async def check_db_connection() -> bool:
    """Check database connectivity."""
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database connection check failed")
        return False
    return True


async def close_db() -> None:
    """Close database connections."""
    await async_engine.dispose()
    sync_engine.dispose()
    logger.info("Database connections closed")


# Health check helper
async def get_db_health() -> dict[str, Any]:
    """Get database health status."""
    try:
        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1 as ok, version()"))
            row = result.fetchone()
            return {
                "connected": True,
                "version": row[1] if row else "unknown",
            }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
        }
