"""Domain models (Pydantic) for API contracts and pipeline data transfer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UserRole(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


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
            k: AgentResult.from_dict(v) if isinstance(v, dict) else v
            for k, v in agents_raw.items()
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
            segments=[
                TranscriptSegment.from_dict(s) for s in (data.get("segments") or [])
            ],
            pii_findings=[
                PiiFinding.from_dict(p) for p in (data.get("pii_findings") or [])
            ],
            agents=agents,
            waveform_peaks=list(data.get("waveform_peaks") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    def touch(self) -> None:
        self.updated_at = utc_now_iso()


# =============================================================================
# Pydantic Models for API Contracts
# =============================================================================


class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    settings: dict[str, Any] | None = None
    is_active: bool | None = None


class OrganizationRead(OrganizationBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserBase(BaseModel):
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    full_name: str | None = Field(None, max_length=255)
    role: UserRole = UserRole.VIEWER


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseModel):
    email: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    full_name: str | None = Field(None, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=8, max_length=128)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    is_active: bool
    is_superuser: bool
    last_login: datetime | None
    created_at: datetime
    updated_at: datetime


class UserReadWithOrg(UserRead):
    organization: OrganizationRead | None = None


class APIKeyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class APIKeyCreate(APIKeyBase):
    pass


class APIKeyRead(APIKeyBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID | None
    prefix: str
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


class APIKeyWithSecret(APIKeyRead):
    key: str


class CallRecordBase(BaseModel):
    filename: str = Field(..., min_length=1, max_length=500)


class CallRecordCreate(CallRecordBase):
    source_path: str = Field(..., min_length=1, max_length=1000)


class CallRecordUpdate(BaseModel):
    filename: str | None = Field(None, min_length=1, max_length=500)
    status: JobStatus | None = None
    error: str | None = None
    progress_pct: float | None = Field(None, ge=0.0, le=1.0)
    progress_message: str | None = None


class CallRecordRead(CallRecordBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    status: JobStatus
    error: str | None
    progress_pct: float
    progress_message: str
    duration_sec: float | None
    language: str | None
    full_transcript: str
    scrubbed_transcript: str
    segments: list[dict[str, Any]]
    pii_findings: list[dict[str, Any]]
    agents: dict[str, dict[str, Any]]
    waveform_peaks: list[float]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class CallRecordListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    duration_sec: float | None
    language: str | None
    error: str | None
    progress_pct: float
    progress_message: str
    qa_score: float | None = None
    pii_count: int = 0


class CallEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    call_id: UUID
    event_type: str
    message: str
    details: dict[str, Any]
    level: str
    created_at: datetime


class AnalyticsSummary(BaseModel):
    total_calls: int
    completed: int
    processing: int
    failed: int
    pending: int
    avg_qa_score: float | None
    avg_compliance_score: float | None
    avg_sentiment_score: float | None
    total_pii_findings: int
    languages: dict[str, int]


class HealthResponse(BaseModel):
    status: str
    nvidia_key_configured: bool
    model: str | None
    base_url: str | None
    api_key_hint: str | None
    version: str
    environment: str
    database_connected: bool
    redis_connected: bool


class CopilotRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class CopilotResponse(BaseModel):
    answer: str


class ImportLocalRequest(BaseModel):
    path: str | None = None
    limit: int = Field(default=1, ge=1, le=50)
    analyze: bool = True
    skip_existing: bool = True


class ImportResponse(BaseModel):
    imported: list[dict[str, str]]
    skipped: list[str]


class UploadResponse(BaseModel):
    id: UUID
    filename: str
    status: JobStatus


class ReanalyzeResponse(BaseModel):
    id: UUID
    status: JobStatus
    message: str | None = None
    progress_pct: float | None = None


class WebhookBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., pattern=r"^https?://.+")
    events: list[str] = Field(default_factory=list)
    is_active: bool = True


class WebhookCreate(WebhookBase):
    pass


class WebhookUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    url: str | None = Field(None, pattern=r"^https?://.+")
    events: list[str] | None = None
    is_active: bool | None = None


class WebhookRead(WebhookBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    last_triggered_at: datetime | None
    last_status: int | None
    created_at: datetime
    updated_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    user_id: UUID | None = None
    organization_id: UUID | None = None
    scopes: list[str] = Field(default_factory=list)
    exp: int | None = None


class LoginRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str


class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None
    request_id: str | None = None


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int