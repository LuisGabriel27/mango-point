"""
MangoPoint API - Authentication Schemas
=======================================
Pydantic models used by the auth endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
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


class CurrentUserUpdateRequest(BaseModel):
    """Editable profile fields for the authenticated account."""

    full_name: str = Field(..., min_length=1, max_length=200)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be empty.")
        return normalized


class PasswordChangeRequest(BaseModel):
    """Current and replacement credentials for a password change."""

    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)

    @model_validator(mode="after")
    def passwords_must_differ(self) -> "PasswordChangeRequest":
        if self.current_password == self.new_password:
            raise ValueError("New password must be different from the current password.")
        return self


class PasswordChangeResponse(BaseModel):
    """Confirmation returned after a password is replaced."""

    message: str


class PasswordResetRequest(BaseModel):
    """Email address used to request a password-reset link."""

    email: str = Field(..., min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized.count("@") != 1 or "." not in normalized.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address.")
        return normalized


class PasswordResetConfirmRequest(BaseModel):
    """Verification challenge, emailed code, and replacement password."""

    challenge_id: str = Field(..., min_length=36, max_length=36)
    code: str = Field(..., pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=8, max_length=256)


class PasswordResetResponse(BaseModel):
    """Neutral password-reset acknowledgement."""

    message: str
    challenge_id: Optional[str] = None


class AccountEmailUpdateRequest(BaseModel):
    """Recovery email change authorized by the current password."""

    email: str = Field(..., min_length=3, max_length=255)
    current_password: str = Field(..., min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return PasswordResetRequest.normalize_email(value)


class LogoutResponse(BaseModel):
    """Logout acknowledgement for client-side token cleanup."""

    message: str
