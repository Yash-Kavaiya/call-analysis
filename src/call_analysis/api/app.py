"""FastAPI app: Production-ready REST API with authentication, rate limiting, and observability."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from call_analysis.auth import (
    get_current_user,
    get_current_user_or_api_key,
    require_admin,
    require_analyst,
)
from call_analysis.celery_app import celery_app, check_celery_health
from call_analysis.config import get_settings
from call_analysis.database import get_async_session, init_db, check_db_connection, close_db, get_db_health
from call_analysis.logging_config import LoggingMiddleware, setup_logging, logger as struct_logger
from call_analysis.models import CallRecord, CallEvent, JobStatus, Organization, User
from call_analysis.redis_client import check_redis_connection, RateLimiter, RedisKeys, get_redis, close_redis
from call_analysis.schemas import (
    AnalyticsSummary,
    APIKeyCreate,
    APIKeyRead,
    APIKeyWithSecret,
    CallRecordListItem,
    CallRecordRead,
    CopilotRequest,
    CopilotResponse,
    ErrorResponse,
    HealthResponse,
    ImportLocalRequest,
    ImportResponse,
    LoginRequest,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    PaginatedResponse,
    Token,
    UploadResponse,
    UserCreate,
    UserRead,
    WebhookCreate,
    WebhookRead,
)
from call_analysis.telemetry import (
    setup_telemetry,
    shutdown_telemetry,
    record_api_request,
    record_call_processed,
)
from call_analysis.tasks import process_call

settings = get_settings()
logger = logging.getLogger(__name__)

# Initialize logging first
setup_logging()

# Rate limiter
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.ratelimit.storage_url)


def recover_interrupted_jobs(store, enqueue):
    """
    Resume work left over from a previous server session.

    Records stuck in ``processing`` (e.g. the process was killed mid-run) are
    reset back to ``pending`` so they can be analyzed again; every ``pending``
    record is then re-queued via ``enqueue(call_id)``.

    Returns ``(reset_count, enqueued_count)`` for diagnostics/tests.
    """
    from call_analysis.models import JobStatus

    reset = 0
    enqueued = 0
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    struct_logger.bind(version=settings.app_version, environment=settings.environment).info("Starting Call Analysis API")

    # Initialize telemetry
    setup_telemetry(app)

    # Initialize database
    await init_db()

    # Check connections
    db_healthy = await check_db_connection()
    redis_healthy = await check_redis_connection()

    struct_logger.bind(healthy=db_healthy).info("Database connection")
    struct_logger.bind(healthy=redis_healthy).info("Redis connection")

    # Recover interrupted jobs
    from call_analysis.storage import CallStore
    store = CallStore()
    reset, enqueued = recover_interrupted_jobs(store, lambda cid: process_call.delay(cid))
    if reset or enqueued:
        struct_logger.bind(reset=reset, enqueued=enqueued).info("Recovered interrupted jobs")

    yield

    # Shutdown
    logger.info("Shutting down Call Analysis API")
    await shutdown_telemetry()
    await close_db()
    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Call Analysis — Contact Center Intelligence",
    version=settings.app_version,
    description="NVIDIA-powered contact center analysis platform",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Logging middleware
app.add_middleware(LoggingMiddleware)

# CORS
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

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# Metrics middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    import time
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    record_api_request(request.method, request.url.path, response.status_code, duration)
    return response


# Health check
@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
@limiter.limit("60/minute")
async def health(request: Request) -> HealthResponse:
    # In testing mode, skip actual connection checks
    if settings.is_testing:
        db_health = {"connected": True}
        redis_healthy = True
    else:
        db_health = await get_db_health()
        redis_healthy = await check_redis_connection()
    
    celery_health = await check_celery_health()

    nvidia_key_ok = settings.nvidia.is_configured
    key_hint = None
    if nvidia_key_ok:
        key_hint = settings.nvidia.api_key[:6] + "..." + settings.nvidia.api_key[-4:]

    # Consider healthy if database is connected; Redis/Celery are optional for basic health
    overall_status = "ok" if db_health["connected"] else "degraded"

    return HealthResponse(
        status=overall_status,
        nvidia_key_configured=nvidia_key_ok,
        model=settings.nvidia.model if nvidia_key_ok else None,
        base_url=settings.nvidia.base_url if nvidia_key_ok else None,
        api_key_hint=key_hint,
        version=settings.app_version,
        environment=settings.environment,
        database_connected=db_health["connected"],
        redis_connected=redis_healthy,
    )


# Authentication endpoints
@app.post("/api/auth/login", response_model=Token, tags=["Authentication"])
@limiter.limit("10/minute")
async def login(
    request: Request,
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Token:
    from call_analysis.auth import verify_password, create_access_token, create_refresh_token
    from call_analysis.database import get_async_session

    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "org_id": str(user.organization_id), "scopes": ["read", "write"]}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "org_id": str(user.organization_id), "type": "refresh"}
    )

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.auth.access_token_expire_minutes * 60,
    )


@app.get("/api/auth/me", response_model=UserRead, tags=["Authentication"])
async def get_current_user_info(
    current_user: UserRead = Depends(get_current_user),
) -> UserRead:
    return current_user


# Organization endpoints (admin only)
@app.post("/api/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED, tags=["Organizations"])
async def create_organization(
    org: OrganizationCreate,
    current_user: UserRead = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> OrganizationRead:
    from slugify import slugify
    slug = slugify(org.name)[:100]
    # Ensure unique slug
    base_slug = slug
    counter = 1
    while True:
        result = await db.execute(select(Organization).where(Organization.slug == slug))
        if not result.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    db_org = Organization(name=org.name, slug=slug, settings=org.settings or {})
    db.add(db_org)
    await db.commit()
    await db.refresh(db_org)
    return OrganizationRead.model_validate(db_org)


@app.get("/api/organizations", response_model=list[OrganizationRead], tags=["Organizations"])
async def list_organizations(
    current_user: UserRead = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> list[OrganizationRead]:
    result = await db.execute(select(Organization).where(Organization.is_active == True))
    return [OrganizationRead.model_validate(o) for o in result.scalars().all()]


@app.get("/api/organizations/{org_id}", response_model=OrganizationRead, tags=["Organizations"])
async def get_organization(
    org_id: UUID,
    current_user: UserRead = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> OrganizationRead:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationRead.model_validate(org)


@app.patch("/api/organizations/{org_id}", response_model=OrganizationRead, tags=["Organizations"])
async def update_organization(
    org_id: UUID,
    update: OrganizationUpdate,
    current_user: UserRead = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> OrganizationRead:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if update.name is not None:
        org.name = update.name
    if update.settings is not None:
        org.settings = update.settings
    if update.is_active is not None:
        org.is_active = update.is_active

    await db.commit()
    await db.refresh(org)
    return OrganizationRead.model_validate(org)


# User management (admin only)
@app.post("/api/users", response_model=UserRead, status_code=status.HTTP_201_CREATED, tags=["Users"])
async def create_user(
    user: UserCreate,
    current_user: UserRead = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> UserRead:
    from call_analysis.auth import hash_password

    # Check email unique within org
    result = await db.execute(
        select(User).where(User.email == user.email, User.organization_id == current_user.organization_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    db_user = User(
        organization_id=current_user.organization_id,
        email=user.email,
        hashed_password=hash_password(user.password),
        full_name=user.full_name,
        role=user.role,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return UserRead.model_validate(db_user)


@app.get("/api/users", response_model=list[UserRead], tags=["Users"])
async def list_users(
    current_user: UserRead = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> list[UserRead]:
    result = await db.execute(
        select(User).where(User.organization_id == current_user.organization_id)
    )
    return [UserRead.model_validate(u) for u in result.scalars().all()]


# API Key management
@app.post("/api/api-keys", response_model=APIKeyWithSecret, status_code=status.HTTP_201_CREATED, tags=["API Keys"])
async def create_api_key(
    api_key: APIKeyCreate,
    current_user: UserRead = Depends(require_analyst),
    db: AsyncSession = Depends(get_async_session),
) -> APIKeyWithSecret:
    from call_analysis.auth import generate_api_key
    from call_analysis.models import APIKey

    plain_key, key_hash = generate_api_key(settings.auth.api_key_prefix, settings.auth.api_key_length)

    db_key = APIKey(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        name=api_key.name,
        key_hash=key_hash,
        prefix=settings.auth.api_key_prefix,
        scopes=api_key.scopes,
        expires_at=api_key.expires_at,
    )
    db.add(db_key)
    await db.commit()
    await db.refresh(db_key)

    return APIKeyWithSecret(
        **APIKeyRead.model_validate(db_key).model_dump(),
        key=plain_key,
    )


@app.get("/api/api-keys", response_model=list[APIKeyRead], tags=["API Keys"])
async def list_api_keys(
    current_user: UserRead = Depends(require_analyst),
    db: AsyncSession = Depends(get_async_session),
) -> list[APIKeyRead]:
    result = await db.execute(
        select(APIKey).where(APIKey.organization_id == current_user.organization_id)
    )
    return [APIKeyRead.model_validate(k) for k in result.scalars().all()]


@app.delete("/api/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["API Keys"])
async def revoke_api_key(
    key_id: UUID,
    current_user: UserRead = Depends(require_analyst),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    result = await db.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.organization_id == current_user.organization_id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.is_active = False
    await db.commit()


# Webhook management
@app.post("/api/webhooks", response_model=WebhookRead, status_code=status.HTTP_201_CREATED, tags=["Webhooks"])
async def create_webhook(
    webhook: WebhookCreate,
    current_user: UserRead = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> WebhookRead:
    import secrets
    secret = secrets.token_urlsafe(32)

    db_webhook = Webhook(
        organization_id=current_user.organization_id,
        name=webhook.name,
        url=webhook.url,
        secret=secret,
        events=webhook.events,
        is_active=webhook.is_active,
    )
    db.add(db_webhook)
    await db.commit()
    await db.refresh(db_webhook)
    return WebhookRead.model_validate(db_webhook)


@app.get("/api/webhooks", response_model=list[WebhookRead], tags=["Webhooks"])
async def list_webhooks(
    current_user: UserRead = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> list[WebhookRead]:
    result = await db.execute(
        select(Webhook).where(Webhook.organization_id == current_user.organization_id)
    )
    return [WebhookRead.model_validate(w) for w in result.scalars().all()]


@app.delete("/api/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Webhooks"])
async def delete_webhook(
    webhook_id: UUID,
    current_user: UserRead = Depends(require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    result = await db.execute(
        select(Webhook).where(Webhook.id == webhook_id, Webhook.organization_id == current_user.organization_id)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(webhook)
    await db.commit()


# Call endpoints
@app.get("/api/analytics", response_model=AnalyticsSummary, tags=["Calls"])
async def analytics(
    current_user: UserRead = Depends(get_current_user_or_api_key),
    db: AsyncSession = Depends(get_async_session),
) -> AnalyticsSummary:
    from sqlalchemy import func

    # Get calls for organization
    stmt = select(CallRecord).where(CallRecord.organization_id == current_user.organization_id)
    result = await db.execute(stmt)
    calls = result.scalars().all()

    by_status = {"completed": 0, "processing": 0, "failed": 0, "pending": 0}
    qa_scores = []
    comp_scores = []
    sent_scores = []
    pii_total = 0
    languages = {}

    for c in calls:
        st = c.status.value if c.status in by_status else "pending"
        by_status[st] = by_status.get(st, 0) + 1
        pii_total += len(c.pii_findings)
        if c.language:
            languages[c.language] = languages.get(c.language, 0) + 1

        agents = c.agents or {}
        qa = agents.get("qa_scorecard")
        if qa and qa.get("score") is not None:
            qa_scores.append(float(qa["score"]))
        cr = agents.get("compliance_risk")
        if cr and cr.get("score") is not None:
            comp_scores.append(float(cr["score"]))
        se = agents.get("sentiment_emotion")
        if se and se.get("score") is not None:
            sent_scores.append(float(se["score"]))

    def avg(xs):
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


@app.get("/api/calls", response_model=PaginatedResponse, tags=["Calls"])
async def list_calls(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    current_user: UserRead = Depends(get_current_user_or_api_key),
    db: AsyncSession = Depends(get_async_session),
) -> PaginatedResponse:
    from sqlalchemy import func, desc

    stmt = select(CallRecord).where(CallRecord.organization_id == current_user.organization_id)
    if status_filter:
        stmt = stmt.where(CallRecord.status == status_filter)

    # Total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.execute(count_stmt)
    total = total.scalar()

    # Pagination
    stmt = stmt.order_by(desc(CallRecord.created_at)).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    calls = result.scalars().all()

    items = []
    for c in calls:
        agents = c.agents or {}
        qa = agents.get("qa_scorecard")
        items.append(CallRecordListItem(
            id=c.id,
            filename=c.filename,
            status=c.status,
            created_at=c.created_at,
            updated_at=c.updated_at,
            duration_sec=c.duration_sec,
            language=c.language,
            error=c.error,
            progress_pct=c.progress_pct,
            progress_message=c.progress_message,
            qa_score=qa.get("score") if qa else None,
            pii_count=len(c.pii_findings),
        ))

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@app.get("/api/calls/{call_id}", response_model=CallRecordRead, tags=["Calls"])
async def get_call(
    call_id: UUID,
    current_user: UserRead = Depends(get_current_user_or_api_key),
    db: AsyncSession = Depends(get_async_session),
) -> CallRecordRead:
    result = await db.execute(
        select(CallRecord).where(
            CallRecord.id == call_id,
            CallRecord.organization_id == current_user.organization_id,
        )
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return CallRecordRead.model_validate(call)


@app.delete("/api/calls/{call_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Calls"])
async def delete_call(
    call_id: UUID,
    current_user: UserRead = Depends(require_analyst),
    db: AsyncSession = Depends(get_async_session),
) -> None:
    result = await db.execute(
        select(CallRecord).where(
            CallRecord.id == call_id,
            CallRecord.organization_id == current_user.organization_id,
        )
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    await db.delete(call)
    await db.commit()


@app.post("/api/calls/upload", response_model=UploadResponse, tags=["Calls"])
@limiter.limit("10/minute")
async def upload_call(
    request: Request,
    file: UploadFile = File(...),
    analyze: bool = True,
    current_user: UserRead = Depends(get_current_user_or_api_key),
    db: AsyncSession = Depends(get_async_session),
) -> UploadResponse:
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    ext = Path(file.filename).suffix.lower()
    if ext not in settings.storage.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")

    # Read file content
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    if len(content) > settings.storage.max_upload_size:
        raise HTTPException(status_code=413, detail="File too large")

    # Save to storage
    from call_analysis.storage import CallStore
    store = CallStore()

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        rec = store.register_upload(tmp_path, copy=True, filename=file.filename)

        # Create database record
        db_call = CallRecord(
            id=UUID(rec.id),
            organization_id=current_user.organization_id,
            filename=rec.filename,
            source_path=rec.source_path,
            status=JobStatus.PENDING,
        )
        db.add(db_call)
        await db.commit()

        if analyze:
            process_call.delay(rec.id, str(current_user.organization_id))

        return UploadResponse(id=UUID(rec.id), filename=rec.filename, status=JobStatus.PENDING)
    finally:
        tmp_path.unlink(missing_ok=True)


@app.post("/api/calls/import-local", response_model=ImportResponse, tags=["Calls"])
async def import_local(
    body: ImportLocalRequest,
    current_user: UserRead = Depends(get_current_user_or_api_key),
    db: AsyncSession = Depends(get_async_session),
) -> ImportResponse:
    from call_analysis.storage import CallStore
    store = CallStore()

    imported = []
    skipped = []
    known = set()

    if body.path:
        p = Path(body.path)
        if not p.is_file():
            raise HTTPException(status_code=400, detail=f"File not found: {body.path}")
        if body.skip_existing and p.name in known:
            skipped.append(p.name)
        else:
            rec = store.register_upload(p, copy=True)
            db_call = CallRecord(
                id=UUID(rec.id),
                organization_id=current_user.organization_id,
                filename=rec.filename,
                source_path=rec.source_path,
                status=JobStatus.PENDING,
            )
            db.add(db_call)
            await db.commit()
            if body.analyze:
                process_call.delay(rec.id, str(current_user.organization_id))
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
            db_call = CallRecord(
                id=UUID(rec.id),
                organization_id=current_user.organization_id,
                filename=rec.filename,
                source_path=rec.source_path,
                status=JobStatus.PENDING,
            )
            db.add(db_call)
            await db.commit()
            known.add(f.name)
            if body.analyze:
                process_call.delay(rec.id, str(current_user.organization_id))
            imported.append({"id": rec.id, "filename": rec.filename})
            if len(imported) >= body.limit:
                break
        if not imported and not skipped:
            raise HTTPException(status_code=404, detail="No recordings found in project folder")

    return ImportResponse(imported=imported, skipped=skipped[:20])


@app.post("/api/calls/{call_id}/analyze", response_model=UploadResponse, tags=["Calls"])
async def analyze_call(
    call_id: UUID,
    current_user: UserRead = Depends(get_current_user_or_api_key),
    db: AsyncSession = Depends(get_async_session),
) -> UploadResponse:
    result = await db.execute(
        select(CallRecord).where(
            CallRecord.id == call_id,
            CallRecord.organization_id == current_user.organization_id,
        )
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.status == JobStatus.PROCESSING:
        return UploadResponse(id=call.id, filename=call.filename, status=call.status)

    process_call.delay(str(call_id), str(current_user.organization_id))
    return UploadResponse(id=call.id, filename=call.filename, status=JobStatus.PROCESSING)


# Copilot endpoint
@app.post("/api/calls/{call_id}/copilot", response_model=CopilotResponse, tags=["Calls"])
@limiter.limit("30/minute")
async def copilot(
    request: Request,
    call_id: UUID,
    body: CopilotRequest,
    current_user: UserRead = Depends(get_current_user_or_api_key),
    db: AsyncSession = Depends(get_async_session),
) -> CopilotResponse:
    from call_analysis.agents.orchestrator import answer_copilot
    from call_analysis.config import load_nvidia_config

    result = await db.execute(
        select(CallRecord).where(
            CallRecord.id == call_id,
            CallRecord.organization_id == current_user.organization_id,
        )
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Call analysis not completed yet")

    try:
        cfg = load_nvidia_config(require_key=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    agent_ctx = {k: v for k, v in call.agents.items()}
    answer = answer_copilot(
        cfg,
        question=body.question,
        transcript=call.scrubbed_transcript or call.full_transcript,
        agent_context=agent_ctx,
    )

    return CopilotResponse(answer=answer)


# Static dashboard
WEB_DIR = Path(__file__).resolve().parents[1] / "web"

if WEB_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html")


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    struct_logger.bind(path=request.url.path, method=request.method).exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            detail="Internal server error",
            error_code="INTERNAL_ERROR",
            request_id=request.state.request_id,
        ).model_dump(),
    )


# Import datetime for login
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select, desc, func


# Backward compatibility for tests
def create_app(store=None) -> FastAPI:
    """Create app instance for testing (backward compatible)."""
    return app