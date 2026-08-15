"""Contact center intelligence platform — NVIDIA-powered call analysis."""

__version__ = "0.4.0"

from call_analysis.config import Settings, get_settings
from call_analysis.database import close_db, get_async_session, init_db
from call_analysis.models import (
    APIKey,
    CallEvent,
    CallRecord,
    CallRecordModel,
    JobStatus,
    Organization,
    SystemMetric,
    User,
    UserRole,
    Webhook,
    WebhookDelivery,
)
from call_analysis.schemas import (
    AnalyticsSummary,
    APIKeyRead,
    CallRecordRead,
    HealthResponse,
    OrganizationRead,
    Token,
    UserRead,
)

__all__ = [
    "APIKey",
    "APIKeyRead",
    "AnalyticsSummary",
    "CallEvent",
    "CallRecord",
    "CallRecordModel",
    "CallRecordRead",
    "HealthResponse",
    "JobStatus",
    "Organization",
    "OrganizationRead",
    "Settings",
    "SystemMetric",
    "Token",
    "User",
    "UserRead",
    "UserRole",
    "Webhook",
    "WebhookDelivery",
    "close_db",
    "get_async_session",
    "get_settings",
    "init_db",
]
