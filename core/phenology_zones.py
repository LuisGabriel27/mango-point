"""
MangoPoint — Per-tree / per-cell phenological stage assignment
==============================================================
Replaces the single-orchard-stage model with a quadrant-first mixed-phenology
assignment. An orchard is split into 4 quadrants (NW/NE/SW/SE) of its bounding
box; each quadrant carries a dominant stage. Within a quadrant, individual
trees are assigned:

  - the dominant stage               with probability 0.7
  - one of the two adjacent stages   with probability 0.2 (split 0.1 / 0.1)
  - the opposite stage in the cycle  with probability 0.1

This gives the donut chart a realistic mix (not 100% one slice) while keeping
spatial identifiability — users can still say "the NW block is flowering."

The phenological cycle is ordered: DORMANT → FLOWERING → FRUITLET → MATURE
(then wraps back to DORMANT). "Adjacent" = ±1 step; "opposite" = +2 steps.

Public API:
  assign_stage_with_mix()         — pick one stage for one tree
  bbox_quadrant()                 — map a (lon, lat) to a quadrant label
  assign_stages_for_points()      — per-tree list for tree_graph mode
  assign_stages_for_grid()        — (rows, cols) np.ndarray for grid mode
  stage_breakdown()               — count trees per stage for the donut
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from core.config import OrchardStage


# Ordered cycle — index arithmetic is used to find adjacent / opposite stages.
_STAGE_CYCLE: Tuple[OrchardStage, ...] = (
    OrchardStage.DORMANT,
    OrchardStage.FLOWERING,
    OrchardStage.FRUITLET,
    OrchardStage.MATURE,
)

_STAGE_NAME_BY_INT: Dict[int, str] = {
    int(OrchardStage.DORMANT):   "dormant",
    int(OrchardStage.FLOWERING): "flowering",
    int(OrchardStage.FRUITLET):  "fruitlet",
    int(OrchardStage.MATURE):    "mature",
}

_STAGE_BY_NAME: Dict[str, OrchardStage] = {
    "dormant":   OrchardStage.DORMANT,
    "flowering": OrchardStage.FLOWERING,
    "fruitlet":  OrchardStage.FRUITLET,
    "mature":    OrchardStage.MATURE,
}

# Default mix profile — 70% dominant, 20% adjacent (split 10/10), 10% opposite.
DEFAULT_MIX: Tuple[float, float, float] = (0.7, 0.2, 0.1)

# Quadrant labels in fixed order.
QUADRANT_LABELS: Tuple[str, str, str, str] = ("nw", "ne", "sw", "se")


def coerce_stage(value) -> OrchardStage:
    """Accept OrchardStage, int, or case-insensitive string and return OrchardStage."""
    if isinstance(value, OrchardStage):
        return value
    if isinstance(value, int):
        return OrchardStage(value)
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _STAGE_BY_NAME:
            return _STAGE_BY_NAME[key]
    raise ValueError(f"Cannot coerce {value!r} to OrchardStage")


def _adjacent_stages(dominant: OrchardStage) -> Tuple[OrchardStage, OrchardStage]:
    """The two stages adjacent to `dominant` in the phenological cycle."""
    idx = _STAGE_CYCLE.index(dominant)
    n = len(_STAGE_CYCLE)
    return _STAGE_CYCLE[(idx - 1) % n], _STAGE_CYCLE[(idx + 1) % n]


def _opposite_stage(dominant: OrchardStage) -> OrchardStage:
    """The stage two steps away from `dominant` (e.g. DORMANT ↔ FRUITLET)."""
    idx = _STAGE_CYCLE.index(dominant)
    return _STAGE_CYCLE[(idx + 2) % len(_STAGE_CYCLE)]


def assign_stage_with_mix(
    dominant: OrchardStage,
    rng: np.random.Generator,
    mix: Tuple[float, float, float] = DEFAULT_MIX,
) -> OrchardStage:
    """
    Pick a stage for one tree given its quadrant's dominant stage and the mix.

    Parameters
    ----------
    dominant
        The quadrant's dominant stage.
    rng
        Seeded numpy Generator — pass the same generator to get reproducible runs.
    mix
        (p_dominant, p_adjacent, p_opposite) summing to 1.0.

    Returns
    -------
    OrchardStage
    """
    p_dom, p_adj, _p_opp = mix  # p_opp implied by remainder
    r = float(rng.random())
    if r < p_dom:
        return dominant
    if r < p_dom + p_adj:
        adj_left, adj_right = _adjacent_stages(dominant)
        return adj_left if rng.random() < 0.5 else adj_right
    return _opposite_stage(dominant)


def bbox_quadrant(
    lon: float,
    lat: float,
    bbox: Tuple[float, float, float, float],
) -> str:
    """
    Map a (lon, lat) point to one of 'nw', 'ne', 'sw', 'se' within `bbox`.

    `bbox` = (min_lon, min_lat, max_lon, max_lat). Points exactly on the midline
    fall into the southern / western quadrants (deterministic tie-break).
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    mid_lon = (min_lon + max_lon) / 2.0
    mid_lat = (min_lat + max_lat) / 2.0
    east = lon > mid_lon
    north = lat > mid_lat
    if north and not east:
        return "nw"
    if north and east:
        return "ne"
    if (not north) and (not east):
        return "sw"
    return "se"


def _normalize_quadrant_map(
    quadrant_stages: Dict[str, object],
    fallback: OrchardStage,
) -> Dict[str, OrchardStage]:
    """Coerce a user-supplied quadrant dict to OrchardStage enum, filling gaps with fallback."""
    out: Dict[str, OrchardStage] = {}
    for label in QUADRANT_LABELS:
        raw = quadrant_stages.get(label) if quadrant_stages else None
        out[label] = coerce_stage(raw) if raw is not None else fallback
    return out


def assign_stages_for_points(
    tree_coords: Sequence[Tuple[float, float]],
    quadrant_stages: Dict[str, object],
    bbox: Optional[Tuple[float, float, float, float]] = None,
    seed: int = 0,
    mix: Tuple[float, float, float] = DEFAULT_MIX,
    fallback: OrchardStage = OrchardStage.MATURE,
) -> List[OrchardStage]:
    """
    Build a per-tree stage list from tree lon/lat coords and a quadrant → stage map.

    If `bbox` is None, it is derived from `tree_coords`.
    Stage assignment is reproducible given the same seed and tree order.
    """
    if not tree_coords:
        return []
    if bbox is None:
        lons = [c[0] for c in tree_coords]
        lats = [c[1] for c in tree_coords]
        bbox = (min(lons), min(lats), max(lons), max(lats))

    resolved = _normalize_quadrant_map(quadrant_stages, fallback)
    rng = np.random.default_rng(seed)

    stages: List[OrchardStage] = []
    for lon, lat in tree_coords:
        q = bbox_quadrant(lon, lat, bbox)
        stages.append(assign_stage_with_mix(resolved[q], rng, mix))
    return stages


def assign_stages_for_grid(
    rows: int,
    cols: int,
    quadrant_stages: Dict[str, object],
    seed: int = 0,
    mix: Tuple[float, float, float] = DEFAULT_MIX,
    fallback: OrchardStage = OrchardStage.MATURE,
) -> np.ndarray:
    """
    Build a (rows, cols) np.ndarray[int] carrying a stage for each grid cell.

    Quadrants map onto grid coordinates as: row 0 is the southern row (lat = origin_lat),
    so rows ≥ rows/2 are 'northern' and cols ≥ cols/2 are 'eastern'.
    """
    resolved = _normalize_quadrant_map(quadrant_stages, fallback)
    rng = np.random.default_rng(seed)

    stage_grid = np.full((rows, cols), int(fallback), dtype=np.int32)
    mid_r = rows / 2.0
    mid_c = cols / 2.0
    for r in range(rows):
        north = r >= mid_r
        for c in range(cols):
            east = c >= mid_c
            if north and not east:
                q = "nw"
            elif north and east:
                q = "ne"
            elif (not north) and (not east):
                q = "sw"
            else:
                q = "se"
            stage_grid[r, c] = int(assign_stage_with_mix(resolved[q], rng, mix))
    return stage_grid


def uniform_stage_grid(rows: int, cols: int, stage: OrchardStage) -> np.ndarray:
    """Build a (rows, cols) stage_grid where every cell carries the same stage."""
    return np.full((rows, cols), int(stage), dtype=np.int32)


def stage_breakdown(stages: Sequence[object]) -> Dict[str, int]:
    """Count per-stage from a sequence of OrchardStage (or int) values.

    Returns a dict with all four stage keys present (zeros included) so the
    phenology donut keeps a consistent legend.
    """
    counts: Dict[str, int] = {name: 0 for name in _STAGE_BY_NAME.keys()}
    for s in stages:
        key = _STAGE_NAME_BY_INT.get(int(s), "mature")
        counts[key] += 1
    return counts


def stage_breakdown_from_grid(
    stage_grid: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> Dict[str, int]:
    """Count per-stage over a stage_grid, optionally restricted to `mask == True`.

    `mask` should be the set of cells representing real trees (e.g. grid.state != EMPTY).
    """
    counts: Dict[str, int] = {name: 0 for name in _STAGE_BY_NAME.keys()}
    if mask is None:
        flat = stage_grid.ravel()
    else:
        flat = stage_grid[mask]
    values, vcounts = np.unique(flat, return_counts=True)
    for v, c in zip(values.tolist(), vcounts.tolist()):
        key = _STAGE_NAME_BY_INT.get(int(v))
        if key is not None:
            counts[key] = int(c)
    return counts


__all__ = [
    "DEFAULT_MIX",
    "QUADRANT_LABELS",
    "coerce_stage",
    "assign_stage_with_mix",
    "bbox_quadrant",
    "assign_stages_for_points",
    "assign_stages_for_grid",
    "uniform_stage_grid",
    "stage_breakdown",
    "stage_breakdown_from_grid",
]
