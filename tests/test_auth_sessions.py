"""Isolated API sessions: no production accounts or database writes."""
import time
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.core.config import settings
from api.core.database import get_db
from api.core.security import create_access_token, create_session_token, decode_access_token, get_password_hash
from api.routes.auth import router
from api.services.auth_service import auth_service
from db.models import UserAccount, UserRoleEnum


@pytest.fixture
def sessions(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_SECRET_KEY", "isolated-session-test-secret-at-least-32-bytes")
    monkeypatch.setattr(settings, "AUTH_ACCESS_TOKEN_EXPIRE_MINUTES", 480)
    user = UserAccount(user_id=7, full_name="Session Test", username="session-test",
                       email="session-test@example.com", password_hash=get_password_hash("old-password"),
                       role=UserRoleEnum.OPERATOR, is_active=True)
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    db = AsyncMock()
    db.execute.return_value = result
    async def database():
        yield db
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, user, db


def login(client, password="old-password"):
    response = client.post("/auth/login", json={"username_or_email": "session-test", "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_password_change_revokes_both_devices_and_current_device(sessions):
    client, user, _ = sessions
    first, second = login(client), login(client)
    assert first != second
    assert client.get("/auth/me", headers=headers(second)).status_code == 200
    changed = client.post("/auth/password", headers=headers(first), json={
        "current_password": "old-password", "new_password": "new-password-123"})
    assert changed.status_code == 200
    for token in (first, second):
        assert client.get("/auth/me", headers=headers(token)).status_code == 401
        assert client.post("/auth/session/refresh", headers=headers(token), json={}).status_code == 401
    assert client.post("/auth/login", json={"username_or_email": "session-test", "password": "old-password"}).status_code == 401
    replacement = login(client, "new-password-123")
    assert client.get("/auth/me", headers=headers(replacement)).status_code == 200
    claims = decode_access_token(replacement)
    assert user.password_hash not in str(claims)


def test_failed_password_change_keeps_sessions_valid_and_profile_changes_do_not_revoke(sessions):
    client, _, _ = sessions
    token = login(client)
    assert client.post("/auth/password", headers=headers(token), json={
        "current_password": "incorrect", "new_password": "new-password-123"}).status_code == 400
    assert client.patch("/auth/me", headers=headers(token), json={"full_name": "Updated Name"}).status_code == 200
    assert client.get("/auth/me", headers=headers(token)).status_code == 200


def test_activity_renewal_is_short_lived_preserves_absolute_lifetime_and_does_not_write(sessions):
    client, _, db = sessions
    token = login(client)
    initial = decode_access_token(token)
    assert 899 <= initial["exp"] - initial["iat"] <= 900
    for _ in range(3):
        assert client.get("/auth/me", headers=headers(token)).status_code == 200
    renewed = client.post("/auth/session/refresh", headers=headers(token), json={"activity_age_seconds": 60})
    assert renewed.status_code == 200
    assert renewed.headers["cache-control"] == "no-store"
    claims = decode_access_token(renewed.json()["access_token"])
    assert claims["session_started_at"] == initial["session_started_at"]
    assert 839 <= claims["exp"] - claims["iat"] <= 841
    db.commit.assert_not_awaited()
    for age in (-1, 900, 1000):
        assert client.post("/auth/session/refresh", headers=headers(token), json={"activity_age_seconds": age}).status_code == 422


def test_expired_and_legacy_tokens_cannot_be_used_or_renewed(sessions):
    client, user, _ = sessions
    claims = decode_access_token(login(client))
    claims["iat"] = claims["session_started_at"] = int(time.time()) - 901
    claims["exp"] = int(time.time()) - 1
    expired = jwt.encode(claims, settings.AUTH_SECRET_KEY, algorithm=settings.AUTH_ALGORITHM)
    legacy, _ = create_access_token(str(user.user_id))
    for token in (expired, legacy):
        assert client.get("/auth/me", headers=headers(token)).status_code == 401
        assert client.post("/auth/session/refresh", headers=headers(token), json={}).status_code == 401


def test_renewal_cannot_extend_the_original_absolute_lifetime(sessions):
    _, user, _ = sessions
    started = int(time.time()) - 480 * 60 + 60
    token, _ = create_session_token(user, session_started_at=started)
    assert decode_access_token(token)["exp"] == started + 480 * 60
    with pytest.raises(HTTPException) as exc_info:
        create_session_token(user, session_started_at=started - 120)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_password_reset_also_revokes_existing_sessions(sessions, monkeypatch):
    client, user, _ = sessions
    first, second = login(client), login(client)
    db = AsyncMock()
    db.add = MagicMock()
    challenge, code = await auth_service.create_password_reset_challenge(db, user)
    result = MagicMock()
    result.scalar_one_or_none.return_value = challenge
    db.execute.return_value = result
    monkeypatch.setattr(auth_service, "get_user_by_id", AsyncMock(return_value=user))
    await auth_service.reset_password(db, challenge.challenge_id, code, "new-password-123")
    for token in (first, second):
        assert client.get("/auth/me", headers=headers(token)).status_code == 401
