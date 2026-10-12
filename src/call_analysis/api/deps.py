"""FastAPI dependencies for auth and repositories."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from call_analysis.auth import api_key_header, get_current_user_or_api_key
from call_analysis.config import get_settings
from call_analysis.database import get_async_session
from call_analysis.repository import CallRepository, get_call_repository
from call_analysis.schemas import UserRead

bearer_scheme = HTTPBearer(auto_error=False)


def auth_enforced() -> bool:
    settings = get_settings()
    return settings.is_production or settings.features.multi_tenant


async def get_optional_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    api_key: Annotated[str | None, Depends(api_key_header)],
    db=Depends(get_async_session),  # noqa: ANN001
) -> UserRead | None:
    if not auth_enforced():
        return None
    return await get_current_user_or_api_key(request, credentials, api_key, db)


async def get_required_user(
    user: Annotated[UserRead | None, Depends(get_optional_user)],
) -> UserRead:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def get_repo(user: Annotated[UserRead | None, Depends(get_optional_user)]) -> CallRepository:
    return get_call_repository(user)


def require_analyst_user(
    user: Annotated[UserRead, Depends(get_required_user)],
) -> UserRead:
    from call_analysis.models import UserRole

    if user.role not in (UserRole.ADMIN, UserRole.ANALYST) and not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Analyst role required")
    return user


async def analyst_for_writes(
    user: Annotated[UserRead | None, Depends(get_optional_user)],
) -> UserRead | None:
    """Require analyst+ when auth is enforced; allow anonymous writes in local dev."""
    if not auth_enforced():
        return user
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    from call_analysis.models import UserRole

    if user.role not in (UserRole.ADMIN, UserRole.ANALYST) and not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Analyst role required")
    return user


def require_admin_user(
    user: Annotated[UserRead, Depends(get_required_user)],
) -> UserRead:
    from call_analysis.models import UserRole

    if user.role != UserRole.ADMIN and not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user
