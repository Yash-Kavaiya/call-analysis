"""Authentication routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from call_analysis.auth import create_access_token, get_current_user, verify_password
from call_analysis.config import get_settings
from call_analysis.database import get_async_session
from call_analysis.models import User
from call_analysis.schemas import LoginRequest, Token, UserRead

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=Token)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> Token:
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user.last_login = datetime.now(UTC).replace(tzinfo=None)
    await db.commit()

    settings = get_settings()
    token = create_access_token(
        {
            "sub": str(user.id),
            "org_id": str(user.organization_id),
            "role": user.role.value,
        }
    )
    return Token(
        access_token=token,
        expires_in=settings.auth.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserRead)
async def me(current_user: Annotated[UserRead, Depends(get_current_user)]) -> UserRead:
    return current_user
