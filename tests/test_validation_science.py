from datetime import datetime, timedelta

import pytest

from validation.metrics import (
    bootstrap_confidence_intervals,
    compute_full_metrics,
    normalized_risk_thresholds,
    risk_score_to_pest_level,
)
from validation.validation_runner import ValidationCase, ValidationResult, ValidationRunner
from validation.weather_scenarios import HistoricalWeatherGenerator


def _metric_row(actual, predicted, actual_value, predicted_value, pest_type="fruitfly"):
    return {
        "actual_level": actual,
        "predicted_level": predicted,
        "actual_value": actual_value,
        "predicted_value": predicted_value,
        "pest_type": pest_type,
        "match": actual == predicted,
    }


def test_bootstrap_confidence_intervals_are_serialized():
    rows = [
        _metric_row("Low", "Low", 0.05, 0.05),
        _metric_row("Medium", "Low", 0.40, 0.20),
        _metric_row("High", "High", 0.90, 0.85),
        _metric_row("High", "Medium", 0.80, 0.50),
    ]

    intervals = bootstrap_confidence_intervals(rows, n_iterations=40, seed=7)
    metrics = compute_full_metrics(rows)
    metrics.confidence_intervals = intervals

    assert "overall_accuracy_pct" in intervals
    assert intervals["overall_accuracy_pct"]["lower"] <= intervals["overall_accuracy_pct"]["upper"]
    assert "confidence_intervals" in metrics.to_dict()
    assert "Bootstrap Confidence Intervals" in metrics.summary_string()


def test_historical_weather_csv_is_used_when_available(tmp_path):
    weather_path = tmp_path / "weather.csv"
    start = datetime(2024, 5, 15, 6)
    rows = ["datetime,temperature_c,wind_speed_ms,wind_dir_deg,rainfall_mm"]
    for hour in range(4):
        ts = start + timedelta(hours=hour)
        rows.append(f"{ts.isoformat()},{28 + hour},1.5,90,{hour * 0.5}")
    weather_path.write_text("\n".join(rows), encoding="utf-8")

    generator = HistoricalWeatherGenerator(
        seed=1,
        historical_weather_path=weather_path,
    )
    df = generator.generate(year=2024, month=5, hours=4)
    stats = generator.get_summary_stats(df)

    assert list(df["temperature_c"]) == [28, 29, 30, 31]
    assert df.attrs["source"] == "historical_weather_csv"
    assert stats["source"] == "historical_weather_csv"
    assert stats["historical_weather_path"] == str(weather_path)
    assert stats["weather_coverage_status"] == "ready"


def test_historical_weather_falls_back_when_month_has_insufficient_rows(tmp_path):
    weather_path = tmp_path / "weather.csv"
    weather_path.write_text(
        "datetime,temperature_c,wind_speed_ms,wind_dir_deg,rainfall_mm\n"
        "2024-05-15T06:00:00,28,1.5,90,0\n",
        encoding="utf-8",
    )

    generator = HistoricalWeatherGenerator(
        seed=1,
        historical_weather_path=weather_path,
    )
    df = generator.generate(year=2024, month=5, hours=4)
    stats = generator.get_summary_stats(df)

    assert df.attrs["source"] == "seasonal_profile_synthetic"
    assert stats["fallback_reason"] == "historical_weather_csv_has_insufficient_rows_for_case_month"
    assert stats["weather_coverage_status"] == "insufficient_rows"


def test_historical_weather_strict_mode_rejects_incomplete_case_month(tmp_path):
    weather_path = tmp_path / "weather.csv"
    weather_path.write_text(
        "datetime,temperature_c,wind_speed_ms,wind_dir_deg,rainfall_mm\n"
        "2024-05-15T06:00:00,28,1.5,90,0\n",
        encoding="utf-8",
    )

    generator = HistoricalWeatherGenerator(
        seed=1,
        historical_weather_path=weather_path,
        require_historical_weather=True,
    )

    with pytest.raises(ValueError, match="Historical weather is required"):
        generator.generate(year=2024, month=5, hours=4)


def test_historical_weather_coverage_summary_reports_fallback_cases(tmp_path):
    weather_path = tmp_path / "weather.csv"
    start = datetime(2024, 5, 15, 6)
    rows = ["datetime,temperature_c,wind_speed_ms,wind_dir_deg,rainfall_mm"]
    for hour in range(4):
        ts = start + timedelta(hours=hour)
        rows.append(f"{ts.isoformat()},{28 + hour},1.5,90,0")
    weather_path.write_text("\n".join(rows), encoding="utf-8")

    generator = HistoricalWeatherGenerator(
        seed=1,
        historical_weather_path=weather_path,
    )
    ready_case = ValidationCase(
        case_id="FF-2024-05",
        year=2024,
        month=5,
        date_str="2024-05",
        pest_type="fruitfly",
        orchard_stage="mature",
        actual_value=2.0,
        actual_level="Low",
        weather_scenario="typical",
    )
    missing_case = ValidationCase(
        case_id="FF-2024-06",
        year=2024,
        month=6,
        date_str="2024-06",
        pest_type="fruitfly",
        orchard_stage="mature",
        actual_value=30.0,
        actual_level="High",
        weather_scenario="typical",
    )

    summary = generator.summarize_case_coverage([ready_case, missing_case], hours=4)

    assert summary["historical_ready_cases"] == 1
    assert summary["fallback_cases"] == 1
    assert summary["status_counts"] == {"ready": 1, "missing_month": 1}


def test_historical_weather_generator_can_sample_monthly_windows(tmp_path):
    weather_path = tmp_path / "weather.csv"
    start = datetime(2024, 5, 1, 0)
    rows = ["datetime,temperature_c,wind_speed_ms,wind_dir_deg,rainfall_mm,humidity_pct"]
    for hour in range(24 * 10):
        ts = start + timedelta(hours=hour)
        rows.append(f"{ts.isoformat()},{28 + hour % 4},1.5,90,0,{75 + hour % 5}")
    weather_path.write_text("\n".join(rows), encoding="utf-8")

    generator = HistoricalWeatherGenerator(
        seed=1,
        historical_weather_path=weather_path,
    )
    windows = generator.generate_monthly_windows(
        year=2024,
        month=5,
        window_hours=48,
        n_windows=4,
    )

    assert len(windows) == 4
    assert all(len(window) == 48 for window in windows)
    assert windows[0].attrs["source"] == "historical_weather_csv"
    assert windows[-1]["datetime"].iloc[0] > windows[0]["datetime"].iloc[0]


def test_validation_cases_include_previous_month_pest_context():
    runner = ValidationRunner(seed=1)
    cases = runner.generate_validation_cases(years=[2022, 2023])
    cases_by_id = {case.case_id: case for case in cases}

    assert cases_by_id["FF-2022-05"].previous_actual_risk == pytest.approx(9.17 / 40.0)
    assert cases_by_id["FF-2022-05"].previous_actual_level == "Medium"
    assert cases_by_id["CF-2023-03"].previous_actual_risk == pytest.approx(27.40 / 100.0)
    assert cases_by_id["CF-2023-03"].previous_actual_level == "High"


def test_validation_runner_assigns_splits_and_computes_split_metrics():
    runner = ValidationRunner(seed=1)
    calibration_case = ValidationCase(
        case_id="FF-2024-05",
        year=2024,
        month=5,
        date_str="2024-05",
        pest_type="fruitfly",
        orchard_stage="mature",
        actual_value=2.0,
        actual_level="Low",
        weather_scenario="typical",
    )
    testing_case = ValidationCase(
        case_id="FF-2025-05",
        year=2025,
        month=5,
        date_str="2025-05",
        pest_type="fruitfly",
        orchard_stage="mature",
        actual_value=30.0,
        actual_level="High",
        weather_scenario="typical",
    )

    splits = runner.assign_case_splits(
        [calibration_case, testing_case],
        split_year=2025,
    )
    runner.results = [
        ValidationResult(
            case=calibration_case,
            predicted_risk=0.05,
            predicted_level="Low",
            match=True,
        ),
        ValidationResult(
            case=testing_case,
            predicted_risk=0.8,
            predicted_level="High",
            match=True,
        ),
    ]

    assert [case.case_id for case in splits["calibration"]] == ["FF-2024-05"]
    assert [case.case_id for case in splits["testing"]] == ["FF-2025-05"]

    testing_metrics = runner.compute_metrics(
        split="testing",
        bootstrap_iterations=10,
        seed=2,
    )
    split_metrics = runner.compute_split_metrics(bootstrap_iterations=0)

    assert testing_metrics.total_tests == 1
    assert testing_metrics.overall_accuracy_pct == pytest.approx(100.0)
    assert "testing" in split_metrics
    assert split_metrics["calibration"].total_tests == 1


def test_bpi_thresholds_are_available_on_normalized_risk_scale():
    fruitfly_low, fruitfly_high = normalized_risk_thresholds("fruitfly")
    cecid_low, cecid_high = normalized_risk_thresholds("cecid")

    assert fruitfly_low == pytest.approx(0.2)
    assert fruitfly_high == pytest.approx(0.5)
    assert cecid_low == pytest.approx(0.05)
    assert cecid_high == pytest.approx(0.15)
    assert risk_score_to_pest_level(0.45, "fruitfly") == "Medium"
    assert risk_score_to_pest_level(0.16, "cecid") == "High"


def test_validation_runner_fits_and_applies_bpi_calibration():
    runner = ValidationRunner(seed=1)
    low_case = ValidationCase(
        case_id="FF-2024-05-low",
        year=2024,
        month=5,
        date_str="2024-05",
        pest_type="fruitfly",
        orchard_stage="mature",
        actual_value=2.0,
        actual_level="Low",
        weather_scenario="typical",
        split="calibration",
    )
    high_case = ValidationCase(
        case_id="FF-2024-06-high",
        year=2024,
        month=6,
        date_str="2024-06",
        pest_type="fruitfly",
        orchard_stage="mature",
        actual_value=30.0,
        actual_level="High",
        weather_scenario="typical",
        split="calibration",
    )
    testing_case = ValidationCase(
        case_id="FF-2025-06-high",
        year=2025,
        month=6,
        date_str="2025-06",
        pest_type="fruitfly",
        orchard_stage="mature",
        actual_value=30.0,
        actual_level="High",
        weather_scenario="typical",
        split="testing",
    )
    runner.results = [
        ValidationResult(low_case, predicted_risk=0.10, predicted_level="Low", match=True),
        ValidationResult(high_case, predicted_risk=0.30, predicted_level="Medium", match=False),
        ValidationResult(testing_case, predicted_risk=0.30, predicted_level="Medium", match=False),
    ]

    calibration = runner.fit_calibration(split="calibration")
    runner.apply_calibration(calibration)
    testing_result = runner.results[-1]

    assert calibration.curves["fruitfly"].n_cases == 2
    assert calibration.curves["fruitfly"].mae_after < calibration.curves["fruitfly"].mae_before
    assert testing_result.raw_predicted_risk == pytest.approx(0.30)
    assert testing_result.calibration_applied is True
    assert testing_result.predicted_risk == pytest.approx(0.75)
    assert testing_result.predicted_level == "High"
    assert testing_result.match is True


def test_validation_calibration_maps_constant_raw_scores_to_calibration_median():
    runner = ValidationRunner(seed=1)
    medium_case = ValidationCase(
        case_id="FF-2024-05-medium",
        year=2024,
        month=5,
        date_str="2024-05",
        pest_type="fruitfly",
        orchard_stage="mature",
        actual_value=10.0,
        actual_level="Medium",
        weather_scenario="typical",
        split="calibration",
    )
    second_medium_case = ValidationCase(
        case_id="FF-2024-06-medium",
        year=2024,
        month=6,
        date_str="2024-06",
        pest_type="fruitfly",
        orchard_stage="mature",
        actual_value=15.0,
        actual_level="Medium",
        weather_scenario="typical",
        split="calibration",
    )
    testing_case = ValidationCase(
        case_id="FF-2025-06-medium",
        year=2025,
        month=6,
        date_str="2025-06",
        pest_type="fruitfly",
        orchard_stage="mature",
        actual_value=15.0,
        actual_level="Medium",
        weather_scenario="typical",
        split="testing",
    )
    runner.results = [
        ValidationResult(medium_case, predicted_risk=1.0, predicted_level="High", match=False),
        ValidationResult(second_medium_case, predicted_risk=1.0, predicted_level="High", match=False),
        ValidationResult(testing_case, predicted_risk=1.0, predicted_level="High", match=False),
    ]

    calibration = runner.fit_calibration(split="calibration")
    runner.apply_calibration(calibration)

    curve = calibration.curves["fruitfly"]
    assert curve.method == "constant_raw_scores_clamped_to_median"
    assert curve.scale == pytest.approx(0.0)
    assert curve.intercept == pytest.approx(0.3125)
    assert runner.results[-1].predicted_level == "Medium"


def test_raw_cecid_score_check_rejects_constant_scores_and_accepts_variation():
    runner = ValidationRunner(seed=1)

    def cecid_result(case_id, score):
        case = ValidationCase(
            case_id=case_id,
            year=2025,
            month=5,
            date_str="2025-05",
            pest_type="cecid",
            orchard_stage="fruitlet",
            actual_value=5.0,
            actual_level="Medium",
            weather_scenario="historical",
        )
        return ValidationResult(
            case,
            predicted_risk=score,
            predicted_level="Low",
            match=False,
        )

    runner.results = [cecid_result("CF-1", 0.02), cecid_result("CF-2", 0.02)]
    with pytest.raises(ValueError, match="constant"):
        runner.require_non_degenerate_raw_scores("cecid")

    runner.results.append(cecid_result("CF-3", 0.08))
    diagnostics = runner.require_non_degenerate_raw_scores("cecid")
    assert diagnostics["count"] == 3
    assert diagnostics["unique_count"] == 2
    assert diagnostics["spread"] == pytest.approx(0.06)
