"""SQLAlchemy ORM models for production database."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class JobStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Organization(Base):
    """Multi-tenant organization."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    users: Mapped[list[User]] = relationship(back_populates="organization", lazy="selectin")
    calls: Mapped[list[CallRecordModel]] = relationship(
        back_populates="organization", lazy="dynamic"
    )
    api_keys: Mapped[list[APIKey]] = relationship(back_populates="organization", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name={self.name!r})>"


class User(Base):
    """System user with role-based access."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="users", lazy="selectin")
    api_keys: Mapped[list[APIKey]] = relationship(back_populates="user", lazy="selectin")

    __table_args__ = (Index("ix_users_org_email", "organization_id", "email"),)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email!r}, role={self.role.value})>"


class APIKey(Base):
    """API keys for programmatic access."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="api_keys", lazy="selectin")
    user: Mapped[User | None] = relationship(back_populates="api_keys", lazy="selectin")

    def __repr__(self) -> str:
        return f"<APIKey(id={self.id}, name={self.name!r}, prefix={self.prefix})>"


class CallRecordModel(Base):
    """Analyzed call recording (SQLAlchemy). Named separately from the dataclass."""

    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.PENDING, nullable=False, index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    progress_pct: Mapped[float] = mapped_column(default=0.0, nullable=False)
    progress_message: Mapped[str] = mapped_column(default="", nullable=False)
    duration_sec: Mapped[float | None] = mapped_column()
    language: Mapped[str | None] = mapped_column(String(10))
    full_transcript: Mapped[str] = mapped_column(Text, default="", nullable=False)
    scrubbed_transcript: Mapped[str] = mapped_column(Text, default="", nullable=False)
    segments: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    pii_findings: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    agents: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    waveform_peaks: Mapped[list[float]] = mapped_column(JSON, default=list, nullable=False)
    call_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped[Organization] = relationship(back_populates="calls", lazy="selectin")
    events: Mapped[list[CallEvent]] = relationship(
        back_populates="call", lazy="dynamic", order_by="CallEvent.created_at"
    )

    __table_args__ = (
        Index("ix_calls_org_status", "organization_id", "status"),
        Index("ix_calls_org_created", "organization_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<CallRecordModel(id={self.id}, filename={self.filename!r}, "
            f"status={self.status.value})>"
        )


class CallEvent(Base):
    """Audit log events for call processing."""

    __tablename__ = "call_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    level: Mapped[str] = mapped_column(String(20), default="INFO", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    call: Mapped[CallRecordModel] = relationship(back_populates="events", lazy="selectin")

    __table_args__ = (Index("ix_call_events_call_type", "call_id", "event_type"),)

    def __repr__(self) -> str:
        return f"<CallEvent(call_id={self.call_id}, type={self.event_type!r})>"


class Webhook(Base):
    """Webhook subscriptions for event notifications."""

    __tablename__ = "webhooks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    events: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    organization: Mapped[Organization] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<Webhook(id={self.id}, name={self.name!r}, url={self.url!r})>"


class WebhookDelivery(Base):
    """Webhook delivery attempts for debugging."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    webhook: Mapped[Webhook] = relationship(lazy="selectin")

    __table_args__ = (Index("ix_webhook_deliveries_webhook_created", "webhook_id", "created_at"),)

    def __repr__(self) -> str:
        return (
            f"<WebhookDelivery(webhook_id={self.webhook_id}, "
            f"event={self.event_type!r}, attempt={self.attempt})>"
        )


class SystemMetric(Base):
    """System metrics for monitoring."""

    __tablename__ = "system_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(nullable=False)
    labels: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    __table_args__ = (Index("ix_system_metrics_name_time", "metric_name", "timestamp"),)

    def __repr__(self) -> str:
        return (
            f"<SystemMetric(name={self.metric_name!r}, value={self.metric_value}, "
            f"labels={self.labels})>"
        )


# =============================================================================
# Domain Models (Dataclasses) - for pipeline data transfer
# =============================================================================

from dataclasses import asdict, dataclass, field  # noqa: E402
from typing import Any  # noqa: E402


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: str = "SPEAKER_00"
    sentiment: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TranscriptSegment:
        return cls(
            start=float(data["start"]),
            end=float(data["end"]),
            text=str(data["text"]),
            speaker=str(data.get("speaker") or "SPEAKER_00"),
            sentiment=data.get("sentiment"),
        )


@dataclass
class PiiFinding:
    entity_type: str
    start: int
    end: int
    redaction: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PiiFinding:
        return cls(
            entity_type=str(data["entity_type"]),
            start=int(data["start"]),
            end=int(data["end"]),
            redaction=str(data["redaction"]),
        )


@dataclass
class AgentResult:
    name: str
    summary: str
    score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentResult:
        return cls(
            name=str(data.get("name") or ""),
            summary=str(data.get("summary") or ""),
            score=data.get("score"),
            details=dict(data.get("details") or {}),
            raw_text=str(data.get("raw_text") or ""),
        )


@dataclass
class CallRecord:
    id: str
    filename: str
    source_path: str
    status: str = JobStatus.PENDING.value
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    duration_sec: float | None = None
    language: str | None = None
    error: str | None = None
    progress_pct: float = 0.0
    progress_message: str = ""
    full_transcript: str = ""
    scrubbed_transcript: str = ""
    segments: list[TranscriptSegment] = field(default_factory=list)
    pii_findings: list[PiiFinding] = field(default_factory=list)
    agents: dict[str, AgentResult] = field(default_factory=dict)
    waveform_peaks: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "source_path": self.source_path,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "duration_sec": self.duration_sec,
            "language": self.language,
            "error": self.error,
            "progress_pct": self.progress_pct,
            "progress_message": self.progress_message,
            "full_transcript": self.full_transcript,
            "scrubbed_transcript": self.scrubbed_transcript,
            "segments": [s.to_dict() for s in self.segments],
            "pii_findings": [p.to_dict() for p in self.pii_findings],
            "agents": {k: v.to_dict() for k, v in self.agents.items()},
            "waveform_peaks": self.waveform_peaks,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CallRecord:
        agents_raw = data.get("agents") or {}
        agents = {
            k: AgentResult.from_dict(v) if isinstance(v, dict) else v for k, v in agents_raw.items()
        }
        return cls(
            id=str(data["id"]),
            filename=str(data.get("filename") or ""),
            source_path=str(data.get("source_path") or ""),
            status=str(data.get("status") or JobStatus.PENDING.value),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            duration_sec=data.get("duration_sec"),
            language=data.get("language"),
            error=data.get("error"),
            progress_pct=float(data.get("progress_pct") or 0.0),
            progress_message=str(data.get("progress_message") or ""),
            full_transcript=str(data.get("full_transcript") or ""),
            scrubbed_transcript=str(data.get("scrubbed_transcript") or ""),
            segments=[TranscriptSegment.from_dict(s) for s in (data.get("segments") or [])],
            pii_findings=[PiiFinding.from_dict(p) for p in (data.get("pii_findings") or [])],
            agents=agents,
            waveform_peaks=list(data.get("waveform_peaks") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def touch(self) -> None:
        self.updated_at = utc_now_iso()
