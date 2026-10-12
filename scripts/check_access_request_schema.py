"""Validate inquiry SQL against local PostgreSQL, rolling all changes back."""

import asyncio
from pathlib import Path

from sqlalchemy import text

from api.core.database import engine
from api.core.migrations import split_sql_statements


async def check():
    root = Path(__file__).resolve().parents[1]
    path = root / "db/migrations/0012_organization_access_requests.sql"
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            for statement in split_sql_statements(path.read_text(encoding="utf-8")):
                await connection.exec_driver_sql(statement)
            assert await connection.scalar(text("SELECT to_regclass('public.access_request') IS NOT NULL"))
            assert await connection.scalar(text(
                "SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_access_request_sync' AND NOT tgisinternal)"
            ))
            print("Local inquiry schema and backup trigger validated; validation changes rolled back.")
        finally:
            await transaction.rollback()
    await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(check())
    except Exception as error:
        # Driver errors can contain credentials. Keep operational output safe.
        print(f"Local inquiry schema validation failed ({type(error).__name__}).")
        raise SystemExit(1) from None
