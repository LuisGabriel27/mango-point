from types import SimpleNamespace

import pytest

from api.models.schemas import (
    AlertEmailRecipientCreate,
    AlertEmailRecipientUpdate,
    AlertSeverityEnum,
)
from api.services.alert_recipient_service import (
    AlertRecipientEmailConflictError,
    AlertRecipientService,
)
from api.services.alert_service import AlertService
from db.models import AlertEmailRecipient


class StubRecipientService(AlertRecipientService):
    def __init__(self, rows, defaults=None, managed=False):
        super().__init__(SimpleNamespace(default_recipients=defaults or []))
        self.rows = rows
        self.managed = managed

    async def _all_rows(self, _db):
        return self.rows

    async def _is_managed(self, _db):
        return self.managed

    async def _mark_managed(self, _db):
        self.managed = True


class FakeSession:
    def __init__(self):
        self.added = []
        self.flushed = False

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flushed = True


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class UpdateSession(FakeSession):
    def __init__(self, *results):
        super().__init__()
        self.results = list(results)
        self.deleted = []

    async def execute(self, _query):
        return FakeResult(self.results.pop(0))

    async def delete(self, value):
        self.deleted.append(value)


@pytest.mark.asyncio
async def test_environment_recipients_are_fallback_until_managed_rows_exist():
    service = StubRecipientService([], defaults=["fallback@example.test"])
    assert await service.effective_emails(object()) == ["fallback@example.test"]

    service.rows = [AlertEmailRecipient(
        email="removed@example.test",
        is_active=False,
    )]
    assert await service.effective_emails(object()) == []

    service.rows = []
    service.managed = True
    assert await service.effective_emails(object()) == []


@pytest.mark.asyncio
async def test_opening_admin_list_imports_environment_recipients_once():
    session = FakeSession()
    service = StubRecipientService([], defaults=["Farmer@Example.test"])

    recipients = await service.list_active(
        session,
        bootstrap_environment=True,
    )

    assert session.flushed is True
    assert len(session.added) == 1
    assert recipients[0].email == "farmer@example.test"
    assert recipients[0].is_active is True


def test_recipient_request_normalizes_email_and_optional_name():
    request = AlertEmailRecipientCreate(
        email=" Farmer.One@Example.test ",
        name="  Farmer One  ",
    )
    assert request.email == "farmer.one@example.test"
    assert request.name == "Farmer One"

    with pytest.raises(ValueError):
        AlertEmailRecipientCreate(email="not-an-email")

    update = AlertEmailRecipientUpdate(
        email=" Updated@Example.test ",
        name="  Updated Farmer  ",
    )
    assert update.email == "updated@example.test"
    assert update.name == "Updated Farmer"

    with pytest.raises(ValueError):
        AlertEmailRecipientUpdate()


@pytest.mark.asyncio
async def test_recipient_can_be_paused_and_resumed_without_removal():
    recipient = AlertEmailRecipient(
        recipient_id=7,
        email="farmer@example.test",
        name="Farmer",
        is_active=True,
    )
    service = AlertRecipientService(SimpleNamespace(default_recipients=[]))

    paused = await service.update(
        UpdateSession(recipient),
        7,
        is_active=False,
    )
    assert paused is recipient
    assert recipient.is_active is False

    resumed = await service.update(
        UpdateSession(recipient),
        7,
        is_active=True,
    )
    assert resumed is recipient
    assert recipient.is_active is True


@pytest.mark.asyncio
async def test_recipient_details_can_be_edited_and_duplicate_email_is_rejected():
    recipient = AlertEmailRecipient(
        recipient_id=8,
        email="old@example.test",
        name=None,
        is_active=True,
    )
    service = AlertRecipientService(SimpleNamespace(default_recipients=[]))

    updated = await service.update(
        UpdateSession(recipient, None),
        8,
        email="new@example.test",
        name="Farmer Name",
        update_name=True,
    )
    assert updated.email == "new@example.test"
    assert updated.name == "Farmer Name"

    duplicate = AlertEmailRecipient(
        recipient_id=9,
        email="used@example.test",
        is_active=True,
    )
    with pytest.raises(AlertRecipientEmailConflictError):
        await service.update(
            UpdateSession(recipient, duplicate),
            8,
            email="used@example.test",
        )


@pytest.mark.asyncio
async def test_hard_delete_removes_row_and_keeps_empty_list_authoritative():
    recipient = AlertEmailRecipient(
        recipient_id=10,
        email="delete@example.test",
        name="Delete Me",
        is_active=False,
    )
    state = SimpleNamespace(is_managed=False, updated_at=None)
    session = UpdateSession(recipient, state)
    service = AlertRecipientService(SimpleNamespace(default_recipients=[]))

    deleted = await service.hard_delete(session, 10)

    assert deleted is recipient
    assert session.deleted == [recipient]
    assert state.is_managed is True


@pytest.mark.asyncio
async def test_alert_delivery_uses_managed_recipient_list(monkeypatch):
    service = AlertService()
    db_marker = object()
    captured = {}

    async def effective_emails(db):
        assert db is db_marker
        return ["managed@example.test"]

    async def send_email_alert(**kwargs):
        captured.update(kwargs)
        return True

    async def send_sms_alert(**_kwargs):
        return False

    monkeypatch.setattr(
        "api.services.alert_service.alert_recipient_service.effective_emails",
        effective_emails,
    )
    monkeypatch.setattr(
        "api.services.alert_service.notification_service.send_email_alert",
        send_email_alert,
    )
    monkeypatch.setattr(
        "api.services.alert_service.notification_service.send_sms_alert",
        send_sms_alert,
    )

    alert = SimpleNamespace(
        alert_id="alert-managed-recipient",
        severity=AlertSeverityEnum.HIGH,
        zone_name="Risk zone",
        message="Inspect the orchard.",
        recommended_actions=[],
        email_sent=False,
        email_sent_at=None,
        sms_sent=False,
        sms_sent_at=None,
    )
    email_sent, sms_sent = await service._send_notifications(alert, db=db_marker)

    assert email_sent is True
    assert sms_sent is False
    assert captured["recipients"] == ["managed@example.test"]
    assert alert.email_sent is True
