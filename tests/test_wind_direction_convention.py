import numpy as np

from core.biological_rules import FruitFlyGate
from core.config import CellState
from core.grid import OrchardGrid


def _grid_with_cardinal_targets() -> OrchardGrid:
    grid = OrchardGrid(rows=5, cols=5, cell_size_m=1.0)
    mask = np.zeros((5, 5), dtype=bool)
    mask[2, 2] = True  # source
    mask[1, 2] = True  # north
    mask[2, 3] = True  # east
    mask[3, 2] = True  # south
    mask[2, 1] = True  # west
    grid.plant_trees(mask, CellState.UNBAGGED)
    grid.infest(2, 2)
    return grid


def test_ca_fruit_fly_wind_from_north_boosts_southward_spread():
    grid = _grid_with_cardinal_targets()

    FruitFlyGate(wind_boost=0.20)._spread_from(
        grid,
        src_r=2,
        src_c=2,
        wind_speed_ms=1.0,
        wind_dir_deg=0.0,  # wind FROM north, blowing south
        temperature_c=30.0,
        sugar_index=0.5,
    )

    assert grid.risk[3, 2] > grid.risk[1, 2]
    assert grid.risk[3, 2] > grid.risk[2, 1]
    assert grid.risk[3, 2] > grid.risk[2, 3]


def test_ca_fruit_fly_wind_from_east_boosts_westward_spread():
    grid = _grid_with_cardinal_targets()

    FruitFlyGate(wind_boost=0.20)._spread_from(
        grid,
        src_r=2,
        src_c=2,
        wind_speed_ms=1.0,
        wind_dir_deg=90.0,  # wind FROM east, blowing west
        temperature_c=30.0,
        sugar_index=0.5,
    )

    assert grid.risk[2, 1] > grid.risk[2, 3]
    assert grid.risk[2, 1] > grid.risk[1, 2]
    assert grid.risk[2, 1] > grid.risk[3, 2]
