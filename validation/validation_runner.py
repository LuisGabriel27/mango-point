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
    
    # Error for regression analysis
    error: float = 0.0
    
    def __post_init__(self):
        """Compute error after initialization."""
        # Normalize actual value to 0-1 scale for comparison
        actual_normalized = normalize_pest_value_to_risk(
            self.case.actual_value,
            self.case.pest_type,
        )
        self.error = abs(self.predicted_risk - actual_normalized)
    
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
        """
        self.data_loader = HistoricalDataLoader(data_path)
        self.weather_generator = HistoricalWeatherGenerator(
            seed=seed,
            historical_weather_path=historical_weather_path,
        )
        self.seed = seed
        self.results: List[ValidationResult] = []
        self._cases: List[ValidationCase] = []
        self._metrics: Optional[ValidationMetrics] = None
        
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
                )
                cases.append(case)
                
                if max_cases and len(cases) >= max_cases:
                    break
            
            # Generate Cecid Fly cases (when biologically relevant)
            if include_cecid and record.mango_stage == "fruitlet":
                case_counter += 1
                # Cecid Fly needs rainfall-triggered emergence
                weather_scenario = "rainy" if record.cecid_fly_infestation_pct > 0 else "typical"
                
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
    
    def _run_single_validation(
        self,
        case: ValidationCase,
        hours: int = DEFAULT_HOURS,
        monte_carlo_runs: int = DEFAULT_MONTE_CARLO_RUNS,
        grid_size: int = DEFAULT_GRID_SIZE,
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
        
        # Create weather for this case
        weather_df = self.weather_generator.generate(
            year=case.year,
            month=case.month,
            hours=hours,
            scenario=case.weather_scenario,
        )
        weather = self._WeatherTimeSeries.from_dataframe(weather_df)
        weather_stats = self.weather_generator.get_summary_stats(weather_df)
        
        # Create grid with some initial infestation
        grid = self._OrchardGrid(rows=grid_size, cols=grid_size)
        
        # Plant trees (full grid for simplicity)
        tree_mask = np.ones((grid_size, grid_size), dtype=bool)
        grid.plant_trees(tree_mask, self._CellState.UNBAGGED)
        
        # Seed initial infestation (1-3 random cells)
        case_seed = int(hashlib.sha256(case.case_id.encode("utf-8")).hexdigest()[:8], 16)
        np.random.seed(self.seed + case_seed % 10000)
        n_seeds = np.random.randint(1, 4)
        seed_positions = [
            (np.random.randint(0, grid_size), np.random.randint(0, grid_size))
            for _ in range(n_seeds)
        ]
        grid.seed_infestation(seed_positions)
        
        # Select appropriate gate based on pest type
        if case.pest_type == "cecid":
            gates = [self._CecidFlyGate()]
        else:
            gates = [self._FruitFlyGate()]
        
        # Map orchard stage
        orchard_stage = self._map_stage_to_enum(case.orchard_stage)
        
        # Determine days since flowering for sugar index
        # Mature stage: 60-90 days post-flowering
        days_flowering_map = {
            "dormant": 0,
            "flowering": 10,
            "fruitlet": 30,
            "mature": 75,
        }
        days_since_flowering = days_flowering_map.get(case.orchard_stage, 60)
        
        # Run Monte Carlo simulation for risk estimation
        try:
            mean_risk = self._SimulationEngine.monte_carlo(
                grid=grid,
                weather=weather,
                n_runs=monte_carlo_runs,
                n_steps=hours,
                seed=self.seed,
                gates=gates,
                orchard_stage=orchard_stage,
                days_since_flowering=days_since_flowering,
                progress=False,
            )
            
            # Compute summary statistics
            # Peak risk: maximum value in the mean risk grid
            peak_risk = float(mean_risk.max())
            
            # Average risk across all non-empty cells
            avg_risk = float(mean_risk.mean())
            
            # Count "at risk" cells (risk > 0.3)
            n_at_risk = int((mean_risk > 0.3).sum())
            
            # Use average risk as the predicted risk score
            predicted_risk = avg_risk
            
        except Exception as e:
            logger.warning(f"Simulation failed for case {case.case_id}: {e}")
            predicted_risk = 0.0
            peak_risk = 0.0
            n_at_risk = 0
        
        elapsed_time = time.time() - start_time
        
        # Convert risk to categorical level
        predicted_level = risk_score_to_level(predicted_risk)
        
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
        )
    
    def run_validation(
        self,
        cases: Optional[List[ValidationCase]] = None,
        hours: int = DEFAULT_HOURS,
        monte_carlo_runs: int = DEFAULT_MONTE_CARLO_RUNS,
        grid_size: int = DEFAULT_GRID_SIZE,
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
            )
            self.results.append(result)
            
            # Log progress
            status = "✓" if result.match else "✗"
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
