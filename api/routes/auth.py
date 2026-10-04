"""
MangoPoint API - Authentication Routes
======================================
Login and current-session endpoints for the dashboard.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import (
    database_unavailable_http_exception,
    get_db,
    is_database_unavailable,
)
from api.core.config import settings
from api.core.security import AuthConfigurationError, get_current_active_user
from api.models.auth import (
    AuthUserResponse,
    AccountEmailUpdateRequest,
    CurrentUserResponse,
    CurrentUserUpdateRequest,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    PasswordChangeRequest,
    PasswordChangeResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetResponse,
)
from api.services.auth_service import (
    AuthenticationError,
    CurrentPasswordError,
    EmailAlreadyUsedError,
    PasswordResetCodeError,
    auth_service,
)
from api.services.notification_service import notification_service
from db.models import UserAccount


router = APIRouter(prefix="/auth", tags=["Authentication"])

PASSWORD_RESET_REQUEST_MESSAGE = (
    "If an active MangoPoint account uses that email, a six-digit reset code has been sent."
)


@router.post("/login", response_model=LoginResponse, summary="Authenticate a dashboard user")
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate with username/email and password, then return a bearer token."""
    try:
        return await auth_service.login(db, payload.username_or_email, payload.password)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        if is_database_unavailable(exc):
            raise database_unavailable_http_exception() from exc
        raise


@router.post(
    "/password/forgot",
    response_model=PasswordResetResponse,
    summary="Request a password-reset link",
)
async def request_password_reset(
    payload: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> PasswordResetResponse:
    """Email a short-lived reset code without disclosing whether an account exists."""
    try:
        user = await auth_service.get_user_by_email(db, payload.email)
        challenge_id = str(uuid.uuid4())
        if user is not None and user.is_active:
            challenge, code = await auth_service.create_password_reset_challenge(db, user)
            delivered = await notification_service.send_password_reset_code(
                user.email,
                code,
                settings.PASSWORD_RESET_CODE_EXPIRE_MINUTES,
            )
            if not delivered:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Brevo could not send the reset code. Please try again shortly.",
                )
            challenge_id = challenge.challenge_id
            await db.commit()
        return PasswordResetResponse(
            message=PASSWORD_RESET_REQUEST_MESSAGE,
            challenge_id=challenge_id,
        )
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        if is_database_unavailable(exc):
            raise database_unavailable_http_exception() from exc
        raise


@router.post(
    "/password/reset",
    response_model=PasswordResetResponse,
    summary="Reset a password using an emailed code",
)
async def reset_password(
    payload: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> PasswordResetResponse:
    """Replace an account password after validating its six-digit reset code."""
    try:
        await auth_service.reset_password(
            db,
            payload.challenge_id,
            payload.code,
            payload.new_password,
        )
        await db.commit()
        return PasswordResetResponse(
            message="Your password has been reset. You can now sign in."
        )
    except PasswordResetCodeError as exc:
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        if is_database_unavailable(exc):
            raise database_unavailable_http_exception() from exc
        raise


@router.get("/me", response_model=CurrentUserResponse, summary="Get the current authenticated user")
async def get_current_user_profile(
    current_user: UserAccount = Depends(get_current_active_user),
) -> CurrentUserResponse:
    """Validate the current bearer token and return the user profile."""
    return CurrentUserResponse(user=AuthUserResponse.from_user(current_user))


def _require_persisted_account(current_user: UserAccount) -> None:
    if current_user.user_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account settings require a database connection. Try again when the server is online.",
        )


@router.patch("/me", response_model=CurrentUserResponse, summary="Update the current user's profile")
async def update_current_user_profile(
    payload: CurrentUserUpdateRequest,
    current_user: UserAccount = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUserResponse:
    """Update the display name shown throughout the dashboard."""
    _require_persisted_account(current_user)
    auth_service.update_profile(current_user, payload.full_name)
    await db.commit()
    await db.refresh(current_user)
    return CurrentUserResponse(user=AuthUserResponse.from_user(current_user))


@router.patch(
    "/me/email",
    response_model=CurrentUserResponse,
    summary="Update the current user's login and recovery email",
)
async def update_current_user_email(
    payload: AccountEmailUpdateRequest,
    current_user: UserAccount = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUserResponse:
    """Change the recovery email after confirming the current password."""
    _require_persisted_account(current_user)
    try:
        await auth_service.change_email(
            db,
            current_user,
            payload.email,
            payload.current_password,
        )
    except (CurrentPasswordError, EmailAlreadyUsedError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(current_user)
    return CurrentUserResponse(user=AuthUserResponse.from_user(current_user))


@router.post(
    "/password",
    response_model=PasswordChangeResponse,
    summary="Change the current user's password",
)
async def change_current_user_password(
    payload: PasswordChangeRequest,
    current_user: UserAccount = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PasswordChangeResponse:
    """Replace the password after checking the user's current credential."""
    _require_persisted_account(current_user)
    try:
        auth_service.change_password(
            current_user,
            payload.current_password,
            payload.new_password,
        )
    except CurrentPasswordError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    return PasswordChangeResponse(message="Password updated successfully.")


@router.post("/logout", response_model=LogoutResponse, summary="Acknowledge client-side logout")
async def logout(
    current_user: UserAccount = Depends(get_current_active_user),
) -> LogoutResponse:
    """Acknowledge logout for stateless JWT sessions."""
    _ = current_user
    return LogoutResponse(message="Logged out. Discard the bearer token on the client.")
