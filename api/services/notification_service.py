"""
MangoPoint API - Notification Service
=====================================
SMTP or HTTPS delivery for pest alerts plus the existing SMS stub.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Iterable, List, Optional

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"
_BREVO_ACCOUNT_URL = "https://api.brevo.com/v3/account"


def normalize_email_recipients(values: Optional[Iterable[str]]) -> List[str]:
    """Return unique, syntactically valid recipient addresses in input order."""
    recipients: List[str] = []
    seen: set[str] = set()
    for raw_value in values or []:
        email = str(raw_value or "").strip()
        normalized = email.lower()
        if not email or not _EMAIL_PATTERN.fullmatch(email) or normalized in seen:
            continue
        seen.add(normalized)
        recipients.append(email)
    return recipients


def _masked_email(value: str) -> str:
    """Mask a recipient for diagnostics without exposing the full address."""
    local, _, domain = value.partition("@")
    if not domain:
        return "***"
    visible = local[:1] if local else ""
    return f"{visible}***@{domain}"


class NotificationService:
    """Send alert notifications without blocking FastAPI's event loop."""

    def __init__(self, config: Any = settings) -> None:
        self.config = config
        self.email_provider = str(
            getattr(config, "ALERT_EMAIL_PROVIDER", "smtp") or "smtp"
        ).strip().lower()
        self.brevo_api_key = str(getattr(config, "BREVO_API_KEY", None) or "").strip()
        self.brevo_timeout = max(
            1,
            int(getattr(config, "BREVO_API_TIMEOUT_SECONDS", 20)),
        )
        self.smtp_host = str(config.SMTP_HOST or "").strip()
        self.smtp_port = int(config.SMTP_PORT)
        self.smtp_user = str(config.SMTP_USER or "").strip()
        self.smtp_password = str(config.SMTP_PASSWORD or "")
        self.from_email = str(config.SMTP_FROM_EMAIL or self.smtp_user or "").strip()
        self.from_name = str(config.SMTP_FROM_NAME or "MangoPoint Alerts").strip()
        self.smtp_security = str(config.SMTP_SECURITY or "starttls").strip().lower()
        self.smtp_timeout = max(1, int(config.SMTP_TIMEOUT_SECONDS))
        self.email_enabled = bool(config.ALERT_EMAIL_ENABLED)
        self.default_recipients = normalize_email_recipients(
            config.ALERT_EMAIL_RECIPIENTS,
        )
        self.retry_attempts = max(1, int(config.ALERT_EMAIL_RETRY_ATTEMPTS))
        self.retry_delay = max(0.0, float(config.ALERT_EMAIL_RETRY_DELAY_SECONDS))
        self.app_url = str(config.ALERT_EMAIL_APP_URL or "").strip()

        self.twilio_sid = config.TWILIO_ACCOUNT_SID
        self.twilio_token = config.TWILIO_AUTH_TOKEN
        self.twilio_phone = config.TWILIO_PHONE_NUMBER

        self.last_error: Optional[str] = None
        self.last_success_at: Optional[str] = None

    @property
    def email_configured(self) -> bool:
        """Return whether enough settings exist to attempt an alert email."""
        common_settings_complete = bool(
            self.email_enabled
            and self.from_email
            and self.default_recipients
        )
        if self.email_provider == "brevo":
            return bool(common_settings_complete and self.brevo_api_key)

        credentials_complete = bool(self.smtp_user) == bool(self.smtp_password)
        return bool(
            common_settings_complete
            and self.smtp_host
            and self.smtp_port
            and credentials_complete
        )

    def email_status(
        self,
        recipients: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Return non-secret delivery diagnostics for authenticated operators."""
        resolved_recipients = normalize_email_recipients(
            recipients if recipients is not None else self.default_recipients,
        )
        configuration_error = self._configuration_error(resolved_recipients)
        return {
            "enabled": self.email_enabled,
            "configured": configuration_error is None,
            "configuration_error": configuration_error,
            "provider": self.email_provider,
            "transport": "https" if self.email_provider == "brevo" else "smtp",
            "brevo_api_key_configured": bool(self.brevo_api_key),
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_security": self.smtp_security,
            "from_email": _masked_email(self.from_email) if self.from_email else None,
            "recipient_count": len(resolved_recipients),
            "recipients": [_masked_email(item) for item in resolved_recipients],
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
        }

    def _configuration_error(self, recipients: List[str]) -> Optional[str]:
        if not self.email_enabled:
            return "Alert email delivery is disabled."
        if not recipients:
            return "No valid ALERT_EMAIL_RECIPIENTS are configured."
        if not self.from_email or not _EMAIL_PATTERN.fullmatch(self.from_email):
            return "A valid SMTP_FROM_EMAIL (or SMTP_USER) is required."

        if self.email_provider == "brevo":
            if not self.brevo_api_key:
                return "BREVO_API_KEY is required when ALERT_EMAIL_PROVIDER=brevo."
            return None

        if self.email_provider != "smtp":
            return "ALERT_EMAIL_PROVIDER must be smtp or brevo."
        if not self.smtp_host or not self.smtp_port:
            return "SMTP host and port are required."
        if bool(self.smtp_user) != bool(self.smtp_password):
            return "SMTP_USER and SMTP_PASSWORD must either both be set or both be empty."
        if self.smtp_security not in {"starttls", "ssl", "none"}:
            return "SMTP_SECURITY must be starttls, ssl, or none."
        return None

    def _connect(self):
        context = ssl.create_default_context()
        if self.smtp_security == "ssl":
            return smtplib.SMTP_SSL(
                self.smtp_host,
                self.smtp_port,
                timeout=self.smtp_timeout,
                context=context,
            )

        server = smtplib.SMTP(
            self.smtp_host,
            self.smtp_port,
            timeout=self.smtp_timeout,
        )
        if self.smtp_security == "starttls":
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        return server

    def _build_message(
        self,
        subject: str,
        message: str,
        alert_id: str,
    ) -> EmailMessage:
        email = EmailMessage()
        email["Subject"] = subject.replace("\r", " ").replace("\n", " ")
        email["From"] = formataddr((self.from_name, self.from_email))
        # Farmer addresses remain envelope recipients instead of being exposed
        # to every recipient in a To/Cc header.
        email["To"] = "Undisclosed recipients:;"

        dashboard_line = f"\nOpen MangoPoint: {self.app_url}\n" if self.app_url else ""
        text_body = (
            "MangoPoint Pest Risk Alert\n"
            "==========================\n\n"
            f"Alert ID: {alert_id}\n\n"
            f"{message.strip()}\n"
            f"{dashboard_line}\n"
            "This is an automated alert from the MangoPoint pest monitoring system.\n"
        )
        email.set_content(text_body)

        safe_message = html.escape(message.strip()).replace("\n", "<br>")
        safe_alert_id = html.escape(alert_id)
        dashboard_html = (
            f'<p><a href="{html.escape(self.app_url, quote=True)}" '
            'style="display:inline-block;padding:10px 16px;background:#176b45;color:#fff;'
            'text-decoration:none;border-radius:6px;">Open MangoPoint</a></p>'
            if self.app_url
            else ""
        )
        email.add_alternative(
            f"""<!doctype html>
<html><body style="margin:0;background:#f3f7f4;font-family:Arial,sans-serif;color:#1f2937;">
  <div style="max-width:640px;margin:24px auto;padding:0 16px;">
    <div style="background:#fff;border:1px solid #d7e3db;border-top:5px solid #b42318;border-radius:10px;padding:24px;">
      <div style="font-size:22px;font-weight:700;color:#b42318;margin-bottom:8px;">Pest Risk Alert</div>
      <div style="font-size:12px;color:#667085;margin-bottom:18px;">Alert ID: {safe_alert_id}</div>
      <div style="font-size:15px;line-height:1.65;">{safe_message}</div>
      {dashboard_html}
    </div>
    <p style="font-size:12px;color:#667085;line-height:1.5;">
      Automated notification from MangoPoint. Inspect the orchard and confirm conditions before treatment.
    </p>
  </div>
</body></html>""",
            subtype="html",
        )
        return email

    def _send_email_sync(
        self,
        email: EmailMessage,
        recipients: List[str],
    ) -> None:
        with self._connect() as server:
            if self.smtp_user:
                server.login(self.smtp_user, self.smtp_password)
            refused = server.send_message(
                email,
                from_addr=self.from_email,
                to_addrs=recipients,
            )
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)

    @staticmethod
    def _brevo_response_error(response: httpx.Response) -> RuntimeError:
        """Create a useful provider error without reflecting secrets or HTML."""
        message = "request rejected"
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = str(payload.get("message") or payload.get("code") or message)
        except ValueError:
            pass
        return RuntimeError(
            f"Brevo API returned HTTP {response.status_code}: {message[:300]}"
        )

    async def _send_brevo_email(
        self,
        email: EmailMessage,
        recipients: List[str],
    ) -> None:
        """Send the alert over Brevo's HTTPS API instead of an SMTP socket."""
        html_part = email.get_body(preferencelist=("html",))
        plain_part = email.get_body(preferencelist=("plain",))
        html_content = (
            html_part.get_content()
            if html_part is not None
            else f"<pre>{html.escape(plain_part.get_content() if plain_part else '')}</pre>"
        )
        payload: dict[str, Any] = {
            "sender": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "subject": str(email["Subject"]),
            "htmlContent": html_content,
        }

        if len(recipients) == 1:
            payload["to"] = [{"email": recipients[0]}]
        else:
            # A separate message version keeps designated farmer addresses from
            # being disclosed to one another in a shared To/Cc header.
            payload["messageVersions"] = [
                {"to": [{"email": recipient}]}
                for recipient in recipients
            ]

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": self.brevo_api_key,
        }
        async with httpx.AsyncClient(
            timeout=self.brevo_timeout,
            follow_redirects=False,
        ) as client:
            response = await client.post(
                _BREVO_SEND_URL,
                headers=headers,
                json=payload,
            )
        if response.status_code != 201:
            raise self._brevo_response_error(response)

    async def _deliver_email(
        self,
        email: EmailMessage,
        recipients: List[str],
    ) -> None:
        if self.email_provider == "brevo":
            await self._send_brevo_email(email, recipients)
            return
        await asyncio.to_thread(
            self._send_email_sync,
            email,
            recipients,
        )

    async def send_email_alert(
        self,
        subject: str,
        message: str,
        alert_id: str,
        recipients: Optional[List[str]] = None,
    ) -> bool:
        """Send one alert to the designated farmers with bounded retries."""
        resolved_recipients = normalize_email_recipients(
            recipients if recipients is not None else self.default_recipients,
        )
        configuration_error = self._configuration_error(resolved_recipients)
        if configuration_error:
            self.last_error = configuration_error
            logger.warning("Skipping email for alert %s: %s", alert_id, configuration_error)
            return False

        email = self._build_message(subject, message, alert_id)
        for attempt in range(1, self.retry_attempts + 1):
            try:
                await self._deliver_email(email, resolved_recipients)
                self.last_error = None
                self.last_success_at = datetime.now(timezone.utc).isoformat()
                logger.info(
                    "Email alert %s sent via %s to %d designated recipient(s)",
                    alert_id,
                    self.email_provider,
                    len(resolved_recipients),
                )
                return True
            except Exception as exc:
                self.last_error = str(exc)[:500]
                logger.warning(
                    "Email alert %s attempt %d/%d failed: %s",
                    alert_id,
                    attempt,
                    self.retry_attempts,
                    exc,
                )
                if attempt < self.retry_attempts and self.retry_delay:
                    await asyncio.sleep(self.retry_delay * attempt)
        return False

    async def send_sms_alert(
        self,
        message: str,
        alert_id: str,
        recipients: Optional[List[str]] = None,
    ) -> bool:
        """Keep the existing Twilio-ready stub without claiming delivery."""
        if not self.twilio_sid or not self.twilio_token:
            return False
        if not recipients:
            logger.warning("No SMS recipients configured")
            return False
        logger.info(
            "[SMS STUB] Would send to %s: %s... (alert: %s)",
            recipients,
            message[:50],
            alert_id,
        )
        return False

    async def test_email_connection(self) -> bool:
        """Authenticate to the configured provider without sending mail."""
        configuration_error = self._configuration_error(self.default_recipients)
        if configuration_error:
            self.last_error = configuration_error
            return False

        try:
            if self.email_provider == "brevo":
                async with httpx.AsyncClient(
                    timeout=self.brevo_timeout,
                    follow_redirects=False,
                ) as client:
                    response = await client.get(
                        _BREVO_ACCOUNT_URL,
                        headers={
                            "accept": "application/json",
                            "api-key": self.brevo_api_key,
                        },
                    )
                if response.status_code != 200:
                    raise self._brevo_response_error(response)
                self.last_error = None
                return True

            def connect_and_authenticate() -> None:
                with self._connect() as server:
                    if self.smtp_user:
                        server.login(self.smtp_user, self.smtp_password)

            await asyncio.to_thread(connect_and_authenticate)
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = str(exc)[:500]
            logger.error("Email provider connection test failed: %s", exc)
            return False


notification_service = NotificationService()
