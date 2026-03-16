"""
MangoPoint — GIS Utilities
===========================
Convert GIS vector data (GeoJSON / Shapefile) into the simulation grid.

Workflow
--------
1. Load farm boundary polygon  →  compute bounding box
2. Create OrchardGrid aligned to that bounding box
3. Load tree point data  →  map each point to (row, col)
4. Optionally: rasterise polygon to mark cells inside the farm

Supported inputs
    • GeoJSON  (.geojson)
    • Shapefile (.shp) via geopandas
    • Manual coordinate lists
"""

from __future__ import annotations

import numpy as np
import geopandas as gpd
from shapely.geometry import Point, Polygon, box, mapping
from typing import Optional, Tuple, List

from core.config import CELL_SIZE_M, CellState
from core.grid import OrchardGrid


# ─────────────────────────────────────────────
#  Coordinate ↔ Grid Index conversion
# ─────────────────────────────────────────────
def _metres_per_degree(lat: float) -> Tuple[float, float]:
    """Approximate metres per degree at given latitude."""
    m_lat = 111_132.0
    m_lon = 111_132.0 * np.cos(np.radians(lat))
    return m_lat, m_lon


def lonlat_to_grid(
    lon: float,
    lat: float,
    origin_lon: float,
    origin_lat: float,
    cell_size_m: float,
    m_lat: float,
    m_lon: float,
) -> Tuple[int, int]:
    """Convert (lon, lat) to (row, col) in the grid."""
    col = int(np.floor((lon - origin_lon) * m_lon / cell_size_m))
    row = int(np.floor((lat - origin_lat) * m_lat / cell_size_m))
    return row, col


def grid_to_lonlat(
    row: int,
    col: int,
    origin_lon: float,
    origin_lat: float,
    cell_size_m: float,
    m_lat: float,
    m_lon: float,
) -> Tuple[float, float]:
    """Convert grid (row, col) to centre (lon, lat)."""
    lon = origin_lon + (col + 0.5) * cell_size_m / m_lon
    lat = origin_lat + (row + 0.5) * cell_size_m / m_lat
    return lon, lat


# ─────────────────────────────────────────────
#  Build grid from farm boundary
# ─────────────────────────────────────────────
def grid_from_boundary(
    boundary_gdf: gpd.GeoDataFrame,
    cell_size_m: float = CELL_SIZE_M,
    buffer_cells: int = 2,
) -> OrchardGrid:
    """
    Create an OrchardGrid whose extent covers the farm boundary polygon,
    with an optional buffer of extra cells around the edge.
    """
    boundary_gdf = boundary_gdf.to_crs(epsg=4326)
    bounds = boundary_gdf.total_bounds  # (minx, miny, maxx, maxy)
    origin_lon, origin_lat = bounds[0], bounds[1]
    max_lon, max_lat = bounds[2], bounds[3]

    m_lat, m_lon = _metres_per_degree((origin_lat + max_lat) / 2)

    cols = int(np.ceil((max_lon - origin_lon) * m_lon / cell_size_m)) + 2 * buffer_cells
    rows = int(np.ceil((max_lat - origin_lat) * m_lat / cell_size_m)) + 2 * buffer_cells

    # Shift origin to account for buffer
    origin_lon -= buffer_cells * cell_size_m / m_lon
    origin_lat -= buffer_cells * cell_size_m / m_lat

    grid = OrchardGrid(rows, cols, cell_size_m)
    grid.origin_lon = origin_lon
    grid.origin_lat = origin_lat
    return grid


# ─────────────────────────────────────────────
#  Rasterise farm boundary → mark cells inside
# ─────────────────────────────────────────────
def rasterise_boundary(
    grid: OrchardGrid,
    boundary_gdf: gpd.GeoDataFrame,
    state: CellState = CellState.UNBAGGED,
) -> None:
    """
    For each grid cell whose centroid falls inside the farm boundary,
    set its state to *state* (default: UNBAGGED = tree present).
    """
    boundary_gdf = boundary_gdf.to_crs(epsg=4326)
    farm_poly = boundary_gdf.union_all()

    m_lat, m_lon = _metres_per_degree(grid.origin_lat + grid.rows * grid.cell_size_m / 111_132 / 2)

    for r in range(grid.rows):
        for c in range(grid.cols):
            lon, lat = grid_to_lonlat(
                r, c, grid.origin_lon, grid.origin_lat,
                grid.cell_size_m, m_lat, m_lon,
            )
            if farm_poly.contains(Point(lon, lat)):
                grid.set_state(r, c, state)


# ─────────────────────────────────────────────
#  Plant trees from point GeoDataFrame
# ─────────────────────────────────────────────
def plant_trees_from_points(
    grid: OrchardGrid,
    points_gdf: gpd.GeoDataFrame,
    state: CellState = CellState.UNBAGGED,
    id_column: Optional[str] = None,
) -> int:
    """
    Map each point feature to a grid cell and set it to *state*.
    Returns the number of trees successfully placed.
    """
    points_gdf = points_gdf.to_crs(epsg=4326)
    m_lat, m_lon = _metres_per_degree(grid.origin_lat + grid.rows * grid.cell_size_m / 111_132 / 2)
    n_placed = 0

    for idx, row in points_gdf.iterrows():
        lon, lat = row.geometry.x, row.geometry.y
        r, c = lonlat_to_grid(
            lon, lat, grid.origin_lon, grid.origin_lat,
            grid.cell_size_m, m_lat, m_lon,
        )
        if 0 <= r < grid.rows and 0 <= c < grid.cols:
            grid.set_state(r, c, state)
            if id_column and id_column in row.index:
                grid.tree_ids[r, c] = str(row[id_column])
            n_placed += 1

    return n_placed


# ─────────────────────────────────────────────
#  Create sample GeoJSON for demo
# ─────────────────────────────────────────────
def create_sample_orchard_geojson(filepath: str) -> gpd.GeoDataFrame:
    """
    Generate a sample Guimaras mango orchard GeoJSON polygon
    (≈ 600 m × 600 m rectangular area on the island).
    """
    # Centro, Jordan, Guimaras approximate coords
    lon_c, lat_c = 122.4026, 10.7915
    half_w = 0.002   # ≈ 220 m
    half_h = 0.002   # ≈ 220 m

    farm_poly = Polygon([
        (lon_c - half_w, lat_c - half_h),
        (lon_c + half_w, lat_c - half_h),
        (lon_c + half_w, lat_c + half_h),
        (lon_c - half_w, lat_c + half_h),
    ])

    gdf = gpd.GeoDataFrame(
        {"name": ["Sample Mango Farm"], "area_ha": [3.6]},
        geometry=[farm_poly],
        crs="EPSG:4326",
    )
    gdf.to_file(filepath, driver="GeoJSON")
    return gdf


def create_sample_tree_points(
    boundary_gdf: gpd.GeoDataFrame,
    spacing_m: float = 20.0,
    filepath: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """
    Generate a regular grid of tree points within the farm boundary.
    """
    boundary_gdf = boundary_gdf.to_crs(epsg=4326)
    bounds = boundary_gdf.total_bounds
    farm_poly = boundary_gdf.union_all()

    lat_mid = (bounds[1] + bounds[3]) / 2
    m_lat, m_lon = _metres_per_degree(lat_mid)

    lon_step = spacing_m / m_lon
    lat_step = spacing_m / m_lat

    points = []
    ids = []
    tree_id = 1
    lon = bounds[0]
    while lon < bounds[2]:
        lat = bounds[1]
        while lat < bounds[3]:
            pt = Point(lon, lat)
            if farm_poly.contains(pt):
                points.append(pt)
                ids.append(f"T{tree_id:04d}")
                tree_id += 1
            lat += lat_step
        lon += lon_step

    gdf = gpd.GeoDataFrame(
        {"tree_id": ids},
        geometry=points,
        crs="EPSG:4326",
    )
    if filepath:
        gdf.to_file(filepath, driver="GeoJSON")
    return gdf
