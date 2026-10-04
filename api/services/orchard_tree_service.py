"""Portable orchard-tree identity and GeoJSON persistence helpers."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, Optional, Tuple

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Orchard, Tree


TREE_ID_KEYS = ("tree_id", "Tree_ID", "id", "fid")
STATUS_VALUES = {
    "healthy",
    "infected",
    "bagged",
    "dead",
    "history_infected",
    "suspect",
}
STAGE_VALUES = {"dormant", "flowering", "fruitlet", "mature"}


def feature_tree_id(feature: Dict[str, Any]) -> Optional[str]:
    """Return the stable tree label carried by one GeoJSON feature."""
    properties = feature.get("properties") or {}
    for key in TREE_ID_KEYS:
        value = properties.get(key)
        if value not in (None, ""):
            return str(value).strip()
    value = feature.get("id")
    return str(value).strip() if value not in (None, "") else None


def feature_tree_coordinates(feature: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Return a point coordinate for a tree feature when available."""
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if geometry.get("type") != "Point" or len(coordinates) < 2:
        return None
    try:
        return float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError):
        return None


def find_tree_feature(
    geojson: Optional[Dict[str, Any]],
    external_id: str,
) -> Optional[Dict[str, Any]]:
    """Find a GeoJSON tree by its portable, string-normalized label."""
    target = str(external_id).strip()
    for feature in (geojson or {}).get("features", []) or []:
        if feature_tree_id(feature) == target:
            return feature
    return None


def update_geojson_trees(
    geojson: Optional[Dict[str, Any]],
    tree_ids: Iterable[str],
    *,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    clear_status: bool = False,
    clear_stage: bool = False,
) -> tuple[Dict[str, Any], list[str], list[str]]:
    """Return a copied map with stage/status properties updated by tree label."""
    wanted = list(dict.fromkeys(str(value).strip() for value in tree_ids if str(value).strip()))
    wanted_set = set(wanted)
    found: set[str] = set()
    updated_geojson = copy.deepcopy(geojson or {"type": "FeatureCollection", "features": []})

    for feature in updated_geojson.get("features", []) or []:
        external_id = feature_tree_id(feature)
        if external_id not in wanted_set:
            continue
        properties = feature.setdefault("properties", {})
        if status is not None:
            properties["status"] = status
            properties["Status"] = status
        if clear_status:
            properties.pop("status", None)
            properties.pop("Status", None)
        if stage is not None:
            properties["stage"] = stage
            properties["Stage"] = stage
        if clear_stage:
            properties.pop("stage", None)
            properties.pop("Stage", None)
        found.add(external_id)

    return updated_geojson, [value for value in wanted if value in found], [value for value in wanted if value not in found]


def _feature_status(feature: Optional[Dict[str, Any]]) -> str:
    properties = (feature or {}).get("properties") or {}
    value = str(properties.get("status", properties.get("Status", "healthy"))).strip().lower()
    if value == "unbagged":
        value = "healthy"
    return value if value in STATUS_VALUES else "healthy"


def _feature_stage(feature: Optional[Dict[str, Any]]) -> str:
    properties = (feature or {}).get("properties") or {}
    value = str(properties.get("stage", properties.get("Stage", "dormant"))).strip().lower()
    return value if value in STAGE_VALUES else "dormant"


async def ensure_tree_row(
    db: AsyncSession,
    orchard: Orchard,
    external_id: str,
    *,
    feature: Optional[Dict[str, Any]] = None,
) -> Optional[Tree]:
    """Resolve or lazily create the database row for a GeoJSON tree label.

    Older installations may have imported rows before ``external_id`` existed.
    In that case the row is linked by its numeric ID or exact stored coordinate
    before a new row is created, preserving existing infestation history.
    """
    normalized_id = str(external_id).strip()
    if not normalized_id:
        return None

    existing = (
        await db.execute(
            select(Tree).where(
                Tree.orchard_id == orchard.orchard_id,
                Tree.external_id == normalized_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    if normalized_id.isdigit():
        legacy = (
            await db.execute(
                select(Tree).where(
                    Tree.orchard_id == orchard.orchard_id,
                    Tree.tree_id == int(normalized_id),
                )
            )
        ).scalar_one_or_none()
        if legacy is not None and not legacy.external_id:
            legacy.external_id = normalized_id
            return legacy

    feature = feature or find_tree_feature(orchard.geojson, normalized_id)
    if feature is None:
        return None
    coordinates = feature_tree_coordinates(feature)
    if coordinates is None:
        return None
    lon, lat = coordinates

    tolerance = 1e-9
    coordinate_match = (
        await db.execute(
            select(Tree).where(
                and_(
                    Tree.orchard_id == orchard.orchard_id,
                    Tree.external_id.is_(None),
                    Tree.x_coordinate.between(lon - tolerance, lon + tolerance),
                    Tree.y_coordinate.between(lat - tolerance, lat + tolerance),
                )
            ).limit(1)
        )
    ).scalar_one_or_none()
    if coordinate_match is not None:
        coordinate_match.external_id = normalized_id
        return coordinate_match

    tree = Tree(
        external_id=normalized_id,
        orchard_id=orchard.orchard_id,
        x_coordinate=lon,
        y_coordinate=lat,
        status=_feature_status(feature),
        current_stage=_feature_stage(feature),
    )
    db.add(tree)
    await db.flush()
    return tree
