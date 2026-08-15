"""Authentication module with JWT tokens and API keys."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select

from call_analysis.config import get_settings
from call_analysis.database import get_async_session
from call_analysis.models import APIKey, User, UserRole
from call_analysis.schemas import TokenData, UserRead

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()

# Use argon2 for password hashing (modern, secure, no bcrypt version issues)
# Fallback to sha256 if argon2 not available
try:
    import argon2  # noqa: F401 — presence check for argon2-cffi

    pwd_context = CryptContext(
        schemes=["argon2"],
        deprecated="auto",
    )
except ImportError:
    # Fallback to sha256 with salt
    import hashlib
    import os

    class Sha256Context:
        def hash(self, secret: str) -> str:
            salt = os.urandom(16).hex()
            hash_obj = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), 100000)
            return f"sha256${salt}${hash_obj.hex()}"

        def verify(self, secret: str, hash_str: str) -> bool:
            try:
                parts = hash_str.split("$")
                if len(parts) != 3:
                    return False
                algo, salt, expected = parts
                if algo != "sha256":
                    return False
                hash_obj = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), 100000)
                return hash_obj.hex() == expected
            except Exception:
                return False

    pwd_context = Sha256Context()

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.auth.access_token_expire_minutes)
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(UTC),
            "type": "access",
            "aud": settings.auth.jwt_audience,
            "iss": settings.auth.jwt_issuer,
        }
    )
    return jwt.encode(to_encode, settings.auth.secret_key, algorithm=settings.auth.algorithm)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=settings.auth.refresh_token_expire_days)
    to_encode.update({"exp": expire, "iat": datetime.now(UTC), "type": "refresh"})
    return jwt.encode(to_encode, settings.auth.secret_key, algorithm=settings.auth.algorithm)


def decode_token(token: str) -> TokenData | None:
    try:
        payload = jwt.decode(
            token,
            settings.auth.secret_key,
            algorithms=[settings.auth.algorithm],
            audience=settings.auth.jwt_audience,
            issuer=settings.auth.jwt_issuer,
        )
        return TokenData(
            user_id=payload.get("sub"),
            organization_id=payload.get("org_id"),
            scopes=payload.get("scopes", []),
            exp=payload.get("exp"),
        )
    except JWTError:
        return None


def generate_api_key(prefix: str = "ca_", length: int = 32) -> tuple[str, str]:
    """Generate API key and its hash. Returns (plain_key, key_hash)."""
    random_part = secrets.token_urlsafe(length)
    plain_key = f"{prefix}{random_part}"
    key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
    return plain_key, key_hash


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserRead:
    """Validate JWT token and return current user."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_token(credentials.credentials)
    if not token_data or not token_data.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UserRead.model_validate(user)


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserRead | None:
    """Validate JWT token but don't require authentication."""
    if not credentials:
        return None

    token_data = decode_token(credentials.credentials)
    if not token_data or not token_data.user_id:
        return None

    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    return UserRead.model_validate(user)


async def get_api_key_user(
    api_key: Annotated[str | None, Security(api_key_header)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserRead:
    """Validate API key and return associated user."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
    )
    api_key_obj = result.scalar_one_or_none()

    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key_obj.expires_at and api_key_obj.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expired",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Update last used
    api_key_obj.last_used_at = datetime.now(UTC)
    await db.commit()

    # Get user
    result = await db.execute(select(User).where(User.id == api_key_obj.user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Associated user not found or inactive",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return UserRead.model_validate(user)


async def get_current_user_or_api_key(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    api_key: Annotated[str | None, Security(api_key_header)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> UserRead:
    """Try JWT first, then API key."""
    settings = get_settings()

    # Allow unauthenticated access in testing mode
    if settings.is_testing:
        from uuid import uuid4

        from call_analysis.schemas import UserRole

        return UserRead(
            id=uuid4(),
            organization_id=uuid4(),
            email="test@example.com",
            full_name="Test User",
            role=UserRole.ADMIN,
            is_active=True,
            is_superuser=True,
            last_login=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    # Try JWT
    if credentials:
        token_data = decode_token(credentials.credentials)
        if token_data and token_data.user_id:
            result = await db.execute(select(User).where(User.id == token_data.user_id))
            user = result.scalar_one_or_none()
            if user and user.is_active:
                return UserRead.model_validate(user)

    # Try API key
    if api_key:
        return await get_api_key_user(api_key, db)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer, ApiKey"},
    )


def require_role(*allowed_roles: UserRole) -> Any:
    """Dependency factory for role-based access control."""

    async def role_checker(
        current_user: Annotated[UserRead, Depends(get_current_user_or_api_key)],
    ) -> UserRead:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {', '.join(r.value for r in allowed_roles)}",
            )
        return current_user

    return role_checker


# Convenience dependencies
require_admin = require_role(UserRole.ADMIN)
require_analyst = require_role(UserRole.ADMIN, UserRole.ANALYST)
require_viewer = require_role(
    UserRead.model_construct(role="admin"),
    UserRead.model_construct(role="analyst"),
    UserRead.model_construct(role="viewer"),
)
