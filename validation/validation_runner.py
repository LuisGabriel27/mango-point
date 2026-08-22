"""
MangoPoint Validation — Validation Runner
==========================================
Main orchestrator for running historical validation against the simulation model.

This module:
1. Loads historical pest monitoring data
2. Creates weather scenarios matching historical conditions
3. Runs simulations using the existing simulation engine
4. Compares predicted risk with actual observations
5. Computes validation metrics

The runner integrates with the existing system by:
- Calling SimulationEngine.monte_carlo() for risk prediction
- Using existing biological gate logic (CecidFlyGate, FruitFlyGate)
- Preserving all existing configurations and thresholds

Usage
-----
    from validation import ValidationRunner
    
    runner = ValidationRunner()
    results = runner.run_full_validation()
    metrics = runner.compute_metrics()
    runner.export_results_csv("validation_results.csv")
"""

from __future__ import annotations

import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

import numpy as np

from .historical_data import (
    HistoricalDataLoader,
    HistoricalRecord,
    PestRiskLevel,
    PestType,
)
from .weather_scenarios import HistoricalWeatherGenerator
from .metrics import (
    ValidationMetrics,
    bootstrap_confidence_intervals,
    compute_full_metrics,
    risk_score_to_level,
    risk_score_to_pest_level,
    normalize_pest_value_to_risk,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationCase:
    """
    A single validation test case derived from historical data.
    
    Attributes
    ----------
    case_id : str
        Unique identifier for this case
    year : int
        Historical year
    month : int
        Historical month
    date_str : str
        Date string (YYYY-MM format)
    pest_type : str
        Pest type ('cecid' or 'fruitfly')
    orchard_stage : str
        Mango phenological stage
    actual_value : float
        Actual recorded pest level (CPTD or infestation %)
    actual_level : str
        Actual risk classification (Low/Medium/High)
    weather_scenario : str
        Weather scenario used for simulation
    """
    case_id: str
    year: int
    month: int
    date_str: str
    pest_type: str
    orchard_stage: str
    actual_value: float
    actual_level: str
    weather_scenario: str
    
    # Optional metadata
    season: str = ""
    split: str = "evaluation"
    source_record: Optional[HistoricalRecord] = field(default=None, repr=False)
    previous_actual_risk: float = 0.0
    previous_actual_level: str = "Low"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "case_id": self.case_id,
            "year": self.year,
            "month": self.month,
            "date": self.date_str,
            "pest_type": self.pest_type,
            "orchard_stage": self.orchard_stage,
            "actual_value": self.actual_value,
            "actual_level": self.actual_level,
            "weather_scenario": self.weather_scenario,
            "season": self.season,
            "split": self.split,
            "previous_actual_risk": self.previous_actual_risk,
            "previous_actual_level": self.previous_actual_level,
        }


@dataclass
class ValidationResult:
    """
    Result of a single validation run.
    
    Attributes
    ----------
    case : ValidationCase
        The validation case that was run
    predicted_risk : float
        Simulated risk score (0-1)
    predicted_level : str
        Predicted risk classification (Low/Medium/High)
    match : bool
        Whether predicted level matches actual level
    simulation_time_s : float
        Time taken to run simulation
    peak_risk : float
        Peak cell risk from simulation
    n_infested : int
        Number of infested cells at end of simulation
    weather_stats : dict
        Summary of weather conditions used
    """
    case: ValidationCase
    predicted_risk: float
    predicted_level: str
    match: bool
    simulation_time_s: float = 0.0
    peak_risk: float = 0.0
    n_infested: int = 0
    weather_stats: Dict = field(default_factory=dict)
    raw_predicted_risk: Optional[float] = None
    raw_predicted_level: Optional[str] = None
    calibration_applied: bool = False
    calibration_method: Optional[str] = None
    risk_features: Dict[str, Any] = field(default_factory=dict)
    
    # Error for regression analysis
    error: float = 0.0
    
    def __post_init__(self):
        """Compute error after initialization."""
        self._refresh_error()

    def _actual_normalized(self) -> float:
        """Return the case's BPI value on the 0-1 risk scale."""
        return normalize_pest_value_to_risk(
            self.case.actual_value,
            self.case.pest_type,
        )

    def _refresh_error(self) -> None:
        """Refresh regression error after prediction changes."""
        self.error = abs(self.predicted_risk - self._actual_normalized())

    def apply_calibrated_prediction(
        self,
        calibrated_risk: float,
        calibrated_level: str,
        method: str,
    ) -> None:
        """Replace the reported prediction while preserving raw simulation output."""
        if self.raw_predicted_risk is None:
            self.raw_predicted_risk = self.predicted_risk
        if self.raw_predicted_level is None:
            self.raw_predicted_level = self.predicted_level

        self.predicted_risk = max(0.0, min(1.0, float(calibrated_risk)))
        self.predicted_level = calibrated_level
        self.match = self.predicted_level == self.case.actual_level
        self.calibration_applied = True
        self.calibration_method = method
        self._refresh_error()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            **self.case.to_dict(),
            "predicted_risk": self.predicted_risk,
            "predicted_level": self.predicted_level,
            "match": self.match,
            "error": self.error,
            "simulation_time_s": self.simulation_time_s,
            "peak_risk": self.peak_risk,
            "n_infested": self.n_infested,
            "weather_source": self.weather_stats.get("source", "unknown"),
            "weather_fallback_reason": self.weather_stats.get("fallback_reason"),
            "raw_predicted_risk": self.raw_predicted_risk,
            "raw_predicted_level": self.raw_predicted_level,
            "calibration_applied": self.calibration_applied,
            "calibration_method": self.calibration_method,
            "risk_features": self.risk_features,
        }
    
    def to_metrics_dict(self) -> Dict[str, Any]:
        """Convert to format expected by metrics calculator."""
        actual_normalized = normalize_pest_value_to_risk(
            self.case.actual_value,
            self.case.pest_type,
        )
        return {
            "actual_level": self.case.actual_level,
            "predicted_level": self.predicted_level,
            "actual_value": actual_normalized,
            "predicted_value": self.predicted_risk,
            "pest_type": self.case.pest_type,
            "match": self.match,
            "split": self.case.split,
        }


class ValidationRunner:
    """
    Main validation runner that orchestrates historical validation.
    
    This class:
    1. Generates validation cases from historical BPI data
    2. Runs simulations for each case using the existing engine
    3. Compares predictions against actual observations
    4. Computes comprehensive validation metrics
    
    Usage
    -----
        runner = ValidationRunner()
        
        # Run full validation
        results = runner.run_full_validation()
        
        # Get metrics
        metrics = runner.compute_metrics()
        
        # Export results
        runner.export_results_csv("validation_results.csv")
    
    Attributes
    ----------
    data_loader : HistoricalDataLoader
        Loader for historical BPI data
    weather_generator : HistoricalWeatherGenerator
        Generator for historical weather scenarios
    results : list[ValidationResult]
        Completed validation results
    """
    
    # Default simulation parameters
    DEFAULT_HOURS = 48
    DEFAULT_MONTE_CARLO_RUNS = 30
    DEFAULT_GRID_SIZE = 20
    
    def __init__(
        self,
        data_path: Optional[Path] = None,
        seed: int = 42,
        historical_weather_path: Optional[Path] = None,
        require_historical_weather: bool = False,
    ):
        """
        Initialize the validation runner.
        
        Parameters
        ----------
        data_path : Path, optional
            Custom path to historical data CSV
        seed : int
            Random seed for reproducibility
        historical_weather_path : Path, optional
            Optional hourly historical weather CSV used before synthetic
            seasonal weather profiles.
        require_historical_weather : bool
            If True, validation fails when a case lacks enough hourly
            historical weather rows.
        """
        self.data_loader = HistoricalDataLoader(data_path)
        self.weather_generator = HistoricalWeatherGenerator(
            seed=seed,
            historical_weather_path=historical_weather_path,
            require_historical_weather=require_historical_weather,
        )
        self.seed = seed
        self.results: List[ValidationResult] = []
        self._cases: List[ValidationCase] = []
        self._metrics: Optional[ValidationMetrics] = None
        self.calibration = None
        
        # Lazy-loaded simulation components
        self._simulation_loaded = False
        self._SimulationEngine = None
        self._OrchardGrid = None
        self._WeatherTimeSeries = None
        self._CecidFlyGate = None
        self._FruitFlyGate = None
        self._CellState = None
        self._OrchardStage = None
    
    def _load_simulation_modules(self) -> None:
        """Lazy load simulation modules to avoid import errors."""
        if self._simulation_loaded:
            return
        
        try:
            from core.simulation_engine import SimulationEngine
            from core.grid import OrchardGrid
            from utils.weather import WeatherTimeSeries
            from core.biological_rules import CecidFlyGate, FruitFlyGate
            from core.config import CellState, OrchardStage
            
            self._SimulationEngine = SimulationEngine
            self._OrchardGrid = OrchardGrid
            self._WeatherTimeSeries = WeatherTimeSeries
            self._CecidFlyGate = CecidFlyGate
            self._FruitFlyGate = FruitFlyGate
            self._CellState = CellState
            self._OrchardStage = OrchardStage
            
            self._simulation_loaded = True
            logger.info("Simulation modules loaded successfully")
            
        except ImportError as e:
            logger.error(f"Failed to import simulation modules: {e}")
            raise ImportError(
                "Could not import simulation modules. "
                "Ensure you're running from the mangopoint directory."
            ) from e
    
    def generate_validation_cases(
        self,
        max_cases: Optional[int] = None,
        pest_types: Optional[List[str]] = None,
        years: Optional[List[int]] = None,
    ) -> List[ValidationCase]:
        """
        Generate validation cases from historical data.
        
        Parameters
        ----------
        max_cases : int, optional
            Maximum number of cases to generate
        pest_types : list[str], optional
            Filter by pest type ('cecid', 'fruitfly', or both)
        years : list[int], optional
            Filter by specific years
        
        Returns
        -------
        list[ValidationCase]
            Generated validation cases
        """
        self.data_loader.ensure_loaded()
        records = self.data_loader.records
        records_by_month = {
            (record.year, record.month): record
            for record in self.data_loader.records
        }

        def previous_month_record(record: HistoricalRecord) -> Optional[HistoricalRecord]:
            prev_year = record.year if record.month > 1 else record.year - 1
            prev_month = record.month - 1 if record.month > 1 else 12
            return records_by_month.get((prev_year, prev_month))

        def previous_pest_context(
            record: HistoricalRecord,
            pest_type: str,
        ) -> Tuple[float, str]:
            previous = previous_month_record(record)
            if previous is None:
                return 0.0, "Low"
            if pest_type == "fruitfly":
                value = previous.fruit_fly_managed_cptd
                level = previous.get_fruit_fly_risk_level(True).value
            else:
                value = previous.cecid_fly_infestation_pct
                level = previous.get_cecid_fly_risk_level().value
            return normalize_pest_value_to_risk(value, pest_type), level
        
        # Filter by years if specified
        if years:
            records = [r for r in records if r.year in years]
        
        cases = []
        case_counter = 0
        
        # Determine which pest types to include
        include_cecid = pest_types is None or "cecid" in pest_types
        include_fruitfly = pest_types is None or "fruitfly" in pest_types
        
        for record in records:
            # Generate Fruit Fly cases (when biologically relevant)
            if include_fruitfly and record.mango_stage == "mature":
                case_counter += 1
                previous_risk, previous_level = previous_pest_context(
                    record,
                    "fruitfly",
                )
                case = ValidationCase(
                    case_id=f"FF-{record.year}-{record.month:02d}",
                    year=record.year,
                    month=record.month,
                    date_str=record.date_str,
                    pest_type="fruitfly",
                    orchard_stage=record.mango_stage,
                    actual_value=record.fruit_fly_managed_cptd,
                    actual_level=record.get_fruit_fly_risk_level(True).value,
                    weather_scenario="typical",
                    season=record.season,
                    source_record=record,
                    previous_actual_risk=previous_risk,
                    previous_actual_level=previous_level,
                )
                cases.append(case)
                
                if max_cases and len(cases) >= max_cases:
                    break
            
            # Generate Cecid Fly cases (when biologically relevant)
            if include_cecid and record.mango_stage == "fruitlet":
                case_counter += 1
                # Cecid Fly needs rainfall-triggered emergence
                weather_scenario = "rainy" if record.cecid_fly_infestation_pct > 0 else "typical"
                previous_risk, previous_level = previous_pest_context(
                    record,
                    "cecid",
                )
                
                case = ValidationCase(
                    case_id=f"CF-{record.year}-{record.month:02d}",
                    year=record.year,
                    month=record.month,
                    date_str=record.date_str,
                    pest_type="cecid",
                    orchard_stage=record.mango_stage,
                    actual_value=record.cecid_fly_infestation_pct,
                    actual_level=record.get_cecid_fly_risk_level().value,
                    weather_scenario=weather_scenario,
                    season=record.season,
                    source_record=record,
                    previous_actual_risk=previous_risk,
                    previous_actual_level=previous_level,
                )
                cases.append(case)
                
                if max_cases and len(cases) >= max_cases:
                    break
        
        self._cases = cases
        logger.info(f"Generated {len(cases)} validation cases")
        return cases

    def assign_case_splits(
        self,
        cases: Optional[List[ValidationCase]] = None,
        split_year: Optional[int] = None,
        test_years: Optional[List[int]] = None,
    ) -> Dict[str, List[ValidationCase]]:
        """
        Assign validation cases to calibration/testing splits.

        If no split is requested, cases remain in the neutral ``evaluation``
        split for backwards-compatible validation runs.
        """
        cases = cases if cases is not None else self._cases
        test_year_set = set(test_years or [])

        grouped: Dict[str, List[ValidationCase]] = {}
        for case in cases:
            if test_year_set:
                case.split = "testing" if case.year in test_year_set else "calibration"
            elif split_year is not None:
                case.split = "calibration" if case.year < split_year else "testing"
            else:
                case.split = "evaluation"

            grouped.setdefault(case.split, []).append(case)

        return grouped
    
    def _map_stage_to_enum(self, stage_str: str):
        """Map stage string to OrchardStage enum."""
        stage_map = {
            "dormant": self._OrchardStage.DORMANT,
            "flowering": self._OrchardStage.FLOWERING,
            "fruitlet": self._OrchardStage.FRUITLET,
            "mature": self._OrchardStage.MATURE,
        }
        return stage_map.get(stage_str, self._OrchardStage.MATURE)

    @staticmethod
    def _clip01(value: float) -> float:
        """Clamp a numeric value to the risk-score interval."""
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _days_since_flowering(stage: str) -> int:
        """Return a representative days-since-flowering value for a stage."""
        days_flowering_map = {
            "dormant": 0,
            "flowering": 10,
            "fruitlet": 30,
            "mature": 75,
        }
        return days_flowering_map.get(stage, 60)

    def _case_seed(self, case: ValidationCase, offset: int = 0) -> int:
        """Return a deterministic integer seed for one validation case."""
        case_hash = hashlib.sha256(case.case_id.encode("utf-8")).hexdigest()
        return self.seed + int(case_hash[:8], 16) % 10000 + offset

    def _seed_positions(
        self,
        case: ValidationCase,
        grid_size: int,
        carryover_weight: float,
        offset: int = 0,
    ) -> List[Tuple[int, int]]:
        """
        Create deterministic initial seed positions.

        When carryover is enabled, the previous month's BPI activity increases
        the number of initial sources. This represents residual orchard pressure
        from the last monitoring period without inventing treatment or neighbor
        records.
        """
        rng = np.random.default_rng(self._case_seed(case, offset))
        base_seeds = int(rng.integers(1, 4))
        if carryover_weight > 0:
            carryover_seeds = 1 + int(round(case.previous_actual_risk * 6))
            n_seeds = max(base_seeds, carryover_seeds)
        else:
            n_seeds = base_seeds
        n_seeds = min(8, max(1, n_seeds))

        flat_positions = rng.choice(
            grid_size * grid_size,
            size=n_seeds,
            replace=False,
        )
        return [
            (int(pos // grid_size), int(pos % grid_size))
            for pos in flat_positions
        ]

    @staticmethod
    def _effective_carryover_weight(
        case: ValidationCase,
        carryover_weight: float,
        fruitfly_carryover_weight: Optional[float] = None,
        cecid_carryover_weight: Optional[float] = None,
    ) -> float:
        """Return the pest-specific carryover weight for a validation case."""
        if case.pest_type == "fruitfly" and fruitfly_carryover_weight is not None:
            return max(0.0, min(1.0, float(fruitfly_carryover_weight)))
        if case.pest_type == "cecid" and cecid_carryover_weight is not None:
            return max(0.0, min(1.0, float(cecid_carryover_weight)))
        return max(0.0, min(1.0, float(carryover_weight)))

    def _weather_suitability_score(
        self,
        case: ValidationCase,
        weather_stats: Dict[str, Any],
    ) -> float:
        """Compute a pest-specific 0-1 weather suitability score."""
        temp_mean = float(weather_stats.get("temp_mean_c", 0.0))
        humidity_mean = float(weather_stats.get("humidity_mean_pct", 75.0))
        rainfall_mean = float(weather_stats.get("rainfall_total_mm", 0.0))
        rainfall_peak = float(weather_stats.get("rainfall_peak_window_mm", rainfall_mean))
        wind_mean = float(weather_stats.get("wind_mean_ms", 0.0))

        humidity_score = self._clip01((humidity_mean - 60.0) / 35.0)
        low_wind_score = 1.0 - self._clip01((wind_mean - 1.0) / 7.0)

        if case.pest_type == "fruitfly":
            temp_score = self._clip01((temp_mean - 24.0) / 8.0)
            rain_penalty = 1.0 - self._clip01(rainfall_mean / 80.0)
            return self._clip01(
                0.50 * temp_score
                + 0.25 * humidity_score
                + 0.15 * rain_penalty
                + 0.10 * low_wind_score
            )

        rain_score = self._clip01(max(rainfall_mean, rainfall_peak * 0.7) / 25.0)
        return self._clip01(
            0.60 * rain_score
            + 0.25 * humidity_score
            + 0.15 * low_wind_score
        )

    @staticmethod
    def _aggregate_weather_stats(
        weather_stats_by_window: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Aggregate several 48-hour weather windows into month-scale stats."""
        if not weather_stats_by_window:
            return {}

        def mean_for(key: str) -> float:
            values = [
                float(stats[key])
                for stats in weather_stats_by_window
                if key in stats and stats[key] is not None
            ]
            return float(np.mean(values)) if values else 0.0

        rainfall_totals = [
            float(stats.get("rainfall_total_mm", 0.0))
            for stats in weather_stats_by_window
        ]
        sources = sorted({
            str(stats.get("source", "unknown"))
            for stats in weather_stats_by_window
        })
        scenarios = sorted({
            str(stats.get("scenario", "unknown"))
            for stats in weather_stats_by_window
        })

        return {
            "source": ",".join(sources),
            "scenario": ",".join(scenarios),
            "hours": int(sum(int(stats.get("hours", 0)) for stats in weather_stats_by_window)),
            "monthly_windows": len(weather_stats_by_window),
            "temp_mean_c": mean_for("temp_mean_c"),
            "humidity_mean_pct": mean_for("humidity_mean_pct"),
            "rainfall_total_mm": float(np.mean(rainfall_totals)) if rainfall_totals else 0.0,
            "rainfall_peak_window_mm": max(rainfall_totals) if rainfall_totals else 0.0,
            "rainfall_hours": int(sum(int(stats.get("rainfall_hours", 0)) for stats in weather_stats_by_window)),
            "wind_mean_ms": mean_for("wind_mean_ms"),
            "wind_max_ms": max(
                float(stats.get("wind_max_ms", 0.0))
                for stats in weather_stats_by_window
            ),
        }

    def _risk_features_from_grid(self, mean_risk: np.ndarray) -> Dict[str, Any]:
        """Derive non-saturated CA features from a Monte Carlo risk grid."""
        return {
            "mean_risk": float(mean_risk.mean()),
            "peak_risk": float(mean_risk.max()),
            "p90_risk": float(np.percentile(mean_risk, 90)),
            "p75_risk": float(np.percentile(mean_risk, 75)),
            "risk_area_10": float((mean_risk >= 0.10).mean()),
            "risk_area_30": float((mean_risk >= 0.30).mean()),
            "risk_area_50": float((mean_risk >= 0.50).mean()),
            "n_at_risk": int((mean_risk >= 0.30).sum()),
        }

    @staticmethod
    def _aggregate_risk_features(
        features_by_window: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Aggregate several 48-hour CA feature sets into a monthly summary."""
        if not features_by_window:
            return {}

        numeric_keys = [
            "mean_risk",
            "peak_risk",
            "p90_risk",
            "p75_risk",
            "risk_area_10",
            "risk_area_30",
            "risk_area_50",
            "n_at_risk",
        ]
        aggregated: Dict[str, Any] = {"monthly_windows": len(features_by_window)}
        for key in numeric_keys:
            values = [float(features.get(key, 0.0)) for features in features_by_window]
            aggregated[f"mean_{key}"] = float(np.mean(values))
            aggregated[f"peak_{key}"] = float(max(values))
        return aggregated

    def _score_from_features(
        self,
        case: ValidationCase,
        risk_features: Dict[str, Any],
        weather_stats: Dict[str, Any],
        score_mode: str,
        carryover_weight: float,
        fruitfly_carryover_weight: Optional[float] = None,
        cecid_carryover_weight: Optional[float] = None,
    ) -> Tuple[float, Dict[str, Any]]:
        """Convert simulation/weather features into a validation risk score."""
        if score_mode == "mean_risk":
            score = float(risk_features.get("mean_mean_risk", 0.0))
            return self._clip01(score), {
                "score_mode": score_mode,
                "spatial_score": score,
                "weather_suitability": None,
                "carryover_weight": 0.0,
            }

        spatial_score = self._clip01(
            0.25 * float(risk_features.get("mean_mean_risk", 0.0))
            + 0.25 * float(risk_features.get("mean_p90_risk", 0.0))
            + 0.20 * float(risk_features.get("peak_mean_risk", 0.0))
            + 0.15 * float(risk_features.get("mean_risk_area_30", 0.0))
            + 0.15 * float(risk_features.get("peak_risk_area_50", 0.0))
        )
        weather_suitability = self._weather_suitability_score(case, weather_stats)
        carryover_weight = self._effective_carryover_weight(
            case,
            carryover_weight,
            fruitfly_carryover_weight=fruitfly_carryover_weight,
            cecid_carryover_weight=cecid_carryover_weight,
        )
        simulation_score = self._clip01(
            0.70 * spatial_score
            + 0.30 * weather_suitability
        )
        score = self._clip01(
            (1.0 - carryover_weight) * simulation_score
            + carryover_weight * case.previous_actual_risk
        )
        return score, {
            "score_mode": score_mode,
            "spatial_score": spatial_score,
            "weather_suitability": weather_suitability,
            "simulation_score_before_carryover": simulation_score,
            "carryover_weight": carryover_weight,
            "previous_actual_risk": case.previous_actual_risk,
            "previous_actual_level": case.previous_actual_level,
        }
    
    def _run_single_validation(
        self,
        case: ValidationCase,
        hours: int = DEFAULT_HOURS,
        monte_carlo_runs: int = DEFAULT_MONTE_CARLO_RUNS,
        grid_size: int = DEFAULT_GRID_SIZE,
        monthly_windows: int = 1,
        score_mode: str = "mean_risk",
        carryover_weight: float = 0.0,
        fruitfly_carryover_weight: Optional[float] = None,
        cecid_carryover_weight: Optional[float] = None,
    ) -> ValidationResult:
        """
        Run a single validation case.
        
        Parameters
        ----------
        case : ValidationCase
            The case to validate
        hours : int
            Simulation duration
        monte_carlo_runs : int
            Number of Monte Carlo runs for risk estimation
        grid_size : int
            Grid dimension (grid_size x grid_size)
        
        Returns
        -------
        ValidationResult
            Result of the validation run
        """
        import time
        
        self._load_simulation_modules()
        
        start_time = time.time()
        effective_carryover_weight = self._effective_carryover_weight(
            case,
            carryover_weight,
            fruitfly_carryover_weight=fruitfly_carryover_weight,
            cecid_carryover_weight=cecid_carryover_weight,
        )

        window_count = max(1, int(monthly_windows))
        weather_windows = self.weather_generator.generate_monthly_windows(
            year=case.year,
            month=case.month,
            window_hours=hours,
            n_windows=window_count,
            scenario=case.weather_scenario,
        )

        risk_features_by_window: List[Dict[str, Any]] = []
        weather_stats_by_window: List[Dict[str, Any]] = []

        # Select appropriate gate based on pest type.
        if case.pest_type == "cecid":
            gates = [self._CecidFlyGate()]
        else:
            gates = [self._FruitFlyGate()]

        orchard_stage = self._map_stage_to_enum(case.orchard_stage)
        days_since_flowering = self._days_since_flowering(case.orchard_stage)

        for window_index, weather_df in enumerate(weather_windows):
            weather = self._WeatherTimeSeries.from_dataframe(weather_df)
            weather_stats_by_window.append(
                self.weather_generator.get_summary_stats(weather_df)
            )

            grid = self._OrchardGrid(rows=grid_size, cols=grid_size)
            tree_mask = np.ones((grid_size, grid_size), dtype=bool)
            grid.plant_trees(tree_mask, self._CellState.UNBAGGED)
            seed_positions = self._seed_positions(
                case=case,
                grid_size=grid_size,
                carryover_weight=effective_carryover_weight,
                offset=window_index * 1000,
            )
            grid.seed_infestation(seed_positions)
            cecid_source_pressures = (
                {tuple(position): 1.0 for position in seed_positions}
                if case.pest_type == "cecid"
                else None
            )

            try:
                mean_risk = self._SimulationEngine.monte_carlo(
                    grid=grid,
                    weather=weather,
                    n_runs=monte_carlo_runs,
                    n_steps=hours,
                    seed=self.seed + window_index * 1000,
                    gates=gates,
                    orchard_stage=orchard_stage,
                    days_since_flowering=days_since_flowering,
                    cecid_source_pressures=cecid_source_pressures,
                    progress=False,
                )
                risk_features_by_window.append(
                    self._risk_features_from_grid(mean_risk)
                )
            except Exception as e:
                logger.warning(
                    "Simulation failed for case %s window %s: %s",
                    case.case_id,
                    window_index + 1,
                    e,
                )

        weather_stats = self._aggregate_weather_stats(weather_stats_by_window)
        risk_features = self._aggregate_risk_features(risk_features_by_window)

        if risk_features:
            predicted_risk, score_features = self._score_from_features(
                case=case,
                risk_features=risk_features,
                weather_stats=weather_stats,
                score_mode=score_mode,
                carryover_weight=effective_carryover_weight,
                fruitfly_carryover_weight=fruitfly_carryover_weight,
                cecid_carryover_weight=cecid_carryover_weight,
            )
            risk_features.update(score_features)
            peak_risk = float(risk_features.get("peak_peak_risk", predicted_risk))
            n_at_risk = int(round(float(risk_features.get("peak_n_at_risk", 0.0))))
        else:
            predicted_risk = 0.0
            peak_risk = 0.0
            n_at_risk = 0
            risk_features = {
                "score_mode": score_mode,
                "monthly_windows": window_count,
                "carryover_weight": effective_carryover_weight,
                "previous_actual_risk": case.previous_actual_risk,
                "previous_actual_level": case.previous_actual_level,
            }
        
        elapsed_time = time.time() - start_time
        
        # Convert risk to categorical level
        predicted_level = risk_score_to_pest_level(predicted_risk, case.pest_type)
        
        # Check if prediction matches actual
        match = predicted_level == case.actual_level
        
        return ValidationResult(
            case=case,
            predicted_risk=predicted_risk,
            predicted_level=predicted_level,
            match=match,
            simulation_time_s=elapsed_time,
            peak_risk=peak_risk,
            n_infested=n_at_risk,
            weather_stats=weather_stats,
            risk_features=risk_features,
        )
    
    def run_validation(
        self,
        cases: Optional[List[ValidationCase]] = None,
        hours: int = DEFAULT_HOURS,
        monte_carlo_runs: int = DEFAULT_MONTE_CARLO_RUNS,
        grid_size: int = DEFAULT_GRID_SIZE,
        monthly_windows: int = 1,
        score_mode: str = "mean_risk",
        carryover_weight: float = 0.0,
        fruitfly_carryover_weight: Optional[float] = None,
        cecid_carryover_weight: Optional[float] = None,
        progress_callback: Optional[callable] = None,
    ) -> List[ValidationResult]:
        """
        Run validation for a list of cases.
        
        Parameters
        ----------
        cases : list[ValidationCase], optional
            Cases to validate. If None, uses previously generated cases.
        hours : int
            Simulation duration
        monte_carlo_runs : int
            Number of Monte Carlo runs
        grid_size : int
            Grid dimension
        monthly_windows : int
            Number of 48-hour windows sampled across each historical month.
        score_mode : str
            "mean_risk" preserves the legacy score; "composite" uses spatial,
            weather, and carryover features for BPI-monthly validation.
        carryover_weight : float
            Weight given to previous-month BPI pest pressure in composite mode.
        fruitfly_carryover_weight : float, optional
            Optional Fruit Fly-specific carryover override.
        cecid_carryover_weight : float, optional
            Optional Cecid Fly-specific carryover override.
        progress_callback : callable, optional
            Callback function(current, total) for progress updates
        
        Returns
        -------
        list[ValidationResult]
            Validation results
        """
        if cases is None:
            cases = self._cases
        
        if not cases:
            raise ValueError(
                "No validation cases available. "
                "Call generate_validation_cases() first."
            )
        
        self.results = []
        total = len(cases)
        
        logger.info(f"Running validation for {total} cases...")
        
        for i, case in enumerate(cases):
            if progress_callback:
                progress_callback(i + 1, total)
            
            result = self._run_single_validation(
                case,
                hours=hours,
                monte_carlo_runs=monte_carlo_runs,
                grid_size=grid_size,
                monthly_windows=monthly_windows,
                score_mode=score_mode,
                carryover_weight=carryover_weight,
                fruitfly_carryover_weight=fruitfly_carryover_weight,
                cecid_carryover_weight=cecid_carryover_weight,
            )
            self.results.append(result)
            
            # Log progress
            status = "PASS" if result.match else "FAIL"
            logger.debug(
                f"[{i+1}/{total}] {status} {case.case_id}: "
                f"Actual={case.actual_level}, Predicted={result.predicted_level}"
            )
        
        logger.info(
            f"Validation complete: "
            f"{sum(r.match for r in self.results)}/{total} correct"
        )
        
        return self.results
    
    def run_full_validation(
        self,
        max_cases: Optional[int] = None,
        pest_types: Optional[List[str]] = None,
        years: Optional[List[int]] = None,
        hours: int = DEFAULT_HOURS,
        monte_carlo_runs: int = DEFAULT_MONTE_CARLO_RUNS,
        grid_size: int = DEFAULT_GRID_SIZE,
        monthly_windows: int = 1,
        score_mode: str = "mean_risk",
        carryover_weight: float = 0.0,
        fruitfly_carryover_weight: Optional[float] = None,
        cecid_carryover_weight: Optional[float] = None,
    ) -> List[ValidationResult]:
        """
        Run complete validation pipeline.
        
        This is the main entry point for running validation:
        1. Loads historical data
        2. Generates validation cases
        3. Runs simulations
        4. Returns results
        
        Parameters
        ----------
        max_cases : int, optional
            Maximum number of cases
        pest_types : list[str], optional
            Pest types to include
        years : list[int], optional
            Years to include
        hours : int
            Simulation duration
        monte_carlo_runs : int
            Number of Monte Carlo runs
        grid_size : int
            Grid dimension
        monthly_windows : int
            Number of forecast-sized windows sampled across each month
        score_mode : str
            Validation score mode ("mean_risk" or "composite")
        carryover_weight : float
            Previous-month BPI pressure weight for composite scoring
        fruitfly_carryover_weight : float, optional
            Fruit Fly-specific previous-month pressure override
        cecid_carryover_weight : float, optional
            Cecid Fly-specific previous-month pressure override
        
        Returns
        -------
        list[ValidationResult]
            All validation results
        """
        # Load data
        self.data_loader.load()
        
        # Generate cases
        self.generate_validation_cases(
            max_cases=max_cases,
            pest_types=pest_types,
            years=years,
        )
        
        # Run validation
        return self.run_validation(
            hours=hours,
            monte_carlo_runs=monte_carlo_runs,
            grid_size=grid_size,
            monthly_windows=monthly_windows,
            score_mode=score_mode,
            carryover_weight=carryover_weight,
            fruitfly_carryover_weight=fruitfly_carryover_weight,
            cecid_carryover_weight=cecid_carryover_weight,
        )
    
    def compute_metrics(
        self,
        split: Optional[str] = None,
        bootstrap_iterations: int = 0,
        confidence: float = 0.95,
        seed: Optional[int] = None,
    ) -> ValidationMetrics:
        """
        Compute validation metrics from results.

        Parameters
        ----------
        split : str, optional
            If provided, compute metrics only for results in this split.
        bootstrap_iterations : int
            Number of bootstrap resamples for confidence intervals.
        confidence : float
            Confidence level for bootstrap intervals.
        seed : int, optional
            Random seed for bootstrap resampling.
        
        Returns
        -------
        ValidationMetrics
            Comprehensive validation metrics
        """
        if not self.results:
            raise ValueError(
                "No validation results available. "
                "Call run_validation() first."
            )
        
        selected_results = [
            result for result in self.results
            if split is None or result.case.split == split
        ]
        if not selected_results:
            raise ValueError(f"No validation results available for split: {split}")

        # Convert results to metrics format
        metrics_data = [r.to_metrics_dict() for r in selected_results]

        metrics = compute_full_metrics(metrics_data)
        if bootstrap_iterations > 0:
            metrics.confidence_intervals = bootstrap_confidence_intervals(
                metrics_data,
                n_iterations=bootstrap_iterations,
                confidence=confidence,
                seed=self.seed if seed is None else seed,
            )

        if split is None:
            self._metrics = metrics
        return metrics

    def raw_score_diagnostics(self, pest_type: str) -> Dict[str, Any]:
        """Summarize uncalibrated model scores for degeneracy checks."""
        normalized_pest = str(pest_type).strip().lower()
        scores = [
            float(
                result.raw_predicted_risk
                if result.raw_predicted_risk is not None
                else result.predicted_risk
            )
            for result in self.results
            if str(result.case.pest_type).strip().lower() == normalized_pest
        ]
        finite_scores = [score for score in scores if np.isfinite(score)]
        if not finite_scores:
            return {
                "pest_type": normalized_pest,
                "count": 0,
                "finite_count": 0,
                "unique_count": 0,
                "minimum": None,
                "maximum": None,
                "mean": None,
                "spread": None,
                "nonzero_count": 0,
            }
        minimum = min(finite_scores)
        maximum = max(finite_scores)
        return {
            "pest_type": normalized_pest,
            "count": len(scores),
            "finite_count": len(finite_scores),
            "unique_count": len({round(score, 12) for score in finite_scores}),
            "minimum": minimum,
            "maximum": maximum,
            "mean": float(np.mean(finite_scores)),
            "spread": maximum - minimum,
            "nonzero_count": sum(abs(score) > 1e-12 for score in finite_scores),
        }

    def require_non_degenerate_raw_scores(
        self,
        pest_type: str,
        min_cases: int = 2,
        min_spread: float = 1e-9,
    ) -> Dict[str, Any]:
        """Fail validation when a pest's raw scores are constant or all zero."""
        diagnostics = self.raw_score_diagnostics(pest_type)
        if diagnostics["finite_count"] != diagnostics["count"]:
            raise ValueError(f"{pest_type} raw validation scores contain non-finite values.")
        if diagnostics["count"] < min_cases:
            raise ValueError(
                f"{pest_type} needs at least {min_cases} cases for a raw-score degeneracy check."
            )
        if diagnostics["nonzero_count"] == 0:
            raise ValueError(f"{pest_type} raw validation scores are all zero.")
        if diagnostics["unique_count"] < 2 or diagnostics["spread"] <= min_spread:
            raise ValueError(f"{pest_type} raw validation scores are constant or effectively constant.")
        return diagnostics

    def fit_calibration(
        self,
        split: Optional[str] = "calibration",
        min_cases: int = 2,
        optimize_level_thresholds: bool = False,
    ):
        """
        Fit pest-specific risk calibration from completed validation results.

        By default, calibration uses only cases assigned to the ``calibration``
        split. Pass ``split=None`` to fit on all available results for
        exploratory analysis.
        """
        if not self.results:
            raise ValueError(
                "No validation results available. "
                "Call run_validation() before fitting calibration."
            )

        selected_results = [
            result for result in self.results
            if split is None or result.case.split == split
        ]
        if not selected_results:
            raise ValueError(f"No validation results available for calibration split: {split}")

        from .calibration import fit_risk_calibration

        self.calibration = fit_risk_calibration(
            selected_results,
            source_split=split or "all_results",
            min_cases=min_cases,
            optimize_level_thresholds=optimize_level_thresholds,
        )
        return self.calibration

    def apply_calibration(self, calibration=None) -> List[ValidationResult]:
        """
        Apply fitted calibration curves to current validation results.

        Raw simulation scores are retained on each ``ValidationResult`` as
        ``raw_predicted_risk`` and ``raw_predicted_level``.
        """
        calibration = calibration or self.calibration
        if calibration is None:
            raise ValueError("No calibration is available to apply.")

        for result in self.results:
            raw_score = (
                result.raw_predicted_risk
                if result.raw_predicted_risk is not None
                else result.predicted_risk
            )
            calibrated_risk = calibration.apply_score(
                raw_score,
                result.case.pest_type,
            )
            calibrated_level = calibration.predict_level(
                calibrated_risk,
                result.case.pest_type,
                raw_score=raw_score,
            )
            result.apply_calibrated_prediction(
                calibrated_risk,
                calibrated_level,
                calibration.method,
            )

        self._metrics = None
        return self.results

    def compute_split_metrics(
        self,
        bootstrap_iterations: int = 0,
        confidence: float = 0.95,
        seed: Optional[int] = None,
    ) -> Dict[str, ValidationMetrics]:
        """Compute metrics for each split present in the validation results."""
        split_names = sorted({result.case.split for result in self.results})
        return {
            split: self.compute_metrics(
                split=split,
                bootstrap_iterations=bootstrap_iterations,
                confidence=confidence,
                seed=seed,
            )
            for split in split_names
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of validation results.
        
        Returns
        -------
        dict
            Summary statistics
        """
        if not self.results:
            return {"status": "No results available"}
        
        # Compute metrics if not already done
        if self._metrics is None:
            self.compute_metrics()
        
        return {
            "total_cases": len(self.results),
            "correct_predictions": sum(r.match for r in self.results),
            "incorrect_predictions": sum(not r.match for r in self.results),
            "accuracy_pct": self._metrics.overall_accuracy_pct,
            "precision": self._metrics.classification.precision,
            "recall": self._metrics.classification.recall,
            "f1_score": self._metrics.classification.f1_score,
            "mae": self._metrics.regression.mae,
            "rmse": self._metrics.regression.rmse,
            "avg_simulation_time_s": np.mean([r.simulation_time_s for r in self.results]),
            "data_range": self.data_loader.get_date_range(),
        }
    
    def print_summary(self) -> None:
        """Print a formatted summary of validation results."""
        if self._metrics is None and self.results:
            self.compute_metrics()
        
        if self._metrics:
            print(self._metrics.summary_string())
        else:
            print("No validation results available.")
    
    def get_results_dataframe(self) -> "pd.DataFrame":
        """
        Get results as a pandas DataFrame.
        
        Returns
        -------
        pd.DataFrame
            Results in tabular format
        """
        import pandas as pd
        
        if not self.results:
            return pd.DataFrame()
        
        return pd.DataFrame([r.to_dict() for r in self.results])
    
    def export_results_csv(self, filepath: str) -> None:
        """
        Export validation results to CSV.
        
        Parameters
        ----------
        filepath : str
            Output file path
        """
        df = self.get_results_dataframe()
        df.to_csv(filepath, index=False)
        logger.info(f"Results exported to {filepath}")
    
    def __repr__(self) -> str:
        n_results = len(self.results) if self.results else 0
        n_cases = len(self._cases) if self._cases else 0
        return f"ValidationRunner(cases={n_cases}, results={n_results})"
