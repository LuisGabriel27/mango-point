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
- rainfall_history (72-hour antecedent context for Cecid soil wetness)
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
from typing import Dict, List, Mapping, Optional, Tuple
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
from core.biological_rules import CecidFlyGate, CecidSourceCohortModel, FruitFlyGate
from core.cecid_habitat import CecidHabitatNetwork, CecidHabitatTracker
from core.config import NEIGHBOR_THREAT_WEIGHT


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
        cecid_antecedent_weather: Optional[List[Dict]] = None,
        stage_grid: Optional[np.ndarray] = None,
        cecid_source_pressures: Optional[Mapping[Tuple[int, int], float]] = None,
        cecid_habitat_network: Optional[CecidHabitatNetwork] = None,
    ):
        self.grid = grid.copy()  # work on a copy to preserve the original
        self.weather = weather
        self.transition_mode = transition_mode
        self.threshold = threshold
        self.gates = gates or [CecidFlyGate(), FruitFlyGate()]
        self.orchard_stage = orchard_stage

        # Per-cell stage grid (mixed phenology). Shape must match the orchard
        # grid. When None, the scalar `orchard_stage` applies uniformly.
        if stage_grid is not None:
            if stage_grid.shape != self.grid.state.shape:
                raise ValueError(
                    f"stage_grid shape {stage_grid.shape} does not match grid "
                    f"shape {self.grid.state.shape}"
                )
            self.stage_grid = stage_grid.astype(np.int32, copy=True)
        else:
            self.stage_grid = None
        
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
        
        # Initialize the 72-hour antecedent rainfall context.
        self.rainfall_history: deque = deque(maxlen=CECID_RAIN_HISTORY_HOURS)
        if initial_rainfall_history:
            seed = [0.0] * CECID_RAIN_HISTORY_HOURS + [float(r) for r in initial_rainfall_history]
            for r in seed[-CECID_RAIN_HISTORY_HOURS:]:
                self.rainfall_history.append(r)
        else:
            for _ in range(CECID_RAIN_HISTORY_HOURS):
                self.rainfall_history.append(0.0)

        self.cecid_source_pressures = (
            None if cecid_source_pressures is None
            else {
                (int(key[0]), int(key[1])): float(value)
                for key, value in cecid_source_pressures.items()
            }
        )
        self.cecid_cohort_model: Optional[CecidSourceCohortModel] = None
        self.cecid_habitat_tracker = (
            CecidHabitatTracker(cecid_habitat_network)
            if cecid_habitat_network is not None else None
        )
        self.cecid_habitat_diagnostics: List[Dict] = []
        if self.cecid_source_pressures is not None:
            self.cecid_cohort_model = CecidSourceCohortModel(
                self.cecid_source_pressures,
                antecedent_rainfall=list(initial_rainfall_history or []),
            )
            if cecid_antecedent_weather:
                cecid_gate = next(
                    (gate for gate in self.gates if isinstance(gate, CecidFlyGate)),
                    None,
                )
                if cecid_gate is not None:
                    stage_for_gate = (
                        cecid_gate.REQUIRED_STAGE
                        if self.stage_grid is not None
                        else self.orchard_stage
                    )
                    replay_history: deque = deque(
                        [0.0] * CECID_RAIN_HISTORY_HOURS,
                        maxlen=CECID_RAIN_HISTORY_HOURS,
                    )
                    replay_components: Dict[str, Dict] = {}

                    def antecedent_window_open(entry: Dict) -> bool:
                        replay_history.append(float(entry.get("rainfall_mm", 0.0)))
                        cecid_gate.set_time_context(entry.get("datetime"))
                        components = cecid_gate.suitability_components(
                            wind_speed_ms=float(entry.get("wind_speed_ms", 0.0)),
                            rainfall_mm=float(entry.get("rainfall_mm", 0.0)),
                            rainfall_history=replay_history,
                            orchard_stage=stage_for_gate,
                            hour=int(entry.get("hour", 0)),
                        )
                        replay_components["current"] = components
                        return bool(components["hard_open"])

                    def advance_antecedent_habitat(
                        entry: Dict,
                        active_cohorts: Dict[str, Dict],
                        _window_open: bool,
                    ) -> None:
                        if self.cecid_habitat_tracker is None:
                            return
                        components = replay_components.get("current", {})
                        self.cecid_habitat_tracker.step(
                            active_cohorts=active_cohorts,
                            eligible=bool(
                                components.get("hard_open")
                                and float(components.get("suitability_score", 0.0)) > 0.0
                            ),
                            wind_speed_ms=float(entry.get("wind_speed_ms", 0.0)),
                            wind_from_deg=float(entry.get("wind_dir_deg", 0.0)),
                        )

                    self.cecid_cohort_model.warm_up(
                        cecid_antecedent_weather,
                        antecedent_window_open,
                        step_observer=advance_antecedent_habitat,
                    )

    def _prepare_cecid_sources(self, gate, step: int, weather: Dict) -> None:
        """Advance fixed soil-source cohorts and expose active pressure to the gate."""
        if not isinstance(gate, CecidFlyGate) or self.cecid_cohort_model is None:
            return
        stage_for_gate = (
            gate.REQUIRED_STAGE
            if self.stage_grid is not None
            else self.orchard_stage
        )
        components = gate.suitability_components(
            wind_speed_ms=weather["wind_speed_ms"],
            rainfall_mm=weather.get("rainfall_mm", 0.0),
            rainfall_history=self.rainfall_history,
            orchard_stage=stage_for_gate,
            hour=weather["hour"],
        )
        active = self.cecid_cohort_model.step(
            timestep=step,
            timestamp=weather.get("datetime"),
            rainfall_mm=weather.get("rainfall_mm", 0.0),
            emergence_window_open=bool(components["hard_open"]),
        )
        gate.set_active_source_pressures(active)

    def _spread_cecid_habitat(self, gate, step: int, weather: Dict) -> bool:
        """Apply the shared one-hop adult relay model when it is configured."""
        if (
            not isinstance(gate, CecidFlyGate)
            or self.cecid_cohort_model is None
            or self.cecid_habitat_tracker is None
        ):
            return False

        stage_for_gate = gate.REQUIRED_STAGE if self.stage_grid is not None else self.orchard_stage
        components = gate.suitability_components(
            wind_speed_ms=weather["wind_speed_ms"],
            rainfall_mm=weather.get("rainfall_mm", 0.0),
            rainfall_history=self.rainfall_history,
            orchard_stage=stage_for_gate,
            hour=weather["hour"],
        )
        eligible = bool(components["hard_open"] and components["suitability_score"] > 0.0)
        contributions = self.cecid_habitat_tracker.step(
            active_cohorts=self.cecid_cohort_model.active_cohorts(),
            eligible=eligible,
            wind_speed_ms=weather["wind_speed_ms"],
            wind_from_deg=weather["wind_dir_deg"],
        )

        neighbor_total = 0.0
        required_stage = int(gate.REQUIRED_STAGE)
        for target, arrivals in contributions.items():
            target_row, target_col = int(target[0]), int(target[1])
            if not (0 <= target_row < self.grid.rows and 0 <= target_col < self.grid.cols):
                continue
            if self.stage_grid is not None and int(self.stage_grid[target_row, target_col]) != required_stage:
                continue
            for arrival in arrivals:
                source = arrival["source"]
                source_row, source_col = int(source[0]), int(source[1])
                source_factor = self.grid.get_source_treatment_factor(source_row, source_col)
                active_pressure = max(0.0, float(arrival["cohort_pressure"]))
                path_efficiency = max(0.0, float(arrival["path_efficiency"]))
                probability = (
                    gate.base_dispersal_prob
                    * float(components["suitability_score"])
                    * active_pressure
                    * path_efficiency
                    * source_factor
                )
                neighbor_boost = (
                    self.grid.get_neighbor_threat(target_row, target_col)
                    * NEIGHBOR_THREAT_WEIGHT
                    * self.grid.get_wind_neighbor_factor(weather["wind_dir_deg"])
                    * float(components["suitability_score"])
                    * min(1.0, active_pressure)
                    * min(1.35, path_efficiency)
                    * source_factor
                )
                probability += neighbor_boost
                neighbor_total += neighbor_boost
                self.grid.apply_dispersal_probability(target_row, target_col, probability)

        self.cecid_habitat_diagnostics.append({
            "timestep": int(step),
            "datetime": str(weather.get("datetime")) if weather.get("datetime") is not None else None,
            "eligible": eligible,
            "wind_speed_ms": float(weather["wind_speed_ms"]),
            "wind_speed_kmh": float(weather["wind_speed_ms"]) * 3.6,
            "wind_from_deg": float(weather["wind_dir_deg"]),
            "downwind_bearing_deg": (float(weather["wind_dir_deg"]) + 180.0) % 360.0,
            "wind_survival_score": float(components["wind_survival_score"]),
            "neighbor_contribution": neighbor_total,
            **self.cecid_habitat_tracker.last_diagnostics,
        })
        return True

    @property
    def cecid_cohort_events(self) -> List[Dict]:
        return list(self.cecid_cohort_model.events) if self.cecid_cohort_model else []

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
            # Engine passes contextual information; gates make biological decisions.
            # With a per-cell stage grid, each gate filters source cells by its own
            # REQUIRED_STAGE so mixed phenology is honoured spatially.
            for gate in self.gates:
                if hasattr(gate, "set_time_context"):
                    gate.set_time_context(w.get("datetime"))
                self._prepare_cecid_sources(gate, step, w)
                if self._spread_cecid_habitat(gate, step, w):
                    continue
                if self.stage_grid is not None and gate.REQUIRED_STAGE is not None:
                    gate.compute_dispersal_per_cell(
                        self.grid,
                        stage_grid=self.stage_grid,
                        hour=w["hour"],
                        wind_speed_ms=w["wind_speed_ms"],
                        wind_dir_deg=w["wind_dir_deg"],
                        temperature_c=w["temperature_c"],
                        rainfall_mm=current_rainfall,
                        rainfall_history=self.rainfall_history,
                        sugar_index=self.sugar_index,
                    )
                else:
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

    def run_final_state(self, n_steps: Optional[int] = None) -> OrchardGrid:
        """
        Execute the simulation without recording per-timestep snapshots.

        Monte Carlo validation only needs the final infested grid. This method
        preserves the same timestep and transition logic as ``run()`` while
        avoiding full state/risk copies on every hour of every ensemble member.
        """
        if n_steps is None:
            n_steps = min(N_TIMESTEPS, len(self.weather))

        for step in range(n_steps):
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

            for gate in self.gates:
                if hasattr(gate, "set_time_context"):
                    gate.set_time_context(w.get("datetime"))
                self._prepare_cecid_sources(gate, step, w)
                if self._spread_cecid_habitat(gate, step, w):
                    continue
                if self.stage_grid is not None and gate.REQUIRED_STAGE is not None:
                    gate.compute_dispersal_per_cell(
                        self.grid,
                        stage_grid=self.stage_grid,
                        hour=w["hour"],
                        wind_speed_ms=w["wind_speed_ms"],
                        wind_dir_deg=w["wind_dir_deg"],
                        temperature_c=w["temperature_c"],
                        rainfall_mm=current_rainfall,
                        rainfall_history=self.rainfall_history,
                        sugar_index=self.sugar_index,
                    )
                else:
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

            if self.transition_mode == "stochastic":
                self.grid.stochastic_transition()
            else:
                self.grid.transition_infested(self.threshold)

            self.grid.reset_risk()
            if not self.grid.susceptible_mask.any():
                break

        return self.grid

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
        initial_rainfall_history: Optional[List[float]] = None,
        cecid_antecedent_weather: Optional[List[Dict]] = None,
        stage_grid: Optional[np.ndarray] = None,
        cecid_source_pressures: Optional[Mapping[Tuple[int, int], float]] = None,
        cecid_habitat_network: Optional[CecidHabitatNetwork] = None,
        progress: bool = True,
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
        cecid_source_pressures : mapping, optional
            Fixed Cecid soil-source anchors. When supplied, newly infested
            fruit cannot become adult sources during the forecast.
        """
        if n_steps is None:
            n_steps = min(N_TIMESTEPS, len(weather))

        risk_sum = np.zeros((grid.rows, grid.cols), dtype=np.float64)

        iterator = range(n_runs)
        if progress:
            iterator = tqdm(iterator, desc="Monte Carlo runs")

        for run_i in iterator:
            np.random.seed(seed + run_i)
            engine = SimulationEngine(
                grid, weather,
                transition_mode="stochastic",
                gates=gates,
                orchard_stage=orchard_stage,
                days_since_flowering=days_since_flowering,
                initial_rainfall_history=initial_rainfall_history,
                cecid_antecedent_weather=cecid_antecedent_weather,
                stage_grid=stage_grid,
                cecid_source_pressures=cecid_source_pressures,
                cecid_habitat_network=cecid_habitat_network,
            )
            final_grid = engine.run_final_state(n_steps=n_steps)
            # record final risk = fraction of cells infested
            risk_sum += (final_grid.state == CellState.INFESTED).astype(float)

        return risk_sum / n_runs
