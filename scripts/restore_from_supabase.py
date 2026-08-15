"""Restore MangoPoint application rows from Supabase."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import Integer, func, select, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RESTORE_ORDER = [
    "user_account",
    "orchard",
    "pest",
    "tree",
    "simulation_run",
    "infestation_record",
    "environmental_condition",
    "mango_stage",
    "alert",
]


async def _remote_rows(remote, table_name: str) -> list[dict[str, Any]]:
    from api.core.database import Base

    table = Base.metadata.tables[table_name]
    columns = [column for column in table.c if column.name != "geom"]
    if "geom" in table.c:
        columns.append(func.ST_AsEWKB(table.c.geom).label("__geom_wkb"))
    result = await remote.execute(select(*columns))
    rows = []
    for row in result.mappings().all():
        values = dict(row)
        if "__geom_wkb" in values:
            values["geom"] = values.pop("__geom_wkb")
        rows.append(values)
    return rows


async def _run(args: argparse.Namespace) -> None:
    from api.core.database import Base, engine
    from api.services.cloud_sync_service import CloudSyncService

    service = CloudSyncService()
    if not service.configured:
        raise RuntimeError("SUPABASE_DATABASE_URL is not configured.")

    remote_engine = service._get_remote_engine()
    counts: dict[str, int] = {}
    async with remote_engine.connect() as remote:
        async with engine.begin() as local:
            await local.execute(text("SET LOCAL mangopoint.sync_disabled = 'true'"))
            for table_name in RESTORE_ORDER:
                if table_name not in Base.metadata.tables:
                    continue
                rows = await _remote_rows(remote, table_name)
                counts[table_name] = len(rows)
                if not args.dry_run:
                    for row in rows:
                        await service._upsert_remote_row(local, table_name, row)

            if not args.dry_run:
                for table_name in RESTORE_ORDER:
                    table = Base.metadata.tables.get(table_name)
                    if table is None:
                        continue
                    pk = next(iter(table.primary_key.columns), None)
                    if pk is None or not getattr(pk, "autoincrement", False):
                        continue
                    sequence = await local.scalar(
                        text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                        {"table_name": table_name, "column_name": pk.name},
                    )
                    if sequence:
                        await local.execute(
                            text(
                                f"SELECT setval(:sequence_name, "
                                f"GREATEST(COALESCE((SELECT MAX(\"{pk.name}\") FROM \"{table_name}\"), 1), 1), "
                                f"COALESCE((SELECT MAX(\"{pk.name}\") FROM \"{table_name}\"), 0) > 0)"
                            ),
                            {"sequence_name": sequence},
                        )

    print(json.dumps({
        "dry_run": args.dry_run,
        "rows": counts,
    }, indent=2, default=str))
    await service.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore MangoPoint data from Supabase.")
    parser.add_argument("--dry-run", action="store_true", help="Report remote row counts without changing local data.")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
