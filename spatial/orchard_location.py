"""
MangoPoint — Orchard Location Helpers
=====================================
Centralised helpers that derive the orchard's latitude/longitude from the
orthophoto raster in ``data/``. If the raster is missing or rasterio is
unavailable, the helpers fall back to the historical Guimaras coordinates.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Tuple

from spatial.raster_utils import get_raster_bounds

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"


def _resolve_map_tif() -> Path:
    for name in ("bpi_map.tif", "Map.tif"):
        candidate = _DATA_DIR / name
        if candidate.exists():
            return candidate
    return _DATA_DIR / "bpi_map.tif"


_MAP_TIF = _resolve_map_tif()

# Historical defaults (Centro, Jordan, Guimaras) used as fallback.
FALLBACK_LAT = 10.7915
FALLBACK_LON = 122.4026


@lru_cache(maxsize=1)
def _load_bounds() -> Tuple[float, float, float, float]:
    """Load orchard bounds from the orthophoto GeoTIFF."""
    if not _MAP_TIF.exists():
        raise FileNotFoundError(f"Orchard raster not found: {_MAP_TIF}")
    return get_raster_bounds(_MAP_TIF)


def get_orchard_bounds() -> Tuple[float, float, float, float]:
    """Return (west, south, east, north) bounds in EPSG:4326."""
    try:
        return _load_bounds()
    except Exception as exc:  # pragma: no cover - fallback path
        logger.info("Using fallback orchard bounds: %s", exc)
        return (
            FALLBACK_LON - 0.002,
            FALLBACK_LAT - 0.002,
            FALLBACK_LON + 0.002,
            FALLBACK_LAT + 0.002,
        )


def get_orchard_location() -> Tuple[float, float]:
    """Return the orchard centroid (lat, lon), falling back if needed."""
    try:
        west, south, east, north = _load_bounds()
        lat = (south + north) / 2.0
        lon = (west + east) / 2.0
        return lat, lon
    except Exception as exc:  # pragma: no cover - fallback path
        logger.info(
            "Using fallback orchard coordinates (%.4f, %.4f): %s",
            FALLBACK_LAT,
            FALLBACK_LON,
            exc,
        )
        return FALLBACK_LAT, FALLBACK_LON


ORCHARD_LAT, ORCHARD_LON = get_orchard_location()
ORCHARD_BOUNDS = get_orchard_bounds()

# Backwards-compatible aliases (mirroring earlier constants)
DEFAULT_LAT = ORCHARD_LAT
DEFAULT_LON = ORCHARD_LON
