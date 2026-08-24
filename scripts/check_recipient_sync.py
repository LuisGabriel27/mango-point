"""Report non-secret local/Supabase recipient backup counts."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import func, select, text


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def main() -> None:
    from api.core.database import async_session_maker
    from api.services.cloud_sync_service import CloudSyncService
    from db.models import AlertEmailRecipient, AlertEmailRecipientState, SyncOutbox

    service = CloudSyncService()
    if not service.configured:
        raise RuntimeError("SUPABASE_DATABASE_URL is not configured.")

    async with async_session_maker() as local:
        local_recipients = int(
            await local.scalar(select(func.count(AlertEmailRecipient.recipient_id))) or 0
        )
        local_state_rows = int(
            await local.scalar(select(func.count(AlertEmailRecipientState.state_id))) or 0
        )
        pending_events = int(
            await local.scalar(
                select(func.count(SyncOutbox.outbox_id)).where(
                    SyncOutbox.synced_at.is_(None),
                    SyncOutbox.entity_type.in_((
                        "alert_email_recipient",
                        "alert_email_recipient_state",
                    )),
                )
            )
            or 0
        )

    remote_engine = service._get_remote_engine()
    try:
        async with remote_engine.connect() as remote:
            remote_recipients = int(
                await remote.scalar(text("SELECT COUNT(*) FROM alert_email_recipient")) or 0
            )
            remote_state_rows = int(
                await remote.scalar(text("SELECT COUNT(*) FROM alert_email_recipient_state")) or 0
            )
    finally:
        await service.close()

    print(json.dumps({
        "local_recipients": local_recipients,
        "supabase_recipients": remote_recipients,
        "local_state_rows": local_state_rows,
        "supabase_state_rows": remote_state_rows,
        "pending_recipient_events": pending_events,
        "in_sync": (
            local_recipients == remote_recipients
            and local_state_rows == remote_state_rows
            and pending_events == 0
        ),
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
