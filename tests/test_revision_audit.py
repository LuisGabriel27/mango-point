"""Check audit safeguards, not field accuracy."""

from dataclasses import replace
import pytest
import pandas as pd

from core import config, biological_rules, cecid_habitat
from validation.historical_data import HistoricalRecord
from validation.validation_runner import ValidationResult
from validation.revision_audit import (
    Scenario, bpi_cases, comparison_metrics, compare_bpi, run_orchard,
    scenario_weather, temporary_coefficients, summarize_sensitivity, export_daylight_response,
)


def test_bpi_audit_keeps_outbreaks_outside_assumed_calendar_without_label_weather():
    records = [HistoricalRecord(2022, 1, 1.7, 2.54, 48.0), HistoricalRecord(2023, 2, 3.4, 8.4, 27.4)]
    cases = bpi_cases(records, "cecid")
    assert len(cases) == 2
    assert [case.actual_level for case in cases] == ["High", "High"]
    assert all(case.orchard_stage == "fruitlet" and case.weather_scenario == "typical" for case in cases)


def test_calibration_and_seasonal_baseline_do_not_use_test_outcomes():
    records = [HistoricalRecord(2022, 1, 1.0, 2.0, 0), HistoricalRecord(2023, 1, 12.0, 18.0, 10),
               HistoricalRecord(2024, 1, 25.0, 30.0, 20), HistoricalRecord(2025, 1, 6.0, 8.0, 0)]
    def run(changed_records):
        cases = bpi_cases(changed_records, "fruitfly")
        results = [ValidationResult(case, raw, "Low", False) for case, raw in zip(cases, [0.1, 0.3, 0.6, 0.2])]
        return compare_bpi(results, changed_records, "fruitfly")
    rows, summary = run(records)
    changed = [*records[:-1], replace(records[-1], fruit_fly_managed_cptd=40.0)]
    changed_rows, changed_summary = run(changed)
    assert summary["calibration"] == changed_summary["calibration"]
    for key in ["raw_risk", "calibrated_risk", "constant_training_median", "seasonal_training_median", "majority_training_class"]:
        assert rows[-1][key] == changed_rows[-1][key]
    assert rows[-1]["actual_risk"] != changed_rows[-1]["actual_risk"]


def test_single_class_perfect_accuracy_is_reported_without_outbreak_recall():
    metrics = comparison_metrics([0, 0.0482], [0.02, 0.02], "cecid")
    assert metrics["accuracy_pct"] == 100
    assert metrics["observed_nonzero_months"] == 1
    assert metrics["observed_medium_high_months"] == 0
    assert metrics["medium_high_recall"] is None


def test_temporary_coefficients_restore_imported_values_after_exception():
    original = config.CECID_MAX_RANGE_M
    with pytest.raises(RuntimeError):
        with temporary_coefficients({"CECID_MAX_RANGE_M": 9.0}):
            assert cecid_habitat.CECID_MAX_RANGE_M == 9
            raise RuntimeError("test")
    assert config.CECID_MAX_RANGE_M == cecid_habitat.CECID_MAX_RANGE_M == original


def test_sensitivity_pairs_each_seed_with_its_own_baseline():
    rows = pd.DataFrame([
        {"pest": "cecid", "mode": "grid", "scenario": name, "seed": seed,
         "new_affected": affected, "parameter": "test", "value": "test",
         "first_affected_hour": 0, "max_distance_m": 10}
        for name, seed, affected in [("baseline", 1, 1), ("baseline", 2, 3), ("changed", 2, 8), ("changed", 1, 2)]
    ])
    summary = summarize_sensitivity(rows).set_index("scenario")
    assert summary.loc["baseline", "mean_paired_change"] == 0
    assert summary.loc["changed", "mean_paired_change"] == 3
    assert summary.loc["changed", "paired_change_se"] == 2


def test_daylight_sensitivity_probes_transition_cloud_and_restores_constants(tmp_path):
    rows = export_daylight_response(tmp_path)
    probe = rows[(rows.cloud_cover_pct == 65) & (rows.ghi_clear_sky_ratio == 0.5)].set_index("setting")
    assert probe.loc["CECID_DAY_CLOUD_MIN_PCT=30.0", "light_score"] > 0
    assert probe.loc["CECID_DAY_CLOUD_MIN_PCT=70.0", "light_score"] == 0
    assert config.CECID_DAY_CLOUD_MIN_PCT == 50


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
@pytest.mark.parametrize("pest", ["cecid", "fruitfly"])
def test_no_sources_or_incompatible_stage_cannot_generate_audit_spread(mode, pest):
    for scenario in [Scenario("none", pest=pest, source_presence=0),
                     Scenario("wrong", pest=pest, stage="mature" if pest == "cecid" else "fruitlet")]:
        result = run_orchard(scenario, mode, 1000, scenario_weather(scenario, hours=3))
        assert result["new_affected"] == 0
        assert result["first_affected_hour"] is None


@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
def test_egg_capacity_override_reaches_cohort_constructor_and_changes_depletion(mode):
    results = []
    for capacity in [4.0, 16.0]:
        scenario = Scenario(str(capacity), light="dim_overcast", coefficients={"CECID_EGG_CAPACITY_HOURS": capacity})
        results.append(run_orchard(scenario, mode, 1000, scenario_weather(scenario, hours=14)))
    assert results[0]["spent_cohort_count"] > results[1]["spent_cohort_count"]
    assert config.CECID_EGG_CAPACITY_HOURS == 8
    assert biological_rules.CECID_EGG_CAPACITY_HOURS == 8
