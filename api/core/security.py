"""
MangoPoint API - Authentication Security Utilities
==================================================
Password hashing, JWT handling, and FastAPI auth dependencies.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
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
SESSION_IDLE_TIMEOUT_SECONDS = 15 * 60


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


def session_credential_stamp(user: UserAccount | None = None) -> str:
    """Bind a session to credentials without exposing their stored hash."""
    value = (
        f"account:{user.user_id}:{user.password_hash}" if user is not None
        else f"offline:{settings.DEFAULT_ADMIN_USERNAME}:{settings.DEFAULT_ADMIN_PASSWORD}"
    )
    return hmac.new(
        _get_secret_key().encode(),
        f"mangopoint-session-v1:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


def create_session_token(
    user: UserAccount,
    session_started_at: int | None = None,
    activity_age_seconds: float = 0,
) -> tuple[str, datetime]:
    """Renew only within the idle window and the original absolute lifetime."""
    now = datetime.now(timezone.utc)
    started = session_started_at if session_started_at is not None else int(now.timestamp())
    absolute_expiry = datetime.fromtimestamp(started, timezone.utc) + timedelta(
        minutes=settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expiry = min(
        now + timedelta(seconds=SESSION_IDLE_TIMEOUT_SECONDS - activity_age_seconds),
        absolute_expiry,
    )
    if expiry <= now:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    offline = user.user_id == 0
    claims = {
        "role": user.role.value,
        "session_started_at": started,
        "credential_stamp": session_credential_stamp(None if offline else user),
        "jti": secrets.token_urlsafe(16),
    }
    if offline:
        claims.update(offline_auth=True, username=user.username, email=user.email,
                      full_name=user.full_name, is_active=user.is_active)
    return create_access_token(str(user.user_id), expiry - now, claims)


def decode_session_token(token: str) -> dict[str, Any]:
    """Reject legacy sessions as well as expired or malformed session claims."""
    try:
        payload = decode_access_token(token)
        started, issued, expires = (payload.get(key) for key in ("session_started_at", "iat", "exp"))
        stamp = payload.get("credential_stamp")
        if (any(type(value) is not int for value in (started, issued, expires))
                or not isinstance(stamp, str) or len(stamp) != 64
                or any(char not in '0123456789abcdef' for char in stamp)
                or started > issued or expires > issued + SESSION_IDLE_TIMEOUT_SECONDS + 1
                or expires > started + settings.AUTH_ACCESS_TOKEN_EXPIRE_MINUTES * 60 + 1):
            raise jwt.exceptions.InvalidTokenError("Unsupported session claims")
        return payload
    except AuthConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except jwt.exceptions.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.") from exc
    except jwt.exceptions.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Session is no longer valid. Please sign in again.") from exc


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

    payload = decode_session_token(credentials.credentials)

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
    if offline_user is not None and (
        not settings.DEFAULT_ADMIN_ENABLED
        or not hmac.compare_digest(payload["credential_stamp"], session_credential_stamp())
    ):
        raise HTTPException(status_code=401, detail="Session is no longer valid. Please sign in again.")

    try:
        result = await db.execute(select(UserAccount).where(UserAccount.user_id == user_id))
        user = result.scalar_one_or_none()

        # Offline fallback tokens use the temporary subject ``0`` because no
        # database row is available when they are issued.  Once PostgreSQL is
        # reachable again, resolve that signed token to the persisted account
        # with the same username.  Returning the temporary model here would
        # make authenticated reads appear healthy while writes fail foreign-key
        # checks such as ``created_by_user_id``.
        if user is None and offline_user is not None:
            recovered_result = await db.execute(
                select(UserAccount).where(
                    func.lower(UserAccount.username)
                    == str(offline_user.username).strip().lower()
                )
            )
            user = recovered_result.scalar_one_or_none()
    except Exception as exc:
        if offline_user is not None and is_database_unavailable(exc):
            return offline_user
        if is_database_unavailable(exc):
            raise database_unavailable_http_exception() from exc
        raise

    if user is None:
        if offline_user is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Offline session no longer matches a database account. Please sign in again.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user no longer exists.",
        )

    if offline_user is not None:
        # A fallback session must never bypass a password changed in the
        # persisted account while PostgreSQL was unavailable to that device.
        valid_credentials = bool(user.password_hash) and verify_password(
            settings.DEFAULT_ADMIN_PASSWORD, user.password_hash
        )
    else:
        valid_credentials = hmac.compare_digest(payload["credential_stamp"], session_credential_stamp(user))
    if not valid_credentials:
        raise HTTPException(status_code=401, detail="Your password changed or your session was revoked. Please sign in again.")
    return user


async def get_current_active_user(current_user: UserAccount = Depends(get_current_user)) -> UserAccount:
    """Return the current user only when the account is active."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )
    return current_user
