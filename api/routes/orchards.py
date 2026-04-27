"""
MangoPoint API - Orchard Routes
===============================
Manage orchard metadata for multi-orchard deployments.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import (
    database_unavailable_http_exception,
    get_db,
    is_database_unavailable,
)
from ..models.schemas import (
    OrchardCreate,
    OrchardListResponse,
    OrchardResponse,
    OrchardUpdate,
)
from db.models import Orchard
from utils.datetime_utils import format_rfc3339

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchards", tags=["Orchards"])


def normalize_orchard_uid(value: str) -> str:
    """Normalize an orchard name or ID into a stable public identifier."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    slug = slug.strip("-")
    return slug or "orchard"


def count_geojson_trees(geojson: Optional[Dict[str, Any]]) -> int:
    """Count Point tree features in an orchard GeoJSON payload."""
    if not geojson:
        return 0

    count = 0
    for feature in geojson.get("features", []) or []:
        geometry = feature.get("geometry", {}) or {}
        geom_type = geometry.get("type")
        if geom_type == "Point":
            count += 1
        elif geom_type == "MultiPoint":
            coordinates = geometry.get("coordinates") or []
            count += len(coordinates)
    return count


def derive_geojson_centroid(
    geojson: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], Optional[float]]:
    """
    Derive a rough lon/lat centroid from tree points, falling back to polygons.

    The dashboard only needs a stable map center here. Detailed spatial work
    still uses the original GeoJSON stored with the orchard or simulation.
    """
    if not geojson:
        return None, None

    point_coords: List[Tuple[float, float]] = []
    boundary_coords: List[Tuple[float, float]] = []

    for feature in geojson.get("features", []) or []:
        geometry = feature.get("geometry", {}) or {}
        geom_type = geometry.get("type")
        coordinates = geometry.get("coordinates")

        if geom_type == "Point":
            pair = _lon_lat_pair(coordinates)
            if pair:
                point_coords.append(pair)
        elif geom_type == "MultiPoint":
            for coord in coordinates or []:
                pair = _lon_lat_pair(coord)
                if pair:
                    point_coords.append(pair)
        elif geom_type == "Polygon":
            boundary_coords.extend(_polygon_lon_lat_pairs(coordinates))
        elif geom_type == "MultiPolygon":
            for polygon in coordinates or []:
                boundary_coords.extend(_polygon_lon_lat_pairs(polygon))

    coords = point_coords or boundary_coords
    if not coords:
        return None, None

    lon = sum(pair[0] for pair in coords) / len(coords)
    lat = sum(pair[1] for pair in coords) / len(coords)
    return lon, lat


def _lon_lat_pair(value: Any) -> Optional[Tuple[float, float]]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def _polygon_lon_lat_pairs(value: Any) -> List[Tuple[float, float]]:
    if not value:
        return []

    ring = value[0] or []
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]

    pairs: List[Tuple[float, float]] = []
    for coord in ring:
        pair = _lon_lat_pair(coord)
        if pair:
            pairs.append(pair)
    return pairs


def orchard_to_response(
    orchard: Orchard,
    include_geojson: bool = True,
) -> OrchardResponse:
    """Convert an ORM orchard row into the public API shape."""
    return OrchardResponse(
        database_id=orchard.orchard_id,
        orchard_id=orchard.orchard_uid or str(orchard.orchard_id),
        name=orchard.name,
        owner_name=orchard.owner_name,
        location=orchard.location,
        area_size=float(orchard.area_size) if orchard.area_size is not None else None,
        tree_count=orchard.tree_count or 0,
        geojson=orchard.geojson if include_geojson else None,
        centroid_lon=orchard.centroid_lon,
        centroid_lat=orchard.centroid_lat,
        description=orchard.description,
        is_active=orchard.is_active,
        monitoring_enabled=orchard.monitoring_enabled,
        orchard_stage=orchard.orchard_stage,
        days_since_flowering=orchard.days_since_flowering,
        monitored_pest_types=orchard.monitored_pest_types or ["cecid", "fruitfly"],
        last_monitoring_scan_at=(
            format_rfc3339(orchard.last_monitoring_scan_at)
            if orchard.last_monitoring_scan_at
            else None
        ),
        created_at=format_rfc3339(orchard.created_at) if orchard.created_at else None,
        updated_at=format_rfc3339(orchard.updated_at) if orchard.updated_at else None,
    )


async def _get_orchard_or_404(
    db: AsyncSession,
    orchard_id: str,
) -> Orchard:
    """Find an orchard by public UID, with numeric DB ID as fallback."""
    result = await db.execute(
        select(Orchard).where(Orchard.orchard_uid == orchard_id)
    )
    orchard = result.scalar_one_or_none()
    if orchard:
        return orchard

    if str(orchard_id).isdigit():
        result = await db.execute(
            select(Orchard).where(Orchard.orchard_id == int(orchard_id))
        )
        orchard = result.scalar_one_or_none()
        if orchard:
            return orchard

    raise HTTPException(status_code=404, detail="Orchard not found")


async def _ensure_unique_uid(
    db: AsyncSession,
    orchard_uid: str,
    current_database_id: Optional[int] = None,
) -> None:
    result = await db.execute(
        select(Orchard).where(Orchard.orchard_uid == orchard_uid)
    )
    existing = result.scalar_one_or_none()
    if existing and existing.orchard_id != current_database_id:
        raise HTTPException(
            status_code=409,
            detail=f"Orchard ID '{orchard_uid}' already exists.",
        )


@router.post(
    "",
    response_model=OrchardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create orchard",
    description="Register an orchard with optional GeoJSON for future map switching.",
)
async def create_orchard(
    payload: OrchardCreate,
    db: AsyncSession = Depends(get_db),
) -> OrchardResponse:
    """Create a managed orchard record."""
    try:
        orchard_uid = normalize_orchard_uid(payload.orchard_id or payload.name)
        await _ensure_unique_uid(db, orchard_uid)

        centroid_lon, centroid_lat = derive_geojson_centroid(payload.geojson)
        tree_count = (
            payload.tree_count
            if payload.tree_count is not None
            else count_geojson_trees(payload.geojson)
        )

        orchard = Orchard(
            orchard_uid=orchard_uid,
            name=payload.name,
            owner_name=payload.owner_name,
            location=payload.location,
            area_size=payload.area_size,
            tree_count=tree_count,
            geojson=payload.geojson,
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
            description=payload.description,
            is_active=payload.is_active,
            monitoring_enabled=payload.monitoring_enabled,
            orchard_stage=payload.orchard_stage.value,
            days_since_flowering=payload.days_since_flowering,
            monitored_pest_types=[pest.value for pest in payload.monitored_pest_types],
        )
        db.add(orchard)
        await db.flush()

        logger.info("Created orchard %s (%s)", orchard.name, orchard.orchard_uid)
        return orchard_to_response(orchard)
    except HTTPException:
        raise
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Orchard already exists.") from exc
    except Exception as exc:
        await db.rollback()
        if is_database_unavailable(exc):
            raise database_unavailable_http_exception() from exc
        logger.error("Failed to create orchard: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create orchard.") from exc


@router.get(
    "",
    response_model=OrchardListResponse,
    summary="List orchards",
    description="List managed orchards for multi-orchard workflows.",
)
async def list_orchards(
    active_only: bool = Query(True, description="Only include active orchards."),
    include_geojson: bool = Query(False, description="Include stored GeoJSON in each row."),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> OrchardListResponse:
    """List orchards with optional active filtering."""
    query = select(Orchard)
    count_query = select(func.count()).select_from(Orchard)

    if active_only:
        query = query.where(Orchard.is_active.is_(True))
        count_query = count_query.where(Orchard.is_active.is_(True))

    query = query.order_by(Orchard.name.asc()).limit(limit).offset(offset)

    result = await db.execute(query)
    total_result = await db.execute(count_query)
    orchards = result.scalars().all()

    return OrchardListResponse(
        total=total_result.scalar_one(),
        orchards=[
            orchard_to_response(orchard, include_geojson=include_geojson)
            for orchard in orchards
        ],
    )


@router.get(
    "/{orchard_id}",
    response_model=OrchardResponse,
    summary="Get orchard",
    description="Get one orchard by public orchard ID.",
)
async def get_orchard(
    orchard_id: str,
    db: AsyncSession = Depends(get_db),
) -> OrchardResponse:
    """Get a managed orchard."""
    orchard = await _get_orchard_or_404(db, orchard_id)
    return orchard_to_response(orchard)


@router.put(
    "/{orchard_id}",
    response_model=OrchardResponse,
    summary="Update orchard",
    description="Update orchard metadata or replace stored GeoJSON.",
)
async def update_orchard(
    orchard_id: str,
    payload: OrchardUpdate,
    db: AsyncSession = Depends(get_db),
) -> OrchardResponse:
    """Update a managed orchard."""
    try:
        orchard = await _get_orchard_or_404(db, orchard_id)
        updates = payload.model_dump(exclude_unset=True)

        if "orchard_id" in updates and updates["orchard_id"]:
            new_uid = normalize_orchard_uid(updates.pop("orchard_id"))
            await _ensure_unique_uid(db, new_uid, current_database_id=orchard.orchard_id)
            orchard.orchard_uid = new_uid

        if "name" in updates and updates["name"] is not None:
            orchard.name = updates.pop("name")

        if "geojson" in updates:
            orchard.geojson = updates.pop("geojson")
            orchard.centroid_lon, orchard.centroid_lat = derive_geojson_centroid(
                orchard.geojson
            )
            if "tree_count" not in updates:
                orchard.tree_count = count_geojson_trees(orchard.geojson)

        if "orchard_stage" in updates and updates["orchard_stage"] is not None:
            updates["orchard_stage"] = updates["orchard_stage"].value

        if "monitored_pest_types" in updates and updates["monitored_pest_types"] is not None:
            updates["monitored_pest_types"] = [
                pest.value for pest in updates["monitored_pest_types"]
            ]

        for key, value in updates.items():
            setattr(orchard, key, value)

        await db.flush()

        logger.info("Updated orchard %s (%s)", orchard.name, orchard.orchard_uid)
        return orchard_to_response(orchard)
    except HTTPException:
        raise
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Orchard already exists.") from exc
    except Exception as exc:
        await db.rollback()
        if is_database_unavailable(exc):
            raise database_unavailable_http_exception() from exc
        logger.error("Failed to update orchard: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update orchard.") from exc


@router.delete(
    "/{orchard_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate orchard",
    description="Soft-delete an orchard by marking it inactive.",
)
async def deactivate_orchard(
    orchard_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Deactivate a managed orchard without deleting its history."""
    orchard = await _get_orchard_or_404(db, orchard_id)
    orchard.is_active = False
    await db.flush()
    logger.info("Deactivated orchard %s (%s)", orchard.name, orchard.orchard_uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
