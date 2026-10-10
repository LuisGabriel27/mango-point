import math
from collections import deque

import numpy as np
import pytest

from core.biological_rules import CecidFlyGate, FruitFlyGate
from core.config import CellState, OrchardStage
from core.grid import OrchardGrid
from core.tree_graph_model import TreeGraph, TreeNode, crown_spread_prob


# GIS grid rows increase latitude, and columns increase longitude.
# Each tuple gives the wind-FROM bearing and the row/column offset DOWNWIND.
DOWNWIND_OFFSETS = [
    (0.0, -1, 0),       # from north -> south
    (45.0, -1, -1),     # from northeast -> southwest
    (90.0, 0, -1),      # from east -> west
    (135.0, 1, -1),     # from southeast -> northwest
    (180.0, 1, 0),      # from south -> north
    (225.0, 1, 1),      # from southwest -> northeast
    (270.0, 0, 1),      # from west -> east
    (315.0, -1, 1),     # from northwest -> southeast
    (360.0, -1, 0),     # 360 and 0 both mean from north
]


def _grid_with_compass_targets() -> OrchardGrid:
    grid = OrchardGrid(rows=3, cols=3, cell_size_m=5.0)
    grid.plant_trees(np.ones((3, 3), dtype=bool), CellState.UNBAGGED)
    grid.infest(1, 1)
    return grid


@pytest.mark.parametrize("wind_from,dr,dc", DOWNWIND_OFFSETS)
@pytest.mark.parametrize("spread_path", ["source", "target"])
def test_grid_fruit_fly_spreads_downwind_in_geographic_coordinates(wind_from, dr, dc, spread_path):
    grid = _grid_with_compass_targets()
    gate = FruitFlyGate(wind_boost=0.20)
    weather = dict(wind_speed_ms=1.0, wind_dir_deg=wind_from, temperature_c=30.0, sugar_index=0.5)

    if spread_path == "source":
        gate._spread_from(grid, src_r=1, src_c=1, **weather)
    else:
        for row, col in zip(*np.where(grid.susceptible_mask)):
            gate._spread_to(grid, target_r=row, target_c=col, **weather)

    # All eight targets have the same Chebyshev distance. Only the target
    # toward which the wind blows should receive the full wind boost.
    downwind = grid.risk[1 + dr, 1 + dc]
    for row, col in zip(*np.where(grid.susceptible_mask)):
        if (row, col) != (1 + dr, 1 + dc):
            assert downwind > grid.risk[row, col]


@pytest.mark.parametrize("wind_from,dr,dc", DOWNWIND_OFFSETS)
def test_grid_cecid_spreads_downwind_in_geographic_coordinates(wind_from, dr, dc):
    grid = _grid_with_compass_targets()
    gate = CecidFlyGate()
    gate.current_hour = 18
    gate._spread_from(
        grid, src_r=1, src_c=1, wind_speed_ms=2.0, wind_dir_deg=wind_from,
        temperature_c=28.0, rainfall_history=deque([0.0] * 68 + [2.0] * 4),
        orchard_stage=OrchardStage.FRUITLET,
    )

    # Compare equal physical distances, including diagonals, so distance
    # attenuation cannot hide an inverted wind bearing.
    downwind = grid.risk[1 + dr, 1 + dc]
    upwind = grid.risk[1 - dr, 1 - dc]
    crosswind = grid.risk[1 + dc, 1 - dr]
    assert downwind > crosswind > upwind


@pytest.mark.parametrize("wind_from,dr,dc", DOWNWIND_OFFSETS)
def test_tree_graph_spreads_downwind_in_geographic_coordinates(wind_from, dr, dc):
    offsets = [(0, 0), (dr, dc), (-dr, -dc), (dc, -dr)]
    nodes = [TreeNode(i, str(i), 122.58 + col * 0.00005, 10.585 + row * 0.00005,
                      col * 5.0, row * 5.0, 2.5)
             for i, (row, col) in enumerate(offsets)]
    graph = TreeGraph(nodes, max_dist=20.0)
    probabilities = {edge.dst: crown_spread_prob(edge, math.radians(wind_from), wind_bias=0.35)
                     for edge in graph.neighbours(0)}

    assert probabilities[1] > probabilities[3] > probabilities[2]
