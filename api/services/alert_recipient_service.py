"""Persistence and fallback rules for designated alert email recipients."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AlertEmailRecipient, AlertEmailRecipientState
from utils.datetime_utils import utcnow_naive

from .notification_service import NotificationService, notification_service

logger = logging.getLogger(__name__)


class AlertRecipientEmailConflictError(ValueError):
    """Raised when an edit would duplicate another managed email address."""


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

    async def _is_managed(self, db: AsyncSession) -> bool:
        result = await db.execute(
            select(AlertEmailRecipientState).where(
                AlertEmailRecipientState.state_id == 1,
            )
        )
        state = result.scalar_one_or_none()
        return bool(state and state.is_managed)

    async def _mark_managed(self, db: AsyncSession) -> None:
        result = await db.execute(
            select(AlertEmailRecipientState).where(
                AlertEmailRecipientState.state_id == 1,
            )
        )
        state = result.scalar_one_or_none()
        if state is None:
            state = AlertEmailRecipientState(state_id=1, is_managed=True)
            db.add(state)
        elif not state.is_managed:
            state.is_managed = True
            state.updated_at = utcnow_naive()
        await db.flush()

    async def list_active(
        self,
        db: AsyncSession,
        *,
        bootstrap_environment: bool = False,
    ) -> list[AlertEmailRecipient]:
        """List active rows, optionally importing initial `.env` recipients once."""
        rows = await self.list_all(
            db,
            bootstrap_environment=bootstrap_environment,
        )
        return [row for row in rows if row.is_active]

    async def list_all(
        self,
        db: AsyncSession,
        *,
        bootstrap_environment: bool = False,
    ) -> list[AlertEmailRecipient]:
        """List active and paused rows, importing initial `.env` recipients once."""
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

        if bootstrap_environment:
            await self._mark_managed(db)

        return rows

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

        if not rows and not await self._is_managed(db):
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

    async def update(
        self,
        db: AsyncSession,
        recipient_id: int,
        *,
        email: Optional[str] = None,
        name: Optional[str] = None,
        update_name: bool = False,
        is_active: Optional[bool] = None,
    ) -> Optional[AlertEmailRecipient]:
        """Edit recipient details or toggle whether future alerts are delivered."""
        result = await db.execute(
            select(AlertEmailRecipient).where(
                AlertEmailRecipient.recipient_id == recipient_id,
            )
        )
        recipient = result.scalar_one_or_none()
        if recipient is None:
            return None

        if email is not None:
            normalized_email = email.strip().lower()
            duplicate_result = await db.execute(
                select(AlertEmailRecipient).where(
                    AlertEmailRecipient.email == normalized_email,
                    AlertEmailRecipient.recipient_id != recipient_id,
                )
            )
            if duplicate_result.scalar_one_or_none() is not None:
                raise AlertRecipientEmailConflictError(
                    "That email address is already assigned to another recipient."
                )
            recipient.email = normalized_email
        if update_name:
            recipient.name = (name or "").strip() or None
        if is_active is not None:
            recipient.is_active = is_active

        recipient.updated_at = utcnow_naive()
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

    async def hard_delete(
        self,
        db: AsyncSession,
        recipient_id: int,
    ) -> Optional[AlertEmailRecipient]:
        """Permanently remove a recipient while keeping the managed list authoritative."""
        result = await db.execute(
            select(AlertEmailRecipient).where(
                AlertEmailRecipient.recipient_id == recipient_id,
            )
        )
        recipient = result.scalar_one_or_none()
        if recipient is None:
            return None
        await self._mark_managed(db)
        await db.delete(recipient)
        await db.flush()
        return recipient


alert_recipient_service = AlertRecipientService()
