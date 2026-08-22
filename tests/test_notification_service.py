from types import SimpleNamespace

import pytest

from api.core.config import Settings
from api.services.notification_service import (
    NotificationService,
    normalize_email_recipients,
)


def test_settings_accept_comma_separated_designated_recipients(monkeypatch):
    monkeypatch.setenv(
        "ALERT_EMAIL_RECIPIENTS",
        "farmer.one@example.test, farmer.two@example.test",
    )
    configured = Settings(_env_file=None)
    assert configured.ALERT_EMAIL_RECIPIENTS == [
        "farmer.one@example.test",
        "farmer.two@example.test",
    ]


def _config(**overrides):
    values = {
        "ALERT_EMAIL_PROVIDER": "smtp",
        "BREVO_API_KEY": None,
        "BREVO_API_TIMEOUT_SECONDS": 20,
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": 587,
        "SMTP_USER": "sender@example.test",
        "SMTP_PASSWORD": "secret",
        "SMTP_FROM_EMAIL": "sender@example.test",
        "SMTP_FROM_NAME": "MangoPoint Alerts",
        "SMTP_SECURITY": "starttls",
        "SMTP_TIMEOUT_SECONDS": 5,
        "ALERT_EMAIL_ENABLED": True,
        "ALERT_EMAIL_RECIPIENTS": ["farmer@example.test"],
        "ALERT_EMAIL_RETRY_ATTEMPTS": 1,
        "ALERT_EMAIL_RETRY_DELAY_SECONDS": 0,
        "ALERT_EMAIL_APP_URL": "https://mangopoint.example.test",
        "TWILIO_ACCOUNT_SID": None,
        "TWILIO_AUTH_TOKEN": None,
        "TWILIO_PHONE_NUMBER": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_recipient_normalization_filters_invalid_and_duplicate_addresses():
    assert normalize_email_recipients([
        " Farmer@example.test ",
        "farmer@example.test",
        "not-an-email",
        "second@example.test",
    ]) == ["Farmer@example.test", "second@example.test"]


@pytest.mark.asyncio
async def test_smtp_delivery_uses_bcc_envelope_and_starttls(monkeypatch):
    events = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            events.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            events.append(("close",))

        def ehlo(self):
            events.append(("ehlo",))

        def starttls(self, context):
            assert context is not None
            events.append(("starttls",))

        def login(self, username, password):
            events.append(("login", username, password))

        def send_message(self, message, from_addr, to_addrs):
            events.append(("send", message, from_addr, to_addrs))
            return {}

    monkeypatch.setattr("api.services.notification_service.smtplib.SMTP", FakeSMTP)

    service = NotificationService(_config())
    sent = await service.send_email_alert(
        subject="[MangoPoint] HIGH Risk Alert",
        message="Inspect the flagged trees.",
        alert_id="alert-test-1",
    )

    assert sent is True
    assert service.last_error is None
    assert any(event[0] == "starttls" for event in events)
    send_event = next(event for event in events if event[0] == "send")
    message = send_event[1]
    assert message["To"] == "Undisclosed recipients:;"
    assert send_event[2] == "sender@example.test"
    assert send_event[3] == ["farmer@example.test"]
    assert "Inspect the flagged trees" in message.get_body(preferencelist=("plain",)).get_content()


@pytest.mark.asyncio
async def test_disabled_email_channel_does_not_connect(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("SMTP should not be contacted while email is disabled")

    monkeypatch.setattr("api.services.notification_service.smtplib.SMTP", fail_if_called)
    service = NotificationService(_config(ALERT_EMAIL_ENABLED=False))

    assert await service.send_email_alert(
        subject="Test",
        message="Test",
        alert_id="alert-disabled",
    ) is False
    assert service.last_error == "Alert email delivery is disabled."


@pytest.mark.asyncio
async def test_brevo_delivery_uses_https_and_private_message_versions(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 201

        def json(self):
            return {"messageId": "<test-message@example.test>"}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            captured["client_options"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers, json):
            captured.update(url=url, headers=headers, payload=json)
            return FakeResponse()

    monkeypatch.setattr(
        "api.services.notification_service.httpx.AsyncClient",
        FakeAsyncClient,
    )
    service = NotificationService(_config(
        ALERT_EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="xkeysib-test-key",
        SMTP_USER=None,
        SMTP_PASSWORD=None,
        ALERT_EMAIL_RECIPIENTS=[
            "farmer.one@example.test",
            "farmer.two@example.test",
        ],
    ))

    sent = await service.send_email_alert(
        subject="[MangoPoint] HTTPS Test",
        message="Inspect the flagged orchard zone.",
        alert_id="alert-brevo-1",
    )

    assert sent is True
    assert service.email_status()["provider"] == "brevo"
    assert service.email_status()["transport"] == "https"
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["headers"]["api-key"] == "xkeysib-test-key"
    assert "to" not in captured["payload"]
    assert captured["payload"]["messageVersions"] == [
        {"to": [{"email": "farmer.one@example.test"}]},
        {"to": [{"email": "farmer.two@example.test"}]},
    ]
    assert "Inspect the flagged orchard zone" in captured["payload"]["htmlContent"]


@pytest.mark.asyncio
async def test_brevo_provider_requires_api_key_without_contacting_network(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("HTTPS provider should not be contacted without an API key")

    monkeypatch.setattr(
        "api.services.notification_service.httpx.AsyncClient",
        fail_if_called,
    )
    service = NotificationService(_config(
        ALERT_EMAIL_PROVIDER="brevo",
        BREVO_API_KEY=None,
    ))

    assert service.email_configured is False
    assert await service.send_email_alert(
        subject="Test",
        message="Test",
        alert_id="alert-no-brevo-key",
    ) is False
    assert service.last_error == (
        "BREVO_API_KEY is required when ALERT_EMAIL_PROVIDER=brevo."
    )
