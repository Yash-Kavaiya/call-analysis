"""User management routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from call_analysis.api.deps import require_admin_user
from call_analysis.auth import hash_password
from call_analysis.database import get_async_session
from call_analysis.models import User
from call_analysis.schemas import UserCreate, UserRead

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_admin_user)],
) -> User:
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        organization_id=current_user.organization_id,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("", response_model=list[UserRead])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[UserRead, Depends(require_admin_user)],
) -> list[User]:
    result = await db.execute(
        select(User)
        .where(User.organization_id == current_user.organization_id)
        .order_by(User.created_at.desc())
    )
    return list(result.scalars().all())
