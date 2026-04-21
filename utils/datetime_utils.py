"""
MangoPoint — Shared datetime helpers
====================================

Centralizes two patterns that used to be scattered across the codebase:

    1. ``datetime.utcnow()``        →  ``utcnow_aware()``
    2. ``dt.isoformat() + "Z"``     →  ``format_rfc3339(dt)``

``datetime.utcnow()`` is deprecated in Python 3.12 because it returns a *naive*
datetime that silently loses timezone information. ``utcnow_aware()`` returns
a timezone-aware UTC datetime instead.

Naively appending ``"Z"`` to ``isoformat()`` is wrong for tz-aware datetimes
(it produces malformed strings like ``2026-04-22T10:00:00+00:00Z``).
``format_rfc3339`` handles both naive and aware inputs correctly.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow_aware() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def utcnow_naive() -> datetime:
    """
    Return the current UTC time as a *naive* datetime.

    Drop-in replacement for the deprecated ``datetime.utcnow()``.
    Use this for SQLAlchemy ``DateTime`` columns (without ``timezone=True``),
    which expect naive datetimes.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def format_rfc3339(dt: datetime) -> str:
    """
    Return an RFC3339 timestamp string.

    - Naive datetimes are assumed UTC and get a trailing ``Z``.
    - Timezone-aware datetimes use the standard ``±HH:MM`` offset
      (the trailing ``Z`` is *not* appended — that would be invalid).
    """
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


def parse_rfc3339(s: str) -> datetime:
    """Parse an RFC3339 timestamp, accepting both ``Z`` and ``±HH:MM`` suffixes."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


__all__ = ["utcnow_aware", "utcnow_naive", "format_rfc3339", "parse_rfc3339"]
