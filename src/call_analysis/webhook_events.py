"""Webhook event emission after call lifecycle changes."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select

from call_analysis.config import get_settings
from call_analysis.database import SyncSessionLocal
from call_analysis.models import CallRecord, Webhook, WebhookDelivery

logger = logging.getLogger(__name__)


def emit_call_event(
    organization_id: str | UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Create webhook deliveries and queue Celery delivery tasks."""
    settings = get_settings()
    if not settings.features.webhook_enabled:
        return

    org_uuid = UUID(str(organization_id))

    with SyncSessionLocal() as db:
        webhooks = (
            db.execute(
                select(Webhook).where(
                    Webhook.organization_id == org_uuid,
                    Webhook.is_active.is_(True),
                )
            )
            .scalars()
            .all()
        )
        if not webhooks:
            return

        delivery_ids: list[str] = []
        for wh in webhooks:
            events = wh.events or []
            if events and event_type not in events:
                continue
            delivery = WebhookDelivery(
                webhook_id=wh.id,
                event_type=event_type,
                payload=payload,
            )
            db.add(delivery)
            db.flush()
            delivery_ids.append(str(delivery.id))
            wh.last_triggered_at = delivery.created_at
        db.commit()

    for delivery_id in delivery_ids:
        try:
            from call_analysis.tasks import webhook_delivery

            webhook_delivery.delay(delivery_id)
        except Exception:
            logger.exception("Failed to queue webhook delivery %s", delivery_id)


def notify_call_completed(organization_id: str, record: CallRecord) -> None:
    """Emit analysis.completed webhook with a redacted summary payload."""
    qa = record.agents.get("qa_scorecard")
    payload = {
        "event": "analysis.completed",
        "call_id": record.id,
        "filename": record.filename,
        "status": record.status,
        "duration_sec": record.duration_sec,
        "language": record.language,
        "qa_score": qa.score if qa else None,
        "pii_count": len(record.pii_findings),
    }
    emit_call_event(organization_id, "analysis.completed", payload)
