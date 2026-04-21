"""
MangoPoint API - Authentication Schemas
=======================================
Pydantic models used by the auth endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from utils.datetime_utils import format_rfc3339


def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    """Serialize datetimes consistently for API responses."""
    if value is None:
        return None
    return format_rfc3339(value)


class LoginRequest(BaseModel):
    """Login request payload."""

    username_or_email: str = Field(..., min_length=1, description="Username or email address")
    password: str = Field(..., min_length=1, description="Account password")


class AuthUserResponse(BaseModel):
    """Authenticated user details returned to the dashboard."""

    user_id: int
    full_name: str
    username: str
    email: str
    role: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login_at: Optional[str] = None

    @classmethod
    def from_user(cls, user) -> "AuthUserResponse":
        """Build a response model from the ORM user object."""
        return cls(
            user_id=user.user_id,
            full_name=user.full_name,
            username=user.username,
            email=user.email,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
            is_active=user.is_active,
            created_at=_serialize_datetime(user.created_at),
            updated_at=_serialize_datetime(user.updated_at),
            last_login_at=_serialize_datetime(user.last_login_at),
        )


class LoginResponse(BaseModel):
    """Successful login response with bearer token metadata."""

    access_token: str
    token_type: str = "bearer"
    expires_at: str
    expires_in_seconds: int
    user: AuthUserResponse


class CurrentUserResponse(BaseModel):
    """Session validation response used by the dashboard."""

    authenticated: bool = True
    user: AuthUserResponse


class LogoutResponse(BaseModel):
    """Logout acknowledgement for client-side token cleanup."""

    message: str
