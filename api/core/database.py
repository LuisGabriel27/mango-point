"""
MangoPoint API — Database Connection
======================================
SQLAlchemy async engine and session management for PostgreSQL + PostGIS.
"""

import logging
from typing import AsyncGenerator

import asyncpg
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from .config import settings

logger = logging.getLogger(__name__)

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


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        # Enable PostGIS extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized successfully")


async def close_db():
    """Close database connections."""
    await engine.dispose()
    logger.info("Database connections closed")
