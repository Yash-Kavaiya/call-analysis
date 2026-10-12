"""FastAPI app: REST API + dashboard (file store or PostgreSQL + Celery)."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from call_analysis.analytics_service import get_analytics
from call_analysis.api.deps import analyst_for_writes, get_optional_user, get_repo
from call_analysis.api.routes import api_keys, auth, organizations, users, webhooks
from call_analysis.config import NVidiaSettings, get_settings, load_nvidia_config
from call_analysis.jobs import enqueue_analysis, recover_interrupted_jobs as _recover_jobs
from call_analysis.logging_config import LoggingMiddleware, setup_logging
from call_analysis.models import CallRecord, JobStatus
from call_analysis.prometheus_metrics import metrics_response, prometheus_middleware
from call_analysis.rate_limit_middleware import rate_limit_middleware
from call_analysis.repository import (
    CallRepository,
    FileCallRepository,
    get_call_repository,
    set_call_repository,
)
from call_analysis.schemas import (
    AnalyticsSummary,
    CopilotRequest,
    CopilotResponse,
    ErrorResponse,
    HealthResponse,
    ImportFolderRequest,
    ImportHubRequest,
    ImportLocalRequest,
    ImportResponse,
    UserRead,
)
from call_analysis.storage import CallStore

settings = get_settings()
setup_logging()
logger = logging.getLogger(__name__)


def get_store() -> CallStore:
    return get_call_repository().store


def _in_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def recover_interrupted_jobs(
    store: CallStore,
    enqueue: Any,
) -> tuple[int, int]:
    """Backward-compatible wrapper for tests (injects file store)."""
    set_call_repository(FileCallRepository(store))

    def _enqueue(call_id: str, org_id: Any = None) -> None:
        enqueue(call_id)

    reset = 0
    enqueued = 0
    with store.data_dir.joinpath(".recovery.lock").open("a+b") as fh:
        pass
    for rec in store.list_calls():
        if rec.status == JobStatus.PROCESSING.value:
            rec.status = JobStatus.PENDING.value
            rec.progress_pct = 0.0
            rec.progress_message = "Interrupted by restart — re-queued"
            store.save(rec)
            reset += 1
        if rec.status == JobStatus.PENDING.value:
            _enqueue(rec.id)
            enqueued += 1
    return reset, enqueued


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


def _org_id(user: UserRead | None) -> Any:
    return user.organization_id if user else None


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

    reset, enqueued = _recover_jobs()
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
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.include_router(auth.router)
app.include_router(organizations.router)
app.include_router(users.router)
app.include_router(api_keys.router)
app.include_router(webhooks.router)

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
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(prometheus_middleware)


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


@app.get("/metrics", tags=["Observability"])
async def prometheus_metrics() -> Response:
    body, content_type = metrics_response()
    return Response(content=body, media_type=content_type)


@app.post("/api/system/shutdown", tags=["System"])
async def system_shutdown() -> dict[str, str]:
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
    nvidia = NVidiaSettings(_env_file=".env", _env_file_encoding="utf-8")
    nvidia_key_ok = nvidia.is_configured

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
        model=nvidia.model if nvidia_key_ok else None,
        base_url=nvidia.base_url if nvidia_key_ok else None,
        version=settings.app_version,
        environment=settings.environment,
        database_connected=db_ok,
        redis_connected=redis_ok,
    )


@app.get("/api/analytics", response_model=AnalyticsSummary, tags=["Calls"])
async def analytics(
    user: Annotated[UserRead | None, Depends(get_optional_user)],
) -> AnalyticsSummary:
    return get_analytics(_org_id(user))


@app.get("/api/analytics/export", tags=["Calls"])
async def export_analytics(
    user: Annotated[UserRead | None, Depends(get_optional_user)],
    fmt: str = Query("json", alias="format"),
) -> Response:
    if not settings.features.export_enabled:
        raise HTTPException(status_code=404, detail="Export disabled")
    summary = get_analytics(_org_id(user))
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["metric", "value"])
        for key, val in summary.model_dump().items():
            writer.writerow([key, val if not isinstance(val, dict) else json.dumps(val)])
        return Response(content=buf.getvalue(), media_type="text/csv")
    return JSONResponse(summary.model_dump())


@app.get("/api/calls", tags=["Calls"])
async def list_calls(
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(get_optional_user)],
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    search: str | None = Query(None),
) -> dict[str, Any]:
    records, total = repo.list_calls(
        _org_id(user), limit=limit, offset=offset, status=status, search=search
    )
    return {
        "calls": [_list_item(c) for c in records],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/calls/{call_id}", tags=["Calls"])
async def get_call(
    call_id: str,
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(get_optional_user)],
) -> dict[str, Any]:
    rec = repo.get(call_id, _org_id(user))
    if rec is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return rec.to_dict()


@app.get("/api/calls/{call_id}/export", tags=["Calls"])
async def export_call(
    call_id: str,
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(get_optional_user)],
    fmt: str = Query("json", alias="format"),
) -> Response:
    if not settings.features.export_enabled:
        raise HTTPException(status_code=404, detail="Export disabled")
    rec = repo.get(call_id, _org_id(user))
    if rec is None:
        raise HTTPException(status_code=404, detail="Call not found")
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["field", "value"])
        for key, val in rec.to_dict().items():
            if isinstance(val, (list, dict)):
                val = json.dumps(val)
            writer.writerow([key, val])
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{call_id}.csv"'},
        )
    return JSONResponse(rec.to_dict())


@app.get("/api/calls/{call_id}/events", tags=["Calls"])
async def call_events(
    call_id: str,
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(get_optional_user)],
    access_token: str | None = Query(None),
) -> StreamingResponse:
    if not settings.features.websocket_enabled:
        raise HTTPException(status_code=404, detail="Live events disabled")

    from call_analysis.api.deps import auth_enforced
    from call_analysis.auth import decode_token

    if auth_enforced() and user is None and access_token:
        token_data = decode_token(access_token)
        if not token_data or not token_data.user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    elif auth_enforced() and user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    async def event_stream() -> Any:
        from call_analysis.redis_client import JobStatusTracker

        tracker = JobStatusTracker()
        last_payload = ""
        for _ in range(120):
            rec = repo.get(call_id, _org_id(user))
            if rec is None:
                yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
                break
            payload = {
                "status": rec.status,
                "progress_pct": rec.progress_pct,
                "progress_message": rec.progress_message,
            }
            try:
                redis_status = await tracker.get_status(call_id)
                if redis_status:
                    payload.update(redis_status)
            except Exception:
                pass
            line = json.dumps(payload)
            if line != last_payload:
                yield f"data: {line}\n\n"
                last_payload = line
            if rec.status in (JobStatus.COMPLETED.value, JobStatus.FAILED.value):
                break
            await asyncio.sleep(1)
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.delete("/api/calls/{call_id}", status_code=204, tags=["Calls"])
async def delete_call(
    call_id: str,
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(analyst_for_writes)],
) -> None:
    if not repo.delete(call_id, _org_id(user)):
        raise HTTPException(status_code=404, detail="Call not found")


@app.post("/api/calls/upload", tags=["Calls"])
async def upload_call(
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(analyst_for_writes)],
    file: UploadFile = File(...),  # noqa: B008
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

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        rec = repo.register_upload(
            tmp_path, copy=True, filename=file.filename, organization_id=_org_id(user)
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    org = _org_id(user)
    if analyze:
        enqueue_analysis(rec.id, org)
    return {"id": rec.id, "filename": rec.filename, "status": rec.status}


@app.post("/api/calls/import-local", response_model=ImportResponse, tags=["Calls"])
async def import_local(
    body: ImportLocalRequest,
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(analyst_for_writes)],
) -> ImportResponse:
    imported: list[dict[str, str]] = []
    skipped: list[str] = []
    records, _ = repo.list_calls(_org_id(user))
    known = {c.filename for c in records}

    if body.path:
        p = Path(body.path)
        if not p.is_file():
            raise HTTPException(status_code=400, detail=f"File not found: {body.path}")
        if body.skip_existing and p.name in known:
            skipped.append(p.name)
        else:
            rec = repo.register_upload(p, copy=True, organization_id=_org_id(user))
            if body.analyze:
                enqueue_analysis(rec.id, _org_id(user))
            imported.append({"id": rec.id, "filename": rec.filename})
    else:
        files = repo.iter_project_recordings(limit=max(body.limit * 5, body.limit))
        if not files:
            raise HTTPException(status_code=404, detail="No recordings found in project folder")
        for f in files:
            if body.skip_existing and f.name in known:
                skipped.append(f.name)
                continue
            rec = repo.register_upload(f, copy=True, organization_id=_org_id(user))
            known.add(f.name)
            if body.analyze:
                enqueue_analysis(rec.id, _org_id(user))
            imported.append({"id": rec.id, "filename": rec.filename})
            if len(imported) >= body.limit:
                break
        if not imported and not skipped:
            raise HTTPException(status_code=404, detail="No recordings found in project folder")

    return ImportResponse(imported=imported, skipped=skipped[:20])


def _import_paths(
    repo: CallRepository,
    sources: list[tuple[Path, str]],
    *,
    analyze: bool,
    skip_existing: bool,
    limit: int,
    organization_id: Any,
) -> ImportResponse:
    imported: list[dict[str, str]] = []
    skipped: list[str] = []
    records, _ = repo.list_calls(organization_id)
    known = {c.filename for c in records}
    for path, name in sources:
        if skip_existing and name in known:
            skipped.append(name)
            continue
        rec = repo.register_upload(path, copy=True, filename=name, organization_id=organization_id)
        known.add(name)
        if analyze:
            enqueue_analysis(rec.id, organization_id)
        imported.append({"id": rec.id, "filename": rec.filename})
        if len(imported) >= limit:
            break
    return ImportResponse(imported=imported, skipped=skipped[:20])


@app.post("/api/calls/import-folder", response_model=ImportResponse, tags=["Calls"])
async def import_folder(
    body: ImportFolderRequest,
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(analyst_for_writes)],
) -> ImportResponse:
    from call_analysis.ingest import iter_folder_audio

    try:
        files = iter_folder_audio(Path(body.path), recursive=body.recursive)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not files:
        raise HTTPException(
            status_code=404, detail=f"No audio files found in folder: {body.path}"
        )
    result = _import_paths(
        repo,
        [(f, f.name) for f in files],
        analyze=body.analyze,
        skip_existing=body.skip_existing,
        limit=body.limit,
        organization_id=_org_id(user),
    )
    if not result.imported and not result.skipped:
        raise HTTPException(status_code=404, detail="No audio files imported")
    return result


@app.post("/api/calls/import-hf", response_model=ImportResponse, tags=["Calls"])
async def import_huggingface(
    body: ImportHubRequest,
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(analyst_for_writes)],
) -> ImportResponse:
    import tempfile

    from call_analysis.ingest import fetch_huggingface_audio, validate_dataset_id

    try:
        dataset = validate_dataset_id(body.dataset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        with tempfile.TemporaryDirectory() as tmp:
            downloaded = await asyncio.to_thread(
                fetch_huggingface_audio,
                dataset,
                dest_dir=Path(tmp),
                limit=body.limit,
            )
            if not downloaded:
                raise HTTPException(
                    status_code=404,
                    detail=f"No audio files found in HuggingFace dataset '{dataset}'",
                )
            sources = [(p, p.name.split("_", 1)[-1]) for p in downloaded]
            return _import_paths(
                repo,
                sources,
                analyze=body.analyze,
                skip_existing=body.skip_existing,
                limit=body.limit,
                organization_id=_org_id(user),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"HuggingFace API error: {exc}") from exc


@app.post("/api/calls/import-kaggle", response_model=ImportResponse, tags=["Calls"])
async def import_kaggle(
    body: ImportHubRequest,
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(analyst_for_writes)],
) -> ImportResponse:
    import tempfile

    from call_analysis.ingest import fetch_kaggle_audio, validate_dataset_id

    try:
        dataset = validate_dataset_id(body.dataset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        with tempfile.TemporaryDirectory() as tmp:
            downloaded = await asyncio.to_thread(
                fetch_kaggle_audio,
                dataset,
                dest_dir=Path(tmp),
                limit=body.limit,
            )
            if not downloaded:
                raise HTTPException(
                    status_code=404,
                    detail=f"No audio files found in Kaggle dataset '{dataset}'",
                )
            return _import_paths(
                repo,
                [(p, p.name) for p in downloaded],
                analyze=body.analyze,
                skip_existing=body.skip_existing,
                limit=body.limit,
                organization_id=_org_id(user),
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Kaggle API error: {exc}") from exc


@app.post("/api/calls/{call_id}/analyze", tags=["Calls"])
async def analyze_call(
    call_id: str,
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(analyst_for_writes)],
) -> dict[str, Any]:
    rec = repo.get(call_id, _org_id(user))
    if rec is None:
        raise HTTPException(status_code=404, detail="Call not found")
    if rec.status == JobStatus.PROCESSING.value:
        return {"id": rec.id, "filename": rec.filename, "status": rec.status}
    rec.status = JobStatus.PENDING.value
    rec.progress_pct = 0.0
    rec.progress_message = "Queued"
    rec.error = None
    repo.save(rec, _org_id(user))
    enqueue_analysis(rec.id, _org_id(user))
    return {"id": rec.id, "filename": rec.filename, "status": JobStatus.PROCESSING.value}


@app.post("/api/calls/{call_id}/copilot", response_model=CopilotResponse, tags=["Calls"])
async def copilot(
    call_id: str,
    body: CopilotRequest,
    repo: Annotated[CallRepository, Depends(get_repo)],
    user: Annotated[UserRead | None, Depends(get_optional_user)],
) -> CopilotResponse:
    if not settings.features.copilot_enabled:
        raise HTTPException(status_code=404, detail="Copilot disabled")
    from call_analysis.agents.orchestrator import answer_copilot

    rec = repo.get(call_id, _org_id(user))
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
    if store is not None:
        from call_analysis.repository import reset_storage_backend_cache

        reset_storage_backend_cache()
        set_call_repository(FileCallRepository(store))
    return app
