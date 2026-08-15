"""Small, versioned SQL migration runner used by local setup and CI."""

from pathlib import Path
import re

from sqlalchemy import text


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"
DOMAIN_SCHEMA_PATH = MIGRATIONS_DIR.parent / "schema.sql"


_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def split_sql_statements(sql: str) -> list[str]:
    """Split PostgreSQL SQL without breaking quoted or dollar-quoted bodies."""
    statements: list[str] = []
    buffer: list[str] = []
    single_quote = False
    double_quote = False
    dollar_tag: str | None = None
    line_comment = False
    index = 0

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue

        if dollar_tag:
            if sql.startswith(dollar_tag, index):
                buffer.append(dollar_tag)
                index += len(dollar_tag)
                dollar_tag = None
            else:
                buffer.append(char)
                index += 1
            continue

        if single_quote:
            buffer.append(char)
            if char == "'":
                if next_char == "'":
                    buffer.append(next_char)
                    index += 2
                    continue
                single_quote = False
            index += 1
            continue

        if double_quote:
            buffer.append(char)
            if char == '"':
                if next_char == '"':
                    buffer.append(next_char)
                    index += 2
                    continue
                double_quote = False
            index += 1
            continue

        if char == "-" and next_char == "-":
            line_comment = True
            index += 2
            continue
        if char == "'":
            single_quote = True
            buffer.append(char)
            index += 1
            continue
        if char == '"':
            double_quote = True
            buffer.append(char)
            index += 1
            continue
        if char == "$":
            match = _DOLLAR_TAG.match(sql, index)
            if match:
                dollar_tag = match.group(0)
                buffer.append(dollar_tag)
                index += len(dollar_tag)
                continue
        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += 1
            continue

        buffer.append(char)
        index += 1

    statement = "".join(buffer).strip()
    if statement:
        statements.append(statement)
    return statements


async def execute_script(conn, sql: str) -> None:
    """Execute a SQL script one statement at a time for asyncpg."""
    for statement in split_sql_statements(sql):
        await conn.exec_driver_sql(statement)


async def apply_migrations(conn) -> list[str]:
    """Apply unapplied SQL migrations in filename order."""
    await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(200) PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """))

    applied_rows = await conn.execute(text("SELECT version FROM schema_migrations"))
    applied = {row[0] for row in applied_rows}
    applied_now: list[str] = []

    # The existing consolidated schema is the version-zero baseline. Keeping
    # it here makes a brand-new Docker database usable without a separate psql
    # step, while later changes remain ordered migration files.
    baseline_version = "0000_domain_schema.sql"
    if baseline_version not in applied:
        await execute_script(conn, DOMAIN_SCHEMA_PATH.read_text(encoding="utf-8"))
        await conn.execute(
            text("INSERT INTO schema_migrations (version) VALUES (:version)"),
            {"version": baseline_version},
        )
        applied_now.append(baseline_version)

    for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = migration_path.name
        if version in applied:
            continue

        sql = migration_path.read_text(encoding="utf-8")
        await execute_script(conn, sql)
        await conn.execute(
            text("INSERT INTO schema_migrations (version) VALUES (:version)"),
            {"version": version},
        )
        applied_now.append(version)

    return applied_now
