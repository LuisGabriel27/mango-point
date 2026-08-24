"""Apply one repository Supabase migration through the configured DB connection."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_ROOT = (PROJECT_ROOT / "supabase" / "migrations").resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _migration_path(value: str) -> Path:
    candidate = (MIGRATION_ROOT / value).resolve()
    if candidate.parent != MIGRATION_ROOT or candidate.suffix.lower() != ".sql":
        raise argparse.ArgumentTypeError(
            "Migration must be a .sql filename inside supabase/migrations."
        )
    if not candidate.is_file():
        raise argparse.ArgumentTypeError(f"Migration does not exist: {candidate.name}")
    return candidate


async def _run(migration_path: Path) -> None:
    from api.core.migrations import split_sql_statements
    from api.services.cloud_sync_service import CloudSyncService

    service = CloudSyncService()
    if not service.configured:
        raise RuntimeError("SUPABASE_DATABASE_URL is not configured.")

    statements = split_sql_statements(migration_path.read_text(encoding="utf-8"))
    remote_engine = service._get_remote_engine()
    try:
        async with remote_engine.begin() as remote:
            for statement in statements:
                if statement.strip().rstrip(";").upper() in {"BEGIN", "COMMIT"}:
                    continue
                await remote.exec_driver_sql(statement)
    finally:
        await service.close()

    print(f"Applied Supabase migration: {migration_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply one SQL file from supabase/migrations."
    )
    parser.add_argument("migration", type=_migration_path)
    args = parser.parse_args()
    asyncio.run(_run(args.migration))


if __name__ == "__main__":
    main()
