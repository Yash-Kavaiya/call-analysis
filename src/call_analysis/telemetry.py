"""OpenTelemetry instrumentation for distributed tracing and metrics."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode

from call_analysis.config import get_settings

_settings = get_settings()
logger = logging.getLogger(__name__)

_tracer_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None


def setup_telemetry(app=None) -> None:
    """Initialize OpenTelemetry tracing and metrics."""
    global _tracer_provider, _meter_provider

    settings = get_settings()
    
    if not settings.telemetry.enabled or settings.is_testing:
        logger.info("Telemetry disabled")
        return

    resource = Resource.create({
        "service.name": settings.telemetry.service_name,
        "service.version": settings.telemetry.service_version,
        "deployment.environment": settings.telemetry.environment,
    })

    # Tracer provider
    _tracer_provider = TracerProvider(resource=resource)
    span_processor = BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint=_settings.telemetry.exporter_endpoint,
            headers=_settings.telemetry.exporter_headers,
        )
    )
    _tracer_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(_tracer_provider)

    # Meter provider
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=_settings.telemetry.exporter_endpoint,
            headers=_settings.telemetry.exporter_headers,
        ),
        export_interval_millis=_settings.telemetry.metrics_interval * 1000,
    )
    _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(_meter_provider)

    # Auto-instrumentation
    if app:
        FastAPIInstrumentor.instrument_app(app)

    SQLAlchemyInstrumentor().instrument(enable_commenter=True)
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)

    logger.info(
        "OpenTelemetry initialized",
        service=_settings.telemetry.service_name,
        endpoint=_settings.telemetry.exporter_endpoint,
    )


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer instance."""
    return trace.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    """Get a meter instance."""
    return metrics.get_meter(name)


# Custom metrics
meter = get_meter("call_analysis")

# Counters
calls_processed = meter.create_counter(
    "calls_processed_total",
    description="Total number of calls processed",
    unit="1",
)

calls_failed = meter.create_counter(
    "calls_failed_total",
    description="Total number of failed call processing",
    unit="1",
)

api_requests = meter.create_counter(
    "api_requests_total",
    description="Total API requests",
    unit="1",
)

api_errors = meter.create_counter(
    "api_errors_total",
    description="Total API errors",
    unit="1",
)

webhook_deliveries = meter.create_counter(
    "webhook_deliveries_total",
    description="Total webhook deliveries",
    unit="1",
)

# Histograms
call_processing_duration = meter.create_histogram(
    "call_processing_duration_seconds",
    description="Call processing duration",
    unit="s",
)

api_request_duration = meter.create_histogram(
    "api_request_duration_seconds",
    description="API request duration",
    unit="s",
)

# Gauges
active_jobs = meter.create_up_down_counter(
    "active_jobs",
    description="Currently active processing jobs",
    unit="1",
)

queue_depth = meter.create_up_down_counter(
    "queue_depth",
    description="Task queue depth",
    unit="1",
)


@asynccontextmanager
async def traced_operation(name: str, attributes: dict[str, Any] | None = None):
    """Context manager for tracing an operation."""
    tracer = get_tracer("call_analysis")
    with tracer.start_as_current_span(name, kind=SpanKind.INTERNAL) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        try:
            yield span
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def record_call_processed(organization_id: str, status: str, duration: float) -> None:
    """Record call processing metrics."""
    calls_processed.add(1, {"organization_id": organization_id, "status": status})
    call_processing_duration.record(duration, {"organization_id": organization_id, "status": status})
    if status == "failed":
        calls_failed.add(1, {"organization_id": organization_id})


def record_api_request(method: str, path: str, status_code: int, duration: float) -> None:
    """Record API request metrics."""
    api_requests.add(1, {"method": method, "path": path, "status": str(status_code)})
    api_request_duration.record(duration, {"method": method, "path": path})
    if status_code >= 400:
        api_errors.add(1, {"method": method, "path": path, "status": str(status_code)})


def record_webhook_delivery(organization_id: str, event_type: str, success: bool) -> None:
    """Record webhook delivery metrics."""
    webhook_deliveries.add(1, {"organization_id": organization_id, "event_type": event_type, "success": str(success).lower()})


def set_active_jobs(count: int) -> None:
    """Set active jobs gauge."""
    active_jobs.add(count)


def set_queue_depth(queue: str, depth: int) -> None:
    """Set queue depth gauge."""
    queue_depth.add(depth, {"queue": queue})


async def shutdown_telemetry() -> None:
    """Shutdown telemetry providers."""
    global _tracer_provider, _meter_provider
    if _tracer_provider:
        _tracer_provider.shutdown()
        _tracer_provider = None
    if _meter_provider:
        _meter_provider.shutdown()
        _meter_provider = None
    logger.info("Telemetry shutdown complete")