from types import SimpleNamespace

import pytest

from api.models.schemas import AlertEmailRecipientCreate, AlertSeverityEnum
from api.services.alert_recipient_service import AlertRecipientService
from api.services.alert_service import AlertService
from db.models import AlertEmailRecipient


class StubRecipientService(AlertRecipientService):
    def __init__(self, rows, defaults=None):
        super().__init__(SimpleNamespace(default_recipients=defaults or []))
        self.rows = rows

    async def _all_rows(self, _db):
        return self.rows


class FakeSession:
    def __init__(self):
        self.added = []
        self.flushed = False

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flushed = True


@pytest.mark.asyncio
async def test_environment_recipients_are_fallback_until_managed_rows_exist():
    service = StubRecipientService([], defaults=["fallback@example.test"])
    assert await service.effective_emails(object()) == ["fallback@example.test"]

    service.rows = [AlertEmailRecipient(
        email="removed@example.test",
        is_active=False,
    )]
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
