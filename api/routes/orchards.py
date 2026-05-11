"""
MangoPoint API - Orchard Routes
===============================
Manage orchard metadata for multi-orchard deployments.
"""

import logging
import base64
import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORCHARD_ASSET_DIR = PROJECT_ROOT / "data" / "orchards"
GEOJSON_SUFFIXES = {".geojson", ".json"}
GEOTIFF_SUFFIXES = {".tif", ".tiff"}


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


def geojson_crs_name(geojson: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return a legacy GeoJSON CRS name when one is present."""
    if not geojson:
        return None

    crs = geojson.get("crs")
    if isinstance(crs, str):
        return crs
    if isinstance(crs, dict):
        properties = crs.get("properties") or {}
        name = properties.get("name") or properties.get("href")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def normalize_geojson_to_wgs84(geojson: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert uploaded tree GeoJSON coordinates to WGS84 lon/lat when CRS is set.

    Many GIS exports still include a legacy GeoJSON ``crs`` object and store
    coordinates in UTM meters. The dashboard/map and simulation APIs expect
    lon/lat, so uploads are normalized before validation and persistence.
    """
    crs_name = geojson_crs_name(geojson)
    if not crs_name:
        return geojson

    try:
        from spatial.raster_utils import prefer_python_proj_data

        prefer_python_proj_data()
        from pyproj import CRS, Transformer

        source_crs = CRS.from_user_input(_normalize_crs_input(crs_name))
        target_crs = CRS.from_epsg(4326)
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="Tree GeoJSON CRS conversion requires pyproj.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Tree GeoJSON CRS '{crs_name}' could not be read: {exc}",
        ) from exc

    normalized = copy.deepcopy(geojson)
    normalized.pop("crs", None)
    normalized.pop("bbox", None)

    if source_crs.equals(target_crs):
        return normalized

    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    try:
        for feature in normalized.get("features", []) or []:
            if not isinstance(feature, dict):
                continue
            feature.pop("bbox", None)
            geometry = feature.get("geometry")
            if isinstance(geometry, dict):
                feature["geometry"] = _transform_geojson_geometry(geometry, transformer)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Tree GeoJSON coordinates could not be transformed from '{crs_name}' to WGS84.",
        ) from exc
    return normalized


def _normalize_crs_input(crs_name: str) -> str:
    epsg_match = re.search(r"EPSG[^0-9]*(\d+)\s*$", crs_name, re.IGNORECASE)
    if epsg_match:
        return f"EPSG:{epsg_match.group(1)}"
    if crs_name.upper() in {"CRS84", "OGC:CRS84", "URN:OGC:DEF:CRS:OGC::CRS84"}:
        return "OGC:CRS84"
    return crs_name


def _transform_geojson_geometry(geometry: Dict[str, Any], transformer: Any) -> Dict[str, Any]:
    transformed = copy.deepcopy(geometry)
    transformed.pop("bbox", None)

    if transformed.get("type") == "GeometryCollection":
        transformed["geometries"] = [
            _transform_geojson_geometry(child, transformer)
            for child in transformed.get("geometries", []) or []
            if isinstance(child, dict)
        ]
        return transformed

    if "coordinates" in transformed:
        transformed["coordinates"] = _transform_geojson_coordinates(
            transformed.get("coordinates"),
            transformer,
        )
    return transformed


def _transform_geojson_coordinates(value: Any, transformer: Any) -> Any:
    if _is_geojson_position(value):
        lon, lat = transformer.transform(float(value[0]), float(value[1]))
        return [lon, lat, *list(value[2:])]
    if isinstance(value, list):
        return [_transform_geojson_coordinates(item, transformer) for item in value]
    if isinstance(value, tuple):
        return [_transform_geojson_coordinates(item, transformer) for item in value]
    return value


def _is_geojson_position(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return False
    return not isinstance(value[0], (list, tuple, dict)) and not isinstance(
        value[1],
        (list, tuple, dict),
    )


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
    orchard_public_id = orchard.orchard_uid or str(orchard.orchard_id)
    return OrchardResponse(
        database_id=orchard.orchard_id,
        orchard_id=orchard_public_id,
        name=orchard.name,
        owner_name=orchard.owner_name,
        location=orchard.location,
        area_size=float(orchard.area_size) if orchard.area_size is not None else None,
        tree_count=orchard.tree_count or 0,
        geojson=orchard.geojson if include_geojson else None,
        centroid_lon=orchard.centroid_lon,
        centroid_lat=orchard.centroid_lat,
        orthophoto_url=(
            f"/orchards/{orchard_public_id}/assets/orthophoto.png"
            if getattr(orchard, "orthophoto_png_path", None)
            else None
        ),
        orthophoto_bounds=getattr(orchard, "orthophoto_bounds", None),
        orthophoto_coordinates=getattr(orchard, "orthophoto_coordinates", None),
        has_dtm=bool(getattr(orchard, "dtm_path", None)),
        has_dsm=bool(getattr(orchard, "dsm_path", None)),
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


def _upload_suffix(upload: UploadFile, allowed_suffixes: set[str], label: str) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in allowed_suffixes:
        allowed = ", ".join(sorted(allowed_suffixes))
        raise HTTPException(
            status_code=400,
            detail=f"{label} must use one of these file extensions: {allowed}.",
        )
    return suffix


async def _save_upload(upload: UploadFile, destination: Path) -> None:
    """Save an UploadFile in chunks so large GeoTIFFs do not sit in memory."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    await upload.seek(0)
    try:
        with destination.open("wb") as out_file:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                out_file.write(chunk)
    finally:
        await upload.close()


def _relative_project_path(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def _safe_project_path(relative_path: Optional[str]) -> Optional[Path]:
    if not relative_path:
        return None
    path = (PROJECT_ROOT / relative_path).resolve()
    allowed_root = ORCHARD_ASSET_DIR.resolve()
    if path != allowed_root and allowed_root not in path.parents:
        return None
    return path


def _load_tree_geojson(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file_obj:
            geojson = json.load(file_obj)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Tree GeoJSON is not valid JSON.") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Tree GeoJSON could not be read.") from exc

    if geojson.get("type") != "FeatureCollection" or not isinstance(geojson.get("features"), list):
        raise HTTPException(
            status_code=400,
            detail="Tree GeoJSON must be a FeatureCollection with a features array.",
        )
    if count_geojson_trees(geojson) <= 0:
        raise HTTPException(
            status_code=400,
            detail="Tree GeoJSON must contain at least one Point or MultiPoint tree feature.",
        )
    return geojson


def _orthophoto_overlay_from_tif(orthophoto_path: Path, png_path: Path) -> Dict[str, Any]:
    try:
        from spatial.raster_utils import load_raster_as_png_b64

        overlay = load_raster_as_png_b64(orthophoto_path, max_pixels=2048)
        png_data = overlay["b64"].split(",", 1)[1]
        png_path.write_bytes(base64.b64decode(png_data))
        return overlay
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="Raster processing dependencies are missing. Install rasterio and Pillow.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Orthophoto GeoTIFF could not be processed: {exc}",
        ) from exc


def _centroid_from_bounds(bounds: List[float]) -> Tuple[Optional[float], Optional[float]]:
    if not bounds or len(bounds) != 4:
        return None, None
    west, south, east, north = bounds
    return (float(west) + float(east)) / 2.0, (float(south) + float(north)) / 2.0


def _point_within_bounds(
    lon: Optional[float],
    lat: Optional[float],
    bounds: List[float],
    tolerance_fraction: float = 0.02,
) -> bool:
    """Return whether a lon/lat point falls inside raster bounds with a small tolerance."""
    if lon is None or lat is None or not bounds or len(bounds) != 4:
        return False
    west, south, east, north = [float(value) for value in bounds]
    lon_pad = max(abs(east - west) * tolerance_fraction, 1e-9)
    lat_pad = max(abs(north - south) * tolerance_fraction, 1e-9)
    return (
        west - lon_pad <= float(lon) <= east + lon_pad
        and south - lat_pad <= float(lat) <= north + lat_pad
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


@router.post(
    "/upload",
    response_model=OrchardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload orchard files",
    description=(
        "Register an orchard by uploading its tree GeoJSON and GeoTIFF assets. "
        "The API derives the orchard location and map overlay bounds automatically "
        "from the orthophoto GeoTIFF."
    ),
)
async def upload_orchard(
    name: str = Form(...),
    tree_geojson: UploadFile = File(...),
    orthophoto: UploadFile = File(...),
    dtm: Optional[UploadFile] = File(None),
    dsm: Optional[UploadFile] = File(None),
    orchard_id: Optional[str] = Form(None),
    owner_name: Optional[str] = Form(None),
    orchard_stage: str = Form("mature"),
    days_since_flowering: int = Form(60),
    db: AsyncSession = Depends(get_db),
) -> OrchardResponse:
    """Create an orchard from dashboard-uploaded files."""
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Orchard name is required.")

    stage = orchard_stage.strip().lower()
    if stage not in {"dormant", "flowering", "fruitlet", "mature"}:
        raise HTTPException(status_code=400, detail="Unsupported orchard stage.")

    try:
        flowering_days = max(0, min(int(days_since_flowering), 180))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="days_since_flowering must be a number.") from exc

    orchard_uid = normalize_orchard_uid(orchard_id or clean_name)
    await _ensure_unique_uid(db, orchard_uid)

    _upload_suffix(tree_geojson, GEOJSON_SUFFIXES, "Tree GeoJSON")
    ortho_suffix = _upload_suffix(orthophoto, GEOTIFF_SUFFIXES, "Orthophoto")
    dtm_suffix = _upload_suffix(dtm, GEOTIFF_SUFFIXES, "DTM") if dtm and dtm.filename else None
    dsm_suffix = _upload_suffix(dsm, GEOTIFF_SUFFIXES, "DSM") if dsm and dsm.filename else None

    upload_dir = ORCHARD_ASSET_DIR / orchard_uid
    upload_dir.mkdir(parents=True, exist_ok=True)

    tree_geojson_path = upload_dir / "trees.geojson"
    orthophoto_path = upload_dir / f"orthophoto{ortho_suffix}"
    orthophoto_png_path = upload_dir / "orthophoto.png"
    dtm_path = upload_dir / f"dtm{dtm_suffix}" if dtm_suffix else None
    dsm_path = upload_dir / f"dsm{dsm_suffix}" if dsm_suffix else None

    try:
        await _save_upload(tree_geojson, tree_geojson_path)
        await _save_upload(orthophoto, orthophoto_path)
        if dtm and dtm_path:
            await _save_upload(dtm, dtm_path)
        if dsm and dsm_path:
            await _save_upload(dsm, dsm_path)

        geojson = normalize_geojson_to_wgs84(_load_tree_geojson(tree_geojson_path))
        tree_geojson_path.write_text(
            json.dumps(geojson, ensure_ascii=False),
            encoding="utf-8",
        )
        overlay = _orthophoto_overlay_from_tif(orthophoto_path, orthophoto_png_path)
        centroid_lon, centroid_lat = _centroid_from_bounds(overlay["bounds"])
        tree_centroid_lon, tree_centroid_lat = derive_geojson_centroid(geojson)
        if not _point_within_bounds(tree_centroid_lon, tree_centroid_lat, overlay["bounds"]):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Tree GeoJSON coordinates do not appear to fall inside the "
                    "uploaded orthophoto bounds. Check that the files belong to "
                    "the same orchard and use compatible coordinates."
                ),
            )
        auto_location = (
            f"Auto-detected at {centroid_lat:.6f}, {centroid_lon:.6f}"
            if centroid_lon is not None and centroid_lat is not None
            else None
        )

        orchard = Orchard(
            orchard_uid=orchard_uid,
            name=clean_name,
            owner_name=owner_name.strip() if owner_name else None,
            location=auto_location,
            tree_count=count_geojson_trees(geojson),
            geojson=geojson,
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
            orthophoto_path=_relative_project_path(orthophoto_path),
            orthophoto_png_path=_relative_project_path(orthophoto_png_path),
            orthophoto_bounds=overlay["bounds"],
            orthophoto_coordinates=overlay["coordinates"],
            dtm_path=_relative_project_path(dtm_path) if dtm_path else None,
            dsm_path=_relative_project_path(dsm_path) if dsm_path else None,
            description="Created from dashboard file upload.",
            is_active=True,
            monitoring_enabled=True,
            orchard_stage=stage,
            days_since_flowering=flowering_days,
            monitored_pest_types=["cecid", "fruitfly"],
        )
        db.add(orchard)
        await db.flush()

        logger.info("Uploaded orchard %s (%s)", orchard.name, orchard.orchard_uid)
        return orchard_to_response(orchard)
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Orchard already exists.") from exc
    except Exception as exc:
        await db.rollback()
        if is_database_unavailable(exc):
            raise database_unavailable_http_exception() from exc
        logger.error("Failed to upload orchard: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to upload orchard files.") from exc


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
    "/{orchard_id}/assets/orthophoto.png",
    summary="Get orchard orthophoto overlay",
    description="Return the web-optimized PNG overlay generated from the uploaded orthophoto GeoTIFF.",
)
async def get_orchard_orthophoto(
    orchard_id: str,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Serve the selected orchard's generated orthophoto PNG."""
    orchard = await _get_orchard_or_404(db, orchard_id)
    png_path = _safe_project_path(orchard.orthophoto_png_path)
    if not png_path or not png_path.exists():
        raise HTTPException(status_code=404, detail="Orthophoto asset not found.")
    return FileResponse(
        path=png_path,
        media_type="image/png",
        filename=f"{orchard.orchard_uid or orchard.orchard_id}-orthophoto.png",
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
