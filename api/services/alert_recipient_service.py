"""Persistence and fallback rules for designated alert email recipients."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AlertEmailRecipient
from utils.datetime_utils import utcnow_naive

from .notification_service import NotificationService, notification_service

logger = logging.getLogger(__name__)


class AlertRecipientService:
    """Manage admin-assigned recipients without writing secrets to source files."""

    def __init__(self, notifier: NotificationService = notification_service) -> None:
        self.notifier = notifier

    async def _all_rows(self, db: AsyncSession) -> list[AlertEmailRecipient]:
        result = await db.execute(
            select(AlertEmailRecipient).order_by(
                AlertEmailRecipient.created_at.asc(),
                AlertEmailRecipient.recipient_id.asc(),
            )
        )
        return list(result.scalars().all())

    async def list_active(
        self,
        db: AsyncSession,
        *,
        bootstrap_environment: bool = False,
    ) -> list[AlertEmailRecipient]:
        """List active rows, optionally importing initial `.env` recipients once."""
        rows = await self._all_rows(db)
        if not rows and bootstrap_environment:
            for email in self.notifier.default_recipients:
                row = AlertEmailRecipient(
                    email=email.strip().lower(),
                    name=None,
                    is_active=True,
                )
                db.add(row)
                rows.append(row)
            if rows:
                await db.flush()

        return [row for row in rows if row.is_active]

    async def effective_emails(self, db: Optional[AsyncSession]) -> list[str]:
        """Use managed rows once any exist; otherwise retain the `.env` fallback."""
        if db is None:
            return list(self.notifier.default_recipients)
        try:
            rows = await self._all_rows(db)
        except Exception as exc:
            logger.warning(
                "Could not load managed alert recipients; using environment fallback: %s",
                exc,
            )
            return list(self.notifier.default_recipients)

        if not rows:
            return list(self.notifier.default_recipients)
        return [row.email for row in rows if row.is_active]

    async def add_or_reactivate(
        self,
        db: AsyncSession,
        *,
        email: str,
        name: Optional[str],
        created_by_user_id: Optional[int],
    ) -> AlertEmailRecipient:
        """Add a new recipient or reactivate an address removed earlier."""
        normalized_email = email.strip().lower()
        normalized_name = (name or "").strip() or None
        result = await db.execute(
            select(AlertEmailRecipient).where(
                AlertEmailRecipient.email == normalized_email,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.is_active = True
            if normalized_name is not None:
                existing.name = normalized_name
            existing.created_by_user_id = created_by_user_id
            existing.updated_at = utcnow_naive()
            await db.flush()
            return existing

        recipient = AlertEmailRecipient(
            email=normalized_email,
            name=normalized_name,
            is_active=True,
            created_by_user_id=created_by_user_id,
        )
        db.add(recipient)
        await db.flush()
        return recipient

    async def deactivate(
        self,
        db: AsyncSession,
        recipient_id: int,
    ) -> Optional[AlertEmailRecipient]:
        """Soft-delete a recipient so an empty managed list remains authoritative."""
        result = await db.execute(
            select(AlertEmailRecipient).where(
                AlertEmailRecipient.recipient_id == recipient_id,
            )
        )
        recipient = result.scalar_one_or_none()
        if recipient is None:
            return None
        recipient.is_active = False
        recipient.updated_at = utcnow_naive()
        await db.flush()
        return recipient


alert_recipient_service = AlertRecipientService()
