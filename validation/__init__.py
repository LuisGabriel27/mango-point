"""
MangoPoint — Historical Validation Module
==========================================
Validates the pest simulation model against historical BPI Guimaras data.

This module is a **non-invasive extension** that:
  - Reads historical pest monitoring data (2022-2025)
  - Recreates historical scenarios using existing simulation engine
  - Compares predicted risk with actual recorded pest levels
  - Computes validation metrics (accuracy, MAE, precision, recall, F1)
  - Generates structured reports for research validation
  - Aggregates simulation outputs into BPI-comparable metrics
  - Analyzes temporal trends and patterns

The validation module integrates with the existing system by:
  - Calling existing simulation functions (SimulationEngine, biological gates)
  - Using existing weather and grid infrastructure
  - Preserving all existing algorithms, configurations, and workflows

Key Components
--------------
- HistoricalDataLoader: Load BPI Guimaras monitoring data (2022-2025)
- ValidationRunner: Orchestrate validation against historical data
- SimulationAggregator: Convert tree-level outputs to BPI-comparable metrics
- TrendAnalyzer: Compare simulated vs actual temporal patterns
- ComparisonReportGenerator: Generate comprehensive validation reports

Usage Example
-------------
    from validation import ValidationRunner, ComparisonReportGenerator
    
    # Run validation
    runner = ValidationRunner()
    results = runner.run_full_validation()
    metrics = runner.compute_metrics()
    
    # Generate comparison reports
    report_gen = ComparisonReportGenerator(
        validation_results=results,
        validation_metrics=metrics,
        historical_loader=runner.data_loader,
    )
    report_gen.export_all("outputs/validation/")
    
    # Or use SimulationAggregator for individual simulation analysis
    from validation import SimulationAggregator
    
    aggregator = SimulationAggregator(simulation_result)
    bpi_metrics = aggregator.get_summary_for_comparison()
"""

from .historical_data import (
    HistoricalDataLoader,
    HistoricalRecord,
    PestRiskLevel,
    PestType,
    classify_fruit_fly_cptd,
    classify_cecid_fly_pct,
)
from .weather_scenarios import (
    HistoricalWeatherGenerator,
    HistoricalWeatherCoverage,
    SeasonalWeatherProfile,
    GUIMARAS_CLIMATE_PROFILES,
)
from .metrics import (
    ValidationMetrics,
    ClassificationMetrics,
    RegressionMetrics,
    ConfusionMatrix,
    compute_classification_metrics,
    compute_regression_metrics,
    compute_full_metrics,
    bootstrap_confidence_intervals,
    risk_score_to_level,
    risk_score_to_pest_level,
    normalized_risk_thresholds,
    normalize_pest_value_to_risk,
)
from .calibration import (
    PestCalibrationCurve,
    ValidationCalibration,
    fit_risk_calibration,
    identity_curve,
)
from .validation_runner import (
    ValidationRunner,
    ValidationCase,
    ValidationResult,
)
from .reports import (
    ValidationReportGenerator,
    export_validation_csv,
    export_validation_json,
)
from .simulation_aggregator import (
    SimulationAggregator,
    AggregatedMetrics,
    InfestationMetrics,
    SpreadRateMetrics,
    DensityMetrics,
)
from .trend_analysis import (
    TrendAnalyzer,
    TrendComparisonResult,
    CorrelationMetrics,
    TrendDirectionMetrics,
    ErrorMetrics,
    SeasonalPatternMetrics,
    compute_pearson_correlation,
    compute_spearman_correlation,
)
from .comparison_report import (
    ComparisonReportGenerator,
)

__all__ = [
    # Data loading
    "HistoricalDataLoader",
    "HistoricalRecord",
    "PestRiskLevel",
    "PestType",
    "classify_fruit_fly_cptd",
    "classify_cecid_fly_pct",
    # Weather scenarios
    "HistoricalWeatherGenerator",
    "HistoricalWeatherCoverage",
    "SeasonalWeatherProfile",
    "GUIMARAS_CLIMATE_PROFILES",
    # Metrics
    "ValidationMetrics",
    "ClassificationMetrics",
    "RegressionMetrics",
    "ConfusionMatrix",
    "compute_classification_metrics",
    "compute_regression_metrics",
    "compute_full_metrics",
    "bootstrap_confidence_intervals",
    "risk_score_to_level",
    "risk_score_to_pest_level",
    "normalized_risk_thresholds",
    "normalize_pest_value_to_risk",
    # Calibration
    "PestCalibrationCurve",
    "ValidationCalibration",
    "fit_risk_calibration",
    "identity_curve",
    # Validation runner
    "ValidationRunner",
    "ValidationCase",
    "ValidationResult",
    # Reports (original)
    "ValidationReportGenerator",
    "export_validation_csv",
    "export_validation_json",
    # Simulation aggregation (new)
    "SimulationAggregator",
    "AggregatedMetrics",
    "InfestationMetrics",
    "SpreadRateMetrics",
    "DensityMetrics",
    # Trend analysis (new)
    "TrendAnalyzer",
    "TrendComparisonResult",
    "CorrelationMetrics",
    "TrendDirectionMetrics",
    "ErrorMetrics",
    "SeasonalPatternMetrics",
    "compute_pearson_correlation",
    "compute_spearman_correlation",
    # Comparison reports (new)
    "ComparisonReportGenerator",
]
