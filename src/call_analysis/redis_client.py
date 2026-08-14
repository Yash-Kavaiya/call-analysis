"""Redis client with connection pooling and utilities."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Optional

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from call_analysis.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_pool: Optional[ConnectionPool] = None
_client: Optional[Redis] = None


def get_redis_pool() -> ConnectionPool:
    """Get or create Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            _settings.redis.url,
            max_connections=_settings.redis.max_connections,
            socket_timeout=_settings.redis.socket_timeout,
            socket_connect_timeout=_settings.redis.socket_connect_timeout,
            decode_responses=_settings.redis.decode_responses,
        )
        logger.info("Redis connection pool created")
    return _pool


def get_redis() -> Redis:
    """Get Redis client from pool."""
    global _client
    if _client is None:
        _client = redis.Redis(connection_pool=get_redis_pool())
    return _client


async def close_redis() -> None:
    """Close Redis connections."""
    global _pool, _client
    if _client:
        await _client.close()
        _client = None
    if _pool:
        await _pool.disconnect()
        _pool = None
    logger.info("Redis connections closed")


@asynccontextmanager
async def redis_connection() -> AsyncGenerator[Redis, None]:
    """Context manager for Redis connection."""
    client = get_redis()
    try:
        yield client
    except Exception:
        logger.exception("Redis operation failed")
        raise


async def check_redis_connection() -> bool:
    """Check Redis connectivity."""
    try:
        client = get_redis()
        await client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection check failed: {e}")
        return False


# Key prefixes
class RedisKeys:
    """Redis key prefixes for namespacing."""

    RATE_LIMIT = "ratelimit:"
    SESSION = "session:"
    CACHE = "cache:"
    JOB_STATUS = "job:"
    WEBSOCKET = "ws:"
    LOCK = "lock:"
    IDEMPOTENCY = "idempotency:"

    @staticmethod
    def rate_limit(key: str) -> str:
        return f"{RedisKeys.RATE_LIMIT}{key}"

    @staticmethod
    def job_status(job_id: str) -> str:
        return f"{RedisKeys.JOB_STATUS}{job_id}"

    @staticmethod
    def websocket_sub(org_id: str, call_id: str) -> str:
        return f"{RedisKeys.WEBSOCKET}{org_id}:{call_id}"

    @staticmethod
    def lock(resource: str) -> str:
        return f"{RedisKeys.LOCK}{resource}"

    @staticmethod
    def idempotency(key: str) -> str:
        return f"{RedisKeys.IDEMPOTENCY}{key}"


# Distributed lock
class RedisLock:
    """Distributed lock using Redis."""

    def __init__(self, resource: str, ttl: int = 30, blocking: bool = True, blocking_timeout: int = 10):
        self.resource = resource
        self.ttl = ttl
        self.blocking = blocking
        self.blocking_timeout = blocking_timeout
        self.lock = None

    async def __aenter__(self) -> bool:
        client = get_redis()
        self.lock = client.lock(
            RedisKeys.lock(self.resource),
            timeout=self.ttl,
            blocking=self.blocking,
            blocking_timeout=self.blocking_timeout,
        )
        return await self.lock.acquire()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.lock:
            await self.lock.release()


# Rate limiting helper
class RateLimiter:
    """Token bucket rate limiter using Redis."""

    def __init__(self, client: Redis | None = None):
        self.client = client or get_redis()

    async def check_limit(
        self,
        key: str,
        limit: int,
        window: int,
        cost: int = 1,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Check if request is within rate limit.

        Returns (allowed, info_dict) where info_dict contains:
        - allowed: bool
        - remaining: int
        - reset_time: int (unix timestamp)
        - total_limit: int
        """
        redis_key = RedisKeys.rate_limit(key)
        now = int(__import__("time").time())
        window_start = now - window

        async with self.client.pipeline(transaction=True) as pipe:
            # Remove expired entries
            pipe.zremrangebyscore(redis_key, 0, window_start)
            # Count current requests
            pipe.zcard(redis_key)
            # Add current request
            pipe.zadd(redis_key, {f"{now}:{__import__('uuid').uuid4().hex}": now})
            # Set expiry
            pipe.expire(redis_key, window)
            results = await pipe.execute()

        current_count = results[1] + cost
        allowed = current_count <= limit
        remaining = max(0, limit - current_count)
        reset_time = now + window

        return allowed, {
            "allowed": allowed,
            "remaining": remaining,
            "reset_time": reset_time,
            "total_limit": limit,
            "current_count": current_count,
        }


# Cache helper
class RedisCache:
    """Simple async cache with TTL."""

    def __init__(self, client: Redis | None = None, default_ttl: int = 300):
        self.client = client or get_redis()
        self.default_ttl = default_ttl

    async def get(self, key: str) -> Any | None:
        data = await self.client.get(RedisKeys.CACHE + key)
        if data:
            import json
            return json.loads(data)
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        import json
        return await self.client.set(
            RedisKeys.CACHE + key,
            json.dumps(value),
            ex=ttl or self.default_ttl,
        )

    async def delete(self, key: str) -> bool:
        return await self.client.delete(RedisKeys.CACHE + key) > 0

    async def exists(self, key: str) -> bool:
        return await self.client.exists(RedisKeys.CACHE + key) > 0


# Job status tracking
class JobStatusTracker:
    """Track background job status in Redis."""

    def __init__(self, client: Redis | None = None, ttl: int = 86400):
        self.client = client or get_redis()
        self.ttl = ttl

    async def set_status(
        self,
        job_id: str,
        status: str,
        progress: float = 0.0,
        message: str = "",
        result: Any | None = None,
        error: str | None = None,
    ) -> None:
        import json
        data = {
            "status": status,
            "progress": progress,
            "message": message,
            "result": result,
            "error": error,
            "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
        await self.client.set(
            RedisKeys.job_status(job_id),
            json.dumps(data),
            ex=self.ttl,
        )

    async def get_status(self, job_id: str) -> dict[str, Any] | None:
        import json
        data = await self.client.get(RedisKeys.job_status(job_id))
        if data:
            return json.loads(data)
        return None

    async def update_progress(self, job_id: str, progress: float, message: str = "") -> None:
        status_data = await self.get_status(job_id)
        if status_data:
            status_data["progress"] = progress
            status_data["message"] = message
            await self.set_status(job_id, **status_data)

    async def delete(self, job_id: str) -> bool:
        return await self.client.delete(RedisKeys.job_status(job_id)) > 0