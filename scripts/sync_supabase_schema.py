"""Check or apply the consolidated MangoPoint schema to Supabase.

The database connection stays server-side in ``.env``. Successful applications
are recorded by content hash so an unchanged consolidated schema is a no-op.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "supabase" / "MangoPoint_Supabase_SQL_Editor.sql"
SCHEMA_STATE_KEY = "consolidated_supabase_schema"
SCHEMA_ADVISORY_LOCK = 681_204_203

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def schema_digest(sql: str) -> str:
    """Return the stable SHA-256 digest stored after a successful update."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def executable_statements(sql: str) -> list[str]:
    """Split the SQL Editor file and omit its outer transaction markers."""
    from api.core.migrations import split_sql_statements

    return [
        statement
        for statement in split_sql_statements(sql)
        if statement.strip().rstrip(";").upper() not in {"BEGIN", "COMMIT"}
    ]


async def _current_digest(remote) -> str | None:
    table_exists = await remote.scalar(
        text("SELECT to_regclass('public.mangopoint_schema_state') IS NOT NULL")
    )
    if not table_exists:
        return None
    return await remote.scalar(
        text(
            "SELECT schema_hash FROM public.mangopoint_schema_state "
            "WHERE schema_key = :schema_key"
        ),
        {"schema_key": SCHEMA_STATE_KEY},
    )


async def sync_schema(*, apply: bool) -> bool:
    """Return True when the remote schema differs; apply it when requested."""
    from api.services.cloud_sync_service import CloudSyncService

    service = CloudSyncService()
    if not service.configured:
        raise RuntimeError("SUPABASE_DATABASE_URL is not configured in .env.")

    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    digest = schema_digest(sql)
    remote_engine = service._get_remote_engine()

    try:
        if not apply:
            async with remote_engine.connect() as remote:
                current = await _current_digest(remote)
            return current != digest

        async with remote_engine.begin() as remote:
            await remote.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": SCHEMA_ADVISORY_LOCK},
            )
            current = await _current_digest(remote)
            if current == digest:
                return False

            for statement in executable_statements(sql):
                await remote.exec_driver_sql(statement)

            await remote.execute(
                text(
                    "INSERT INTO public.mangopoint_schema_state "
                    "(schema_key, schema_hash, applied_at) "
                    "VALUES (:schema_key, :schema_hash, NOW()) "
                    "ON CONFLICT (schema_key) DO UPDATE SET "
                    "schema_hash = EXCLUDED.schema_hash, applied_at = NOW()"
                ),
                {"schema_key": SCHEMA_STATE_KEY, "schema_hash": digest},
            )
        return True
    finally:
        await service.close()


async def _run_with_timeout(*, apply: bool) -> bool:
    async with asyncio.timeout(120):
        return await sync_schema(apply=apply)


def _safe_failure_reason(error: Exception) -> str:
    """Recognize common connection failures without printing driver secrets."""
    message = str(error).lower()
    if "password authentication failed" in message:
        return "Supabase rejected the configured database password."
    if "tenant or user not found" in message or (
        "tenant/user" in message and "not found" in message
    ):
        return "Supabase could not find the configured project or pooler user."
    if "unable to establish connection to upstream database" in message:
        return "The Supabase pooler could not reach the database."
    if isinstance(error, TimeoutError) or "connection timeout" in message:
        return "The Supabase database connection timed out."
    if "SUPABASE_DATABASE_URL is not configured" in str(error):
        return "Set SUPABASE_DATABASE_URL in the server-side .env file."
    return "Check the schema SQL, project availability, and server-side database configuration."


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check or apply the consolidated MangoPoint Supabase schema."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="Check whether the configured Supabase project needs an update.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply the schema when its content hash has changed.",
    )
    args = parser.parse_args()

    try:
        changed = asyncio.run(_run_with_timeout(apply=args.apply))
    except Exception as exc:
        # Driver exceptions may include connection strings or credentials.
        # Report the error type without echoing the raw exception or traceback.
        print(
            f"Supabase schema sync failed ({type(exc).__name__}). "
            f"{_safe_failure_reason(exc)} "
            "Uncommitted schema changes were rolled back.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    if args.apply:
        print("Supabase schema updated." if changed else "Supabase schema is already current.")
    else:
        print("Supabase schema update is pending." if changed else "Supabase schema is current.")


if __name__ == "__main__":
    main()
