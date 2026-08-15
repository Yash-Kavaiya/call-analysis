"""FastAPI app: file-store REST API + dashboard.

The production Postgres/JWT/Celery layer is optional. Local and test
runs use CallStore (JSON under data/) and in-process background jobs so
the dashboard works without Docker, PostgreSQL, or Redis.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from call_analysis.config import get_settings, load_nvidia_config
from call_analysis.logging_config import LoggingMiddleware, setup_logging
from call_analysis.models import CallRecord, JobStatus
from call_analysis.schemas import (
    AnalyticsSummary,
    CopilotRequest,
    CopilotResponse,
    ErrorResponse,
    HealthResponse,
    ImportLocalRequest,
    ImportResponse,
)
from call_analysis.storage import CallStore

settings = get_settings()
setup_logging()
logger = logging.getLogger(__name__)

_store: CallStore | None = None
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="call-pipeline")


def get_store() -> CallStore:
    global _store
    if _store is None:
        _store = CallStore()
    return _store


def _in_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _recovery_lock(store: CallStore) -> Any:
    """Cross-platform exclusive lock so only one worker recovers on startup.

    gunicorn may start several uvicorn workers against the same JSON store; a
    file lock prevents them from re-queuing the same pending calls and tearing
    each other's writes.
    """
    import contextlib

    lock_path = store.data_dir / ".recovery.lock"
    try:
        # Keep the handle open for the duration of the lock (context manager
        # would release it, defeating the lock) — intentional.
        fh = open(lock_path, "a+b")  # noqa: SIM115 — lock must stay held
        if fh.tell() == 0:
            fh.write(b"0")  # msvcrt.locking needs a byte to lock
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

        return _release()
    except OSError:
        return contextlib.nullcontext()


def recover_interrupted_jobs(
    store: CallStore,
    enqueue: Any,
) -> tuple[int, int]:
    """
    Resume work left over from a previous server session.

    Records stuck in ``processing`` (e.g. the process was killed mid-run) are
    reset back to ``pending`` so they can be analyzed again; every ``pending``
    record is then re-queued via ``enqueue(call_id)``.

    Only one worker process may run recovery at a time (file lock), so a
    multi-worker production deploy cannot double-process the same calls.

    Returns ``(reset_count, enqueued_count)`` for diagnostics/tests.
    """
    reset = 0
    enqueued = 0
    with _recovery_lock(store):
        for rec in store.list_calls():
            if rec.status == JobStatus.PROCESSING.value:
                rec.status = JobStatus.PENDING.value
                rec.progress_pct = 0.0
                rec.progress_message = "Interrupted by restart — re-queued"
                store.save(rec)
                reset += 1
            if rec.status == JobStatus.PENDING.value:
                enqueue(rec.id)
                enqueued += 1
    return reset, enqueued


def _run_pipeline(call_id: str) -> None:
    from call_analysis.pipeline.runner import process_call as run_pipeline

    try:
        run_pipeline(call_id, store=get_store())
    except Exception:
        logger.exception("Pipeline failed for %s", call_id)


def enqueue_analysis(call_id: str) -> None:
    """Queue analysis. No-op under pytest so unit tests stay deterministic."""
    if _in_pytest() or settings.is_testing:
        return
    _executor.submit(_run_pipeline, call_id)


def _list_item(rec: CallRecord) -> dict[str, Any]:
    qa = rec.agents.get("qa_scorecard")
    qa_score = qa.score if qa is not None else None
    return {
        "id": rec.id,
        "filename": rec.filename,
        "status": rec.status,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
        "duration_sec": rec.duration_sec,
        "language": rec.language,
        "error": rec.error,
        "progress_pct": rec.progress_pct,
        "progress_message": rec.progress_message,
        "qa_score": qa_score,
        "pii_count": len(rec.pii_findings),
    }


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    logger.info(
        "Starting Call Analysis API v%s (%s)",
        settings.app_version,
        settings.environment,
    )
    try:
        from call_analysis.telemetry import setup_telemetry

        setup_telemetry(app)
    except Exception:
        logger.warning("Telemetry not started", exc_info=True)

    store = get_store()
    reset, enqueued = recover_interrupted_jobs(store, enqueue_analysis)
    if reset or enqueued:
        logger.info("Recovered interrupted jobs reset=%s enqueued=%s", reset, enqueued)

    yield

    logger.info("Shutting down Call Analysis API")
    try:
        from call_analysis.telemetry import shutdown_telemetry

        await shutdown_telemetry()
    except Exception:
        pass


app = FastAPI(
    title="Call Analysis — Contact Center Intelligence",
    version=settings.app_version,
    description="NVIDIA-powered contact center analysis platform",
    lifespan=lifespan,
    # Do not expose the OpenAPI surface in production deployments.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

if settings.cors.enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.allow_origins,
        allow_origin_regex=settings.cors.allow_origin_regex,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=settings.cors.allow_methods,
        allow_headers=settings.cors.allow_headers,
        expose_headers=settings.cors.expose_headers,
        max_age=settings.cors.max_age,
    )

app.add_middleware(LoggingMiddleware)


@app.middleware("http")
async def add_security_headers(request: Request, call_next: Any) -> Any:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.middleware("http")
async def add_request_id(request: Request, call_next: Any) -> Any:
    request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.post("/api/system/shutdown", tags=["System"])
async def system_shutdown() -> dict[str, str]:
    """Graceful shutdown hook for the Electron desktop shell.

    Spawns a background timer that exits the process once the response has
    been flushed. State is safe: every pipeline stage persists via
    ``CallStore.save`` and ``recover_interrupted_jobs`` re-queues anything
    left mid-flight on the next start.
    """
    import threading
    import time

    def _exit() -> None:
        time.sleep(0.3)
        logger.info("Shutdown requested by desktop app")
        os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()
    return {"status": "shutting_down"}


@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health(request: Request) -> HealthResponse:
    nvidia_key_ok = settings.nvidia.is_configured

    db_ok = False
    redis_ok = False
    is_desktop = os.environ.get("CALL_ANALYSIS_ELECTRON") == "1" or getattr(sys, "frozen", False)
    if not settings.is_testing and not _in_pytest() and not is_desktop:
        try:
            from call_analysis.database import check_db_connection

            db_ok = await asyncio.wait_for(check_db_connection(), timeout=0.3)
        except Exception:
            db_ok = False
        try:
            from call_analysis.redis_client import check_redis_connection

            redis_ok = await asyncio.wait_for(check_redis_connection(), timeout=0.3)
        except Exception:
            redis_ok = False

    return HealthResponse(
        status="ok",
        nvidia_key_configured=nvidia_key_ok,
        model=settings.nvidia.model if nvidia_key_ok else None,
        base_url=settings.nvidia.base_url if nvidia_key_ok else None,
        version=settings.app_version,
        environment=settings.environment,
        database_connected=db_ok,
        redis_connected=redis_ok,
    )


@app.get("/api/analytics", response_model=AnalyticsSummary, tags=["Calls"])
async def analytics() -> AnalyticsSummary:
    calls = get_store().list_calls()
    by_status = {"completed": 0, "processing": 0, "failed": 0, "pending": 0}
    qa_scores: list[float] = []
    comp_scores: list[float] = []
    sent_scores: list[float] = []
    pii_total = 0
    languages: dict[str, int] = {}

    for c in calls:
        st = c.status if c.status in by_status else "pending"
        by_status[st] = by_status.get(st, 0) + 1
        pii_total += len(c.pii_findings)
        if c.language:
            languages[c.language] = languages.get(c.language, 0) + 1
        qa = c.agents.get("qa_scorecard")
        if qa and qa.score is not None:
            qa_scores.append(float(qa.score))
        cr = c.agents.get("compliance_risk")
        if cr and cr.score is not None:
            comp_scores.append(float(cr.score))
        se = c.agents.get("sentiment_emotion")
        if se and se.score is not None:
            sent_scores.append(float(se.score))

    def avg(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 1) if xs else None

    return AnalyticsSummary(
        total_calls=len(calls),
        completed=by_status["completed"],
        processing=by_status["processing"],
        failed=by_status["failed"],
        pending=by_status["pending"],
        avg_qa_score=avg(qa_scores),
        avg_compliance_score=avg(comp_scores),
        avg_sentiment_score=avg(sent_scores),
        total_pii_findings=pii_total,
        languages=languages,
    )


@app.get("/api/calls", tags=["Calls"])
async def list_calls() -> dict[str, Any]:
    items = [_list_item(c) for c in get_store().list_calls()]
    return {"calls": items}


@app.get("/api/calls/{call_id}", tags=["Calls"])
async def get_call(call_id: str) -> dict[str, Any]:
    rec = get_store().get(call_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return rec.to_dict()


@app.delete("/api/calls/{call_id}", status_code=204, tags=["Calls"])
async def delete_call(call_id: str) -> None:
    if not get_store().delete(call_id):
        raise HTTPException(status_code=404, detail="Call not found")


@app.post("/api/calls/upload", tags=["Calls"])
async def upload_call(
    file: UploadFile = File(...),  # noqa: B008 — FastAPI injection idiom
    analyze: bool = Query(True),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    ext = Path(file.filename).suffix.lower()
    if ext not in settings.storage.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > settings.storage.max_upload_size:
        raise HTTPException(status_code=413, detail="File too large")

    import tempfile

    store = get_store()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        rec = store.register_upload(tmp_path, copy=True, filename=file.filename)
    finally:
        tmp_path.unlink(missing_ok=True)

    if analyze:
        enqueue_analysis(rec.id)
    return {"id": rec.id, "filename": rec.filename, "status": rec.status}


@app.post("/api/calls/import-local", response_model=ImportResponse, tags=["Calls"])
async def import_local(body: ImportLocalRequest) -> ImportResponse:
    store = get_store()
    imported: list[dict[str, str]] = []
    skipped: list[str] = []
    known = {c.filename for c in store.list_calls()}

    if body.path:
        p = Path(body.path)
        if not p.is_file():
            raise HTTPException(status_code=400, detail=f"File not found: {body.path}")
        if body.skip_existing and p.name in known:
            skipped.append(p.name)
        else:
            rec = store.register_upload(p, copy=True)
            if body.analyze:
                enqueue_analysis(rec.id)
            imported.append({"id": rec.id, "filename": rec.filename})
    else:
        files = store.iter_project_recordings(limit=max(body.limit * 5, body.limit))
        if not files:
            raise HTTPException(status_code=404, detail="No recordings found in project folder")
        for f in files:
            if body.skip_existing and f.name in known:
                skipped.append(f.name)
                continue
            rec = store.register_upload(f, copy=True)
            known.add(f.name)
            if body.analyze:
                enqueue_analysis(rec.id)
            imported.append({"id": rec.id, "filename": rec.filename})
            if len(imported) >= body.limit:
                break
        if not imported and not skipped:
            raise HTTPException(status_code=404, detail="No recordings found in project folder")

    return ImportResponse(imported=imported, skipped=skipped[:20])


@app.post("/api/calls/{call_id}/analyze", tags=["Calls"])
async def analyze_call(call_id: str) -> dict[str, Any]:
    rec = get_store().get(call_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Call not found")
    if rec.status == JobStatus.PROCESSING.value:
        return {"id": rec.id, "filename": rec.filename, "status": rec.status}
    rec.status = JobStatus.PENDING.value
    rec.progress_pct = 0.0
    rec.progress_message = "Queued"
    rec.error = None
    get_store().save(rec)
    enqueue_analysis(rec.id)
    return {"id": rec.id, "filename": rec.filename, "status": JobStatus.PROCESSING.value}


@app.post("/api/calls/{call_id}/copilot", response_model=CopilotResponse, tags=["Calls"])
async def copilot(call_id: str, body: CopilotRequest) -> CopilotResponse:
    from call_analysis.agents.orchestrator import answer_copilot

    rec = get_store().get(call_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Call not found")
    if rec.status != JobStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Call analysis not completed yet")
    try:
        cfg = load_nvidia_config(require_key=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    agent_ctx = {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in rec.agents.items()}
    answer = answer_copilot(
        cfg,
        question=body.question,
        transcript=rec.scrubbed_transcript or rec.full_transcript,
        agent_context=agent_ctx,
    )
    return CopilotResponse(answer=answer)


WEB_DIR = Path(__file__).resolve().parents[1] / "web"

if WEB_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception path=%s", request.url.path)
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            detail="Internal server error",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
        ).model_dump(),
    )


def create_app(store: CallStore | None = None) -> FastAPI:
    """Create app instance for testing (injects a CallStore)."""
    global _store
    if store is not None:
        _store = store
    return app
