"""Replay the calendar-filtered BPI defense design without tuning model biology.

The historical export is a reference, not executable provenance. The replay
fixes 30 realizations for both engines and exports every sampled window/source
and the separate simulation, weather, and observed-prior contributions.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from core import config
from core.tree_graph_model import TreeGraphEngine, TreeState, build_tree_graph_from_lonlat
from utils.weather import WeatherTimeSeries
from validation.metrics import compute_full_metrics, normalize_pest_value_to_risk, risk_score_to_pest_level
from validation.validation_runner import ValidationRunner, ValidationResult


MODES = {"grid": "Enhanced Cellular Automata Grid", "tree_graph": "Enhanced Tree Graph"}
_RUNNER = None
_GRAPH = None


def load_reference(path: Path, cases) -> pd.DataFrame:
    """Reject changed observations, missing cases, and duplicate engine rows."""
    reference = pd.read_csv(path).fillna("")
    expected = {(case.date_str, "Cecid Fly" if case.pest_type == "cecid" else "Fruit Fly"): case
                for case in cases}
    if len(reference) != 2 * len(cases):
        raise ValueError("Legacy reference must contain exactly one row per case and engine")
    for mode, label in MODES.items():
        rows = reference[reference["Simulation Model"] == label]
        keys = list(zip(rows["Date"], rows["Pest"]))
        if len(keys) != len(set(keys)) or set(keys) != set(expected):
            raise ValueError(f"Legacy reference cases differ for {mode}")
        for _, row in rows.iterrows():
            case = expected[row["Date"], row["Pest"]]
            if (not np.isclose(float(row["BPI Ground Value"]), case.actual_value, atol=1e-8, rtol=0)
                    or row["BPI Ground Risk Level"] != case.actual_level
                    or row["Calibration/Test Role"] != case.split
                    or row["Orchard Stage Used"].lower() != case.orchard_stage
                    or int(row["Monthly 48-hour Windows"]) != 4
                    or row["Score Mode"] != "composite"
                    or not np.isclose(float(row["Applied Carryover Weight"]), 0.65 if case.pest_type == "cecid" else 0.1)
                    or not np.isclose(float(row["Previous Month Pest Risk Score"]),
                                      case.previous_actual_risk, atol=0.000051, rtol=0)):
                raise ValueError(f"Legacy inputs differ for {mode}/{case.case_id}")
    return reference


def parse_sources(value: str, known_ids: set[str]) -> list[list[str]]:
    windows = [[item.strip() for item in window.split(";")] for window in value.split("|")]
    if len(windows) != 4 or any(not window or len(window) != len(set(window))
                                or not set(window) <= known_ids for window in windows):
        raise ValueError("Saved graph sources must contain four valid, unique tree-ID lists")
    return windows


def initialize_worker(root: str):
    global _RUNNER, _GRAPH
    root = Path(root)
    _RUNNER = ValidationRunner(seed=42, historical_weather_path=root / "data/hourly_weather.csv",
                               require_historical_weather=True)
    features = json.loads((root / "data/trees.geojson").read_text(encoding="utf-8"))["features"]
    points = np.array([feature["geometry"]["coordinates"][:2] for feature in features])
    # Freeze the legacy graph default, rather than switch its spatial design to
    # the current operational Fruit Fly 25 m graph during this comparison.
    _GRAPH = build_tree_graph_from_lonlat(features, points[:, 0].min(), points[:, 1].min(),
                                         111320.0, 111320.0 * np.cos(np.radians(points[:, 1].mean())),
                                         max_dist=20.0)


def run_case(task):
    case, mode, runs, source_ids = task
    runner = _RUNNER
    started = time.perf_counter()
    frames = runner.weather_generator.generate_monthly_windows(case.year, case.month, 48, 4,
                                                                 case.weather_scenario)
    if len(frames) != 4 or any(len(frame) != 48 or frame.attrs.get("source") != "historical_weather_csv"
                               or not frame.datetime.diff().dropna().eq(pd.Timedelta(hours=1)).all()
                               for frame in frames):
        raise ValueError(f"Incomplete historical windows for {case.case_id}")
    weight = 0.65 if case.pest_type == "cecid" else 0.10
    runner._load_simulation_modules()
    evidence = []
    for wi, frame in enumerate(frames):
        sources = (runner._seed_positions(case, 20, weight, wi * 1000) if mode == "grid" else source_ids[wi])
        evidence.append({"case_id": case.case_id, "mode": mode, "window": wi + 1,
                         **runner.weather_generator.get_summary_stats(frame),
                         "sources": json.dumps(sources), "runs": runs,
                         "first_run_seed": 42 + wi * 1000, "last_run_seed": 42 + wi * 1000 + runs - 1})
    if mode == "grid":
        result = runner._run_single_validation(case, hours=48, monte_carlo_runs=runs, grid_size=20,
                                               monthly_windows=4, score_mode="composite",
                                               fruitfly_carryover_weight=0.10, cecid_carryover_weight=0.65)
        if (result.risk_features.get("monthly_windows") != 4
                or "mean_mean_risk" not in result.risk_features):
            raise RuntimeError(f"One or more CA simulations failed for {case.case_id}")
    elif mode == "tree_graph":
        features = []
        for wi, frame in enumerate(frames):
            sources = set(source_ids[wi])
            for node in _GRAPH.nodes:
                node.state = TreeState.INFESTED if node.tree_id in sources else TreeState.SUSCEPTIBLE
            pressure = {node.index: 1.0 for node in _GRAPH.nodes if node.tree_id in sources}
            risk_sum = np.zeros(len(_GRAPH.nodes))
            weather = WeatherTimeSeries.from_dataframe(frame)
            for run in range(runs):
                np.random.seed(42 + wi * 1000 + run)
                engine = TreeGraphEngine(_GRAPH, weather, pest_type=case.pest_type,
                                          orchard_stage=runner._map_stage_to_enum(case.orchard_stage),
                                          days_since_flowering=runner._days_since_flowering(case.orchard_stage),
                                          cecid_source_pressures=pressure if case.pest_type == "cecid" else None)
                final = engine.run(n_steps=48, progress=False).snapshots[-1]
                risk_sum += np.asarray(final["states"]) == TreeState.INFESTED
            window_features = runner._risk_features_from_grid(risk_sum / runs)
            features.append(window_features)
            evidence[wi].update(window_features)
        stats = runner._aggregate_weather_stats([runner.weather_generator.get_summary_stats(frame)
                                                for frame in frames])
        features = runner._aggregate_risk_features(features)
        score, score_features = runner._score_from_features(case, features, stats, "composite", weight)
        features.update(score_features)
        level = risk_score_to_pest_level(score, case.pest_type)
        result = ValidationResult(case, score, level, level == case.actual_level,
                                  simulation_time_s=time.perf_counter() - started,
                                  peak_risk=features["peak_peak_risk"],
                                  n_infested=round(features["peak_n_at_risk"]),
                                  weather_stats=stats, risk_features=features)
    else:
        raise ValueError(f"Unknown engine {mode}")
    return mode, result, evidence


def summarize(rows: pd.DataFrame, mode: str, split: str, pest: str, prediction: str) -> dict:
    selected = rows[(rows["mode"] == mode)]
    if split != "all":
        selected = selected[selected["split"] == split]
    if pest != "both":
        selected = selected[selected["pest_type"] == pest]
    level_key = {"raw": "raw_level", "calibrated": "predicted_level", "majority": "majority_level",
                 "previous_month": "previous_actual_level", "legacy": "legacy_level"}[prediction]
    score_key = {"raw": "raw_risk", "calibrated": "predicted_risk", "majority": "training_median",
                 "previous_month": "previous_actual_risk", "legacy": "legacy_risk"}[prediction]
    metrics = compute_full_metrics([{"actual_level": row.actual_level, "predicted_level": getattr(row, level_key),
                                     "actual_value": row.actual_risk, "predicted_value": getattr(row, score_key),
                                     "pest_type": row.pest_type,
                                     "match": row.actual_level == getattr(row, level_key)}
                                    for row in selected.itertuples()])
    high_count = int(selected.actual_level.eq("High").sum())
    medium_high = int(selected.actual_level.isin(["Medium", "High"]).sum())
    recalls = selected.loc[selected.actual_level.isin(["Medium", "High"]), level_key].isin(["Medium", "High"])
    return {"mode": mode, "split": split, "pest": pest, "prediction": prediction,
            "n": metrics.total_tests, "correct": metrics.correct_predictions,
            "accuracy_pct": metrics.overall_accuracy_pct,
            **metrics.regression.to_dict(), "observed_high": high_count,
            "high_recall": metrics.classification.recall if high_count else None,
            "high_precision": metrics.classification.precision if high_count else None,
            "high_f1": metrics.classification.f1_score if high_count else None,
            "specificity": metrics.classification.specificity,
            "observed_medium_high": medium_high,
            "medium_high_recall": float(recalls.mean()) if medium_high else None}


def calibrated_rows(runner: ValidationRunner, results: list, reference: pd.DataFrame, mode: str) -> tuple[list, dict]:
    """Fit only 2022-24; keep frozen class calibration separate from numeric fit."""
    runner.results = results
    calibration = runner.fit_calibration(split="calibration", optimize_level_thresholds=True)
    runner.apply_calibration(calibration)
    rows = []
    for result in results:
        case = result.case
        old = reference[(reference["Simulation Model"] == MODES[mode])
                        & (reference["Date"] == case.date_str)
                        & (reference["Pest"] == ("Cecid Fly" if case.pest_type == "cecid" else "Fruit Fly"))].iloc[0]
        training = [item for item in results if item.case.split == "calibration" and item.case.pest_type == case.pest_type]
        counts = {label: sum(item.case.actual_level == label for item in training) for label in ["Low", "Medium", "High"]}
        curve = calibration.curve_for(case.pest_type)
        weight = result.risk_features["carryover_weight"]
        rows.append({"mode": mode, **case.to_dict(), "model_version": config.SIMULATION_MODEL_VERSION,
                     "actual_risk": normalize_pest_value_to_risk(case.actual_value, case.pest_type),
                     "raw_risk": result.raw_predicted_risk, "raw_level": result.raw_predicted_level,
                     "predicted_risk": result.predicted_risk, "predicted_level": result.predicted_level,
                     "match": result.match, "absolute_error": result.error,
                     "legacy_raw_risk": float(old["Raw Simulated Risk Score"]),
                     "legacy_risk": float(old["Calibrated Numeric Risk Score"]),
                     "legacy_level": old["Final Predicted Risk Level"],
                     "majority_level": max(counts, key=counts.get),
                     "training_median": float(np.median([item._actual_normalized() for item in training])),
                     "numeric_scale": curve.scale, "numeric_intercept": curve.intercept,
                     "raw_class_low": curve.raw_level_low_threshold,
                     "raw_class_high": curve.raw_level_high_threshold,
                     "numeric_calibration_method": curve.method,
                     "numeric_threshold_level": risk_score_to_pest_level(result.predicted_risk, case.pest_type),
                     "class_numeric_disagreement": result.predicted_level != risk_score_to_pest_level(result.predicted_risk, case.pest_type),
                     "spatial_contribution": (1 - weight) * 0.70 * result.risk_features["spatial_score"],
                     "weather_contribution": (1 - weight) * 0.30 * result.risk_features["weather_suitability"],
                     "observed_prior_contribution": weight * case.previous_actual_risk,
                     "simulation_time_s": result.simulation_time_s, **result.risk_features,
                     **{f"weather_{key}": value for key, value in result.weather_stats.items()}})
    return rows, calibration.to_dict()


def run_replay(root: Path, output: Path, reference_path: Path, runs: int = 30, workers: int = 4):
    if min(runs, workers) < 1:
        raise ValueError("Realization and worker counts must be positive")
    output.mkdir(parents=True, exist_ok=True)
    runner = ValidationRunner(seed=42, historical_weather_path=root / "data/hourly_weather.csv",
                               require_historical_weather=True)
    cases = runner.generate_validation_cases(years=[2022, 2023, 2024, 2025])
    runner.assign_case_splits(cases, test_years=[2025])
    reference = load_reference(reference_path, cases)
    initialize_worker(str(root))
    ids = {node.tree_id for node in _GRAPH.nodes}
    tasks = []
    for mode in MODES:
        for case in cases:
            old = reference[(reference["Simulation Model"] == MODES[mode]) & (reference["Date"] == case.date_str)
                            & (reference["Pest"] == ("Cecid Fly" if case.pest_type == "cecid" else "Fruit Fly"))].iloc[0]
            sources = parse_sources(old["Seed Tree IDs by Window"], ids) if mode == "tree_graph" else None
            tasks.append((case, mode, runs, sources))
    manifest = {"model_version": config.SIMULATION_MODEL_VERSION,
                "started_utc": datetime.now(timezone.utc).isoformat(),
                "python_version": platform.python_version(), "numpy_version": np.__version__, "pandas_version": pd.__version__,
                "hours": 48, "monthly_windows": 4,
                "runs_per_window_per_engine": runs, "realizations": len(tasks) * 4 * runs,
                "seed": 42, "workers": workers, "grid_cells": 400, "grid_cell_size_m": config.CELL_SIZE_M,
                "graph_trees": len(ids), "graph_max_distance_m": 20,
                "cecid_habitat_relay": False, "carryover": {"cecid": 0.65, "fruitfly": 0.1},
                "train_years": [2022, 2023, 2024], "test_years": [2025],
                "score": "legacy composite with final affected-frequency field for both engines",
                "legacy_reproduction_limit": "Old export omits realization counts, RNG seed, graph cutoff and tree-risk implementation. Replay declares these explicitly; not a bit-for-bit reproduction.",
                "initial_conditions": "fresh assumed sources per window, all unbagged, initial rain history zero, no adult antecedent replay, no treatment or external neighbor pressure",
                "missing_historical_fields": ["cloud cover", "instant GHI", "instant DNI", "measured fruit stage", "source locations", "treatment", "bagging", "neighbor pressure"],
                "input_sha256": {str(path.relative_to(root) if path.is_relative_to(root) else path): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in [reference_path, root / "data/hourly_weather.csv", root / "data/trees.geojson",
                                              runner.data_loader.data_path.resolve()]},
                "core_sha256": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in [root / "core/config.py", root / "core/biological_rules.py",
                                             root / "core/simulation_engine.py", root / "core/tree_graph_model.py",
                                             root / "core/cecid_habitat.py", root / "utils/daylight.py",
                                             root / "utils/solar.py", root / "utils/weather.py",
                                             root / "validation/weather_scenarios.py", root / "validation/metrics.py",
                                             root / "validation/validation_runner.py", root / "validation/calibration.py",
                                             root / "validation/defense_replay.py", root / "scripts/run_defense_replay.py"]}}
    (output / "replay_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    completed = {mode: {} for mode in MODES}
    evidence = []
    def record(answer):
        mode, result, windows = answer
        completed[mode][result.case.case_id] = result
        evidence.extend(windows)
        print(f"{sum(len(group) for group in completed.values())}/{len(tasks)} {mode} {result.case.case_id} raw={result.predicted_risk:.6f}", flush=True)
    if workers == 1:
        for task in tasks:
            record(run_case(task))
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=initialize_worker, initargs=(str(root),)) as pool:
            futures = [pool.submit(run_case, task) for task in tasks]
            for future in as_completed(futures):
                record(future.result())
    rows = []
    calibrations = {}
    for mode in MODES:
        new_rows, calibration = calibrated_rows(runner, [completed[mode][case.case_id] for case in cases], reference, mode)
        rows.extend(new_rows)
        calibrations[mode] = calibration
    details = pd.DataFrame(rows)
    summary = pd.DataFrame([summarize(details, mode, split, pest, prediction)
                            for mode in MODES for split in ["all", "calibration", "testing"]
                            for pest in ["both", "cecid", "fruitfly"]
                            for prediction in ["legacy", "raw", "calibrated", "majority", "previous_month"]])
    details.to_csv(output / "defense_case_results.csv", index=False)
    summary.to_csv(output / "defense_metrics.csv", index=False)
    pd.DataFrame(evidence).sort_values(["mode", "case_id", "window"]).to_csv(output / "defense_weather_windows.csv", index=False)
    (output / "calibration.json").write_text(json.dumps(calibrations, indent=2), encoding="utf-8")
    manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["completed_case_engine_pairs"] = len(details)
    manifest["completed_weather_windows"] = len(evidence)
    (output / "replay_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    export_figure(output, details)
    export_defense_tables(output, details, summary, manifest)
    return details, summary


def export_defense_tables(output: Path, details: pd.DataFrame, summary: pd.DataFrame, manifest: dict):
    """Export compact, spreadsheet-readable defense tables and a discussion."""
    table = []
    for mode in MODES:
        for prediction, version in [("legacy", "Saved old defense"), ("calibrated", manifest["model_version"])]:
            def metric(split):
                return summary[(summary["mode"] == mode) & (summary.split == split)
                               & (summary.pest == "both") & (summary.prediction == prediction)].iloc[0]
            all_cases, training, testing = (metric(split) for split in ["all", "calibration", "testing"])
            table.append({"Engine": "Cellular Automata" if mode == "grid" else "Tree-to-Tree Graph",
                          "Version": version, "Cases": int(all_cases.n), "Correct": int(all_cases.correct),
                          "Overall agreement %": all_cases.accuracy_pct,
                          "Calibration agreement %": training.accuracy_pct,
                          "2025 agreement %": testing.accuracy_pct,
                          "MAE": all_cases.mae, "RMSE": all_cases.rmse, "R-squared": all_cases.r_squared,
                          "High recall": all_cases.high_recall})
    revision = manifest["model_version"].rsplit("-", 1)[-1]
    pd.DataFrame(table).to_csv(output / f"chapter4_{revision}_validation_results_table.csv", index=False)
    settings = [
        ("Model", manifest["model_version"], "Both current engines; no biological coefficient tuning"),
        ("Cases", "20 per engine; 15 calibration, 5 testing", "Same dates and pests as saved defense"),
        ("Weather", "Bundled Open-Meteo historical hourly archive", "All four 48-hour windows required; no fallback"),
        ("Realizations", manifest["runs_per_window_per_engine"], "Per window and engine"),
        ("Grid", "20x20, 400 unbagged tree cells, 5 m", "Synthetic orchard; legacy geometry"),
        ("Tree Graph", "194 mapped trees, 20 m edge cutoff", "Saved source IDs; crown widths converted to radii"),
        ("Scoring", "Composite spatial/weather/observed carryover", "Raw composite includes BPI inputs"),
        ("Carryover", "Cecid 0.65; Fruit Fly 0.10", "Previous observed month, including test-year history"),
        ("Training", "2022-2024", "Separate affine numeric and raw-class calibration per pest"),
        ("Testing", "2025", "Calibration frozen; majority baseline matches all five classes"),
        ("Cecid paths", "Fixed soil sources; no habitat relay", "Retain legacy representation during comparison"),
        ("Unknown management", "No treatment, bagging or external pressure applied", "Assumptions, not reconstructed records"),
        ("Missing daylight", "Cloud, instant GHI and DNI unavailable", "Cloudy-daylight rule cannot be validated here"),
        ("Reproduction limit", manifest["legacy_reproduction_limit"], "Old/current change is not solely a biological effect"),
    ]
    pd.DataFrame(settings, columns=["Validation Item", "Setting", "Interpretation"]).to_csv(
        output / f"chapter4_{revision}_validation_configuration_table.csv", index=False)
    lines = ["# Updated Chapter 4 historical validation comparison", "",
             "The current engines were compared with the saved defense on the same 20 monthly BPI cases, historical weather windows, composite scoring, observed carryover, and training/testing years.", "",
             "| Engine | Version | Overall | Calibration | 2025 test | MAE | RMSE | R² |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in table:
        lines.append(f"| {row['Engine']} | {row['Version']} | {row['Overall agreement %']:.1f}% | {row['Calibration agreement %']:.1f}% | {row['2025 agreement %']:.1f}% | {row['MAE']:.4f} | {row['RMSE']:.4f} | {row['R-squared']:.4f} |")
    lines += ["", "Overall agreement includes calibration cases. The five 2025 cases contain only Low Cecid and Medium Fruit Fly observations; a training-majority baseline already matches all five. No High outbreaks were held out in this subset.", "",
              "The raw composite includes observed previous-month BPI values and weather suitability. The replay exports their contributions separately from spatial simulation frequency. Numeric calibration and optimized class cut-points are distinct; class agreement does not imply numeric agreement.", "",
              "These results support a retrospective aggregate risk-class comparison under stated assumptions. They do not establish individual-tree forecast accuracy or cloudy-daylight activity, because the BPI records are monthly and the historical archive lacks the necessary light fields.", "",
              "The saved export omits some execution settings. The replay declares its settings explicitly and uses 30 realizations per window by default; it is not a bit-for-bit old-run reproduction. See docs/v16-validation-defense.md and the broader full-month audit for the complete interpretation.", ""]
    (output / f"chapter4_{revision}_validation_discussion.md").write_text("\n".join(lines), encoding="utf-8")


def export_figure(output: Path, details: pd.DataFrame):
    version = str(details["model_version"].iloc[0])
    os.environ.setdefault("MPLCONFIGDIR", str(output / ".matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharey="row")
    for col, mode in enumerate(MODES):
        for row, pest in enumerate(["cecid", "fruitfly"]):
            ax = axes[row, col]
            rows = details[(details["mode"] == mode) & (details.pest_type == pest)]
            x = np.arange(len(rows))
            ax.plot(x, rows.actual_risk, "o-", label="BPI normalized observation")
            ax.plot(x, rows.legacy_risk, ".--", label="Saved old calibrated score")
            ax.plot(x, rows.raw_risk, "x:", label="Composite before calibration")
            ax.plot(x, rows.predicted_risk, "s-", label="Calibrated numeric score")
            first_test = next(i for i, value in enumerate(rows.split) if value == "testing")
            ax.axvspan(first_test - 0.5, len(rows) - 0.5, alpha=0.08, color="green", label="2025 held out")
            ax.set_xticks(x, rows.date, rotation=60, ha="right", fontsize=8)
            ax.set_title(f"{'Cecid Fly' if pest == 'cecid' else 'Fruit Fly'} / {'Cellular Automata' if mode == 'grid' else 'Tree Graph'}")
            ax.set_ylim(-0.02, 1.02)
            ax.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=8)
    axes[0, 0].set_ylabel("Normalized monthly score")
    axes[1, 0].set_ylabel("Normalized monthly score")
    fig.suptitle(f"Original defense design / {version}\nNumeric scores; class cut-points fitted separately")
    fig.tight_layout()
    fig.savefig(output / "defense_comparison.png", dpi=170)
    plt.close(fig)
