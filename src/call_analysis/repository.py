"""Call persistence: file store, PostgreSQL, or hybrid (DB + JSON mirror)."""

from __future__ import annotations

import logging
import os
import sys
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import func, select

from call_analysis.config import get_settings
from call_analysis.database import SyncSessionLocal, check_db_connection
from call_analysis.models import (
    AgentResult,
    CallRecord,
    CallRecordModel,
    JobStatus,
    Organization,
    PiiFinding,
    TranscriptSegment,
)
from call_analysis.storage import CallStore, default_data_dir

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from call_analysis.schemas import UserRead

logger = logging.getLogger(__name__)

_backend_cache: str | None = None


def _is_desktop_runtime() -> bool:
    return os.environ.get("CALL_ANALYSIS_ELECTRON") == "1" or getattr(sys, "frozen", False)


def resolve_storage_backend() -> str:
    """Resolve effective storage backend (cached after first call)."""
    global _backend_cache
    if _backend_cache is not None:
        return _backend_cache

    settings = get_settings()
    configured = settings.storage.backend
    if configured == "file" or _is_desktop_runtime() or settings.is_testing:
        _backend_cache = "file"
        return _backend_cache

    if configured == "postgres":
        _backend_cache = "postgres"
        return _backend_cache

    # auto: prefer postgres when DB is reachable
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # FastAPI lifespan / sync context — assume postgres in production compose
            _backend_cache = "postgres" if settings.is_production else "file"
        else:
            _backend_cache = "postgres" if asyncio.run(check_db_connection()) else "file"
    except RuntimeError:
        _backend_cache = "postgres" if asyncio.run(check_db_connection()) else "file"

    return _backend_cache


def reset_storage_backend_cache() -> None:
    global _backend_cache
    _backend_cache = None


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.now(UTC).replace(tzinfo=None)


def record_to_orm(record: CallRecord, organization_id: UUID) -> dict[str, Any]:
    status = record.status
    try:
        job_status = JobStatus(status)
    except ValueError:
        job_status = JobStatus.PENDING

    return {
        "id": UUID(record.id),
        "organization_id": organization_id,
        "filename": record.filename,
        "source_path": record.source_path,
        "status": job_status,
        "error": record.error,
        "progress_pct": record.progress_pct,
        "progress_message": record.progress_message,
        "duration_sec": record.duration_sec,
        "language": record.language,
        "full_transcript": record.full_transcript,
        "scrubbed_transcript": record.scrubbed_transcript,
        "segments": [s.to_dict() for s in record.segments],
        "pii_findings": [p.to_dict() for p in record.pii_findings],
        "agents": {k: v.to_dict() for k, v in record.agents.items()},
        "waveform_peaks": record.waveform_peaks,
        "call_metadata": dict(record.metadata),
        "created_at": _parse_dt(record.created_at),
        "updated_at": _parse_dt(record.updated_at),
        "completed_at": _parse_dt(record.metadata.get("completed_at"))
        if record.status == JobStatus.COMPLETED.value
        else None,
    }


def orm_to_record(model: CallRecordModel) -> CallRecord:
    agents_raw = model.agents or {}
    agents = {
        k: AgentResult.from_dict(v) if isinstance(v, dict) else v for k, v in agents_raw.items()
    }
    return CallRecord(
        id=str(model.id),
        filename=model.filename,
        source_path=model.source_path,
        status=model.status.value if hasattr(model.status, "value") else str(model.status),
        created_at=model.created_at.isoformat() if model.created_at else "",
        updated_at=model.updated_at.isoformat() if model.updated_at else "",
        duration_sec=model.duration_sec,
        language=model.language,
        error=model.error,
        progress_pct=float(model.progress_pct or 0.0),
        progress_message=model.progress_message or "",
        full_transcript=model.full_transcript or "",
        scrubbed_transcript=model.scrubbed_transcript or "",
        segments=[TranscriptSegment.from_dict(s) for s in (model.segments or [])],
        pii_findings=[PiiFinding.from_dict(p) for p in (model.pii_findings or [])],
        agents=agents,
        waveform_peaks=list(model.waveform_peaks or []),
        metadata=dict(model.call_metadata or {}),
    )


def get_default_organization_id() -> UUID:
    """Return default org UUID, creating org slug 'default' if missing."""
    with SyncSessionLocal() as db:
        org = db.execute(select(Organization).where(Organization.slug == "default")).scalar_one_or_none()
        if org:
            return org.id
        org = Organization(name="Default Organization", slug="default", settings={})
        db.add(org)
        db.commit()
        db.refresh(org)
        return org.id


class CallRepository(ABC):
    """Abstract call persistence used by the API."""

    @property
    @abstractmethod
    def store(self) -> CallStore:
        """Underlying file store for the pipeline."""

    @abstractmethod
    def get(self, call_id: str, organization_id: UUID | None = None) -> CallRecord | None:
        pass

    @abstractmethod
    def save(self, record: CallRecord, organization_id: UUID | None = None) -> CallRecord:
        pass

    @abstractmethod
    def list_calls(
        self,
        organization_id: UUID | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[CallRecord], int]:
        pass

    @abstractmethod
    def delete(self, call_id: str, organization_id: UUID | None = None) -> bool:
        pass

    @abstractmethod
    def register_upload(
        self,
        source: Path,
        *,
        copy: bool = True,
        filename: str | None = None,
        organization_id: UUID | None = None,
    ) -> CallRecord:
        pass

    def iter_project_recordings(self, **kwargs: Any) -> list[Path]:
        return self.store.iter_project_recordings(**kwargs)


class FileCallRepository(CallRepository):
    """JSON file store only (desktop / local dev)."""

    def __init__(self, store: CallStore | None = None) -> None:
        self._store = store or CallStore()

    @property
    def store(self) -> CallStore:
        return self._store

    def get(self, call_id: str, organization_id: UUID | None = None) -> CallRecord | None:
        return self._store.get(call_id)

    def save(self, record: CallRecord, organization_id: UUID | None = None) -> CallRecord:
        return self._store.save(record)

    def list_calls(
        self,
        organization_id: UUID | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[CallRecord], int]:
        records = self._store.list_calls()
        records = _filter_records(records, status=status, search=search)
        total = len(records)
        if offset:
            records = records[offset:]
        if limit is not None:
            records = records[:limit]
        return records, total

    def delete(self, call_id: str, organization_id: UUID | None = None) -> bool:
        return self._store.delete(call_id)

    def register_upload(
        self,
        source: Path,
        *,
        copy: bool = True,
        filename: str | None = None,
        organization_id: UUID | None = None,
    ) -> CallRecord:
        return self._store.register_upload(source, copy=copy, filename=filename)


class HybridCallRepository(CallRepository):
    """PostgreSQL source of truth with JSON mirror for the pipeline."""

    def __init__(
        self,
        organization_id: UUID | None = None,
        store: CallStore | None = None,
    ) -> None:
        self._default_org = organization_id
        org_str = str(organization_id) if organization_id else None
        self._store = store or CallStore(organization_id=org_str)

    @property
    def store(self) -> CallStore:
        return self._store

    def _org(self, organization_id: UUID | None) -> UUID:
        return organization_id or self._default_org or get_default_organization_id()

    def get(self, call_id: str, organization_id: UUID | None = None) -> CallRecord | None:
        org = self._org(organization_id)
        with SyncSessionLocal() as db:
            stmt = select(CallRecordModel).where(
                CallRecordModel.id == UUID(call_id),
                CallRecordModel.organization_id == org,
            )
            model = db.execute(stmt).scalar_one_or_none()
            if model:
                record = orm_to_record(model)
                self._store.save(record)
                return record
        return self._store.get(call_id)

    def save(self, record: CallRecord, organization_id: UUID | None = None) -> CallRecord:
        org = self._org(organization_id)
        saved = self._store.save(record)
        fields = record_to_orm(saved, org)
        with SyncSessionLocal() as db:
            model = db.get(CallRecordModel, fields["id"])
            if model is None:
                model = CallRecordModel(**fields)
                db.add(model)
            else:
                for key, value in fields.items():
                    if key != "id":
                        setattr(model, key, value)
            db.commit()
        return saved

    def list_calls(
        self,
        organization_id: UUID | None = None,
        *,
        limit: int | None = None,
        offset: int = 0,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[CallRecord], int]:
        org = self._org(organization_id)
        with SyncSessionLocal() as db:
            base = select(CallRecordModel).where(CallRecordModel.organization_id == org)
            if status:
                try:
                    base = base.where(CallRecordModel.status == JobStatus(status))
                except ValueError:
                    pass
            if search:
                base = base.where(CallRecordModel.filename.ilike(f"%{search}%"))
            count_stmt = select(func.count()).select_from(base.subquery())
            total = int(db.execute(count_stmt).scalar_one())
            stmt = base.order_by(CallRecordModel.created_at.desc()).offset(offset)
            if limit is not None:
                stmt = stmt.limit(limit)
            models = db.execute(stmt).scalars().all()
            return [orm_to_record(m) for m in models], total

    def delete(self, call_id: str, organization_id: UUID | None = None) -> bool:
        org = self._org(organization_id)
        deleted = self._store.delete(call_id)
        with SyncSessionLocal() as db:
            model = db.execute(
                select(CallRecordModel).where(
                    CallRecordModel.id == UUID(call_id),
                    CallRecordModel.organization_id == org,
                )
            ).scalar_one_or_none()
            if model:
                db.delete(model)
                db.commit()
                deleted = True
        return deleted

    def register_upload(
        self,
        source: Path,
        *,
        copy: bool = True,
        filename: str | None = None,
        organization_id: UUID | None = None,
    ) -> CallRecord:
        org = self._org(organization_id)
        call_id = str(uuid4())
        record = self._store.register_upload(
            source, copy=copy, filename=filename, call_id=call_id
        )
        record.metadata["organization_id"] = str(org)
        self._store.save(record)
        fields = record_to_orm(record, org)
        with SyncSessionLocal() as db:
            db.add(CallRecordModel(**fields))
            db.commit()
        return record


def _filter_records(
    records: list[CallRecord],
    *,
    status: str | None,
    search: str | None,
) -> list[CallRecord]:
    out = records
    if status:
        out = [r for r in out if r.status == status]
    if search:
        q = search.lower()
        out = [r for r in out if q in r.filename.lower()]
    return out


_repository: CallRepository | None = None


def get_call_repository(user: UserRead | None = None) -> CallRepository:
    """Factory for the active call repository."""
    global _repository
    if _repository is not None and user is None:
        return _repository

    backend = resolve_storage_backend()
    org_id = user.organization_id if user else None
    if backend == "postgres":
        repo: CallRepository = HybridCallRepository(organization_id=org_id)
    else:
        repo = FileCallRepository()

    if user is None:
        _repository = repo
    return repo


def set_call_repository(repo: CallRepository | None) -> None:
    global _repository
    _repository = repo


def org_store_for_user(user: UserRead | None) -> CallStore:
    """CallStore scoped to the user's organization when using postgres."""
    backend = resolve_storage_backend()
    if backend == "postgres" and user is not None:
        return CallStore(organization_id=str(user.organization_id))
    return get_call_repository(user).store


def list_pending_call_ids(organization_id: UUID | None = None) -> list[str]:
    repo = get_call_repository()
    records, _ = repo.list_calls(organization_id, status=JobStatus.PENDING.value)
    processing, _ = repo.list_calls(organization_id, status=JobStatus.PROCESSING.value)
    ids = [r.id for r in records + processing]
    return ids
