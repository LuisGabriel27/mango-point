"""
MangoPoint API - Authentication Routes
======================================
Login and current-session endpoints for the dashboard.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import (
    database_unavailable_http_exception,
    get_db,
    is_database_unavailable,
)
from api.core.config import settings
from api.core.security import AuthConfigurationError, bearer_scheme, decode_session_token, get_current_active_user
from api.models.auth import (
    AuthUserResponse,
    AccountEmailUpdateRequest,
    CurrentUserResponse,
    CurrentUserUpdateRequest,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    PasswordChangeRequest,
    PasswordChangeCodeRequest,
    PasswordChangeResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    SessionRefreshRequest,
)
from api.services.auth_service import (
    AuthenticationError,
    CurrentPasswordError,
    EmailAlreadyUsedError,
    PasswordResetCodeError,
    SessionLimitError,
    VerificationCooldownError,
    auth_service,
)
from api.services.notification_service import notification_service
from db.models import AuthSession, UserAccount
from api.core.security import verify_password
from utils.datetime_utils import utcnow_naive


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
        result = await auth_service.login(db, payload.username_or_email, payload.password)
        await db.commit()
        return result
    except SessionLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    summary="Request a password-reset code",
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
    except VerificationCooldownError:
        return PasswordResetResponse(message=PASSWORD_RESET_REQUEST_MESSAGE, challenge_id=str(uuid.uuid4()))
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


@router.post("/session/refresh", response_model=LoginResponse, summary="Renew a session after user interaction")
async def refresh_current_session(
    payload: SessionRefreshRequest,
    response: Response,
    current_user: UserAccount = Depends(get_current_active_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Mint a short-lived token; ordinary background reads never extend it."""
    claims = decode_session_token(credentials.credentials)
    response.headers["Cache-Control"] = "no-store"
    result = await auth_service.renew_session(db, current_user, claims, payload.activity_age_seconds)
    await db.commit()
    return result


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
    """Change the recovery email after checking the password and existing inbox."""
    _require_persisted_account(current_user)
    try:
        # Prove access to the existing inbox before changing where future codes go.
        if not verify_password(payload.current_password, current_user.password_hash):
            raise CurrentPasswordError("Current password is incorrect.")
        await auth_service.verify_account_code(db, current_user, "email", payload.challenge_id, payload.code)
        await auth_service.change_email(
            db,
            current_user,
            payload.email,
            payload.current_password,
        )
        await db.commit()
    except (CurrentPasswordError, EmailAlreadyUsedError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PasswordResetCodeError as exc:
        await db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="That email is already used by another account.") from exc
    await db.refresh(current_user)
    return CurrentUserResponse(user=AuthUserResponse.from_user(current_user))


@router.post("/password/code", response_model=PasswordResetResponse, summary="Email a password-change verification code")
async def request_password_change_code(
    payload: PasswordChangeCodeRequest,
    current_user: UserAccount = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PasswordResetResponse:
    return await _request_account_code(payload, current_user, db, "change")


@router.post("/me/email/code", response_model=PasswordResetResponse, summary="Verify the existing recovery email before replacing it")
async def request_email_change_code(
    payload: PasswordChangeCodeRequest,
    current_user: UserAccount = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PasswordResetResponse:
    return await _request_account_code(payload, current_user, db, "email")


async def _request_account_code(payload, current_user, db, purpose: str) -> PasswordResetResponse:
    _require_persisted_account(current_user)
    await auth_service.lock_account(db, current_user)
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    try:
        challenge, code = await auth_service.create_password_reset_challenge(db, current_user, purpose=purpose)
        delivered = await notification_service.send_password_reset_code(
            current_user.email, code, settings.PASSWORD_RESET_CODE_EXPIRE_MINUTES, purpose=purpose)
        if not delivered:
            await db.rollback()
            raise HTTPException(status_code=503, detail="Could not send the verification email. Your password has not changed. Try again shortly.")
        await db.commit()
        return PasswordResetResponse(challenge_id=challenge.challenge_id,
            message="A six-digit verification code was sent to your current account email. It expires in 10 minutes.")
    except VerificationCooldownError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "60"}) from exc


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
    """Replace the password after verifying the current password and emailed code."""
    _require_persisted_account(current_user)
    try:
        await auth_service.confirm_password_change(db, current_user, payload)
    except CurrentPasswordError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PasswordResetCodeError as exc:
        # Persist failed-attempt counters, never a changed password on failure.
        await db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return PasswordChangeResponse(message="Password updated. All devices must sign in again.")


@router.post("/logout", response_model=LogoutResponse, summary="Revoke the current session")
async def logout(
    current_user: UserAccount = Depends(get_current_active_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> LogoutResponse:
    """Revoke this session and free its account slot immediately."""
    claims = decode_session_token(credentials.credentials)
    session = await db.get(AuthSession, claims["sid"], with_for_update=True, populate_existing=True)
    if session is not None and session.user_id == current_user.user_id:
        session.revoked_at = utcnow_naive()
    await db.commit()
    return LogoutResponse(message="Logged out.")
