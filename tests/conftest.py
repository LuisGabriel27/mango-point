"""Test compatibility for legacy synchronous asyncio test helpers on Python 3.14+."""

import asyncio

import pytest


@pytest.fixture(autouse=True)
def ensure_current_event_loop():
    """Keep ``asyncio.get_event_loop()`` helpers working between tests."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield
