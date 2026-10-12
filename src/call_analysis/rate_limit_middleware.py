"""HTTP rate limiting middleware (Redis-backed with in-memory fallback)."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

from call_analysis.config import get_settings

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

_memory_buckets: dict[str, list[float]] = defaultdict(list)
_LIMIT_RE = re.compile(r"^(\d+)\s*/\s*(\w+)$")


def _parse_limit(spec: str) -> tuple[int, int]:
    match = _LIMIT_RE.match(spec.strip())
    if not match:
        return 100, 60
    count = int(match.group(1))
    unit = match.group(2).lower()
    window = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}.get(unit, 60)
    return count, window


def _path_limit(path: str, settings: Any) -> str:
    if "/upload" in path:
        return settings.ratelimit.upload_limit
    if "/analyze" in path:
        return settings.ratelimit.analyze_limit
    if "/copilot" in path:
        return settings.ratelimit.copilot_limit
    return settings.ratelimit.default_limit


def _memory_check(key: str, limit: int, window: int) -> tuple[bool, dict[str, int]]:
    now = time.time()
    bucket = _memory_buckets[key]
    _memory_buckets[key] = [t for t in bucket if t > now - window]
    allowed = len(_memory_buckets[key]) < limit
    if allowed:
        _memory_buckets[key].append(now)
    remaining = max(0, limit - len(_memory_buckets[key]))
    return allowed, {"remaining": remaining, "reset_time": int(now + window)}


async def rate_limit_middleware(request: Request, call_next: object) -> Response:
    from starlette.responses import Response as StarletteResponse

    settings = get_settings()
    if not settings.ratelimit.enabled or request.url.path == "/metrics":
        return await call_next(request)  # type: ignore[call-arg, misc]

    limit_spec = _path_limit(request.url.path, settings)
    limit, window = _parse_limit(limit_spec)
    client = request.client.host if request.client else "unknown"
    key = f"{client}:{request.method}:{request.url.path}"

    allowed = True
    info: dict[str, int] = {"remaining": limit, "reset_time": int(time.time() + window)}

    if settings.ratelimit.storage_url.startswith("memory"):
        allowed, info = _memory_check(key, limit, window)
    else:
        try:
            from call_analysis.redis_client import RateLimiter

            limiter = RateLimiter()
            allowed, info = await limiter.check_limit(key, limit, window)
        except Exception:
            allowed, info = _memory_check(key, limit, window)

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(info.get("remaining", 0)),
                "X-RateLimit-Reset": str(info.get("reset_time", 0)),
            },
        )

    response: StarletteResponse = await call_next(request)  # type: ignore[call-arg, misc]
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", limit))
    response.headers["X-RateLimit-Reset"] = str(info.get("reset_time", 0))
    return response
