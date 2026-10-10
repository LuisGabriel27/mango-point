"""Protect historical replay provenance and held-out evaluation semantics."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from validation import defense_replay
from validation.defense_replay import calibrated_rows, load_reference, parse_sources, summarize
from validation.validation_runner import ValidationResult, ValidationRunner


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def design():
    runner = ValidationRunner(seed=42, historical_weather_path=ROOT / "data/hourly_weather.csv",
                               require_historical_weather=True)
    cases = runner.generate_validation_cases(years=[2022, 2023, 2024, 2025])
    runner.assign_case_splits(cases, test_years=[2025])
    reference = load_reference(ROOT / "docs/v16-defense-legacy-reference.csv", cases)
    return runner, cases, reference


def test_saved_design_has_identical_cases_and_split_for_both_engines(design):
    _, cases, reference = design
    assert len(cases) == 20
    assert sum(case.split == "testing" for case in cases) == 5
    assert len(reference) == 40
    assert {case.month for case in cases if case.pest_type == "cecid"} == {3, 4}
    assert {case.month for case in cases if case.pest_type == "fruitfly"} == {5, 6, 7}


@pytest.mark.parametrize("change", ["duplicate", "observation", "carryover"])
def test_replay_rejects_silent_reference_changes(design, tmp_path, change):
    _, cases, reference = design
    if change == "duplicate":
        reference.iloc[1] = reference.iloc[0]
    elif change == "observation":
        reference.loc[0, "BPI Ground Value"] = 100.0
    else:
        reference.loc[0, "Applied Carryover Weight"] = 0.2
    path = tmp_path / "reference.csv"
    reference.to_csv(path, index=False)
    with pytest.raises(ValueError, match="Legacy"):
        load_reference(path, cases)


@pytest.mark.parametrize("value", ["1 | 1 | 1", "1;1 | 1 | 1 | 1", "9 | 1 | 1 | 1", " | 1 | 1 | 1"])
def test_saved_source_lists_reject_missing_duplicated_or_unknown_trees(value):
    with pytest.raises(ValueError, match="four valid"):
        parse_sources(value, {"1", "2"})


def test_holdout_observations_cannot_change_fitted_numeric_or_class_calibration(design):
    runner, cases, reference = design
    def run(changed):
        results = [ValidationResult(case, 0.01 + index * 0.02, "Low", False,
                                    risk_features={"carryover_weight": 0.65 if case.pest_type == "cecid" else 0.1,
                                                   "spatial_score": 0.02, "weather_suitability": 0.3})
                   for index, case in enumerate(changed)]
        return calibrated_rows(runner, results, reference, "grid")
    rows, calibration = run(cases)
    changed = [replace(case, actual_value=40.0, actual_level="High")
               if case.split == "testing" and case.pest_type == "fruitfly" else case for case in cases]
    new_rows, new_calibration = run(changed)
    assert calibration == new_calibration
    assert [row["predicted_level"] for row in rows] == [row["predicted_level"] for row in new_rows]
    assert [row["predicted_risk"] for row in rows] == [row["predicted_risk"] for row in new_rows]
    assert [row["majority_level"] for row in rows] == [row["majority_level"] for row in new_rows]
    assert [row["training_median"] for row in rows] == [row["training_median"] for row in new_rows]


def test_low_only_testing_reports_missing_outbreak_recall(design):
    runner, cases, reference = design
    results = [ValidationResult(case, 0.01, "Low", False,
                                risk_features={"carryover_weight": 0.65 if case.pest_type == "cecid" else 0.1,
                                               "spatial_score": 0.01, "weather_suitability": 0.01}) for case in cases]
    rows, _ = calibrated_rows(runner, results, reference, "grid")
    metrics = summarize(pd.DataFrame(rows), "grid", "testing", "cecid", "majority")
    assert metrics["accuracy_pct"] == 100
    assert metrics["n"] == 2
    assert metrics["observed_high"] == metrics["observed_medium_high"] == 0
    assert metrics["high_recall"] is None and metrics["medium_high_recall"] is None


def test_real_replay_sources_and_component_accounting_match_saved_design(design):
    runner, cases, reference = design
    defense_replay.initialize_worker(str(ROOT))
    case = cases[0]
    ids = {node.tree_id for node in defense_replay._GRAPH.nodes}
    saved = reference[reference["Simulation Model"] == "Enhanced Tree Graph"].iloc[0]
    sources = parse_sources(saved["Seed Tree IDs by Window"], ids)
    for mode in ["grid", "tree_graph"]:
        _, result, windows = defense_replay.run_case((case, mode, 1, sources if mode == "tree_graph" else None))
        assert len(windows) == result.risk_features["monthly_windows"] == 4
        assert all(row["source"] == "historical_weather_csv" and row["hours"] == 48 for row in windows)
        features = result.risk_features
        weight = features["carryover_weight"]
        assert np.isclose(result.predicted_risk,
                          (1 - weight) * (0.7 * features["spatial_score"] + 0.3 * features["weather_suitability"])
                          + weight * case.previous_actual_risk)
        if mode == "tree_graph":
            # The no-rain first-month graph behavior also reproduces the saved
            # source-only composite to its original six-decimal precision.
            assert result.predicted_risk == pytest.approx(float(saved["Raw Simulated Risk Score"]), abs=0.00000051)


def test_partial_or_synthetic_windows_cannot_be_reported_as_historical(design, monkeypatch):
    _, cases, _ = design
    defense_replay.initialize_worker(str(ROOT))
    generator = defense_replay._RUNNER.weather_generator
    frames = generator.generate_monthly_windows(2022, 3, 48, 4, "typical")
    frames[0].attrs["source"] = "synthetic"
    monkeypatch.setattr(generator, "generate_monthly_windows", lambda *args: frames)
    with pytest.raises(ValueError, match="Incomplete historical"):
        defense_replay.run_case((cases[0], "grid", 1, None))


def test_failed_grid_batch_is_not_mistaken_for_four_completed_windows(design, monkeypatch):
    _, cases, _ = design
    defense_replay.initialize_worker(str(ROOT))
    monkeypatch.setattr(defense_replay._RUNNER, "_run_single_validation",
                        lambda case, **kwargs: ValidationResult(case, 0.0, "Low", True,
                                                                  risk_features={"monthly_windows": 4}))
    with pytest.raises(RuntimeError, match="CA simulations failed"):
        defense_replay.run_case((cases[0], "grid", 1, None))
