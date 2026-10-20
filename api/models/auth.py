"""
MangoPoint API - Authentication Schemas
=======================================
Pydantic models used by the auth endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from utils.datetime_utils import format_rfc3339
from utils.input_validation import normalize_email, normalize_person_name


def _serialize_datetime(value: Optional[datetime]) -> Optional[str]:
    """Serialize datetimes consistently for API responses."""
    if value is None:
        return None
    return format_rfc3339(value)


class LoginRequest(BaseModel):
    """Login request payload."""

    username_or_email: str = Field(..., min_length=1, max_length=254, description="Username or email address")
    password: str = Field(..., min_length=1, max_length=256, description="Account password")
    recover_sessions: bool = Field(default=False, strict=True, description="Request email-verified session recovery")

    @field_validator("username_or_email")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Enter your username or email address.")
        return value


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


class LoginChallengeResponse(BaseModel):
    """Password accepted; no authenticated session exists until email verification."""

    verification_required: bool = True
    session_recovery: bool = False
    challenge_id: str
    masked_email: str
    expires_at: str
    resend_after_seconds: int
    message: str = "Enter the six-digit code sent to your account email."


class LoginChallengeRequest(BaseModel):
    challenge_id: str = Field(..., min_length=36, max_length=36)


class LoginVerifyRequest(LoginChallengeRequest):
    code: str = Field(..., pattern=r"^[0-9]{6}$")


class CurrentUserResponse(BaseModel):
    """Session validation response used by the dashboard."""

    authenticated: bool = True
    user: AuthUserResponse


class SessionRefreshRequest(BaseModel):
    """Age of the latest user interaction; background reads do not renew."""

    activity_age_seconds: float = Field(default=0, ge=0, lt=900, allow_inf_nan=False)


class CurrentUserUpdateRequest(BaseModel):
    """Editable profile fields for the authenticated account."""

    full_name: str = Field(..., min_length=1, max_length=200)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        return normalize_person_name(value)


class PasswordChangeRequest(BaseModel):
    """Current and replacement credentials for a password change."""

    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)
    challenge_id: str = Field(..., min_length=36, max_length=36)
    code: str = Field(..., pattern=r"^[0-9]{6}$")

    @field_validator("new_password")
    @classmethod
    def password_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("New password cannot be blank.")
        return value

    @model_validator(mode="after")
    def passwords_must_differ(self) -> "PasswordChangeRequest":
        if self.current_password == self.new_password:
            raise ValueError("New password must be different from the current password.")
        return self


class PasswordChangeResponse(BaseModel):
    """Confirmation returned after a password is replaced."""

    message: str


class PasswordChangeCodeRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)


class PasswordResetRequest(BaseModel):
    """Email address used to request a password-reset code."""

    email: str = Field(..., min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class PasswordResetConfirmRequest(BaseModel):
    """Verification challenge, emailed code, and replacement password."""

    challenge_id: str = Field(..., min_length=36, max_length=36)
    code: str = Field(..., pattern=r"^[0-9]{6}$")
    new_password: str = Field(..., min_length=8, max_length=256)

    @field_validator("new_password")
    @classmethod
    def password_must_not_be_blank(cls, value: str) -> str:
        return PasswordChangeRequest.password_must_not_be_blank(value)


class PasswordResetResponse(BaseModel):
    """Neutral password-reset acknowledgement."""

    message: str
    challenge_id: Optional[str] = None


class AccountEmailUpdateRequest(BaseModel):
    """Recovery email change authorized by the password and existing inbox."""

    email: str = Field(..., min_length=3, max_length=255)
    current_password: str = Field(..., min_length=1, max_length=256)
    challenge_id: str = Field(..., min_length=36, max_length=36)
    code: str = Field(..., pattern=r"^[0-9]{6}$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return PasswordResetRequest.normalize_email(value)


class LogoutResponse(BaseModel):
    """Logout acknowledgement after revoking the persisted session."""

    message: str
