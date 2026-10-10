import numpy as np
import pandas as pd
import pytest

from core.biological_rules import CecidFlyGate
from core.cecid_habitat import CecidHabitatNetwork
from core.config import CellState, OrchardStage
from core.grid import OrchardGrid
from core.simulation_engine import SimulationEngine
from utils.weather import WeatherTimeSeries


def _engine(route, transition_mode="threshold", threshold=2.0):
    grid = OrchardGrid(1, 2)
    grid.plant_trees(np.ones((1, 2), dtype=bool), CellState.UNBAGGED)
    positions = {(0, 0): (122.58, 10.585), (0, 1): (122.580045, 10.585)}
    if route == "local":
        grid.infest(0, 0)
        sources = {(0, 0): 1.0}
    else:
        grid.set_neighbor_threat_uniform(0.6)
        sources = {}
    network = CecidHabitatNetwork.from_lonlat(
        {cell: positions[cell] for cell in sources}, positions, [],
    )
    weather = WeatherTimeSeries(pd.DataFrame([{
        "datetime": pd.Timestamp("2026-04-01T18:00:00+08:00"),
        "wind_speed_ms": 1.0,
        "wind_dir_deg": 270.0,
        "temperature_c": 28.0,
        "rainfall_mm": 0.0,
    }]), source="test")
    return SimulationEngine(
        grid, weather, transition_mode=transition_mode, threshold=threshold,
        gates=[CecidFlyGate()], orchard_stage=OrchardStage.FRUITLET,
        initial_rainfall_history=[0.0] * 68 + [2.0] * 4,
        cecid_source_pressures=sources, cecid_habitat_network=network,
    )


@pytest.mark.parametrize("route", ["local", "external"])
def test_recorded_grid_reports_cecid_exposure_before_establishment(route):
    engine = _engine(route)
    snapshot = engine.run(n_steps=1, progress=False).snapshots[0]
    target = (0, 1)
    hourly_risk = snapshot["risk"][target]

    assert 0.0 < hourly_risk < 1.0
    assert snapshot["state"][target] == CellState.UNBAGGED
    # A single eligible exposure has the same hourly and cumulative probability.
    assert snapshot["cecid_cumulative_probability"][target] == pytest.approx(hourly_risk)
    assert snapshot["cecid_peak_hourly_risk"][target] == pytest.approx(hourly_risk)
    assert snapshot["cecid_exposure_hours"][target] == 1
    assert snapshot["cecid_local_exposure_hours"][target] == int(route == "local")
    assert snapshot["cecid_external_exposure_hours"][target] == int(route == "external")


@pytest.mark.parametrize("route", ["local", "external"])
def test_recording_diagnostics_preserves_cecid_transitions_and_random_draws(route):
    recorded = _engine(route, transition_mode="stochastic")
    np.random.seed(11)
    result = recorded.run(n_steps=1, progress=False)
    recorded_next_draws = np.random.random(3)

    final_only = _engine(route, transition_mode="stochastic")
    np.random.seed(11)
    final_grid = final_only.run_final_state(n_steps=1)
    final_only_next_draws = np.random.random(3)

    np.testing.assert_array_equal(result.grid.state, final_grid.state)
    np.testing.assert_array_equal(recorded_next_draws, final_only_next_draws)
    snapshot = result.snapshots[0]
    target = (0, 1)
    # This seed establishes infestation. Diagnostics must retain the incoming
    # probability and count the exposure while the target was still susceptible.
    assert snapshot["state"][target] == CellState.INFESTED
    assert snapshot["risk"][target] == 1.0
    assert 0.0 < snapshot["cecid_cumulative_probability"][target] < 1.0
    assert snapshot["cecid_exposure_hours"][target] == 1
    for name in (
        "cecid_cumulative_probability", "cecid_peak_hourly_risk", "cecid_exposure_hours",
        "cecid_local_exposure_hours", "cecid_external_exposure_hours",
    ):
        np.testing.assert_array_equal(snapshot[name], getattr(final_only, name))
