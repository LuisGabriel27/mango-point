"""
MangoPoint — Raster Utilities
==============================
Load drone orthophoto / DTM GeoTIFFs and convert them to base64 PNG
images with geographic bounds, suitable for overlay on Plotly Mapbox
or Leaflet maps.

Requires: rasterio, Pillow (PIL)
"""

from __future__ import annotations

import base64
import importlib.util
import io
import os
from pathlib import Path
from typing import Tuple, Optional, Dict

import numpy as np

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import rasterio
    import rasterio.enums
    from rasterio.warp import transform_bounds
    from PIL import Image

_HAS_RASTERIO = False
_HAS_PIL = False


def _prefer_python_proj_data() -> None:
    """
    Keep rasterio from using PostGIS' bundled PROJ database on Windows.

    PostgreSQL/PostGIS installers commonly set PROJ_LIB to a PostGIS folder.
    Rasterio/GDAL can then fail with "DATABASE.LAYOUT.VERSION" errors because
    that proj.db is older than the one expected by Python's geospatial wheels.
    """
    data_dir: Optional[Path] = None

    rasterio_spec = importlib.util.find_spec("rasterio")
    if rasterio_spec and rasterio_spec.origin:
        candidate = Path(rasterio_spec.origin).resolve().parent / "proj_data"
        if (candidate / "proj.db").exists():
            data_dir = candidate

    if data_dir is None:
        try:
            from pyproj import datadir
        except ImportError:
            return
        pyproj_data = datadir.get_data_dir()
        if pyproj_data:
            data_dir = Path(pyproj_data)

    if data_dir is None:
        return

    os.environ["PROJ_LIB"] = str(data_dir)
    os.environ["PROJ_DATA"] = str(data_dir)


def prefer_python_proj_data() -> None:
    """Prefer the projection database bundled with Python geospatial wheels."""
    _prefer_python_proj_data()


try:
    prefer_python_proj_data()
    import rasterio as rasterio  # noqa: F811
    import rasterio.enums  # noqa: F811
    import rasterio._env as rasterio_env  # noqa: F811
    from rasterio.warp import transform_bounds  # noqa: F811
    proj_data = os.environ.get("PROJ_DATA")
    if proj_data:
        rasterio_env.set_proj_data_search_path(proj_data)
    _HAS_RASTERIO = True
except ImportError:
    pass

try:
    from PIL import Image  # noqa: F811
    _HAS_PIL = True
except ImportError:
    pass


def _ensure_deps():
    if not _HAS_RASTERIO:
        raise ImportError("rasterio is required  →  pip install rasterio")
    if not _HAS_PIL:
        raise ImportError("Pillow is required  →  pip install Pillow")


# ─────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────

def _normalize_color_bands(data: np.ndarray) -> np.ndarray:
    """Normalize raster color bands to uint8 without treating alpha as color."""
    if data.dtype == np.uint8:
        return data.astype(np.uint8, copy=False)

    out = np.zeros_like(data, dtype=np.uint8)
    for i in range(data.shape[0]):
        band = data[i].astype(np.float64)
        valid = band[np.isfinite(band) & (band != 0)]
        if valid.size > 0:
            lo, hi = np.percentile(valid, [2, 98])
        else:
            lo, hi = 0.0, 1.0
        if hi <= lo:
            hi = lo + 1
        scaled = (band - lo) / (hi - lo) * 255
        scaled = np.nan_to_num(scaled, nan=0.0, posinf=255.0, neginf=0.0)
        out[i] = np.clip(scaled, 0, 255).astype(np.uint8)
    return out


def _alpha_to_uint8(alpha: np.ndarray) -> np.ndarray:
    """Convert a raster alpha band to uint8 while preserving constant opacity."""
    if alpha.dtype == np.uint8:
        return alpha.astype(np.uint8, copy=False)

    band = alpha.astype(np.float64)
    band = np.nan_to_num(band, nan=0.0, posinf=0.0, neginf=0.0)
    max_value = float(np.max(band)) if band.size else 0.0
    if max_value <= 0:
        scaled = band
    elif max_value <= 1.0:
        scaled = band * 255.0
    elif max_value > 255.0:
        scaled = band / max_value * 255.0
    else:
        scaled = band
    return np.clip(scaled, 0, 255).astype(np.uint8)


def _repair_empty_alpha(arr: np.ndarray) -> np.ndarray:
    """Replace broken all-transparent alpha with an RGB-derived mask."""
    if arr.ndim != 3 or arr.shape[2] < 4:
        return arr
    if int(np.max(arr[:, :, 3])) != 0:
        return arr

    visible = np.any(arr[:, :, :3] > 0, axis=2)
    if not np.any(visible):
        return arr

    repaired = arr.copy()
    repaired[:, :, 3] = np.where(visible, 255, 0).astype(np.uint8)
    return repaired


def load_raster_as_png_b64(
    tif_path: str | Path,
    max_pixels: int = 2048,
    bands: Optional[Tuple[int, ...]] = None,
) -> Dict:
    """
    Read a GeoTIFF and return a dict with:

      - ``b64``         : data-URI string (``data:image/png;base64,…``)
      - ``bounds``      : ``[west, south, east, north]`` in EPSG 4326
      - ``coordinates`` : corner list for Plotly mapbox image layer
                          ``[[W,N], [E,N], [E,S], [W,S]]``
      - ``width``       : pixel width of the output PNG
      - ``height``      : pixel height of the output PNG

    Parameters
    ----------
    tif_path : path
        Path to a single- or multi-band GeoTIFF.
    max_pixels : int
        Longest edge of the output PNG (down-sampled for performance).
    bands : tuple of int, optional
        1-based band indices to read.  ``None`` → auto-detect
        (RGB if ≥3 bands, greyscale if 1 band).
    """
    _ensure_deps()
    tif_path = Path(tif_path)

    with rasterio.open(tif_path) as src:
        # --- determine bands to read ---------------------------------
        n_bands = src.count
        if bands is None:
            if n_bands >= 4:
                bands = (1, 2, 3, 4)   # keep alpha for transparency
            elif n_bands >= 3:
                bands = (1, 2, 3)
            else:
                bands = (1,)

        # --- compute downscale factor --------------------------------
        h, w = src.height, src.width
        scale = min(max_pixels / max(h, w), 1.0)
        out_h = max(1, int(h * scale))
        out_w = max(1, int(w * scale))

        # --- read + resample ----------------------------------------
        data = src.read(
            bands,
            out_shape=(len(bands), out_h, out_w),
            resampling=rasterio.enums.Resampling.bilinear,
        )

        # --- geographic bounds in WGS-84 -----------------------------
        src_crs = src.crs
        if src_crs and str(src_crs) != "EPSG:4326":
            west, south, east, north = transform_bounds(
                src_crs, "EPSG:4326",
                *src.bounds,
            )
        else:
            west, south, east, north = src.bounds

    # --- convert to uint8 RGB(A) image --------------------------------
    if data.shape[0] >= 4:
        color_data = _normalize_color_bands(data[:3])
        alpha_data = _alpha_to_uint8(data[3])
        data = np.concatenate([color_data, alpha_data[np.newaxis, :, :]], axis=0)
    else:
        data = _normalize_color_bands(data)

    if data.shape[0] == 1:
        # greyscale → RGB
        arr = np.stack([data[0], data[0], data[0]], axis=-1).astype(np.uint8)
    elif data.shape[0] == 3:
        arr = np.moveaxis(data, 0, -1)  # (3,H,W) → (H,W,3)
    elif data.shape[0] >= 4:
        arr = np.moveaxis(data[:4], 0, -1)  # keep RGBA
    else:
        arr = np.moveaxis(data, 0, -1)
    arr = _repair_empty_alpha(arr)

    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64_str = base64.b64encode(buf.getvalue()).decode("ascii")

    coordinates = [
        [west, north],  # top-left
        [east, north],  # top-right
        [east, south],  # bottom-right
        [west, south],  # bottom-left
    ]

    return {
        "b64": f"data:image/png;base64,{b64_str}",
        "bounds": [west, south, east, north],
        "coordinates": coordinates,
        "width": out_w,
        "height": out_h,
    }


def get_raster_bounds(tif_path: str | Path) -> Tuple[float, float, float, float]:
    """Return (west, south, east, north) in EPSG 4326."""
    _ensure_deps()
    with rasterio.open(tif_path) as src:
        if src.crs and str(src.crs) != "EPSG:4326":
            return transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        return src.bounds
