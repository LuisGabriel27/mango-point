"""Protected endpoints for cloud synchronization status and manual runs."""

from typing import Optional

from fastapi import APIRouter, Query

from api.services.cloud_sync_service import cloud_sync_service

router = APIRouter(prefix="/sync", tags=["Cloud Sync"])


@router.get("/status")
async def sync_status():
    """Return local queue state and the last cloud synchronization result."""
    return await cloud_sync_service.status()


@router.post("/run")
async def run_sync(
    limit: Optional[int] = Query(None, ge=1, le=1000),
):
    """Run a manual cloud synchronization batch."""
    return await cloud_sync_service.run_once(limit=limit)
