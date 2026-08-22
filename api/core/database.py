"""
MangoPoint API — Database Connection
======================================
SQLAlchemy async engine and session management for PostgreSQL + PostGIS.
"""

import json
import logging
from pathlib import Path
from typing import AsyncGenerator

import asyncpg
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from .config import settings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ORCHARD_GEOJSON = PROJECT_ROOT / "data" / "trees.geojson"

DATABASE_UNAVAILABLE_DETAIL = "Database unavailable. Check PostgreSQL configuration and credentials."
DATABASE_ERROR_TYPES = (
    SQLAlchemyError,
    asyncpg.PostgresError,
    ConnectionError,
    OSError,
)

# Convert sync URL to async
DATABASE_URL = settings.DATABASE_URL
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG,
    future=True,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def _normalize_user_role_enum(conn) -> None:
    """Normalize legacy uppercase role labels to the schema's lowercase labels."""
    await conn.execute(text("""
        DO $$
        BEGIN
            IF to_regtype('user_role_enum') IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'user_role_enum'::regtype
                      AND enumlabel = 'ADMIN'
                ) AND NOT EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'user_role_enum'::regtype
                      AND enumlabel = 'admin'
                ) THEN
                    ALTER TYPE user_role_enum RENAME VALUE 'ADMIN' TO 'admin';
                END IF;

                IF EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'user_role_enum'::regtype
                      AND enumlabel = 'ANALYST'
                ) AND NOT EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'user_role_enum'::regtype
                      AND enumlabel = 'analyst'
                ) THEN
                    ALTER TYPE user_role_enum RENAME VALUE 'ANALYST' TO 'analyst';
                END IF;

                IF EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'user_role_enum'::regtype
                      AND enumlabel = 'OPERATOR'
                ) AND NOT EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'user_role_enum'::regtype
                      AND enumlabel = 'operator'
                ) THEN
                    ALTER TYPE user_role_enum RENAME VALUE 'OPERATOR' TO 'operator';
                END IF;
            END IF;
        END $$;
    """))
    await conn.execute(text("""
        ALTER TABLE IF EXISTS user_account
        ALTER COLUMN role SET DEFAULT 'admin';
    """))
    await conn.execute(text("""
        DO $$
        BEGIN
            IF to_regclass('user_account') IS NOT NULL THEN
                UPDATE user_account
                SET role = lower(role::text)::user_role_enum
                WHERE role::text IN ('ADMIN', 'ANALYST', 'OPERATOR');
            END IF;
        END $$;
    """))


async def _normalize_pesttype_enum(conn) -> None:
    """Normalize legacy pest enum labels to the schema's lowercase labels."""
    await conn.execute(text("""
        DO $$
        BEGIN
            IF to_regtype('pesttype') IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'pesttype'::regtype
                      AND enumlabel = 'CECID_FLY'
                ) AND NOT EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'pesttype'::regtype
                      AND enumlabel = 'cecid'
                ) THEN
                    ALTER TYPE pesttype RENAME VALUE 'CECID_FLY' TO 'cecid';
                END IF;

                IF EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'pesttype'::regtype
                      AND enumlabel = 'FRUIT_FLY'
                ) AND NOT EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumtypid = 'pesttype'::regtype
                      AND enumlabel = 'fruitfly'
                ) THEN
                    ALTER TYPE pesttype RENAME VALUE 'FRUIT_FLY' TO 'fruitfly';
                END IF;
            END IF;
        END $$;
    """))


async def _ensure_simulation_id_sequence(conn) -> None:
    """Ensure simulation_run.simulation_id auto-generates values on old DBs."""
    await conn.execute(text("""
        CREATE SEQUENCE IF NOT EXISTS simulation_run_simulation_id_seq;
    """))
    await conn.execute(text("""
        SELECT setval(
            'simulation_run_simulation_id_seq',
            GREATEST(
                COALESCE((SELECT MAX(simulation_id) FROM simulation_run), 0),
                1
            ),
            COALESCE((SELECT MAX(simulation_id) FROM simulation_run), 0) > 0
        )
        WHERE to_regclass('simulation_run') IS NOT NULL;
    """))
    await conn.execute(text("""
        ALTER TABLE IF EXISTS simulation_run
        ALTER COLUMN simulation_id
        SET DEFAULT nextval('simulation_run_simulation_id_seq');
    """))
    await conn.execute(text("""
        ALTER SEQUENCE simulation_run_simulation_id_seq
        OWNED BY simulation_run.simulation_id;
    """))


def is_database_unavailable(exc: Exception) -> bool:
    """Return True when an exception indicates a database connectivity issue."""
    if isinstance(exc, DATABASE_ERROR_TYPES):
        return True

    message = str(exc).lower()
    connectivity_markers = (
        "connection refused",
        "database unavailable",
        "could not connect",
        "failed to establish a new connection",
        "remote computer refused",
    )
    return any(marker in message for marker in connectivity_markers)


def database_unavailable_http_exception() -> HTTPException:
    """Create a standard HTTP 503 for database connectivity issues."""
    return HTTPException(status_code=503, detail=DATABASE_UNAVAILABLE_DETAIL)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            try:
                await session.rollback()
            except Exception as rollback_error:
                logger.warning(f"Database rollback failed: {rollback_error}")
            raise
        finally:
            try:
                await session.close()
            except Exception as close_error:
                logger.warning(f"Database session close failed: {close_error}")


async def _ensure_default_orchard(conn) -> None:
    """Register the bundled BPI map once without overwriting managed data."""
    exists = await conn.scalar(text(
        "SELECT 1 FROM orchard WHERE orchard_uid = 'default-orchard' LIMIT 1"
    ))
    if exists or not DEFAULT_ORCHARD_GEOJSON.exists():
        return

    try:
        geojson = json.loads(DEFAULT_ORCHARD_GEOJSON.read_text(encoding="utf-8"))
        points = []
        for feature in geojson.get("features", []) or []:
            geometry = feature.get("geometry", {}) or {}
            if geometry.get("type") != "Point":
                continue
            coordinates = geometry.get("coordinates") or []
            if len(coordinates) >= 2:
                points.append((float(coordinates[0]), float(coordinates[1])))
        centroid_lon = sum(point[0] for point in points) / len(points) if points else None
        centroid_lat = sum(point[1] for point in points) / len(points) if points else None
        async def insert_default_orchard() -> None:
            await conn.execute(text("""
                INSERT INTO orchard (
                    orchard_uid, name, location, tree_count, geojson,
                    cecid_weed_zones, centroid_lon, centroid_lat,
                    is_active, monitoring_enabled, orchard_stage,
                    days_since_flowering, monitored_pest_types,
                    created_at, updated_at
                ) VALUES (
                    'default-orchard', 'Default Orchard (BPI)',
                    'Guimaras, Philippines', :tree_count, CAST(:geojson AS JSONB),
                    '[]'::jsonb, :centroid_lon, :centroid_lat,
                    TRUE, TRUE, 'mature', 60, '["cecid", "fruitfly"]'::jsonb,
                    NOW(), NOW()
                )
                ON CONFLICT (orchard_uid) DO NOTHING
            """), {
                "tree_count": len(points),
                "geojson": json.dumps(geojson),
                "centroid_lon": centroid_lon,
                "centroid_lat": centroid_lat,
            })

        # Keep optional default-data registration inside a savepoint so a
        # legacy constraint cannot abort the entire startup migration. The
        # lightweight connection used by unit tests does not expose savepoints.
        begin_nested = getattr(conn, "begin_nested", None)
        if begin_nested is None:
            await insert_default_orchard()
        else:
            async with begin_nested():
                await insert_default_orchard()
        logger.info("Registered bundled default-orchard with %d trees", len(points))
    except Exception as exc:
        logger.warning("Could not register bundled default-orchard: %s", exc)


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        from .migrations import apply_migrations

        await apply_migrations(conn)
        await conn.run_sync(Base.metadata.create_all)
        await _normalize_user_role_enum(conn)
        await _normalize_pesttype_enum(conn)
        await _ensure_simulation_id_sequence(conn)
        # Backward-compatible migration for older installs: field
        # observations are ground truth and do not belong to a simulation run.
        await conn.execute(text(
            "ALTER TABLE IF EXISTS infestation_record "
            "ALTER COLUMN simulation_id DROP NOT NULL;"
        ))
        # Backward-compatible migration for multi-orchard support. create_all()
        # creates these columns on fresh installs, while older local databases
        # need idempotent ALTER statements.
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS orchard_uid VARCHAR(100);"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS owner_name VARCHAR(200);"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS geojson JSONB;"))
        await conn.execute(text(
            "ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS "
            "cecid_weed_zones JSONB NOT NULL DEFAULT '[]'::jsonb;"
        ))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS centroid_lon DOUBLE PRECISION;"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS centroid_lat DOUBLE PRECISION;"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS orthophoto_path VARCHAR(500);"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS orthophoto_png_path VARCHAR(500);"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS orthophoto_bounds JSONB;"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS orthophoto_coordinates JSONB;"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS dtm_path VARCHAR(500);"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS dsm_path VARCHAR(500);"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS description TEXT;"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS monitoring_enabled BOOLEAN NOT NULL DEFAULT TRUE;"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS orchard_stage VARCHAR(50) NOT NULL DEFAULT 'mature';"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS days_since_flowering INTEGER NOT NULL DEFAULT 60;"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS monitored_pest_types JSONB;"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS last_monitoring_scan_at TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ALTER COLUMN created_at SET DEFAULT NOW();"))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ALTER COLUMN updated_at SET DEFAULT NOW();"))
        await conn.execute(text(
            "UPDATE orchard SET orchard_uid = 'orchard-' || orchard_id "
            "WHERE orchard_uid IS NULL OR orchard_uid = '';"
        ))
        await conn.execute(text("ALTER TABLE IF EXISTS orchard ALTER COLUMN orchard_uid SET NOT NULL;"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_orchard_uid ON orchard (orchard_uid);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_orchard_active ON orchard (is_active);"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_orchard_monitoring_enabled ON orchard (monitoring_enabled);"))
        await _ensure_default_orchard(conn)
        await conn.execute(text("ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS treatment_applications JSONB;"))
        await conn.execute(text("ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS simulation_mode VARCHAR(50) DEFAULT 'grid';"))
        await conn.execute(text("ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS request_payload JSONB;"))
        await conn.execute(text("ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS response_payload JSONB;"))
        await conn.execute(text("ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS result_metadata JSONB;"))
        await conn.execute(text("ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS time_series JSONB;"))
        await conn.execute(text("ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS timesteps JSONB;"))
        await conn.execute(text("ALTER TABLE IF EXISTS simulation_run ADD COLUMN IF NOT EXISTS impact_assumptions JSONB;"))
        await conn.execute(text("ALTER TABLE IF EXISTS alert ADD COLUMN IF NOT EXISTS recommended_actions JSONB;"))
        await conn.execute(text("ALTER TABLE IF EXISTS alert ADD COLUMN IF NOT EXISTS action_status VARCHAR(50) NOT NULL DEFAULT 'pending';"))
        await conn.execute(text("ALTER TABLE IF EXISTS alert ADD COLUMN IF NOT EXISTS action_assigned_to VARCHAR(100);"))
        await conn.execute(text("ALTER TABLE IF EXISTS alert ADD COLUMN IF NOT EXISTS action_notes TEXT;"))
        await conn.execute(text("ALTER TABLE IF EXISTS alert ADD COLUMN IF NOT EXISTS action_due_at TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE IF EXISTS alert ADD COLUMN IF NOT EXISTS action_completed_at TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE IF EXISTS alert ADD COLUMN IF NOT EXISTS suggested_simulation_params JSONB;"))
    logger.info("Database initialized successfully")


async def close_db():
    """Close database connections."""
    await engine.dispose()
    logger.info("Database connections closed")
