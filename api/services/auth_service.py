"""
MangoPoint API - Authentication Service
=======================================
User lookup, credential verification, token issuance, and default admin seeding.
"""

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.core.security import (
    AuthConfigurationError,
    create_access_token,
    get_password_hash,
    verify_password,
)
from api.models.auth import AuthUserResponse, LoginResponse
from db.models import UserAccount, UserRoleEnum


class AuthenticationError(RuntimeError):
    """Raised when login credentials are invalid or the account is unavailable."""


class AuthService:
    """Authentication-related business logic."""

    async def get_user_by_id(self, db: AsyncSession, user_id: int) -> UserAccount | None:
        """Fetch a user by primary key."""
        result = await db.execute(select(UserAccount).where(UserAccount.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_user_by_login(self, db: AsyncSession, login_value: str) -> UserAccount | None:
        """Fetch a user by username or email, case-insensitively."""
        normalized = login_value.strip().lower()
        if not normalized:
            return None

        result = await db.execute(
            select(UserAccount).where(
                or_(
                    func.lower(UserAccount.username) == normalized,
                    func.lower(UserAccount.email) == normalized,
                )
            )
        )
        return result.scalar_one_or_none()

    async def authenticate_user(
        self,
        db: AsyncSession,
        username_or_email: str,
        password: str,
    ) -> UserAccount:
        """Validate login credentials and return the matching user."""
        user = await self.get_user_by_login(db, username_or_email)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid username/email or password.")
        if not user.is_active:
            raise AuthenticationError("User account is inactive.")
        return user

    async def login(
        self,
        db: AsyncSession,
        username_or_email: str,
        password: str,
    ) -> LoginResponse:
        """Authenticate a user and issue a bearer token."""
        user = await self.authenticate_user(db, username_or_email, password)
        token, expires_at = create_access_token(
            subject=str(user.user_id),
            extra_claims={"role": user.role.value},
        )

        user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)

        expires_at_utc = expires_at.astimezone(timezone.utc)
        return LoginResponse(
            access_token=token,
            expires_at=expires_at_utc.isoformat().replace("+00:00", "Z"),
            expires_in_seconds=max(int((expires_at_utc - datetime.now(timezone.utc)).total_seconds()), 0),
            user=AuthUserResponse.from_user(user),
        )

    async def ensure_default_admin(self, db: AsyncSession) -> tuple[str, UserAccount | None]:
        """Create or sync the configured default admin account."""
        if not settings.DEFAULT_ADMIN_ENABLED:
            return "disabled", None

        username = settings.DEFAULT_ADMIN_USERNAME.strip()
        email = settings.DEFAULT_ADMIN_EMAIL.strip().lower()
        password = settings.DEFAULT_ADMIN_PASSWORD
        full_name = settings.DEFAULT_ADMIN_FULL_NAME.strip() or "MangoPoint Administrator"
        role_value = settings.DEFAULT_ADMIN_ROLE.strip().lower() or UserRoleEnum.ADMIN.value

        if not username or not email or not password:
            raise AuthConfigurationError(
                "Default admin seeding requires DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_EMAIL, and DEFAULT_ADMIN_PASSWORD."
            )

        try:
            role = UserRoleEnum(role_value)
        except ValueError as exc:
            raise AuthConfigurationError(
                f"Unsupported DEFAULT_ADMIN_ROLE '{settings.DEFAULT_ADMIN_ROLE}'."
            ) from exc

        existing_user = await self.get_user_by_login(db, username)
        if existing_user is None and email:
            existing_user = await self.get_user_by_login(db, email)
        if existing_user is not None:
            updated = False

            if existing_user.full_name != full_name:
                existing_user.full_name = full_name
                updated = True
            if existing_user.username != username:
                existing_user.username = username
                updated = True
            if existing_user.email.lower() != email:
                existing_user.email = email
                updated = True
            if existing_user.role != role:
                existing_user.role = role
                updated = True
            if not existing_user.is_active:
                existing_user.is_active = True
                updated = True
            if not verify_password(password, existing_user.password_hash):
                existing_user.password_hash = get_password_hash(password)
                updated = True

            if updated:
                await db.flush()
                return "updated", existing_user
            return "unchanged", existing_user

        user = UserAccount(
            full_name=full_name,
            username=username,
            email=email,
            password_hash=get_password_hash(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        return "created", user


auth_service = AuthService()
