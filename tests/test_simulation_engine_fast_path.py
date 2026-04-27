import numpy as np

from core.biological_rules import FruitFlyGate
from core.config import CellState, OrchardStage
from core.grid import OrchardGrid
from core.simulation_engine import SimulationEngine
from utils.weather import WeatherTimeSeries


def _seeded_grid(rows=6, cols=6):
    grid = OrchardGrid(rows=rows, cols=cols)
    grid.plant_trees(np.ones((rows, cols), dtype=bool), CellState.UNBAGGED)
    grid.seed_infestation([(rows // 2, cols // 2)])
    return grid


def _weather(hours=12):
    return WeatherTimeSeries.synthetic(hours=hours, seed=7)


def test_run_final_state_matches_recorded_run_final_grid():
    grid = _seeded_grid()
    weather = _weather()
    seed = 2026

    np.random.seed(seed)
    recorded = SimulationEngine(
        grid,
        weather,
        gates=[FruitFlyGate()],
        orchard_stage=OrchardStage.MATURE,
        days_since_flowering=75,
    ).run(n_steps=12, progress=False)

    np.random.seed(seed)
    final_grid = SimulationEngine(
        grid,
        weather,
        gates=[FruitFlyGate()],
        orchard_stage=OrchardStage.MATURE,
        days_since_flowering=75,
    ).run_final_state(n_steps=12)

    np.testing.assert_array_equal(final_grid.state, recorded.grid.state)


def test_monte_carlo_matches_recorded_run_ensemble():
    grid = _seeded_grid()
    weather = _weather()
    n_runs = 4
    n_steps = 12
    seed = 99

    expected = np.zeros((grid.rows, grid.cols), dtype=float)
    for run_i in range(n_runs):
        np.random.seed(seed + run_i)
        recorded = SimulationEngine(
            grid,
            weather,
            transition_mode="stochastic",
            gates=[FruitFlyGate()],
            orchard_stage=OrchardStage.MATURE,
            days_since_flowering=75,
        ).run(n_steps=n_steps, progress=False)
        expected += (recorded.grid.state == CellState.INFESTED).astype(float)
    expected /= n_runs

    actual = SimulationEngine.monte_carlo(
        grid=grid,
        weather=weather,
        n_runs=n_runs,
        n_steps=n_steps,
        seed=seed,
        gates=[FruitFlyGate()],
        orchard_stage=OrchardStage.MATURE,
        days_since_flowering=75,
        progress=False,
    )

    np.testing.assert_array_equal(actual, expected)


def test_fruit_fly_target_side_spread_matches_source_side_spread():
    gate = FruitFlyGate()
    grid = OrchardGrid(rows=6, cols=6)
    grid.plant_trees(np.ones((6, 6), dtype=bool), CellState.UNBAGGED)
    grid.state[:] = CellState.INFESTED
    for cell in [(0, 0), (0, 1), (5, 5)]:
        grid.set_state(*cell, CellState.UNBAGGED)

    expected = grid.copy()
    infested_rows, infested_cols = np.where(expected.infested_mask)
    for src_r, src_c in zip(infested_rows, infested_cols):
        gate._spread_from(
            expected,
            int(src_r),
            int(src_c),
            wind_speed_ms=2.0,
            wind_dir_deg=45.0,
            temperature_c=30.0,
            orchard_stage=OrchardStage.MATURE,
            sugar_index=0.8,
        )

    actual = grid.copy()
    gate.compute_dispersal(
        actual,
        hour=10,
        wind_speed_ms=2.0,
        wind_dir_deg=45.0,
        temperature_c=30.0,
        orchard_stage=OrchardStage.MATURE,
        sugar_index=0.8,
    )

    np.testing.assert_allclose(actual.risk, expected.risk)
