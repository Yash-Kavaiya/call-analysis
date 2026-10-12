"""Background job dispatch: Celery when available, else in-process thread pool."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable
from uuid import UUID

from call_analysis.config import get_settings
from call_analysis.repository import get_call_repository, resolve_storage_backend

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="call-pipeline")
_celery_checked: bool | None = None
_celery_available: bool = False


def _in_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _celery_usable() -> bool:
    global _celery_checked, _celery_available
    if _celery_checked:
        return _celery_available

    settings = get_settings()
    if settings.is_testing or _in_pytest():
        _celery_checked = True
        _celery_available = False
        return False

    if resolve_storage_backend() != "postgres":
        _celery_checked = True
        _celery_available = False
        return False

    try:
        import redis

        client = redis.from_url(settings.redis.url, socket_connect_timeout=0.5)
        client.ping()
        client.close()
        _celery_available = True
    except Exception:
        logger.debug("Celery dispatch unavailable (Redis)", exc_info=True)
        _celery_available = False

    _celery_checked = True
    return _celery_available


def _run_pipeline(call_id: str) -> None:
    from call_analysis.pipeline.runner import process_call as run_pipeline
    from call_analysis.webhook_events import notify_call_completed

    repo = get_call_repository()
    try:
        result = run_pipeline(call_id, store=repo.store)
        if resolve_storage_backend() == "postgres":
            repo.save(result)
        org_id = result.metadata.get("organization_id")
        if result.status == "completed" and org_id:
            notify_call_completed(str(org_id), result)
    except Exception:
        logger.exception("Pipeline failed for %s", call_id)


def enqueue_analysis(call_id: str, organization_id: UUID | str | None = None) -> None:
    """Queue call analysis via Celery or local thread pool."""
    if _in_pytest() or get_settings().is_testing:
        return

    org_str = str(organization_id) if organization_id else None

    if _celery_usable():
        from call_analysis.tasks import process_call

        process_call.delay(call_id, org_str)
        logger.info("Queued Celery analysis call_id=%s org=%s", call_id, org_str)
        return

    _executor.submit(_run_pipeline, call_id)


def recover_interrupted_jobs(
    enqueue: Callable[[str, UUID | str | None], None] | None = None,
) -> tuple[int, int]:
    """Reset stuck processing jobs and re-queue pending work."""
    from call_analysis.models import JobStatus

    enqueue_fn = enqueue or enqueue_analysis
    repo = get_call_repository()
    store = repo.store
    reset = 0
    enqueued = 0

    import contextlib

    lock_path = store.data_dir / ".recovery.lock"
    try:
        fh = open(lock_path, "a+b")  # noqa: SIM115
        if fh.tell() == 0:
            fh.write(b"0")
            fh.flush()
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        @contextlib.contextmanager
        def _release() -> Any:
            try:
                yield
            finally:
                try:
                    if os.name == "nt":
                        import msvcrt

                        fh.seek(0)
                        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                finally:
                    fh.close()

        lock_ctx = _release()
    except OSError:
        lock_ctx = contextlib.nullcontext()

    with lock_ctx:
        records, _ = repo.list_calls()
        for rec in records:
            if rec.status == JobStatus.PROCESSING.value:
                rec.status = JobStatus.PENDING.value
                rec.progress_pct = 0.0
                rec.progress_message = "Interrupted by restart — re-queued"
                repo.save(rec)
                reset += 1
            if rec.status == JobStatus.PENDING.value:
                org = rec.metadata.get("organization_id")
                enqueue_fn(rec.id, org)
                enqueued += 1

    return reset, enqueued
