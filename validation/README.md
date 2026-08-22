# MangoPoint Validation

Historical validation tools for comparing MangoPoint predictions against BPI Guimaras monitoring data from 2022-2025.

## Command Line

```bash
cd mango-point

python -m scripts.run_validation
python -m scripts.run_validation --pest-type fruitfly
python -m scripts.run_validation --max-cases 10 --monte-carlo 10 --verbose
python -m scripts.run_validation --split-year 2025
python -m scripts.run_validation --test-years 2025 --bootstrap 1000
python -m scripts.run_validation --test-years 2025 --no-calibration
python -m scripts.run_validation --historical-weather-csv data/hourly_weather.csv
python -m scripts.run_validation --historical-weather-csv data/hourly_weather.csv --require-historical-weather
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

Validation uses the BPI Guimaras pest monitoring CSV by default. The repository includes `data/hourly_weather.csv`, a normalized Open-Meteo historical hourly archive for 2022-2025. Pass it with `--historical-weather-csv` when you want validation to replay historical cases with hourly weather rather than seasonal synthetic profiles.

Expected weather CSV columns:

- `datetime`
- `temperature_c`
- `wind_speed_ms`
- `wind_dir_deg`
- `rainfall_mm` (optional, defaults to 0)

If a weather CSV is supplied but a case month does not have enough hourly rows for the requested duration, that case falls back to the seasonal synthetic profile and records the fallback reason in CSV/JSON output.

For stricter defense runs, add `--require-historical-weather`. This checks every selected validation case before simulation and exits if any case month lacks enough hourly rows. The CLI also prints a historical weather coverage summary showing how many cases can use real weather and how many would fall back.

Use the normal fallback mode while developing or demoing. Use `--require-historical-weather` when you want to claim that a validation run replayed cases with historical weather rather than synthetic seasonal profiles. Open-Meteo historical weather is model/reanalysis data; if you obtain PAGASA station observations, replace or add a CSV with the same normalized columns and document that source in reports.

## Calibration And Testing

Use `--split-year YYYY` or `--test-years YYYY,YYYY` to create calibration and testing groups. Split runs now fit pest-specific risk-score calibration on the calibration group, preserve each case's `raw_predicted_risk`, then apply the frozen calibration before reporting testing metrics. Use `--no-calibration` to report raw simulator scores only, or `--calibrate` without a split for exploratory all-case calibration.

Whenever Cecid cases are included, the CLI checks the uncalibrated Cecid scores
before fitting calibration. It reports their count, unique values, and range,
and fails the run if the scores are all zero or effectively constant. This
guards against a weather/source gate that silently produces degenerate output;
it does not turn monthly BPI aggregates into event-level validation evidence.

The calibration layer is deliberately small: it fits a non-negative affine curve per pest type from simulated risk to BPI-normalized observed risk, then classifies calibrated scores with BPI-equivalent thresholds:

- Fruit fly: CPTD 8 and 20 mapped to the 0-1 risk scale.
- Cecid fly: infestation 5% and 15% mapped to the 0-1 risk scale.

Bootstrap confidence intervals are enabled by default in the CLI with `--bootstrap 500`. Use `--bootstrap 0` to disable them.

## Manual Field Validation Protocol

Use this protocol when you want to validate a current forecast without adding a new field-validation feature to the app yet. It complements BPI historical validation by checking whether a forecast made today matches orchard observations after the forecast period.

1. Run a simulation for the orchard, pest type, weather source, and forecast duration you want to test.
2. Record the forecast date, orchard, pest type, simulation settings, and forecast horizon.
3. Select inspection targets from multiple risk levels, not only high-risk trees. A small practical sample is 10 high-risk trees, 5 medium-risk trees, and 5 low-risk control trees.
4. Inspect those same trees after the forecast period, such as 24 hours, 3 days, or 7 days.
5. Record whether pest signs were found, the observed severity, and any field notes such as spray activity, pruning, rain, or unusual orchard conditions.
6. Compare each inspected tree against the saved forecast:
   - Predicted high risk and pest found: correct warning.
   - Predicted high risk and no pest found: false alarm.
   - Predicted low risk and pest found: missed warning.
   - Predicted low risk and no pest found: correct safe prediction.

Suggested spreadsheet columns:

```text
forecast_date, orchard_id, pest_type, forecast_horizon, tree_id, predicted_risk, predicted_level, inspection_date, pest_found, observed_severity, treatment_or_spray_notes, result_type, notes
```

Summarize each manual validation round with accuracy, precision, recall, false alarms, and missed warnings. For defense, describe this as operational field checking, not as a replacement for historical BPI validation.

## Notes

- The validation package now imports directly from `core` and `utils`.
- Biological thresholds used by simulation come from `core/config.py`; BPI comparison thresholds come from `validation/historical_data.py`.
- Monthly BPI aggregates cannot establish event-level forecast accuracy. Without hourly field observations and additional trials, validation should be described as calibrated historical plausibility testing, not final proof of forecasting accuracy.
