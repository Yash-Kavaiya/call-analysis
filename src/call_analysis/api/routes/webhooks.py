"""Webhook subscription routes."""

from __future__ import annotations

import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from call_analysis.api.deps import require_admin_user
from call_analysis.config import get_settings
from call_analysis.database import get_async_session
from call_analysis.models import Webhook
from call_analysis.schemas import UserRead, WebhookCreate, WebhookRead

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


def _ensure_webhooks_enabled() -> None:
    if not get_settings().features.webhook_enabled:
        raise HTTPException(status_code=404, detail="Webhooks feature disabled")


@router.post("", response_model=WebhookRead, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    body: WebhookCreate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_admin_user)],
) -> Webhook:
    _ensure_webhooks_enabled()
    wh = Webhook(
        organization_id=current_user.organization_id,
        name=body.name,
        url=body.url,
        secret=secrets.token_urlsafe(32),
        events=body.events,
        is_active=body.is_active,
    )
    db.add(wh)
    await db.commit()
    await db.refresh(wh)
    return wh


@router.get("", response_model=list[WebhookRead])
async def list_webhooks(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_admin_user)],
) -> list[Webhook]:
    _ensure_webhooks_enabled()
    result = await db.execute(
        select(Webhook)
        .where(Webhook.organization_id == current_user.organization_id)
        .order_by(Webhook.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: UUID,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_admin_user)],
) -> None:
    _ensure_webhooks_enabled()
    wh = await db.get(Webhook, webhook_id)
    if wh is None or wh.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(wh)
    await db.commit()
