"""
MangoPoint — Simulation Engine
================================
Phenology- and data-calibrated biological trigger system for pest dispersal.

The main Cellular Automata engine orchestrates:
    1. Weather ingestion (per-timestep, including rainfall)
    2. Orchard phenological stage management
    3. Biological gate evaluation (Cecid Fly + Fruit Fly)
    4. Contextual information passing (NOT biological decisions)
    5. Dispersal probability accumulation on the grid
    6. State transitions (susceptible → infested)
    7. Time-series recording for visualisation

The engine passes contextual information to biological gates:
- hour, wind_speed, temperature, rainfall (current)
- rainfall_history (24-hour rolling accumulation)
- orchard_stage (Dormant, Flowering, Fruitlet, Mature)
- sugar_index (fruit ripeness based on days since flowering)

All biological logic MUST remain inside the pest gate classes.

Usage
-----
    grid    = OrchardGrid(30, 30)
    weather = WeatherTimeSeries.synthetic(hours=48)
    engine  = SimulationEngine(grid, weather, orchard_stage=OrchardStage.MATURE)
    results = engine.run()
"""

from __future__ import annotations

import numpy as np
from typing import List, Dict, Optional
from collections import deque
from tqdm import tqdm

from core.config import (
    CellState, 
    OrchardStage,
    N_TIMESTEPS,
    CECID_RAIN_HISTORY_HOURS,
    FRUIT_FLY_SUGAR_INDEX_START,
    FRUIT_FLY_SUGAR_INDEX_GROWTH,
    FRUIT_FLY_SUGAR_INDEX_MAX,
    FRUIT_FLY_DEFAULT_DAYS_FLOWERING,
)
from core.grid import OrchardGrid
from utils.weather import WeatherTimeSeries
from core.biological_rules import CecidFlyGate, FruitFlyGate


class SimulationResult:
    """
    Container for the full time-series output of one simulation run.

    Attributes
    ----------
    snapshots : list[dict]
        Per-timestep dicts with keys: timestep, datetime, hour,
        state (2-D array), risk (2-D array), weather, n_infested, n_new.
    grid : OrchardGrid
        Final grid state after the simulation.
    """

    def __init__(self):
        self.snapshots: List[Dict] = []
        self.grid: Optional["OrchardGrid"] = None

    def append(
        self,
        timestep: int,
        dt,
        hour: int,
        state: np.ndarray,
        risk: np.ndarray,
        weather: dict,
        n_infested: int,
        n_new: int,
    ):
        self.snapshots.append({
            "timestep":   timestep,
            "datetime":   dt,
            "hour":       hour,
            "state":      state.copy(),
            "risk":       risk.copy(),
            "weather":    weather.copy(),
            "n_infested": n_infested,
            "n_new":      n_new,
        })

    # ── convenience ─────────────────────────────────────────────
    @property
    def risk_series(self) -> np.ndarray:
        """3-D array (timestep, row, col) of accumulated risk."""
        return np.stack([s["risk"] for s in self.snapshots])

    @property
    def state_series(self) -> np.ndarray:
        """3-D array (timestep, row, col) of cell states."""
        return np.stack([s["state"] for s in self.snapshots])

    @property
    def infested_count_series(self) -> np.ndarray:
        return np.array([s["n_infested"] for s in self.snapshots])

    @property
    def datetimes(self) -> list:
        return [s["datetime"] for s in self.snapshots]

    def __len__(self):
        return len(self.snapshots)


class SimulationEngine:
    """
    Cellular Automata engine for pest dispersal simulation.

    Parameters
    ----------
    grid : OrchardGrid
        Initial orchard state (trees planted, some may be seeded as infested).
    weather : WeatherTimeSeries
        Hourly weather data covering the forecast window.
    transition_mode : str
        'stochastic' — Monte Carlo roll per cell each timestep
        'threshold'  — deterministic transition when risk ≥ threshold
    threshold : float
        Risk threshold for deterministic transition (default 0.5).
    gates : list, optional
        Custom list of DispersalGate instances.  Defaults to
        [CecidFlyGate(), FruitFlyGate()].
    orchard_stage : OrchardStage
        Current phenological stage of the orchard.
        - DORMANT: No pest activity
        - FLOWERING: No pest activity (flowers only)
        - FRUITLET: Cecid Fly can activate (post-flowering, young fruitlets)
        - MATURE: Fruit Fly can activate (ripe fruit)
    days_since_flowering : int, optional
        Days since flowering ended. Used to compute sugar_index for
        fruit fly attraction. Default is FRUIT_FLY_DEFAULT_DAYS_FLOWERING.
    """

    def __init__(
        self,
        grid: OrchardGrid,
        weather: WeatherTimeSeries,
        transition_mode: str = "stochastic",
        threshold: float = 0.5,
        gates=None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        days_since_flowering: Optional[int] = None,
        initial_rainfall_history: Optional[List[float]] = None,
    ):
        self.grid = grid.copy()  # work on a copy to preserve the original
        self.weather = weather
        self.transition_mode = transition_mode
        self.threshold = threshold
        self.gates = gates or [CecidFlyGate(), FruitFlyGate()]
        self.orchard_stage = orchard_stage
        
        # Days since flowering (for sugar index calculation)
        if days_since_flowering is None:
            days_since_flowering = FRUIT_FLY_DEFAULT_DAYS_FLOWERING
        self.days_since_flowering = days_since_flowering
        
        # Compute initial sugar index from days since flowering
        # Sugar index starts at FRUIT_FLY_SUGAR_INDEX_START and grows over time
        self.sugar_index = min(
            FRUIT_FLY_SUGAR_INDEX_MAX,
            FRUIT_FLY_SUGAR_INDEX_START + (days_since_flowering * FRUIT_FLY_SUGAR_INDEX_GROWTH)
        )
        
        # Initialize 24-hour rainfall history (deque for efficient rolling window)
        self.rainfall_history: deque = deque(maxlen=CECID_RAIN_HISTORY_HOURS)
        if initial_rainfall_history:
            seed = [0.0] * CECID_RAIN_HISTORY_HOURS + [float(r) for r in initial_rainfall_history]
            for r in seed[-CECID_RAIN_HISTORY_HOURS:]:
                self.rainfall_history.append(r)
        else:
            for _ in range(CECID_RAIN_HISTORY_HOURS):
                self.rainfall_history.append(0.0)

    # ── main loop ───────────────────────────────────────────────
    def run(self, n_steps: Optional[int] = None, progress: bool = True) -> SimulationResult:
        """
        Execute the CA simulation for *n_steps* timesteps.

        Returns
        -------
        SimulationResult
            Full time-series of grid snapshots plus metadata.
        """
        if n_steps is None:
            n_steps = min(N_TIMESTEPS, len(self.weather))

        result = SimulationResult()
        iterator = range(n_steps)
        if progress:
            iterator = tqdm(iterator, desc="MangoPoint simulation", unit="step")

        # Track the running maximum risk each cell has ever seen
        max_risk = np.zeros_like(self.grid.risk)

        for step in iterator:
            w = self.weather.at(step)
            
            # Get current rainfall and update rolling history
            current_rainfall = w.get("rainfall_mm", 0.0)
            self.rainfall_history.append(current_rainfall)
            
            # Update sugar index (increases slightly each day of simulation)
            # 1 day = 24 hours, so increment by growth rate / 24 per hour
            self.sugar_index = min(
                FRUIT_FLY_SUGAR_INDEX_MAX,
                self.sugar_index + (FRUIT_FLY_SUGAR_INDEX_GROWTH / 24.0)
            )

            # — accumulate dispersal from all gates —
            # Engine passes contextual information; gates make biological decisions
            for gate in self.gates:
                gate.compute_dispersal(
                    self.grid,
                    hour=w["hour"],
                    wind_speed_ms=w["wind_speed_ms"],
                    wind_dir_deg=w["wind_dir_deg"],
                    temperature_c=w["temperature_c"],
                    rainfall_mm=current_rainfall,
                    rainfall_history=self.rainfall_history,
                    orchard_stage=self.orchard_stage,
                    sugar_index=self.sugar_index,
                )

            # — state transition —
            if self.transition_mode == "stochastic":
                n_new = self.grid.stochastic_transition()
            else:
                n_new = self.grid.transition_infested(self.threshold)

            n_infested = int(self.grid.infested_mask.sum())

            # Update running max-risk (cumulative high-water mark)
            np.maximum(max_risk, self.grid.risk, out=max_risk)
            # Mark infested cells as 1.0 risk in the cumulative map
            max_risk[self.grid.infested_mask] = 1.0

            # — record snapshot —
            result.append(
                timestep=step,
                dt=w["datetime"],
                hour=w["hour"],
                state=self.grid.state,
                risk=max_risk,
                weather=w,
                n_infested=n_infested,
                n_new=n_new,
            )

            # — reset risk accumulator for next timestep —
            self.grid.reset_risk()

        result.grid = self.grid
        return result

    # ── Monte Carlo ensemble ────────────────────────────────────
    @staticmethod
    def monte_carlo(
        grid: OrchardGrid,
        weather: WeatherTimeSeries,
        n_runs: int = 50,
        n_steps: Optional[int] = None,
        seed: int = 0,
        gates=None,
        orchard_stage: OrchardStage = OrchardStage.MATURE,
        days_since_flowering: Optional[int] = None,
    ) -> np.ndarray:
        """
        Run the simulation *n_runs* times and return the **mean risk**
        field (rows × cols) across all runs at the final timestep.

        This is the recommended approach for the 48-hour forecast heatmap.
        
        Parameters
        ----------
        gates : list, optional
            Custom list of DispersalGate instances.  Defaults to
            [CecidFlyGate(), FruitFlyGate()].
        orchard_stage : OrchardStage
            Current phenological stage of the orchard.
        days_since_flowering : int, optional
            Days since flowering ended for sugar index calculation.
        """
        if n_steps is None:
            n_steps = min(N_TIMESTEPS, len(weather))

        risk_sum = np.zeros((grid.rows, grid.cols), dtype=np.float64)

        for run_i in tqdm(range(n_runs), desc="Monte Carlo runs"):
            np.random.seed(seed + run_i)
            engine = SimulationEngine(
                grid, weather,
                transition_mode="stochastic",
                gates=gates,
                orchard_stage=orchard_stage,
                days_since_flowering=days_since_flowering,
            )
            res = engine.run(n_steps=n_steps, progress=False)
            # record final risk = fraction of cells infested
            risk_sum += (res.grid.state == CellState.INFESTED).astype(float)  # type: ignore[union-attr]

        return risk_sum / n_runs
