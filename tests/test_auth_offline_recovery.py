from unittest.mock import AsyncMock, MagicMock
import time

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.core import security
from api.core.config import settings
from db.models import UserAccount, UserRoleEnum


def _credentials() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-token")


def _offline_payload() -> dict:
    issued = int(time.time())
    return {
        "sub": "0",
        "offline_auth": True,
        "username": "admin",
        "email": "admin@mangopoint.local",
        "full_name": "MangoPoint Administrator",
        "role": "admin",
        "is_active": True,
        "iat": issued, "exp": issued + 900, "session_started_at": issued,
        "credential_stamp": security.session_credential_stamp(),
    }


def _result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.fixture(autouse=True)
def session_settings(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_SECRET_KEY", "isolated-auth-test-secret")
    monkeypatch.setattr(settings, "DEFAULT_ADMIN_ENABLED", True)
    monkeypatch.setattr(settings, "DEFAULT_ADMIN_PASSWORD", "test-default-password")


@pytest.mark.asyncio
async def test_offline_token_recovers_persisted_user_when_database_returns(monkeypatch):
    persisted_user = UserAccount(
        user_id=1,
        full_name="MangoPoint Administrator",
        username="admin",
        email="admin@mangopoint.local",
        password_hash=security.get_password_hash(settings.DEFAULT_ADMIN_PASSWORD),
        role=UserRoleEnum.ADMIN,
        is_active=True,
    )
    db = AsyncMock()
    db.execute.side_effect = [_result(None), _result(persisted_user)]
    payload = _offline_payload()
    monkeypatch.setattr(security, "decode_access_token", lambda _token: payload)

    resolved = await security.get_current_user(_credentials(), db)

    assert resolved is persisted_user
    assert resolved.user_id == 1
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_offline_token_requires_login_when_persisted_account_is_missing(monkeypatch):
    db = AsyncMock()
    db.execute.side_effect = [_result(None), _result(None)]
    monkeypatch.setattr(security, "decode_access_token", lambda _token: _offline_payload())

    with pytest.raises(HTTPException) as exc_info:
        await security.get_current_user(_credentials(), db)

    assert exc_info.value.status_code == 401
    assert "sign in again" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_offline_session_cannot_bypass_a_changed_persisted_password(monkeypatch):
    persisted = UserAccount(user_id=1, username="admin", password_hash=security.get_password_hash("changed-password"))
    db = AsyncMock()
    db.execute.side_effect = [_result(None), _result(persisted)]
    payload = _offline_payload()
    monkeypatch.setattr(security, "decode_access_token", lambda _token: payload)
    with pytest.raises(HTTPException) as exc_info:
        await security.get_current_user(_credentials(), db)
    assert exc_info.value.status_code == 401
