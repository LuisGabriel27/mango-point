"""One-way local PostgreSQL to Supabase backup synchronization."""

from __future__ import annotations

import asyncio
import enum
import json
import logging
import mimetypes
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx
from sqlalchemy import JSON, Integer, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from api.core.config import settings
from api.core.database import async_session_maker
from db.models import Orchard, OrchardAsset, SyncOutbox, SyncState
from utils.datetime_utils import utcnow_naive

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYNC_ADVISORY_LOCK = 681_204_202


def _async_database_url(value: str) -> str:
    """Convert a standard PostgreSQL URL to SQLAlchemy's asyncpg URL."""
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+asyncpg://", 1)
    return value


class CloudSyncService:
    """Replicate local durable database rows to Supabase."""

    def __init__(self) -> None:
        self._remote_engine: Optional[AsyncEngine] = None
        self._scheduler_task: Optional[asyncio.Task] = None

    @property
    def configured(self) -> bool:
        """Return whether the remote database is configured."""
        return bool(settings.SUPABASE_DATABASE_URL)

    @property
    def storage_configured(self) -> bool:
        """Return whether optional server-side asset backup is configured."""
        return bool(
            settings.CLOUD_SYNC_ASSETS
            and settings.SUPABASE_URL
            and settings.SUPABASE_SERVICE_ROLE_KEY
        )

    def _get_remote_engine(self) -> AsyncEngine:
        if not settings.SUPABASE_DATABASE_URL:
            raise RuntimeError("SUPABASE_DATABASE_URL is not configured.")
        if self._remote_engine is None:
            self._remote_engine = create_async_engine(
                _async_database_url(settings.SUPABASE_DATABASE_URL),
                pool_size=1,
                max_overflow=0,
                pool_pre_ping=True,
                connect_args={"statement_cache_size": 0},
            )
        return self._remote_engine

    async def close(self) -> None:
        """Dispose the remote connection pool."""
        if self._remote_engine is not None:
            await self._remote_engine.dispose()
            self._remote_engine = None

    async def status(self) -> dict[str, Any]:
        """Return local queue and last-run information."""
        async with async_session_maker() as db:
            pending = await db.scalar(
                select(func.count(SyncOutbox.outbox_id)).where(
                    SyncOutbox.synced_at.is_(None),
                )
            )
            state = await db.get(SyncState, 1)
            return {
                "configured": self.configured,
                "assets_enabled": settings.CLOUD_SYNC_ASSETS,
                "storage_configured": self.storage_configured,
                "pending_events": int(pending or 0),
                "last_event_id": state.last_event_id if state else None,
                "last_success_at": state.last_success_at.isoformat() if state and state.last_success_at else None,
                "last_attempt_at": state.last_attempt_at.isoformat() if state and state.last_attempt_at else None,
                "last_error": state.last_error if state else None,
                "interval_seconds": settings.CLOUD_SYNC_INTERVAL_SECONDS,
            }

    async def run_once(self, limit: Optional[int] = None) -> dict[str, Any]:
        """Synchronize one batch of pending events, retrying failures later."""
        if not self.configured:
            return {
                "configured": False,
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "message": "SUPABASE_DATABASE_URL is not configured.",
            }

        batch_size = max(1, min(limit or settings.CLOUD_SYNC_BATCH_SIZE, 1000))
        processed = succeeded = failed = skipped = 0

        async with async_session_maker() as lock_db:
            lock_result = await lock_db.execute(
                # Transaction-scoped locks cannot remain stuck in a pooled
                # connection after a worker exits or raises.
                text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                {"lock_id": SYNC_ADVISORY_LOCK},
            )
            acquired = bool(lock_result.scalar())
            if not acquired:
                return {
                    "configured": True,
                    "processed": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "skipped": 0,
                    "message": "Another synchronization run is already active.",
                }

            try:
                async with async_session_maker() as db:
                    state = await db.get(SyncState, 1)
                    if state is None:
                        state = SyncState(state_id=1)
                        db.add(state)
                        await db.flush()
                    state.last_attempt_at = utcnow_naive()
                    state.last_error = None
                    await db.commit()

                for _ in range(batch_size):
                    result = await self._process_one()
                    if result == "empty":
                        break
                    processed += 1
                    if result == "succeeded":
                        succeeded += 1
                    elif result == "skipped":
                        skipped += 1
                    else:
                        failed += 1

                async with async_session_maker() as db:
                    state = await db.get(SyncState, 1)
                    if state:
                        state.pending_count = int(
                            await db.scalar(
                                select(func.count(SyncOutbox.outbox_id)).where(
                                    SyncOutbox.synced_at.is_(None),
                                )
                            )
                            or 0
                        )
                        await db.commit()
            finally:
                await lock_db.rollback()

        return {
            "configured": True,
            "processed": processed,
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "pending_events": (await self.status()).get("pending_events", 0),
        }

    async def _process_one(self) -> str:
        """Process the oldest eligible event and update its retry state."""
        async with async_session_maker() as db:
            event = (
                await db.execute(
                    select(SyncOutbox)
                    .where(
                        SyncOutbox.synced_at.is_(None),
                        # sync_outbox uses PostgreSQL TIMESTAMP (without time
                        # zone), and trigger-created events use PostgreSQL's
                        # session clock. Compare with the same database clock
                        # so a non-UTC server timezone cannot hide eligible
                        # events from the worker.
                        SyncOutbox.next_attempt_at <= func.now(),
                    )
                    .order_by(SyncOutbox.outbox_id.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if event is None:
                return "empty"

            try:
                if event.entity_type == "orchard_asset" and not settings.CLOUD_SYNC_ASSETS:
                    # Orchard files are intentionally local-only. Mark the
                    # legacy manifest event as handled without contacting
                    # Supabase Storage or replicating the manifest row.
                    asset = await db.get(OrchardAsset, int(event.entity_key))
                    if asset is not None:
                        asset.sync_status = "local_only"
                        asset.updated_at = utcnow_naive()
                    event.synced_at = utcnow_naive()
                    event.last_error = None
                    state = await db.get(SyncState, 1)
                    if state:
                        state.last_event_id = event.outbox_id
                        state.last_error = None
                    await db.commit()
                    return "skipped"

                remote_engine = self._get_remote_engine()
                async with remote_engine.begin() as remote:
                    await remote.execute(text("SET LOCAL mangopoint.sync_disabled = 'true'"))
                    if event.operation == "delete":
                        await self._delete_remote_row(remote, event.entity_type, event.entity_key)
                    else:
                        if event.entity_type == "orchard_asset":
                            await self._upload_asset(db, event.entity_key)
                        row = await self._fetch_local_row(db, event.entity_type, event.entity_key)
                        if row is not None:
                            await self._upsert_remote_row(remote, event.entity_type, row)

                event.synced_at = utcnow_naive()
                event.last_error = None
                state = await db.get(SyncState, 1)
                if state:
                    state.last_event_id = event.outbox_id
                    state.last_success_at = utcnow_naive()
                    state.last_error = None
                await db.commit()
                return "succeeded"
            except Exception as exc:  # noqa: BLE001 - retryable boundary
                event.attempt_count = (event.attempt_count or 0) + 1
                event.last_error = str(exc)[:4000]
                if event.attempt_count >= max(1, settings.CLOUD_SYNC_MAX_RETRIES):
                    delay_seconds = 24 * 60 * 60
                else:
                    delay_seconds = min(3600, 30 * (2 ** min(event.attempt_count - 1, 7)))
                # Keep retry timestamps in the same timezone-less database
                # clock used by the TIMESTAMP column and trigger defaults.
                event.next_attempt_at = await db.scalar(
                    text(
                        "SELECT NOW()::timestamp "
                        "+ (:delay_seconds * INTERVAL '1 second')"
                    ),
                    {"delay_seconds": delay_seconds},
                )
                state = await db.get(SyncState, 1)
                if state:
                    state.last_error = event.last_error
                await db.commit()
                logger.warning(
                    "Cloud sync failed for %s/%s (attempt %s): %s",
                    event.entity_type,
                    event.entity_key,
                    event.attempt_count,
                    exc,
                )
                return "failed"

    async def _fetch_local_row(
        self,
        db: AsyncSession,
        entity_type: str,
        entity_key: str,
    ) -> Optional[dict[str, Any]]:
        """Fetch a current local row using the table's primary key."""
        from api.core.database import Base

        table = Base.metadata.tables.get(entity_type)
        if table is None or entity_type in {"weather_cache", "sync_outbox", "sync_state"}:
            return None
        primary_key = next(iter(table.primary_key.columns), None)
        if primary_key is None:
            return None
        key: Any = entity_key
        if isinstance(primary_key.type, Integer):
            key = int(entity_key)

        columns = [column for column in table.c if column.name != "geom"]
        if "geom" in table.c:
            columns.append(func.ST_AsEWKB(table.c.geom).label("__geom_wkb"))
        result = await db.execute(
            select(*columns).where(primary_key == key)
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        values = dict(row)
        if "__geom_wkb" in values:
            values["geom"] = values.pop("__geom_wkb")
        return values

    async def _upsert_remote_row(self, remote, entity_type: str, values: dict[str, Any]) -> None:
        """Upsert a serialized local row into the remote PostgreSQL schema."""
        from api.core.database import Base

        table = Base.metadata.tables.get(entity_type)
        if table is None:
            raise ValueError(f"Unsupported sync entity: {entity_type}")
        primary_key = next(iter(table.primary_key.columns), None)
        if primary_key is None:
            raise ValueError(f"Sync entity has no primary key: {entity_type}")

        bind_values: dict[str, Any] = {}
        insert_columns: list[str] = []
        insert_values: list[str] = []
        update_values: list[str] = []

        for column in table.c:
            name = column.name
            value = values.get(name)
            bind_name = f"v_{name}"
            if isinstance(value, enum.Enum):
                value = value.value
            if isinstance(column.type, JSON) and value is not None:
                value = json.dumps(value, default=str)
            bind_values[bind_name] = value
            insert_columns.append(f'"{name}"')
            if name == "geom":
                insert_values.append(f"ST_GeomFromEWKB(:{bind_name})")
            elif isinstance(column.type, JSON):
                insert_values.append(f"CAST(:{bind_name} AS JSONB)")
            else:
                insert_values.append(f":{bind_name}")
            if name != primary_key.name:
                update_values.append(f'"{name}" = EXCLUDED."{name}"')

        if "geom" in table.c and "v_geom" not in bind_values:
            bind_values["v_geom"] = values.get("geom")

        sql = (
            f'INSERT INTO "{entity_type}" ({", ".join(insert_columns)}) '
            f'VALUES ({", ".join(insert_values)}) '
            f'ON CONFLICT ("{primary_key.name}") DO UPDATE SET {", ".join(update_values)}'
        )
        await remote.execute(text(sql), bind_values)

    async def _delete_remote_row(self, remote, entity_type: str, entity_key: str) -> None:
        """Delete a remote row by the same primary key used locally."""
        from api.core.database import Base

        table = Base.metadata.tables.get(entity_type)
        if table is None or entity_type in {"weather_cache", "sync_outbox", "sync_state"}:
            return
        primary_key = next(iter(table.primary_key.columns), None)
        if primary_key is None:
            return
        key: Any = int(entity_key) if isinstance(primary_key.type, Integer) else entity_key
        await remote.execute(
            text(f'DELETE FROM "{entity_type}" WHERE "{primary_key.name}" = :key'),
            {"key": key},
        )

    async def _upload_asset(self, db: AsyncSession, entity_key: str) -> None:
        """Upload one local orchard asset to the private Supabase bucket."""
        if not self.storage_configured:
            raise RuntimeError("Supabase Storage is not configured.")

        asset = await db.get(OrchardAsset, int(entity_key))
        if asset is None:
            return
        orchard = await db.get(Orchard, asset.orchard_id)
        if orchard is None:
            raise RuntimeError(f"Orchard {asset.orchard_id} is missing for asset {asset.asset_id}.")

        local_path = (PROJECT_ROOT / asset.local_path).resolve()
        allowed_root = (PROJECT_ROOT / "data" / "orchards").resolve()
        if allowed_root not in local_path.parents:
            raise RuntimeError(f"Asset path is outside the orchard asset directory: {asset.local_path}")
        if not local_path.exists():
            raise FileNotFoundError(str(local_path))

        storage_key = asset.storage_key or (
            f"orchards/{orchard.orchard_uid}/{asset.asset_type}/{asset.sha256}/{local_path.name}"
        )
        bucket = asset.storage_bucket or settings.SUPABASE_STORAGE_BUCKET
        url = (
            f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/"
            f"{quote(bucket, safe='')}/{quote(storage_key, safe='/')}"
        )
        content_type = asset.mime_type or mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        payload = await asyncio.to_thread(local_path.read_bytes)
        headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY or "",
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(url, content=payload, headers=headers)
            if response.status_code not in {200, 201, 204}:
                raise RuntimeError(
                    f"Storage upload failed ({response.status_code}): {response.text[:500]}"
                )

        asset.storage_key = storage_key
        asset.sync_status = "uploaded"
        asset.updated_at = utcnow_naive()

    async def run_scheduler(self) -> None:
        """Keep a best-effort two-hour scheduler alive with the API process."""
        while True:
            try:
                if settings.CLOUD_SYNC_ENABLED and self.configured:
                    await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - scheduler must remain alive
                logger.exception("Cloud synchronization scheduler failed")
            await asyncio.sleep(max(60, settings.CLOUD_SYNC_INTERVAL_SECONDS))


cloud_sync_service = CloudSyncService()
