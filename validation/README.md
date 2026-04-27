# MangoPoint Validation

Historical validation tools for comparing MangoPoint predictions against BPI Guimaras monitoring data from 2022-2025.

## Command Line

```bash
cd capstone/mangopoint

python -m scripts.run_validation
python -m scripts.run_validation --pest-type fruitfly
python -m scripts.run_validation --max-cases 10 --monte-carlo 10 --verbose
python -m scripts.run_validation --split-year 2025
python -m scripts.run_validation --test-years 2025 --bootstrap 1000
python -m scripts.run_validation --historical-weather-csv data/hourly_weather.csv
python -m scripts.run_validation --data-summary
python -m scripts.run_validation --list-cases
```

## Python Usage

```python
from validation import ValidationRunner, ComparisonReportGenerator

runner = ValidationRunner(seed=42)
results = runner.run_full_validation(max_cases=20)
metrics = runner.compute_metrics(bootstrap_iterations=500)

report = ComparisonReportGenerator(
    validation_results=results,
    validation_metrics=metrics,
    historical_loader=runner.data_loader,
)
report.export_all("outputs/validation")
```

## Module Layout

| Path | Purpose |
|---|---|
| `validation/historical_data.py` | BPI data loading and risk classification |
| `validation/weather_scenarios.py` | Historical weather generation |
| `validation/validation_runner.py` | Batch validation orchestration |
| `validation/metrics.py` | Classification and regression metrics |
| `validation/reports.py` | Legacy validation exports |
| `validation/simulation_aggregator.py` | BPI-style aggregate metrics from simulation output |
| `validation/trend_analysis.py` | Temporal comparison and seasonality analysis |
| `validation/comparison_report.py` | Expanded report generation |

## Weather Inputs

Validation uses the BPI Guimaras pest monitoring CSV by default. Hourly historical weather is optional because the repository does not include a complete hourly weather archive. Provide one with `--historical-weather-csv` when available.

Expected weather CSV columns:

- `datetime`
- `temperature_c`
- `wind_speed_ms`
- `wind_dir_deg`
- `rainfall_mm` (optional, defaults to 0)

If a weather CSV is supplied but a case month does not have enough hourly rows for the requested duration, that case falls back to the seasonal synthetic profile and records the fallback reason in CSV/JSON output.

## Calibration And Testing

Use `--split-year YYYY` or `--test-years YYYY,YYYY` to report calibration and testing metrics separately. The split only changes reporting groups; model parameters are not auto-fit yet.

Bootstrap confidence intervals are enabled by default in the CLI with `--bootstrap 500`. Use `--bootstrap 0` to disable them.

## Notes

- The validation package now imports directly from `core` and `utils`.
- Thresholds used by validation come from `core/config.py`.
- Without an hourly historical weather CSV and true parameter calibration, validation should be described as historical plausibility testing, not a final proof of forecasting accuracy.
