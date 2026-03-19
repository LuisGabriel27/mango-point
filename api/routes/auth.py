"""
MangoPoint API - Authentication Routes
======================================
Login and current-session endpoints for the dashboard.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.core.security import AuthConfigurationError, get_current_active_user
from api.models.auth import CurrentUserResponse, LoginRequest, LoginResponse, LogoutResponse
from api.services.auth_service import AuthenticationError, auth_service
from db.models import UserAccount


router = APIRouter(prefix="/auth", tags=["Authentication"])


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


@router.get("/me", response_model=CurrentUserResponse, summary="Get the current authenticated user")
async def get_current_user_profile(
    current_user: UserAccount = Depends(get_current_active_user),
) -> CurrentUserResponse:
    """Validate the current bearer token and return the user profile."""
    from api.models.auth import AuthUserResponse

    return CurrentUserResponse(user=AuthUserResponse.from_user(current_user))


@router.post("/logout", response_model=LogoutResponse, summary="Acknowledge client-side logout")
async def logout(
    current_user: UserAccount = Depends(get_current_active_user),
) -> LogoutResponse:
    """Acknowledge logout for stateless JWT sessions."""
    _ = current_user
    return LogoutResponse(message="Logged out. Discard the bearer token on the client.")
