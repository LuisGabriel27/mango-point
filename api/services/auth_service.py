"""
MangoPoint API - Authentication Service
=======================================
User lookup, credential verification, token issuance, and default admin seeding.
"""

from datetime import datetime, timedelta, timezone
import secrets
import uuid

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.core.security import (
    AuthConfigurationError,
    create_session_token,
    get_password_hash,
    verify_password,
    session_credential_stamp,
)
from api.models.auth import AuthUserResponse, LoginResponse
from db.models import AuthSession, PasswordResetChallenge, UserAccount, UserRoleEnum
from utils.datetime_utils import utcnow_naive


class AuthenticationError(RuntimeError):
    """Raised when login credentials are invalid or the account is unavailable."""


class CurrentPasswordError(RuntimeError):
    """Raised when an account change is not authorized by the current password."""


class PasswordResetCodeError(RuntimeError):
    """Raised when a password-reset challenge or code cannot be accepted."""


class EmailAlreadyUsedError(RuntimeError):
    """Raised when another account already owns a requested email address."""


class SessionLimitError(RuntimeError):
    """An account already has two active sessions."""


class VerificationCooldownError(RuntimeError):
    """A verification code was requested too recently."""


class AuthService:
    """Authentication-related business logic."""

    @staticmethod
    def session_response(
        user: UserAccount,
        session_started_at: int | None = None,
        activity_age_seconds: float = 0,
        session_id: str | None = None,
    ) -> LoginResponse:
        token, expires_at = create_session_token(user, session_started_at, activity_age_seconds, session_id)
        return LoginResponse(
            access_token=token,
            expires_at=expires_at.isoformat().replace("+00:00", "Z"),
            expires_in_seconds=max(int((expires_at - datetime.now(timezone.utc)).total_seconds()), 0),
            user=AuthUserResponse.from_user(user),
        )

    async def get_user_by_id(self, db: AsyncSession, user_id: int, *, lock: bool = False) -> UserAccount | None:
        """Fetch a user by primary key."""
        query = select(UserAccount).where(UserAccount.user_id == user_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def lock_account(db: AsyncSession, user: UserAccount) -> None:
        await db.execute(select(UserAccount).where(UserAccount.user_id == user.user_id)
            .with_for_update().execution_options(populate_existing=True))

    async def get_user_by_login(self, db: AsyncSession, login_value: str, *, lock: bool = False) -> UserAccount | None:
        """Fetch a user by username or email, case-insensitively."""
        normalized = login_value.strip().lower()
        if not normalized:
            return None

        query = select(UserAccount).where(
                or_(
                    func.lower(UserAccount.username) == normalized,
                    func.lower(UserAccount.email) == normalized,
                )
            )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_email(self, db: AsyncSession, email: str) -> UserAccount | None:
        """Fetch a user by email without accepting usernames."""
        normalized = email.strip().lower()
        if not normalized:
            return None
        result = await db.execute(
            select(UserAccount).where(func.lower(UserAccount.email) == normalized)
        )
        return result.scalar_one_or_none()

    async def authenticate_user(
        self,
        db: AsyncSession,
        username_or_email: str,
        password: str,
    ) -> UserAccount:
        """Validate login credentials and return the matching user."""
        user = await self.get_user_by_login(db, username_or_email, lock=True)
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
        # The account row lock serializes simultaneous logins across API workers.
        user = await self.authenticate_user(db, username_or_email, password)
        now = utcnow_naive()
        stamp = session_credential_stamp(user)
        await db.execute(delete(AuthSession).where(AuthSession.user_id == user.user_id,
            or_(AuthSession.expires_at <= now, AuthSession.revoked_at.is_not(None), AuthSession.credential_stamp != stamp)))
        count = await db.scalar(select(func.count()).select_from(AuthSession).where(
            AuthSession.user_id == user.user_id, AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now, AuthSession.credential_stamp == stamp))
        if count >= 2:
            raise SessionLimitError("This account already has two active sessions. Log out on another browser or wait for an inactive session to expire, then try again.")
        session_id = str(uuid.uuid4())
        response = self.session_response(user, session_id=session_id)
        db.add(AuthSession(session_id=session_id, user_id=user.user_id, credential_stamp=stamp,
            expires_at=datetime.fromisoformat(response.expires_at.replace("Z", "+00:00")).replace(tzinfo=None), created_at=now))
        user.last_login_at = now
        await db.flush()
        return response

    async def renew_session(self, db: AsyncSession, user: UserAccount, claims: dict, activity_age: float) -> LoginResponse:
        # Use the same lock order as login; a revoked session cannot be renewed.
        await db.execute(select(UserAccount).where(UserAccount.user_id == user.user_id).with_for_update().execution_options(populate_existing=True))
        session = await db.get(AuthSession, claims["sid"], populate_existing=True, with_for_update=True)
        now = utcnow_naive()
        if (session is None or session.user_id != user.user_id or session.revoked_at is not None
                or session.expires_at <= now or session.credential_stamp != session_credential_stamp(user)
                or claims["credential_stamp"] != session_credential_stamp(user)):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Session ended. Please sign in again.")
        response = self.session_response(user, claims["session_started_at"], activity_age, session.session_id)
        session.expires_at = datetime.fromisoformat(response.expires_at.replace("Z", "+00:00")).replace(tzinfo=None)
        await db.flush()
        return response

    @staticmethod
    def update_profile(user: UserAccount, full_name: str) -> UserAccount:
        """Apply the current user's editable profile fields."""
        user.full_name = full_name.strip()
        return user

    @staticmethod
    def change_password(
        user: UserAccount,
        current_password: str,
        new_password: str,
    ) -> UserAccount:
        """Verify the existing password before storing a replacement hash."""
        if not user.password_hash or not verify_password(current_password, user.password_hash):
            raise CurrentPasswordError("Current password is incorrect.")
        user.password_hash = get_password_hash(new_password)
        return user

    async def change_email(
        self,
        db: AsyncSession,
        user: UserAccount,
        email: str,
        current_password: str,
    ) -> UserAccount:
        """Change the login and recovery email after rechecking the password."""
        await db.execute(select(UserAccount).where(UserAccount.user_id == user.user_id).with_for_update().execution_options(populate_existing=True))
        if not user.password_hash or not verify_password(current_password, user.password_hash):
            raise CurrentPasswordError("Current password is incorrect.")
        normalized = email.strip().lower()
        existing = await self.get_user_by_email(db, normalized)
        if existing is not None and existing.user_id != user.user_id:
            raise EmailAlreadyUsedError("That email is already used by another account.")
        user.email = normalized
        return user

    async def create_password_reset_challenge(
        self,
        db: AsyncSession,
        user: UserAccount,
        *, purpose: str = "reset",
    ) -> tuple[PasswordResetChallenge, str]:
        """Create a hashed six-digit code and invalidate older unused codes."""
        now = utcnow_naive()
        await self.lock_account(db, user)
        last = await db.scalar(select(PasswordResetChallenge.created_at).where(
            PasswordResetChallenge.user_id == user.user_id).order_by(PasswordResetChallenge.created_at.desc()).limit(1))
        if isinstance(last, datetime) and (now - last).total_seconds() < 60:
            raise VerificationCooldownError("Wait 60 seconds before requesting another verification code.")
        await db.execute(
            update(PasswordResetChallenge)
            .where(
                PasswordResetChallenge.user_id == user.user_id,
                PasswordResetChallenge.purpose == purpose,
                PasswordResetChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge = PasswordResetChallenge(
            challenge_id=str(uuid.uuid4()),
            user_id=user.user_id,
            code_hash=get_password_hash(code),
            attempt_count=0,
            expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_CODE_EXPIRE_MINUTES),
            created_at=now,
            purpose=purpose,
            email_snapshot=user.email,
            credential_stamp=session_credential_stamp(user),
        )
        db.add(challenge)
        await db.flush()
        return challenge, code

    async def reset_password(
        self,
        db: AsyncSession,
        challenge_id: str,
        code: str,
        new_password: str,
    ) -> UserAccount:
        """Validate an emailed code and replace the associated password."""
        result = await db.execute(
            select(PasswordResetChallenge).where(
                PasswordResetChallenge.challenge_id == challenge_id
            )
        )
        challenge = result.scalar_one_or_none()
        if challenge is None:
            raise PasswordResetCodeError("This reset code is invalid or has expired.")
        # All credential operations lock the account before the challenge row.
        user = await self.get_user_by_id(db, challenge.user_id, lock=True)
        result = await db.execute(select(PasswordResetChallenge).where(
            PasswordResetChallenge.challenge_id == challenge_id).with_for_update().execution_options(populate_existing=True))
        challenge = result.scalar_one_or_none()
        now = utcnow_naive()
        if challenge is None or challenge.purpose != "reset" or challenge.consumed_at is not None or challenge.expires_at <= now:
            raise PasswordResetCodeError("This reset code is invalid or has expired.")
        if challenge.attempt_count >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
            challenge.consumed_at = now
            raise PasswordResetCodeError("Too many incorrect attempts. Request a new code.")
        if not verify_password(code, challenge.code_hash):
            challenge.attempt_count += 1
            if challenge.attempt_count >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
                challenge.consumed_at = now
                raise PasswordResetCodeError("Too many incorrect attempts. Request a new code.")
            remaining = settings.PASSWORD_RESET_MAX_ATTEMPTS - challenge.attempt_count
            raise PasswordResetCodeError(f"Incorrect reset code. {remaining} attempts remaining.")

        if user is None or not user.is_active:
            challenge.consumed_at = now
            raise PasswordResetCodeError("This reset code is invalid or has expired.")
        if (challenge.email_snapshot is not None and challenge.email_snapshot != user.email
                or challenge.credential_stamp is not None and challenge.credential_stamp != session_credential_stamp(user)):
            challenge.consumed_at = now
            raise PasswordResetCodeError("Account details changed. Request a new code.")

        if verify_password(new_password, user.password_hash):
            raise PasswordResetCodeError("Choose a password you have not already used.")

        user.password_hash = get_password_hash(new_password)
        challenge.consumed_at = now
        return user

    async def confirm_password_change(self, db: AsyncSession, user: UserAccount, payload) -> None:
        await db.execute(select(UserAccount).where(UserAccount.user_id == user.user_id).with_for_update().execution_options(populate_existing=True))
        if not verify_password(payload.current_password, user.password_hash):
            raise CurrentPasswordError("Current password is incorrect.")
        await self.verify_account_code(db, user, "change", payload.challenge_id, payload.code)
        self.change_password(user, payload.current_password, payload.new_password)

    async def verify_account_code(self, db: AsyncSession, user: UserAccount, purpose: str, challenge_id: str, code: str) -> None:
        await self.lock_account(db, user)
        result = await db.execute(select(PasswordResetChallenge).where(
            PasswordResetChallenge.challenge_id == challenge_id).with_for_update())
        challenge = result.scalar_one_or_none()
        now = utcnow_naive()
        if (challenge is None or challenge.purpose != purpose or challenge.user_id != user.user_id
                or challenge.consumed_at is not None or challenge.expires_at <= now
                or challenge.email_snapshot != user.email
                or challenge.credential_stamp != session_credential_stamp(user)):
            raise PasswordResetCodeError("This verification code is invalid or has expired. Request a new code.")
        if challenge.attempt_count >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
            raise PasswordResetCodeError("Too many incorrect attempts. Request a new code.")
        if not verify_password(code, challenge.code_hash):
            challenge.attempt_count += 1
            if challenge.attempt_count >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
                challenge.consumed_at = now
            raise PasswordResetCodeError("Incorrect verification code. Request a new code after five incorrect attempts.")
        challenge.consumed_at = now

    async def ensure_default_admin(self, db: AsyncSession) -> tuple[str, UserAccount | None]:
        """Create the configured default admin and keep its account identity active."""
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

            if existing_user.username != username:
                existing_user.username = username
                updated = True
            # Account owners can replace the bootstrap email with a real
            # recovery address. Never overwrite that choice during startup.
            if existing_user.role != role:
                existing_user.role = role
                updated = True
            if not existing_user.is_active:
                existing_user.is_active = True
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
