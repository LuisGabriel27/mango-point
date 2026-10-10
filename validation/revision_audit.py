"""Reproducible sensitivity and BPI monthly comparison.

Run in a separate CLI process: coefficient overrides are temporary module
globals and are deliberately unsuitable for concurrent API requests.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch
from contextlib import ExitStack
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from core import config, biological_rules, cecid_habitat, grid as grid_module
from core import tree_graph_model
from core.biological_rules import CecidFlyGate, FruitFlyGate
from core.cecid_habitat import CecidHabitatNetwork
from core.config import CellState, OrchardStage
from core.grid import OrchardGrid
from core.simulation_engine import SimulationEngine
from core.tree_graph_model import TreeGraph, TreeGraphEngine, TreeNode, TreeState, build_tree_graph_from_lonlat
from utils import daylight
from utils.solar import MANILA_TZ, clear_sky_shortwave_reference
from utils.weather import WeatherTimeSeries
from validation.calibration import fit_risk_calibration
from validation.historical_data import (
    HistoricalDataLoader, classify_cecid_fly_pct, classify_fruit_fly_cptd,
)
from validation.metrics import risk_score_to_pest_level, normalize_pest_value_to_risk
from validation.validation_runner import ValidationCase, ValidationResult, ValidationRunner


@dataclass(frozen=True)
class Scenario:
    name: str
    pest: str = "cecid"
    parameter: str = "baseline"
    value: Any = "default"
    coefficients: dict = field(default_factory=dict)
    source_presence: float = 1.0
    bagged_fraction: float = 0.5
    initial_moisture: float = 1.0
    light: str | None = None
    radiation_ratio: float = 0.5
    cloud: float | None = 80.0
    temperature: float = 28.0
    wind: float = 2.0
    rain_pattern: str = "dry"
    pressure: float = 1.0
    stage: str | None = None


def sensitivity_scenarios() -> list[Scenario]:
    scenarios = [Scenario("baseline")]
    coefficients = {
        "egg_capacity_hours": ("CECID_EGG_CAPACITY_HOURS", [4.0, 16.0]),
        "adult_max_age_hours": ("CECID_ADULT_MAX_AGE_HOURS", [24, 72]),
        "adult_half_life_hours": ("CECID_ADULT_HALF_LIFE_HOURS", [12.0, 48.0]),
        "soil_half_life_hours": ("CECID_SOIL_WETNESS_HALF_LIFE_HOURS", [24.0, 96.0]),
        "movement_range_m": ("CECID_MAX_RANGE_M", [10.0, 20.0]),
        "wind_direction_assist": ("CECID_WIND_DIRECTION_MAX_ASSIST", [0.0, 0.70]),
        "cloud_min_pct": ("CECID_DAY_CLOUD_MIN_PCT", [30.0, 70.0]),
        "light_bright_ratio": ("CECID_LIGHT_BRIGHT_RATIO", [0.65, 0.95]),
        "daytime_activity_max": ("CECID_CLOUD_DAY_ACTIVITY_MAX", [0.3, 0.9]),
        "bagging_reduction": ("BAG_RESISTANCE", [0.4, 0.9]),
        "spread_probability": ("CECID_BASE_DISPERSAL_PROB", [0.06, 0.24]),
    }
    for parameter, (constant, values) in coefficients.items():
        for value in values:
            scenarios.append(Scenario(f"{parameter}_{value}", parameter=parameter,
                                      value=value, coefficients={constant: value}))
    for value in [0.0, 0.5]:
        scenarios.append(Scenario(f"source_presence_{value}", parameter="source_presence",
                                  value=value, source_presence=value))
    for value in [0.0, 1.0]:
        scenarios.append(Scenario(f"bagged_fraction_{value}", parameter="bagged_fraction",
                                  value=value, bagged_fraction=value))
    for value in [0.0, 0.25]:
        scenarios.append(Scenario(f"initial_moisture_{value}", parameter="initial_moisture",
                                  value=value, initial_moisture=value))
    for light in ["bright_sunshine", "intermittent_sunshine", "dim_overcast"]:
        scenarios.append(Scenario(light, parameter="daylight_condition", value=light, light=light))
    scenarios.extend([
        Scenario("unknown_light", parameter="daylight_evidence", value="missing", cloud=None),
        Scenario("rain_break", parameter="rain_schedule", value="4h rain,1h dry,repeat",
                 rain_pattern="break", light="dim_overcast", initial_moisture=0),
        Scenario("continuous_rain", parameter="rain_schedule", value="2mm/h",
                 rain_pattern="continuous", light="dim_overcast"),
        Scenario("wrong_host_stage", parameter="host_stage", value="mature", stage="mature"),
    ])
    scenarios.append(Scenario("baseline", pest="fruitfly"))
    for parameter, constant, values in [
        ("night_activity", "FRUIT_FLY_NIGHT_ACTIVITY", [0.0, 0.10]),
        ("bagging_reduction", "BAG_RESISTANCE", [0.4, 0.9]),
        ("spread_probability", "FRUIT_FLY_BASE_DISPERSAL_PROB", [0.04, 0.16]),
    ]:
        for value in values:
            scenarios.append(Scenario(f"{parameter}_{value}", pest="fruitfly", parameter=parameter,
                                      value=value, coefficients={constant: value}))
    for value in [22.0, 34.0]:
        scenarios.append(Scenario(f"temperature_{value}", pest="fruitfly", parameter="temperature_c",
                                  value=value, temperature=value))
    for value in [0.0, 0.5]:
        scenarios.append(Scenario(f"source_presence_{value}", pest="fruitfly", parameter="source_presence",
                                  value=value, source_presence=value))
    for value in [0.0, 1.0]:
        scenarios.append(Scenario(f"bagged_fraction_{value}", pest="fruitfly", parameter="bagged_fraction",
                                  value=value, bagged_fraction=value))
    scenarios.append(Scenario("wrong_host_stage", pest="fruitfly", parameter="host_stage",
                              value="fruitlet", stage="fruitlet"))
    return scenarios


@contextmanager
def temporary_coefficients(values: dict):
    """Restore every imported constant even if a simulation raises."""
    modules = (config, biological_rules, cecid_habitat, grid_module, tree_graph_model, daylight)
    with ExitStack() as stack:
        for name, value in values.items():
            if not hasattr(config, name):
                raise ValueError(f"Unknown model coefficient: {name}")
            for module in modules:
                if hasattr(module, name):
                    stack.enter_context(patch.object(module, name, value))
        yield


def orchard_geometry(side: int = 7) -> list[tuple[float, float]]:
    """Ten-metre tree spacing; identical positions in both engines."""
    return [(col * 10.0, row * 10.0) for row in range(side) for col in range(side)]


def scenario_weather(scenario: Scenario, hours: int = 48) -> pd.DataFrame:
    start = datetime(2026, 4, 1, 8, tzinfo=MANILA_TZ)
    rows = []
    for step in range(hours):
        timestamp = start + timedelta(hours=step)
        reference = clear_sky_shortwave_reference(timestamp, 10.585, 122.580)
        rain = 2.0 if scenario.rain_pattern == "continuous" else (
            0.0 if step % 5 == 4 else 2.0
        ) if scenario.rain_pattern == "break" else 0.0
        rows.append({
            "datetime": timestamp, "temperature_c": scenario.temperature,
            "wind_speed_ms": scenario.wind, "wind_dir_deg": 270.0, "rainfall_mm": rain,
            "cloud_cover_pct": scenario.cloud,
            "shortwave_radiation_wm2": reference * scenario.radiation_ratio if scenario.cloud is not None else None,
            "direct_normal_irradiance_wm2": 200.0 if reference > 0 and scenario.cloud is not None else None,
            "daylight_condition": scenario.light,
            "daylight_condition_basis": "assumed" if scenario.light else None,
        })
    return pd.DataFrame(rows)


def run_orchard(scenario: Scenario, mode: str, seed: int, frame: pd.DataFrame,
                side: int = 7, antecedent: list[dict] | None = None) -> dict:
    positions = orchard_geometry(side)
    source_indices = [side * (side // 2) + side // 2, side + 1]
    # Presence uses a separate stream so it does not shift establishment draws.
    presence_rng = np.random.default_rng(seed + 971_003)
    sources = [index for index in source_indices if presence_rng.random() < scenario.source_presence]
    bag_order = np.random.default_rng(8001).permutation([i for i in range(len(positions)) if i not in source_indices])
    bagged = set(bag_order[:round(len(bag_order) * scenario.bagged_fraction)].tolist())
    lonlat = [(122.580 + x / (111320 * np.cos(np.radians(10.585))), 10.585 + y / 111320)
              for x, y in positions]
    rain_history = [float(entry.get("rainfall_mm", 0.0)) for entry in antecedent or []]
    stage = OrchardStage.FRUITLET if (scenario.stage or ("fruitlet" if scenario.pest == "cecid" else "mature")) == "fruitlet" else OrchardStage.MATURE
    with temporary_coefficients(scenario.coefficients):
        weather = WeatherTimeSeries.from_dataframe(frame.copy())
        gate = CecidFlyGate(initial_soil_moisture_score=scenario.initial_moisture) if scenario.pest == "cecid" else FruitFlyGate()
        common = dict(gates=[gate], orchard_stage=stage, initial_rainfall_history=rain_history,
                      cecid_antecedent_weather=antecedent, days_since_flowering=75)
        if mode == "grid":
            grid = OrchardGrid(2 * side - 1, 2 * side - 1)
            keys = [(2 * (i // side), 2 * (i % side)) for i in range(len(positions))]
            for i, key in enumerate(keys):
                grid.set_state(*key, CellState.INFESTED if scenario.pest == "fruitfly" and i in sources
                               else CellState.BAGGED if i in bagged else CellState.UNBAGGED)
            if scenario.pest == "cecid":
                network = CecidHabitatNetwork.from_lonlat({keys[i]: lonlat[i] for i in sources},
                                                          dict(zip(keys, lonlat)), [])
                common.update(cecid_source_pressures={keys[i]: scenario.pressure for i in sources},
                              cecid_habitat_network=network)
            engine = SimulationEngine(grid, weather, **common)
        elif mode == "tree_graph":
            nodes = [TreeNode(i, str(i), *lonlat[i], *positions[i], 2.5,
                             TreeState.INFESTED if scenario.pest == "fruitfly" and i in sources
                             else TreeState.BAGGED if i in bagged else TreeState.SUSCEPTIBLE)
                     for i in range(len(positions))]
            if scenario.pest == "cecid":
                network = CecidHabitatNetwork.from_lonlat({i: lonlat[i] for i in sources}, dict(enumerate(lonlat)), [])
                common.update(cecid_source_pressures={i: scenario.pressure for i in sources}, cecid_habitat_network=network)
            # Align rate variations relative to each engine's own baseline.
            multiplier = scenario.coefficients.get("FRUIT_FLY_BASE_DISPERSAL_PROB", 0.08) / 0.08
            engine = TreeGraphEngine(TreeGraph(nodes, max_dist=20), weather, pest_type=scenario.pest,
                                     lambda0=config.TG_LAMBDA0 * multiplier, **common)
        else:
            raise ValueError(f"Unknown engine: {mode}")
        if scenario.pest == "cecid":
            # Constructor defaults are bound at import, so set this explicitly.
            engine.cecid_cohort_model.egg_capacity_hours = config.CECID_EGG_CAPACITY_HOURS
        np.random.seed(seed)
        result = engine.run(n_steps=len(frame), progress=False)
        target_indices = [i for i in range(len(positions)) if i not in source_indices]
        outcomes = []
        for snapshot in result.snapshots:
            states = [int(snapshot["state"][key]) for key in keys] if mode == "grid" else snapshot["states"]
            outcomes.append([i for i in target_indices if int(states[i]) == int(CellState.INFESTED)])
        affected = outcomes[-1]
        first = next((i for i, indices in enumerate(outcomes) if indices), None)
        distances = [min(np.linalg.norm(np.array(positions[i]) - positions[j]) for j in sources) for i in affected] if sources else []
        lifecycle = engine.cecid_cohort_model.lifecycle_diagnostics() if scenario.pest == "cecid" else {}
        return {
            "scenario": scenario.name, "pest": scenario.pest, "mode": mode, "seed": seed,
            "parameter": scenario.parameter, "value": str(scenario.value), "source_count": len(sources),
            "target_count": len(target_indices), "new_affected": len(affected),
            "affected_fraction": len(affected) / len(target_indices),
            "first_affected_hour": first, "max_distance_m": max(distances, default=0.0),
            "emergence_events": len(engine.cecid_cohort_events) if scenario.pest == "cecid" else 0,
            **lifecycle,
        }


def summarize_sensitivity(rows: pd.DataFrame) -> pd.DataFrame:
    records = []
    for (pest, mode, name), group in rows.groupby(["pest", "mode", "scenario"], sort=False):
        baseline = rows[(rows.pest == pest) & (rows["mode"] == mode) & (rows.scenario == "baseline")]
        paired = group.merge(baseline[["seed", "new_affected"]], on="seed", suffixes=("", "_baseline"))
        if baseline.empty or len(paired) != len(group):
            raise ValueError(f"Missing or duplicated paired baseline seeds for {pest}/{mode}/{name}")
        deltas = paired.new_affected - paired.new_affected_baseline
        records.append({
            "pest": pest, "mode": mode, "scenario": name, "parameter": group.parameter.iloc[0],
            "value": group.value.iloc[0], "runs": len(group), "mean_new_affected": group.new_affected.mean(),
            "p05_new_affected": group.new_affected.quantile(0.05), "p95_new_affected": group.new_affected.quantile(0.95),
            "mean_paired_change": deltas.mean(), "paired_change_se": deltas.std(ddof=1) / np.sqrt(len(deltas)) if len(deltas) > 1 else 0.0,
            "runs_with_spread": int((group.new_affected > 0).sum()),
            "mean_first_hour_among_spread": group.first_affected_hour.mean(),
            "mean_max_distance_m": group.max_distance_m.mean(),
        })
    return pd.DataFrame(records)


def bpi_cases(records, pest: str, use_managed: bool = True) -> list[ValidationCase]:
    """Keep every month; host availability is an assumption, never a label filter."""
    cases = []
    for record in records:
        value = (record.cecid_fly_infestation_pct if pest == "cecid" else
                 record.fruit_fly_managed_cptd if use_managed else record.fruit_fly_unmanaged_cptd)
        level = classify_cecid_fly_pct(value).value if pest == "cecid" else classify_fruit_fly_cptd(value).value
        cases.append(ValidationCase(
            case_id=f"{pest}-{record.year}-{record.month:02d}", year=record.year, month=record.month,
            date_str=record.date_str, pest_type=pest, orchard_stage="fruitlet" if pest == "cecid" else "mature",
            actual_value=value, actual_level=level, weather_scenario="typical", season=record.season,
            source_record=record, split="testing" if record.year == 2025 else "calibration",
        ))
    return cases


def comparison_metrics(actual: list[float], predicted: list[float], pest: str) -> dict:
    if not actual:
        return {"n": 0}
    a, p = np.array(actual), np.array(predicted)
    al = [risk_score_to_pest_level(v, pest) for v in a]
    pl = [risk_score_to_pest_level(v, pest) for v in p]
    levels = ["Low", "Medium", "High"]
    confusion = [[sum(x == row and y == col for x, y in zip(al, pl)) for col in levels] for row in levels]
    recalls = [confusion[i][i] / sum(confusion[i]) for i in range(3) if sum(confusion[i])]
    positives = a > 0  # Also expose outbreaks hidden by the coarse Low category.
    high = np.array([v != "Low" for v in al])
    warnings = np.array([v != "Low" for v in pl])
    return {
        "n": len(a), "correct": sum(x == y for x, y in zip(al, pl)),
        "accuracy_pct": 100 * np.mean([x == y for x, y in zip(al, pl)]),
        "balanced_accuracy_present_classes_pct": 100 * np.mean(recalls),
        "mae_normalized": float(np.mean(np.abs(a - p))),
        "rmse_normalized": float(np.sqrt(np.mean((a - p) ** 2))),
        "observed_nonzero_months": int(positives.sum()), "observed_medium_high_months": int(high.sum()),
        "missed_medium_high_months": int((high & ~warnings).sum()),
        "false_warning_months": int((~high & warnings).sum()),
        "medium_high_recall": float((high & warnings).sum() / high.sum()) if high.any() else None,
        "levels": levels, "confusion_actual_rows_predicted_columns": confusion,
    }


def compare_bpi(results: list[ValidationResult], records, pest: str, use_managed: bool = True,
                test_year: int = 2025) -> tuple[list[dict], dict]:
    results = [result for result in results if result.case.year <= test_year]
    train = [result for result in results if result.case.year < test_year]
    calibration = fit_risk_calibration(train, source_split=f"years_before_{test_year}", optimize_level_thresholds=False)
    rows = []
    by_date = {(r.year, r.month): r for r in records}
    value_for = lambda r: r.cecid_fly_infestation_pct if pest == "cecid" else r.fruit_fly_managed_cptd if use_managed else r.fruit_fly_unmanaged_cptd
    majority = max(["Low", "Medium", "High"], key=lambda level: sum(r.case.actual_level == level for r in train))
    # A training median is both a numeric constant baseline and the source of its label.
    median = float(np.median([r._actual_normalized() for r in train]))
    for result in results:
        case = result.case
        previous_date = (case.year, case.month - 1) if case.month > 1 else (case.year - 1, 12)
        previous = by_date.get(previous_date)
        seasonal_values = [r._actual_normalized() for r in train if r.case.month == case.month]
        raw = result.predicted_risk
        rows.append({
            "pest": pest, "series": "cecid_infestation_pct" if pest == "cecid" else "managed_cptd" if use_managed else "unmanaged_cptd",
            "date": case.date_str, "split": "testing" if case.year == test_year else "calibration", "actual_value": case.actual_value,
            "actual_risk": result._actual_normalized(), "actual_level": case.actual_level,
            "raw_risk": raw, "calibrated_risk": calibration.apply_score(raw, pest),
            "constant_training_median": median, "seasonal_training_median": float(np.median(seasonal_values)),
            "previous_month": normalize_pest_value_to_risk(value_for(previous), pest) if previous else median,
            "majority_training_class": majority,
        })
    methods = ["raw_risk", "calibrated_risk", "constant_training_median", "seasonal_training_median", "previous_month"]
    score_range = [min(r.predicted_risk for r in results), max(r.predicted_risk for r in results)]
    summary = {"test_year": test_year, "calibration": calibration.to_dict(), "splits": {},
               "raw_score_range": score_range, "raw_score_is_constant": score_range[1] - score_range[0] <= 1e-9}
    for split in ["calibration", "testing"]:
        group = [row for row in rows if row["split"] == split]
        actual = [row["actual_risk"] for row in group]
        summary["splits"][split] = {method: comparison_metrics(actual, [row[method] for row in group], pest) for method in methods}
        summary["splits"][split]["majority_training_class"] = {
            "n": len(group), "class": majority,
            "accuracy_pct": 100 * np.mean([row["actual_level"] == majority for row in group]),
        }
    return rows, summary


def input_audit(root: Path) -> dict:
    paths = [root / "data/guimaras_pest_data_2022_2025.csv", root / "data/hourly_weather.csv", root / "data/trees.geojson"]
    pest, weather = [pd.read_csv(path) for path in paths[:2]]
    timestamps = pd.to_datetime(weather.datetime)
    records = HistoricalDataLoader(paths[0]); records.ensure_loaded()
    legacy = ValidationRunner(data_path=paths[0]).generate_validation_cases()
    return {
        "model_version": config.SIMULATION_MODEL_VERSION,
        "inputs": [{"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths],
        "bpi_months": len(pest), "bpi_start": records.records[0].date_str, "bpi_end": records.records[-1].date_str,
        "weather_rows": len(weather), "weather_start": str(timestamps.min()), "weather_end": str(timestamps.max()),
        "weather_duplicate_timestamps": int(timestamps.duplicated().sum()),
        "weather_nonhourly_gaps": int((timestamps.diff().dropna() != pd.Timedelta(hours=1)).sum()),
        "missing_daylight_columns": [field for field in ["cloud_cover_pct", "shortwave_radiation_wm2", "direct_normal_irradiance_wm2"] if field not in weather],
        "legacy_cases": len(legacy),
        "mapped_tree_count": len(json.loads(paths[2].read_text(encoding="utf-8"))["features"]),
        "legacy_excluded_cecid_outbreaks": [{"date": r.date_str, "infestation_pct": r.cecid_fly_infestation_pct, "assumed_stage": r.mango_stage}
                                           for r in records.records if r.mango_stage != "fruitlet" and r.cecid_fly_infestation_pct >= 5],
        "held_out_year": 2025, "held_out_months_per_series": int((pest.year == 2025).sum()),
        "bpi_denominators_and_inspection_dates_available": False,
    }


def run_sensitivity(output: Path, seeds: list[int]) -> pd.DataFrame:
    rows = []
    scenarios = sensitivity_scenarios()
    for index, scenario in enumerate(scenarios):
        frame = scenario_weather(scenario)
        for mode in ["grid", "tree_graph"]:
            for seed in seeds:
                rows.append(run_orchard(scenario, mode, seed, frame))
        print(f"Sensitivity {index + 1}/{len(scenarios)}: {scenario.pest}/{scenario.name}", flush=True)
    raw = pd.DataFrame(rows)
    raw.to_csv(output / "sensitivity_runs.csv", index=False)
    summary = summarize_sensitivity(raw)
    summary.to_csv(output / "sensitivity_summary.csv", index=False)
    (output / "sensitivity_design.json").write_text(json.dumps({
        "model_version": config.SIMULATION_MODEL_VERSION, "seeds": seeds, "hours": 48,
        "orchard": {"trees": 49, "target_trees": 47, "spacing_m": 10, "crown_radius_m": 2.5, "sources": 2},
        "external_sources": False, "antecedent": "none; fresh soil batches at Hour 0 for controlled experiments",
        "baseline_presence": 1.0, "scenarios": [asdict(scenario) for scenario in scenarios],
        "intervals": "5th-95th run quantiles; stochastic variability, not confidence in field accuracy",
        "fruitfly_rate_variation": "grid base probability and tree-graph lambda0 multiplied by the same relative factor",
        "adult_72h_case": "exploratory stress test outside the project's 48h expert scenario",
    }, indent=2), encoding="utf-8")
    return summary


_BPI_WORKER = None
_BPI_GRAPH = None


def _initialize_bpi_worker(weather_path: str):
    global _BPI_WORKER, _BPI_GRAPH
    _BPI_WORKER = ValidationRunner(seed=42, historical_weather_path=weather_path, require_historical_weather=True)
    features = json.loads((Path(weather_path).parent / "trees.geojson").read_text(encoding="utf-8"))["features"]
    coordinates = [feature["geometry"]["coordinates"] for feature in features]
    origin_lon = min(point[0] for point in coordinates)
    origin_lat = min(point[1] for point in coordinates)
    latitude = np.mean([point[1] for point in coordinates])
    _BPI_GRAPH = build_tree_graph_from_lonlat(features, origin_lon, origin_lat, 111320.0,
                                             111320 * np.cos(np.radians(latitude)),
                                             max_dist=config.FRUIT_FLY_TG_MAX_NEIGHBOR_DIST_M)


def _mapped_bpi_case(case, runs: int, windows: int) -> ValidationResult:
    fractions = []
    frames = _BPI_WORKER.weather_generator.generate_monthly_windows(case.year, case.month, 48, windows, "typical")
    for window_index, frame in enumerate(frames):
        rng = np.random.default_rng(_BPI_WORKER._case_seed(case, window_index * 1000))
        sources = rng.choice(len(_BPI_GRAPH.nodes), size=int(rng.integers(1, 4)), replace=False).tolist()
        for node in _BPI_GRAPH.nodes:
            node.state = TreeState.INFESTED if node.index in sources else TreeState.SUSCEPTIBLE
        weather = WeatherTimeSeries.from_dataframe(frame)
        for run in range(runs):
            common = dict(orchard_stage=OrchardStage.FRUITLET if case.pest_type == "cecid" else OrchardStage.MATURE,
                          days_since_flowering=75, pest_type=case.pest_type)
            if case.pest_type == "cecid":
                target_positions = {node.index: (node.lon, node.lat) for node in _BPI_GRAPH.nodes}
                common.update(cecid_source_pressures={index: 1.0 for index in sources},
                              cecid_habitat_network=CecidHabitatNetwork.from_lonlat(
                                  {index: target_positions[index] for index in sources}, target_positions, []))
            np.random.seed(42 + window_index * 1000 + run)
            engine = TreeGraphEngine(_BPI_GRAPH, weather, **common)
            result = engine.run(n_steps=48, progress=False)
            fractions.append(float(np.mean(np.array(result.snapshots[-1]["states"]) == TreeState.INFESTED)))
    raw = float(np.mean(fractions))
    level = risk_score_to_pest_level(raw, case.pest_type)
    return ValidationResult(case=case, predicted_risk=raw, predicted_level=level, match=level == case.actual_level,
                            risk_features={"monthly_windows": len(frames)})


def _bpi_worker_case(task):
    case, runs, windows, mode = task
    if mode == "tree_graph":
        return _mapped_bpi_case(case, runs, windows)
    return _BPI_WORKER._run_single_validation(case, hours=48, monte_carlo_runs=runs,
                                             grid_size=20, monthly_windows=windows,
                                             score_mode="mean_risk", carryover_weight=0.0)


def run_bpi(output: Path, root: Path, runs: int, windows: int = 4, workers: int = 1, mode: str = "grid") -> dict:
    """Retest raw simulator separately from calibration and previous-label baselines."""
    runner = ValidationRunner(seed=42, historical_weather_path=root / "data/hourly_weather.csv", require_historical_weather=True)
    runner.data_loader.ensure_loaded()
    records = runner.data_loader.records
    all_rows, rolling_rows, summaries = [], [], {}
    for pest in ["cecid", "fruitfly"]:
        cases = bpi_cases(records, pest)
        results = []
        with ExitStack() as stack:
            if workers > 1:
                pool = stack.enter_context(ProcessPoolExecutor(max_workers=workers, initializer=_initialize_bpi_worker,
                                                               initargs=(str(root / "data/hourly_weather.csv"),)))
                iterator = pool.map(_bpi_worker_case, [(case, runs, windows, mode) for case in cases])
            elif mode == "tree_graph":
                _initialize_bpi_worker(str(root / "data/hourly_weather.csv"))
                iterator = (_mapped_bpi_case(case, runs, windows) for case in cases)
            else:
                iterator = (runner._run_single_validation(case, hours=48, monte_carlo_runs=runs,
                                                         grid_size=20, monthly_windows=windows,
                                                         score_mode="mean_risk", carryover_weight=0.0) for case in cases)
            for i, result in enumerate(iterator):
                if result.risk_features.get("monthly_windows") != windows:
                    raise RuntimeError(f"Incomplete simulation windows for {result.case.case_id}")
                results.append(result)
                print(f"BPI {pest} {i + 1}/{len(cases)}: {result.case.date_str} raw={result.predicted_risk:.5f}", flush=True)
        rows, summary = compare_bpi(results, records, pest)
        all_rows.extend(rows); summaries[pest] = summary
        summaries[pest]["earlier_year_checks"] = {}
        for test_year in [2023, 2024]:
            earlier_rows, earlier = compare_bpi(results, records, pest, test_year=test_year)
            summaries[pest]["earlier_year_checks"][str(test_year)] = earlier
            rolling_rows.extend({**row, "test_year": test_year} for row in earlier_rows if row["split"] == "testing")
        if pest == "fruitfly":
            # Same raw exposure scores compared with the second monitoring series;
            # this does not pretend that management was independently simulated.
            alternate = bpi_cases(records, pest, use_managed=False)
            unmanaged_results = [ValidationResult(case=case, predicted_risk=result.predicted_risk,
                                                  predicted_level=result.predicted_level, match=False)
                                 for case, result in zip(alternate, results)]
            rows, summary = compare_bpi(unmanaged_results, records, pest, use_managed=False)
            all_rows.extend(rows); summaries["fruitfly_unmanaged"] = summary
            summaries["fruitfly_unmanaged"]["earlier_year_checks"] = {}
            for test_year in [2023, 2024]:
                earlier_rows, earlier = compare_bpi(unmanaged_results, records, pest, use_managed=False, test_year=test_year)
                summaries["fruitfly_unmanaged"]["earlier_year_checks"][str(test_year)] = earlier
                rolling_rows.extend({**row, "test_year": test_year} for row in earlier_rows if row["split"] == "testing")
    prefix = "bpi" if mode == "grid" else "bpi_tree_graph"
    pd.DataFrame(all_rows).to_csv(output / f"{prefix}_predictions.csv", index=False)
    pd.DataFrame(rolling_rows).to_csv(output / f"{prefix}_earlier_year_predictions.csv", index=False)
    summaries["design"] = {
        "model_version": config.SIMULATION_MODEL_VERSION, "calibration_years": [2022, 2023, 2024], "testing_year": 2025,
        "hours_per_window": 48, "windows_per_month": windows, "monte_carlo_runs_per_window": runs,
        "workers": workers, "parallelism": "independent processes; results preserve case ordering and fixed seeds",
        "grid": "20x20 artificial all-tree grid, 5m cell spacing; not reconstructed historical trees",
        "engine": mode,
        "mapped_tree_graph": "194 present-day mapped tree points and crown widths; historical states/phenology not reconstructed; Cecid habitat relay enabled",
        "score": "mean final affected-cell/tree frequency, including 1-3 seeded hosts; no weather blend or BPI carryover",
        "source_initialization": "1-3 deterministic assumed fresh sources per month/window; not inferred from target labels",
        "soil_context": "zero initial rainfall; weather builds moisture within each window; no adult antecedent replay",
        "host_stage": "fruitlet for Cecid, mature for Fruit Fly in ALL months; unmeasured scenario assumption",
        "daylight": "unknown (archive lacks cloud/GHI/DNI); Cecid daytime exception unavailable, solar twilight still active",
        "calibration": "nonnegative affine fitted on 2022-2024 only; biological coefficients unchanged; no optimized class cutoffs",
        "unmanaged": "separate score mapping to unmanaged catches; management differences are not simulated",
        "numeric_normalization": "Cecid percent/100; both Fruit Fly series use the existing managed CPTD/40 proxy clipped at 1; unmanaged catches above 40 lose magnitude in normalized errors",
        "interpretation": "monthly aggregate plausibility comparison; cannot establish tree/hour/fruit-level forecast accuracy",
        "evaluation_status": "retrospective split: 2025 records were already in this repository, not a prospective unseen trial",
        "earlier_year_checks": "2023 tested with 2022 mapping; 2024 tested with 2022-2023 mapping; includes higher Cecid classes absent in 2025",
        "previous_month_baseline": "rolling one-month-ahead comparison uses the preceding observation, including earlier 2025 observations",
    }
    (output / f"{prefix}_metrics.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    return summaries


def export_figures(output: Path, summary: pd.DataFrame | None = None):
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if summary is not None:
        fig, axes = plt.subplots(1, 2, figsize=(14, 9))
        for ax, pest in zip(axes, ["cecid", "fruitfly"]):
            group = summary[(summary.pest == pest) & (summary.scenario != "baseline")]
            order = group.groupby("scenario").mean_paired_change.mean().sort_values().index
            for offset, mode in [(-0.18, "grid"), (0.18, "tree_graph")]:
                values = group[group["mode"] == mode].set_index("scenario").reindex(order)
                ax.barh(np.arange(len(order)) + offset, values.mean_paired_change,
                        xerr=values.paired_change_se, height=0.34, label=mode, error_kw={"elinewidth": 0.7})
            ax.set_yticks(np.arange(len(order)), order, fontsize=7)
            ax.axvline(0, color="black", linewidth=0.7)
            ax.set_title(pest); ax.set_xlabel("Mean change in newly affected trees (47 targets)"); ax.legend()
        design_path = output / "sensitivity_design.json"
        version = json.loads(design_path.read_text(encoding="utf-8")).get("model_version", "Version not recorded") if design_path.exists() else "Version not recorded"
        fig.suptitle(f"{version}\nSensitivity controls: repeated seeds; error bars = one standard error")
        fig.tight_layout(); fig.savefig(output / "sensitivity.png", dpi=180); plt.close(fig)
    for prefix in ["bpi", "bpi_tree_graph"]:
        predictions = output / f"{prefix}_predictions.csv"
        if not predictions.exists():
            continue
        data = pd.read_csv(predictions)
        fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
        for ax, series in zip(axes, ["cecid_infestation_pct", "managed_cptd", "unmanaged_cptd"]):
            group = data[data.series == series]
            dates = pd.to_datetime(group.date + "-01")
            ax.plot(dates, group.actual_risk, "o-", markersize=3, label="BPI normalized observation")
            ax.plot(dates, group.calibrated_risk, label="Simulator with training-only mapping")
            ax.plot(dates, group.seasonal_training_median, ":", label="Training seasonal median")
            ax.axvline(datetime(2025, 1, 1), color="black", linestyle="--", label="2025 test split")
            ax.set_title(series); ax.set_ylabel("Normalized proxy (0-1)"); ax.set_ylim(-0.02, 1.02)
        axes[0].legend(fontsize=8, ncol=2)
        engine_label = "Grid, artificial orchard" if prefix == "bpi" else "Tree Graph, mapped orchard"
        metrics_path = output / f"{prefix}_metrics.json"
        version = json.loads(metrics_path.read_text(encoding="utf-8")).get("design", {}).get("model_version", "Version not recorded") if metrics_path.exists() else "Version not recorded"
        fig.suptitle(f"{engine_label}: BPI monthly comparison\n{version}, normalized proxies")
        fig.tight_layout(); fig.savefig(output / f"{prefix}_comparison.png", dpi=180); plt.close(fig)


def export_daylight_response(output: Path) -> pd.DataFrame:
    """Probe cloud/light coefficients where the cloud ramp is not saturated."""
    timestamp = datetime(2026, 4, 1, 12, tzinfo=MANILA_TZ)
    reference = clear_sky_shortwave_reference(timestamp, 10.585, 122.580)
    settings = [("baseline", {})]
    for name, values in {
        "CECID_DAY_CLOUD_MIN_PCT": [30.0, 70.0], "CECID_DAY_CLOUD_FULL_PCT": [65.0, 95.0],
        "CECID_LIGHT_DIM_RATIO": [0.1, 0.4], "CECID_LIGHT_BRIGHT_RATIO": [0.65, 0.95],
        "CECID_LIGHT_DNI_REFERENCE_WM2": [400.0, 1200.0], "CECID_CLOUD_DAY_ACTIVITY_MAX": [0.3, 0.9],
    }.items():
        settings.extend((f"{name}={value}", {name: value}) for value in values)
    rows = []
    for cloud in [50, 65, 80]:
        for brightness in [0.2, 0.5, 0.9]:
            for setting, values in settings:
                with temporary_coefficients(values):
                    light = daylight.daylight_light_components({"cloud_cover_pct": cloud,
                        "shortwave_radiation_wm2": reference * brightness, "direct_normal_irradiance_wm2": 300},
                        timestamp, 10.585, 122.580)
                    rows.append({"cloud_cover_pct": cloud, "ghi_clear_sky_ratio": brightness,
                                 "dni_wm2": 300, "setting": setting,
                                 "light_score": light["daylight_light_score"],
                                 "daytime_activity_weight": config.CECID_CLOUD_DAY_ACTIVITY_MAX * light["daylight_light_score"]})
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "daylight_response_sensitivity.csv", index=False)
    return frame
