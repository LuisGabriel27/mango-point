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
import io
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

try:
    import rasterio as rasterio  # noqa: F811
    import rasterio.enums  # noqa: F811
    from rasterio.warp import transform_bounds  # noqa: F811
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
    if data.dtype != np.uint8:
        # normalise each band to 0-255 as float64 first, then cast
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
        data = out

    if data.shape[0] == 1:
        # greyscale → RGB
        arr = np.stack([data[0], data[0], data[0]], axis=-1).astype(np.uint8)
    elif data.shape[0] == 3:
        arr = np.moveaxis(data, 0, -1)  # (3,H,W) → (H,W,3)
    elif data.shape[0] >= 4:
        arr = np.moveaxis(data[:4], 0, -1)  # keep RGBA
    else:
        arr = np.moveaxis(data, 0, -1)

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
