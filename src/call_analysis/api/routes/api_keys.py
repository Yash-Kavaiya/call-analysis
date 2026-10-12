"""API key management routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from call_analysis.api.deps import require_analyst_user
from call_analysis.auth import generate_api_key
from call_analysis.database import get_async_session
from call_analysis.models import APIKey
from call_analysis.schemas import APIKeyCreate, APIKeyRead, APIKeyWithSecret, UserRead

router = APIRouter(prefix="/api/api-keys", tags=["API Keys"])


@router.post("", response_model=APIKeyWithSecret, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: APIKeyCreate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_analyst_user)],
) -> APIKeyWithSecret:
    plain, key_hash = generate_api_key()
    prefix = plain[:8]
    row = APIKey(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        name=body.name,
        key_hash=key_hash,
        prefix=prefix,
        scopes=body.scopes,
        expires_at=body.expires_at,
        is_active=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    data = APIKeyRead.model_validate(row)
    return APIKeyWithSecret(**data.model_dump(), key=plain)


@router.get("", response_model=list[APIKeyRead])
async def list_api_keys(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_analyst_user)],
) -> list[APIKey]:
    result = await db.execute(
        select(APIKey)
        .where(APIKey.organization_id == current_user.organization_id)
        .order_by(APIKey.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_analyst_user)],
) -> None:
    row = await db.get(APIKey, key_id)
    if row is None or row.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="API key not found")
    row.is_active = False
    await db.commit()
