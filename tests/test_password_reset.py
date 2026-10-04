from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.core.config import settings
from api.core.security import get_password_hash, verify_password
from api.models.auth import AccountEmailUpdateRequest, PasswordResetRequest
from api.routes import auth as auth_routes
from api.services.auth_service import (
    CurrentPasswordError,
    PasswordResetCodeError,
    auth_service,
)
from api.services.notification_service import notification_service
from db.models import UserAccount, UserRoleEnum


def _user() -> UserAccount:
    return UserAccount(
        user_id=7,
        full_name="Orchard Manager",
        username="manager",
        email="manager@example.com",
        password_hash=get_password_hash("old-password"),
        role=UserRoleEnum.ADMIN,
        is_active=True,
    )


def _result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def test_password_reset_and_account_emails_are_normalized():
    assert PasswordResetRequest(email="  MANAGER@example.com ").email == "manager@example.com"
    payload = AccountEmailUpdateRequest(
        email="  NEW@example.com ",
        current_password="old-password",
    )
    assert payload.email == "new@example.com"


@pytest.mark.asyncio
async def test_reset_code_changes_password_and_cannot_be_reused(monkeypatch):
    user = _user()
    db = AsyncMock()
    db.add = MagicMock()
    challenge, code = await auth_service.create_password_reset_challenge(db, user)
    db.execute.return_value = _result(challenge)
    monkeypatch.setattr(auth_service, "get_user_by_id", AsyncMock(return_value=user))

    resolved = await auth_service.reset_password(
        db,
        challenge.challenge_id,
        code,
        "new-password-123",
    )

    assert resolved is user
    assert verify_password("new-password-123", user.password_hash)
    assert challenge.consumed_at is not None
    with pytest.raises(PasswordResetCodeError, match="invalid or has expired"):
        await auth_service.reset_password(
            db,
            challenge.challenge_id,
            code,
            "another-password-123",
        )


@pytest.mark.asyncio
async def test_incorrect_reset_codes_are_counted(monkeypatch):
    user = _user()
    db = AsyncMock()
    db.add = MagicMock()
    challenge, _ = await auth_service.create_password_reset_challenge(db, user)
    db.execute.return_value = _result(challenge)
    monkeypatch.setattr(auth_service, "get_user_by_id", AsyncMock(return_value=user))

    with pytest.raises(PasswordResetCodeError, match="attempts remaining"):
        await auth_service.reset_password(
            db,
            challenge.challenge_id,
            "999999",
            "new-password-123",
        )

    assert challenge.attempt_count == 1


@pytest.mark.asyncio
async def test_forgot_password_response_does_not_disclose_account_existence(monkeypatch):
    send_code = AsyncMock(return_value=True)
    monkeypatch.setattr(notification_service, "send_password_reset_code", send_code)
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(auth_service, "get_user_by_email", lookup)
    db = AsyncMock()

    missing_response = await auth_routes.request_password_reset(
        PasswordResetRequest(email="missing@example.com"),
        db,
    )
    send_code.assert_not_awaited()

    lookup.return_value = _user()
    challenge = SimpleNamespace(challenge_id="0d1c6dc0-dedd-4e39-bace-2a7d2b178f7c")
    monkeypatch.setattr(
        auth_service,
        "create_password_reset_challenge",
        AsyncMock(return_value=(challenge, "123456")),
    )
    existing_response = await auth_routes.request_password_reset(
        PasswordResetRequest(email="manager@example.com"),
        db,
    )

    assert missing_response.message == existing_response.message
    assert existing_response.challenge_id == challenge.challenge_id
    send_code.assert_awaited_once_with(
        "manager@example.com",
        "123456",
        settings.PASSWORD_RESET_CODE_EXPIRE_MINUTES,
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_recovery_email_change_requires_current_password(monkeypatch):
    user = _user()
    db = AsyncMock()
    monkeypatch.setattr(auth_service, "get_user_by_email", AsyncMock(return_value=None))

    with pytest.raises(CurrentPasswordError):
        await auth_service.change_email(db, user, "new@example.com", "wrong-password")

    await auth_service.change_email(db, user, "new@example.com", "old-password")
    assert user.email == "new@example.com"
