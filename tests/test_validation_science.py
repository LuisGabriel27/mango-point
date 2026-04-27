from datetime import datetime, timedelta

import pytest

from validation.metrics import (
    bootstrap_confidence_intervals,
    compute_full_metrics,
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
