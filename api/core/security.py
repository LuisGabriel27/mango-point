"""
MangoPoint API - Authentication Security Utilities
==================================================
Password hashing, JWT handling, and FastAPI auth dependencies.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.core.database import (
    database_unavailable_http_exception,
    get_db,
    is_database_unavailable,
)
from db.models import UserAccount, UserRoleEnum
from utils.datetime_utils import utcnow_naive


class AuthConfigurationError(RuntimeError):
    """Raised when auth-specific settings are missing or invalid."""


password_context = None

try:
    from passlib.context import CryptContext

    # Use PBKDF2-SHA256 to avoid the bcrypt 5.x incompatibility present in
    # some local Windows environments while still keeping password hashing secure.
    password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
except ModuleNotFoundError:
    password_context = None


bearer_scheme = HTTPBearer(auto_error=False)


def _role_from_claim(role_value: Any) -> UserRoleEnum:
    """Coerce token role claim to a known enum value."""
    normalized = str(role_value or "").strip().lower()
    try:
        return UserRoleEnum(normalized)
    except ValueError:
        return UserRoleEnum.ADMIN


def _build_offline_user_from_payload(payload: dict[str, Any], user_id: int) -> UserAccount | None:
    """Create an in-memory user model when offline auth claims are present."""
    if not payload.get("offline_auth"):
        return None

    now = utcnow_naive()
    return UserAccount(
        user_id=user_id,
        full_name=str(payload.get("full_name") or settings.DEFAULT_ADMIN_FULL_NAME or "MangoPoint Administrator"),
        username=str(payload.get("username") or settings.DEFAULT_ADMIN_USERNAME or "admin"),
        email=str(payload.get("email") or settings.DEFAULT_ADMIN_EMAIL or "admin@mangopoint.local"),
        password_hash="",
        role=_role_from_claim(payload.get("role")),
        is_active=bool(payload.get("is_active", True)),
        created_at=now,
        updated_at=now,
        last_login_at=now,
    )


def _get_secret_key() -> str:
    """Return the configured JWT secret key or raise a configuration error."""
    secret = (settings.AUTH_SECRET_KEY or "").strip()
    if not secret:
        raise AuthConfigurationError(
            "Authentication is not configured. Set AUTH_SECRET_KEY in the environment."
        )
    return secret


def _ensure_password_context() -> Any:
    """Return the password hashing context once the dependency is installed."""
    if password_context is None:
        raise AuthConfigurationError(
            "Password hashing is unavailable. Install API dependencies from requirements-api.txt."
        )
    return password_context


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored hash."""
    context = _ensure_password_context()
    return context.verify(plain_password, password_hash)


def get_password_hash(password: str) -> str:
    """Hash a plaintext password for database storage."""
    context = _ensure_password_context()
    return context.hash(password)


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> tuple[str, datetime]:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    expire_at = now + (expires_delta or timedelta(minutes=settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES))

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire_at.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, _get_secret_key(), algorithm=settings.AUTH_ALGORITHM)
    return token, expire_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    return jwt.decode(
        token,
        _get_secret_key(),
        algorithms=[settings.AUTH_ALGORITHM],
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> UserAccount:
    """Resolve the current user from a bearer token."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except jwt.exceptions.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
        ) from exc
    except jwt.exceptions.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        ) from exc

    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )

    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        ) from exc

    offline_user = _build_offline_user_from_payload(payload, user_id)

    try:
        result = await db.execute(select(UserAccount).where(UserAccount.user_id == user_id))
    except Exception as exc:
        if offline_user is not None and is_database_unavailable(exc):
            return offline_user
        if is_database_unavailable(exc):
            raise database_unavailable_http_exception() from exc
        raise

    user = result.scalar_one_or_none()
    if user is None:
        if offline_user is not None:
            return offline_user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user no longer exists.",
        )

    return user


async def get_current_active_user(current_user: UserAccount = Depends(get_current_user)) -> UserAccount:
    """Return the current user only when the account is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )
    return current_user
