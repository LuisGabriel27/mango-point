# MangoPoint Validation

Historical validation tools for comparing MangoPoint predictions against BPI Guimaras monitoring data from 2022-2025.

## Command Line

```bash
cd capstone/mangopoint

python -m scripts.run_validation
python -m scripts.run_validation --pest-type fruitfly
python -m scripts.run_validation --max-cases 10 --monte-carlo 10 --verbose
python -m scripts.run_validation --data-summary
python -m scripts.run_validation --list-cases
```

## Python Usage

```python
from validation import ValidationRunner, ComparisonReportGenerator

runner = ValidationRunner(seed=42)
results = runner.run_full_validation(max_cases=20)
metrics = runner.compute_metrics()

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

## Notes

- The validation package now imports directly from `core` and `utils`.
- Thresholds used by validation come from `core/config.py`.
