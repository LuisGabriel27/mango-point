"""Combine external orchard sources without losing their individual wind bearings."""

import math
import numpy as np

from core.config import DIRECTION_BEARING_MAP, WIND_NEIGHBOR_BOOST


def resolve_neighbor_sources(sources, threat=0.0, direction=None):
    """An explicit list replaces legacy inputs; an empty list disables pressure."""
    if sources is None:
        return [{"direction": direction, "threat": float(threat), "label": None}] if threat > 0 else []
    return [
        source.model_dump(mode="json") if hasattr(source, "model_dump") else dict(source)
        for source in sources
    ]


def combine_neighbor_pressure(components, wind_dir_deg=None):
    """Cap summed local pressure at one, then apply its pressure-weighted wind factor.

    Each component is (source, spatial pressure array). This preserves the
    single-source equation and keeps opposite neighbors from sharing a bearing.
    """
    if not components:
        return 0.0
    total = np.zeros_like(components[0][1], dtype=float)
    weighted = np.zeros_like(total)
    for source, pressure in components:
        total += pressure
        direction = source.get("direction")
        factor = 1.0
        if wind_dir_deg is not None and direction:
            bearing = DIRECTION_BEARING_MAP[direction.upper()]
            factor += WIND_NEIGHBOR_BOOST * math.cos(math.radians(wind_dir_deg - bearing))
        weighted += pressure * max(0.0, min(2.0, factor))
    if wind_dir_deg is None:
        return np.minimum(total, 1.0)
    factor = np.divide(weighted, total, out=np.ones_like(total), where=total > 0)
    return np.minimum(total, 1.0) * factor
