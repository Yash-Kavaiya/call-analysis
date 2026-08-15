"""Structured logging configuration with structlog and OpenTelemetry."""

from __future__ import annotations

import logging
import sys
from datetime import UTC
from typing import TYPE_CHECKING, Any

import structlog
from pythonjsonlogger import jsonlogger

from call_analysis.config import get_settings

if TYPE_CHECKING:
    from structlog.types import EventDict, WrappedLogger

_settings = get_settings()


def add_severity_level(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Add severity level to log entry."""
    event_dict["severity"] = method_name.upper()
    return event_dict


def add_timestamp(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Add ISO timestamp to log entry."""
    from datetime import datetime

    event_dict["timestamp"] = datetime.now(UTC).isoformat()
    return event_dict


def redact_sensitive_data(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Redact sensitive keys from log entries."""
    redact_keys = _settings.logging.redact_keys
    for key in list(event_dict.keys()):
        if any(rk in key.lower() for rk in redact_keys):
            event_dict[key] = "***REDACTED***"
    return event_dict


def add_request_id(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Add request ID from context if available."""
    import contextvars

    request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
        "request_id", default=None
    )
    request_id = request_id_var.get()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def setup_logging() -> None:
    """Configure structlog with JSON or console output."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_timestamp,
        add_severity_level,
        add_request_id,
        redact_sensitive_data,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if _settings.logging.format == "json":
        # JSON output for production
        renderer = structlog.processors.JSONRenderer()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(jsonlogger.JsonFormatter())
    else:
        # Console output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
        handler = logging.StreamHandler(sys.stdout)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(_settings.logging.level)

    # Configure structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to use structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )
    handler.setFormatter(formatter)

    # Set levels for noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)

    # File handler if configured
    if _settings.logging.file_path:
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            _settings.logging.file_path,
            maxBytes=_settings.logging.file_max_bytes,
            backupCount=_settings.logging.file_backup_count,
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger instance."""
    return structlog.get_logger(name)


# Context variable for request ID
import contextvars  # noqa: E402 — module-level after setup_logging call

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def set_request_id(request_id: str) -> None:
    """Set request ID for current context."""
    request_id_var.set(request_id)


def clear_request_id() -> None:
    """Clear request ID from context."""
    request_id_var.set(None)


class LoggingMiddleware:
    """ASGI middleware for request logging."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        import time
        import uuid

        from structlog import get_logger

        # ASGI headers are a list of (name, value) tuples
        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", uuid.uuid4().hex[:12])
        if isinstance(request_id, bytes):
            request_id = request_id.decode()

        set_request_id(request_id)
        logger = get_logger("request")
        start_time = time.time()

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                duration = time.time() - start_time
                logger.info(
                    "HTTP request completed",
                    method=scope["method"],
                    path=scope["path"],
                    status_code=message["status"],
                    duration_ms=round(duration * 1000, 2),
                    request_id=request_id,
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration = time.time() - start_time
            logger.exception(
                "HTTP request failed",
                method=scope["method"],
                path=scope["path"],
                duration_ms=round(duration * 1000, 2),
                request_id=request_id,
            )
            raise
        finally:
            clear_request_id()


# Initialize on import
setup_logging()

# Export logger for convenience
logger = get_logger(__name__)
