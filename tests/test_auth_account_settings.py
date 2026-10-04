from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from api.core.security import get_password_hash, verify_password
from api.models.auth import CurrentUserUpdateRequest, PasswordChangeRequest
from api.services.auth_service import CurrentPasswordError, auth_service
from db.models import UserAccount, UserRoleEnum


def _user(password: str = "old-password") -> UserAccount:
    return UserAccount(
        user_id=1,
        full_name="Original Name",
        username="admin",
        email="admin@mangopoint.local",
        password_hash=get_password_hash(password),
        role=UserRoleEnum.ADMIN,
        is_active=True,
    )


def test_profile_name_is_trimmed_and_empty_names_are_rejected():
    assert CurrentUserUpdateRequest(full_name="  Updated Manager  ").full_name == "Updated Manager"
    with pytest.raises(ValidationError):
        CurrentUserUpdateRequest(full_name="   ")


def test_password_change_checks_current_password_and_hashes_replacement():
    user = _user()

    auth_service.change_password(user, "old-password", "new-password-123")

    assert verify_password("new-password-123", user.password_hash)
    assert not verify_password("old-password", user.password_hash)


def test_password_change_rejects_wrong_or_reused_passwords():
    user = _user()
    with pytest.raises(CurrentPasswordError, match="incorrect"):
        auth_service.change_password(user, "wrong-password", "new-password-123")
    with pytest.raises(ValidationError):
        PasswordChangeRequest(
            current_password="same-password",
            new_password="same-password",
        )


@pytest.mark.asyncio
async def test_default_admin_startup_preserves_user_changed_name_and_password(monkeypatch):
    user = _user("custom-password")
    user.full_name = "Custom Manager Name"
    monkeypatch.setattr(auth_service, "get_user_by_login", AsyncMock(return_value=user))
    db = AsyncMock()

    status, resolved = await auth_service.ensure_default_admin(db)

    assert status == "unchanged"
    assert resolved is user
    assert user.full_name == "Custom Manager Name"
    assert verify_password("custom-password", user.password_hash)
    db.flush.assert_not_awaited()
