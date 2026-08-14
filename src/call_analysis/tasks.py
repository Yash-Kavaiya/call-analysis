"""Celery tasks for background processing."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from celery import shared_task
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from call_analysis.celery_app import celery_app
from call_analysis.database import sync_session_context
from call_analysis.models import CallEvent, CallRecord, SystemMetric, Webhook, WebhookDelivery
from call_analysis.redis_client import JobStatusTracker, get_redis
from call_analysis.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Job status tracker
_job_tracker = JobStatusTracker()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_call(self, call_id: str, organization_id: str | None = None) -> dict[str, Any]:
    """
    Process a call recording through the full pipeline.
    
    This is the main analysis task that runs in the background.
    """
    from call_analysis.pipeline.runner import process_call as run_pipeline
    from call_analysis.storage import CallStore

    call_uuid = UUID(call_id)
    org_uuid = UUID(organization_id) if organization_id else None

    # Update job status
    _job_tracker.set_status(call_id, "processing", 0.0, "Starting analysis")

    try:
        # Use sync session for Celery worker
        with sync_session_context() as db:
            # Get call record
            stmt = select(CallRecord).where(CallRecord.id == call_uuid)
            if org_uuid:
                stmt = stmt.where(CallRecord.organization_id == org_uuid)
            call = db.execute(stmt).scalar_one_or_none()

            if not call:
                raise ValueError(f"Call {call_id} not found")

            # Create store with database-backed paths
            store = CallStore()
            
            def progress_callback(msg: str, pct: float) -> None:
                _job_tracker.set_status(call_id, "processing", pct, msg)
                # Also update database
                call.progress_pct = pct
                call.progress_message = msg
                db.commit()

            # Run pipeline
            result = run_pipeline(
                call_id,
                store=store,
                on_progress=progress_callback,
            )

            # Update database record
            call.status = result.status
            call.error = result.error
            call.progress_pct = result.progress_pct
            call.progress_message = result.progress_message
            call.duration_sec = result.duration_sec
            call.language = result.language
            call.full_transcript = result.full_transcript
            call.scrubbed_transcript = result.scrubbed_transcript
            call.segments = [s.to_dict() for s in result.segments]
            call.pii_findings = [p.to_dict() for p in result.pii_findings]
            call.agents = {k: v.to_dict() for k, v in result.agents.items()}
            call.waveform_peaks = result.waveform_peaks
            call.metadata = result.metadata
            call.completed_at = datetime.now(timezone.utc) if result.status == "completed" else None

            # Add event
            event = CallEvent(
                call_id=call.id,
                event_type="analysis_completed" if result.status == "completed" else "analysis_failed",
                message=f"Analysis {result.status}",
                details={"status": result.status, "error": result.error},
                level="INFO" if result.status == "completed" else "ERROR",
            )
            db.add(event)
            db.commit()

        _job_tracker.set_status(
            call_id,
            result.status,
            1.0 if result.status == "completed" else result.progress_pct,
            result.progress_message or result.error or "Complete",
        )

        return {"status": result.status, "call_id": call_id}

    except Exception as exc:
        logger.exception(f"Call processing failed for {call_id}")
        _job_tracker.set_status(call_id, "failed", 0.0, str(exc))

        # Update database
        with sync_session_context() as db:
            stmt = select(CallRecord).where(CallRecord.id == call_uuid)
            call = db.execute(stmt).scalar_one_or_none()
            if call:
                call.status = "failed"
                call.error = str(exc)
                call.progress_message = f"Failed: {exc}"
                event = CallEvent(
                    call_id=call.id,
                    event_type="analysis_failed",
                    message=f"Analysis failed: {exc}",
                    details={"error": str(exc)},
                    level="ERROR",
                )
                db.add(event)
                db.commit()

        # Retry logic
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)

        return {"status": "failed", "call_id": call_id, "error": str(exc)}


@shared_task(bind=True, max_retries=2)
def analyze_batch(self, call_ids: list[str], organization_id: str) -> dict[str, Any]:
    """Process multiple calls in batch."""
    org_uuid = UUID(organization_id)
    results = []

    for call_id in call_ids:
        try:
            result = process_call.delay(call_id, organization_id)
            results.append({"call_id": call_id, "task_id": result.id, "status": "queued"})
        except Exception as exc:
            logger.exception(f"Failed to queue call {call_id}")
            results.append({"call_id": call_id, "status": "failed", "error": str(exc)})

    return {"organization_id": organization_id, "results": results}


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def webhook_delivery(self, delivery_id: str) -> dict[str, Any]:
    """Deliver webhook with retry logic."""
    import httpx

    delivery_uuid = UUID(delivery_id)

    with sync_session_context() as db:
        delivery = db.execute(
            select(WebhookDelivery).where(WebhookDelivery.id == delivery_uuid)
        ).scalar_one_or_none()

        if not delivery:
            return {"status": "not_found", "delivery_id": delivery_id}

        webhook = db.execute(
            select(Webhook).where(Webhook.id == delivery.webhook_id)
        ).scalar_one_or_none()

        if not webhook or not webhook.is_active:
            delivery.error = "Webhook not found or inactive"
            db.commit()
            return {"status": "skipped", "delivery_id": delivery_id}

        try:
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Signature": _sign_payload(delivery.payload, webhook.secret),
                "X-Webhook-Event": delivery.event_type,
                "X-Webhook-Delivery": str(delivery.id),
            }

            with httpx.Client(timeout=30.0) as client:
                response = client.post(webhook.url, json=delivery.payload, headers=headers)

            delivery.response_status = response.status_code
            delivery.response_body = response.text[:1000] if response.text else None

            if 200 <= response.status_code < 300:
                delivery.error = None
                db.commit()
                return {"status": "delivered", "delivery_id": delivery_id, "status_code": response.status_code}
            else:
                delivery.error = f"HTTP {response.status_code}: {response.text[:200]}"
                db.commit()
                raise Exception(f"Webhook returned {response.status_code}")

        except Exception as exc:
            delivery.error = str(exc)
            delivery.attempt += 1
            db.commit()

            if self.request.retries < self.max_retries:
                raise self.retry(exc=exc)

            return {"status": "failed", "delivery_id": delivery_id, "error": str(exc)}


def _sign_payload(payload: dict, secret: str) -> str:
    import hmac
    import hashlib
    import json
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@shared_task
def cleanup_old_jobs(days: int = 30) -> dict[str, Any]:
    """Clean up completed/failed jobs older than specified days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    with sync_session_context() as db:
        # Clean up old call records (keep for compliance, just archive status)
        # In production, you might move to cold storage instead
        deleted_calls = 0  # Placeholder for actual cleanup logic

        # Clean up Redis job statuses
        redis = get_redis()
        # This would need a scan - simplified for now

    return {"deleted_calls": deleted_calls, "cutoff": cutoff.isoformat()}


@shared_task
def cleanup_old_events(days: int = 90) -> dict[str, Any]:
    """Clean up old call events."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    with sync_session_context() as db:
        result = db.execute(
            delete(CallEvent).where(CallEvent.created_at < cutoff)
        )
        db.commit()
        deleted = result.rowcount

    return {"deleted_events": deleted, "cutoff": cutoff.isoformat()}


@shared_task
def collect_system_metrics() -> dict[str, Any]:
    """Collect system metrics for monitoring."""
    import psutil
    import time

    metrics = []

    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.1)
    metrics.append(SystemMetric(
        metric_name="system.cpu.percent",
        metric_value=cpu_percent,
        labels={"host": "localhost"},
    ))

    # Memory
    mem = psutil.virtual_memory()
    metrics.append(SystemMetric(
        metric_name="system.memory.percent",
        metric_value=mem.percent,
        labels={"host": "localhost"},
    ))
    metrics.append(SystemMetric(
        metric_name="system.memory.available_bytes",
        metric_value=mem.available,
        labels={"host": "localhost"},
    ))

    # Disk
    disk = psutil.disk_usage("/")
    metrics.append(SystemMetric(
        metric_name="system.disk.percent",
        metric_value=(disk.used / disk.total) * 100,
        labels={"host": "localhost", "mount": "/"},
    ))

    # Network
    net = psutil.net_io_counters()
    metrics.append(SystemMetric(
        metric_name="system.network.bytes_sent",
        metric_value=net.bytes_sent,
        labels={"host": "localhost"},
    ))
    metrics.append(SystemMetric(
        metric_name="system.network.bytes_recv",
        metric_value=net.bytes_recv,
        labels={"host": "localhost"},
    ))

    # Celery queue depths (if available)
    try:
        inspect = celery_app.control.inspect()
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        for worker, tasks in active.items():
            metrics.append(SystemMetric(
                metric_name="celery.worker.active_tasks",
                metric_value=len(tasks),
                labels={"worker": worker},
            ))
        for worker, tasks in reserved.items():
            metrics.append(SystemMetric(
                metric_name="celery.worker.reserved_tasks",
                metric_value=len(tasks),
                labels={"worker": worker},
            ))
    except Exception:
        pass

    with sync_session_context() as db:
        db.add_all(metrics)
        db.commit()

    return {"metrics_collected": len(metrics), "timestamp": datetime.now(timezone.utc).isoformat()}