"""Prometheus metrics exposed at GET /metrics."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

calls_processed_total = Counter(
    "calls_processed_total",
    "Total number of calls processed",
    ["status"],
)

call_processing_duration_seconds = Histogram(
    "call_processing_duration_seconds",
    "Call processing duration in seconds",
    ["status"],
)

api_requests_total = Counter(
    "api_requests_total",
    "Total API requests",
    ["method", "path", "status"],
)

api_request_duration_seconds = Histogram(
    "api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "path"],
)

active_jobs = Gauge(
    "active_jobs",
    "Currently active processing jobs",
)

queue_depth = Gauge(
    "queue_depth",
    "Task queue depth",
    ["queue"],
)


def metrics_response() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


async def prometheus_middleware(request: Request, call_next: object) -> Response:
    """Record request counts and latency for Prometheus."""
    from starlette.responses import Response as StarletteResponse

    start = time.perf_counter()
    response: StarletteResponse = await call_next(request)  # type: ignore[call-arg, misc]
    duration = time.perf_counter() - start
    path = request.url.path
    if path == "/metrics":
        return response

    status = str(response.status_code)
    method = request.method
    api_requests_total.labels(method=method, path=path, status=status).inc()
    api_request_duration_seconds.labels(method=method, path=path).observe(duration)

    try:
        from call_analysis.telemetry import record_api_request

        record_api_request(method, path, response.status_code, duration)
    except Exception:
        pass

    return response
