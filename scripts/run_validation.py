#!/usr/bin/env python3
"""
MangoPoint — Historical Validation CLI
=======================================
Command-line interface for running model validation against BPI Guimaras data.

This script runs the validation module independently from the main application,
making it suitable for batch processing and research workflows.

The validation system compares simulated pest behavior with actual BPI monitoring
data to quantify model accuracy and demonstrate real-world applicability.

Features
--------
- Run full validation against 2022-2025 BPI Guimaras data
- Filter by pest type (Fruit Fly, Cecid Fly, or both)
- Generate comprehensive comparison reports with trend analysis
- Export metrics in multiple formats (CSV, JSON, TXT)

Usage Examples
--------------
    # Run full validation with defaults
    python -m scripts.run_validation
    
    # Run validation for specific pest type
    python -m scripts.run_validation --pest-type fruitfly
    
    # Run validation for specific years
    python -m scripts.run_validation --years 2023,2024
    
    # Limit number of cases
    python -m scripts.run_validation --max-cases 20
    
    # Save detailed reports with trend analysis
    python -m scripts.run_validation --output-dir outputs/validation --with-trends
    
    # Quick test with fewer Monte Carlo runs
    python -m scripts.run_validation --max-cases 5 --monte-carlo 10

    # Fit on 2022-2024 and report held-out 2025 testing metrics
    python -m scripts.run_validation --test-years 2025

Output Files
------------
    - validation_comparison_<timestamp>.csv: Detailed per-case results
    - validation_summary_<timestamp>.csv: Summary metrics
    - validation_full_<timestamp>.json: Complete data for programmatic access
    - validation_report_<timestamp>.txt: Human-readable report with trend analysis
"""

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from validation import (
    ValidationRunner,
    ValidationReportGenerator,
    HistoricalDataLoader,
    TrendAnalyzer,
    ComparisonReportGenerator,
)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


UNICODE_PROGRESS_CHARS = ("\u2588", "\u2591")
ASCII_PROGRESS_CHARS = ("#", "-")


def _stream_supports_text(stream, text: str) -> bool:
    """Return whether a stream can encode the given text safely."""
    encoding = getattr(stream, "encoding", None) or sys.getdefaultencoding()
    try:
        text.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def _progress_chars(stream=None) -> tuple[str, str]:
    """Choose progress-bar characters that will not crash the console."""
    stream = stream or sys.stdout
    if _stream_supports_text(stream, "".join(UNICODE_PROGRESS_CHARS)):
        return UNICODE_PROGRESS_CHARS
    return ASCII_PROGRESS_CHARS


def _format_progress_bar(
    current: int,
    total: int,
    bar_len: int = 30,
    stream=None,
) -> str:
    """Format a console-safe progress bar."""
    if total <= 0:
        filled = 0
        pct = 0.0
        total = 0
        current = 0
    else:
        current = max(0, min(current, total))
        pct = current / total * 100
        filled = int(bar_len * current / total)

    fill_char, empty_char = _progress_chars(stream)
    bar = fill_char * filled + empty_char * (bar_len - filled)
    return f"\r  Progress: [{bar}] {current}/{total} ({pct:.0f}%)"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run historical model validation against BPI Guimaras pest data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scripts.run_validation                           # Full validation
  python -m scripts.run_validation --pest-type fruitfly      # Fruit Fly only
  python -m scripts.run_validation --years 2023,2024         # Specific years
  python -m scripts.run_validation --test-years 2025         # Calibrate then test on 2025
  python -m scripts.run_validation --max-cases 10 --verbose  # Quick test with debug output
        """,
    )
    
    # Data options
    parser.add_argument(
        "--pest-type", "-p",
        choices=["cecid", "fruitfly", "both"],
        default="both",
        help="Pest type to validate (default: both)"
    )
    parser.add_argument(
        "--years", "-y",
        type=str,
        default=None,
        help="Comma-separated years to include (e.g., '2023,2024')"
    )
    parser.add_argument(
        "--max-cases", "-n",
        type=int,
        default=None,
        help="Maximum number of validation cases to run"
    )
    parser.add_argument(
        "--historical-weather-csv",
        type=str,
        default=None,
        help=(
            "Optional hourly weather CSV with datetime, temperature_c, "
            "wind_speed_ms, wind_dir_deg, and rainfall_mm columns"
        )
    )
    parser.add_argument(
        "--require-historical-weather",
        action="store_true",
        help=(
            "Fail before simulation if any selected validation case lacks "
            "enough hourly rows in --historical-weather-csv"
        ),
    )
    parser.add_argument(
        "--split-year",
        type=int,
        default=None,
        help=(
            "Use years before this as calibration and this year or later as "
            "testing"
        )
    )
    parser.add_argument(
        "--test-years",
        type=str,
        default=None,
        help=(
            "Comma-separated years reserved for testing; all other selected "
            "years become calibration"
        )
    )
    parser.add_argument(
        "--bootstrap",
        type=int,
        default=500,
        help="Bootstrap resamples for confidence intervals (default: 500; use 0 to disable)"
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.95,
        help="Confidence level for bootstrap intervals (default: 0.95)"
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help=(
            "Fit pest-specific risk calibration before metrics. With a split, "
            "calibration uses calibration years and is applied to testing years; "
            "without a split, all selected cases are used."
        ),
    )
    parser.add_argument(
        "--no-calibration",
        action="store_true",
        help="Disable automatic calibration for split-year/test-year runs",
    )
    
    # Simulation options
    parser.add_argument(
        "--hours", "-H",
        type=int,
        default=48,
        help="Simulation duration in hours (default: 48)"
    )
    parser.add_argument(
        "--monte-carlo", "-m",
        type=int,
        default=30,
        help="Number of Monte Carlo runs (default: 30)"
    )
    parser.add_argument(
        "--grid-size", "-g",
        type=int,
        default=20,
        help="Grid dimension (default: 20x20)"
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)"
    )
    
    # Output options
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=None,
        help="Output directory for reports (default: outputs/validation)"
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Skip exporting reports (only print summary)"
    )
    parser.add_argument(
        "--with-trends",
        action="store_true",
        help="Include detailed trend analysis in reports (default: True)"
    )
    parser.add_argument(
        "--legacy-format",
        action="store_true",
        help="Use legacy report format (without comparison reports)"
    )
    
    # Other options
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--data-summary",
        action="store_true",
        help="Only print historical data summary (don't run validation)"
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="Only list available validation cases (don't run validation)"
    )
    parser.add_argument(
        "--show-trend-analysis",
        action="store_true",
        help="Show detailed trend analysis after validation"
    )
    
    return parser.parse_args()


def _parse_years(value: str | None) -> list[int] | None:
    """Parse comma-separated years from CLI arguments."""
    if not value:
        return None
    return [int(year.strip()) for year in value.split(",") if year.strip()]


def _split_metadata(args: argparse.Namespace, test_years: list[int] | None) -> dict:
    """Build split metadata for reports."""
    if test_years:
        return {
            "strategy": "explicit_test_years",
            "test_years": test_years,
            "calibration_years": "all_selected_years_not_in_test_years",
        }
    if args.split_year is not None:
        return {
            "strategy": "split_year",
            "calibration": f"year < {args.split_year}",
            "testing": f"year >= {args.split_year}",
        }
    return {"strategy": "evaluation_only"}


def _should_apply_calibration(args: argparse.Namespace, has_split: bool) -> bool:
    """Return whether this run should fit and apply validation calibration."""
    if args.no_calibration:
        return False
    return bool(args.calibrate or has_split)


def _print_weather_coverage(summary: dict) -> None:
    """Print a compact historical weather coverage summary."""
    total = summary.get("total_cases", 0)
    ready = summary.get("historical_ready_cases", 0)
    fallback = summary.get("fallback_cases", 0)
    status_counts = summary.get("status_counts", {})

    print("\nHistorical weather coverage:")
    print(f"  Cases ready for historical weather: {ready}/{total}")
    print(f"  Cases that would use fallback weather: {fallback}/{total}")
    if status_counts:
        counts_text = ", ".join(
            f"{status}: {count}"
            for status, count in sorted(status_counts.items())
        )
        print(f"  Status counts: {counts_text}")

    missing = [
        item for item in summary.get("case_months", [])
        if not item.get("ready")
    ]
    if missing:
        print("  First uncovered case months:")
        for item in missing[:5]:
            print(
                "    "
                f"{item['year']}-{item['month']:02d}: "
                f"{item['status']} "
                f"({item['rows_available']}/{item['required_hours']} rows)"
            )


def print_data_summary() -> None:
    """Print summary of historical data."""
    print("\n" + "=" * 60)
    print("HISTORICAL DATA SUMMARY")
    print("=" * 60)
    
    loader = HistoricalDataLoader()
    loader.load()
    summary = loader.summary()
    
    print(f"\nData Source: BPI Guimaras Research and Development Center")
    print(f"Records: {summary['n_records']} monthly observations")
    print(f"Year Range: {summary['year_range']}")
    
    print("\nFruit Fly Risk Distribution:")
    for level, count in summary['fruit_fly_risk_distribution'].items():
        print(f"  {level}: {count} records")
    
    print("\nCecid Fly Risk Distribution:")
    for level, count in summary['cecid_fly_risk_distribution'].items():
        print(f"  {level}: {count} records")
    
    print(f"\nBiologically Relevant Records:")
    print(f"  Fruit Fly (MATURE stage): {summary['fruit_fly_relevant_records']}")
    print(f"  Cecid Fly (FRUITLET stage): {summary['cecid_fly_relevant_records']}")
    
    print("\n" + "=" * 60)


def list_validation_cases(
    pest_types: list = None,
    years: list = None,
    max_cases: int = None,
) -> None:
    """List available validation cases."""
    print("\n" + "=" * 60)
    print("AVAILABLE VALIDATION CASES")
    print("=" * 60)
    
    runner = ValidationRunner()
    cases = runner.generate_validation_cases(
        max_cases=max_cases,
        pest_types=pest_types,
        years=years,
    )
    
    print(f"\nTotal cases: {len(cases)}")
    print("\n{:<12} {:<8} {:<10} {:<12} {:<10} {:<10}".format(
        "Case ID", "Date", "Pest", "Stage", "Actual", "Level"
    ))
    print("-" * 62)
    
    for case in cases:
        print("{:<12} {:<8} {:<10} {:<12} {:<10.2f} {:<10}".format(
            case.case_id,
            case.date_str,
            case.pest_type,
            case.orchard_stage,
            case.actual_value,
            case.actual_level,
        ))
    
    print("\n" + "=" * 60)


def run_validation(args: argparse.Namespace) -> None:
    """Run the validation process."""
    logger = logging.getLogger(__name__)
    
    # Parse pest types
    if args.pest_type == "both":
        pest_types = None  # Both types
    else:
        pest_types = [args.pest_type]
    
    # Parse years
    years = _parse_years(args.years)
    test_years = _parse_years(args.test_years)
    has_split = args.split_year is not None or bool(test_years)
    calibration_requested = _should_apply_calibration(args, has_split)
    
    print("\n" + "=" * 60)
    print("MANGOPOINT MODEL VALIDATION")
    print("=" * 60)
    print(f"\nStarted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Configuration:")
    print(f"  Pest types: {pest_types or 'all'}")
    print(f"  Years: {years or 'all'}")
    print(f"  Max cases: {args.max_cases or 'unlimited'}")
    print(f"  Simulation hours: {args.hours}")
    print(f"  Monte Carlo runs: {args.monte_carlo}")
    print(f"  Grid size: {args.grid_size}x{args.grid_size}")
    print(f"  Random seed: {args.seed}")
    print(f"  Historical weather CSV: {args.historical_weather_csv or 'not provided'}")
    print(f"  Require historical weather: {'yes' if args.require_historical_weather else 'no'}")
    print(f"  Validation split: {_split_metadata(args, test_years)['strategy']}")
    print(f"  Risk calibration: {'enabled' if calibration_requested else 'disabled'}")
    print(f"  Bootstrap CI resamples: {args.bootstrap}")
    print("\n" + "-" * 60)
    
    # Create and run validation
    runner = ValidationRunner(
        seed=args.seed,
        historical_weather_path=(
            Path(args.historical_weather_csv)
            if args.historical_weather_csv
            else None
        ),
        require_historical_weather=args.require_historical_weather,
    )
    
    logger.info("Loading historical data...")
    runner.data_loader.load()
    
    logger.info("Generating validation cases...")
    cases = runner.generate_validation_cases(
        max_cases=args.max_cases,
        pest_types=pest_types,
        years=years,
    )
    split_groups = runner.assign_case_splits(
        cases,
        split_year=args.split_year,
        test_years=test_years,
    )
    print(f"Generated {len(cases)} validation cases")
    if args.split_year is not None or test_years:
        split_counts = ", ".join(
            f"{split}: {len(split_cases)}"
            for split, split_cases in sorted(split_groups.items())
        )
        print(f"Split counts: {split_counts}")

    weather_coverage = runner.weather_generator.summarize_case_coverage(
        cases,
        hours=args.hours,
    )
    _print_weather_coverage(weather_coverage)
    if args.require_historical_weather and weather_coverage.get("fallback_cases", 0):
        raise SystemExit(
            "Historical weather coverage is incomplete. "
            "Provide a CSV covering all selected case months or remove "
            "--require-historical-weather to allow synthetic fallback."
        )
    
    logger.info(f"Running validation ({len(cases)} cases)...")
    print("\nRunning simulations (this may take several minutes)...")
    
    def progress_callback(current, total):
        print(_format_progress_bar(current, total), end="", flush=True)
    
    results = runner.run_validation(
        cases=cases,
        hours=args.hours,
        monte_carlo_runs=args.monte_carlo,
        grid_size=args.grid_size,
        progress_callback=progress_callback,
    )
    
    print()  # New line after progress bar

    calibration = None
    if calibration_requested:
        calibration_source_split = "calibration" if has_split else None
        try:
            calibration = runner.fit_calibration(split=calibration_source_split)
            results = runner.apply_calibration(calibration)
            print("\nApplied risk-score calibration:")
            for pest_type, curve in sorted(calibration.curves.items()):
                print(
                    f"  {pest_type}: scale={curve.scale:.3f}, "
                    f"intercept={curve.intercept:.3f}, "
                    f"cases={curve.n_cases}, "
                    f"MAE {curve.mae_before:.3f}->{curve.mae_after:.3f}"
                )
        except ValueError as exc:
            print(f"\nCalibration skipped: {exc}")
    
    # Compute metrics
    metrics = runner.compute_metrics(
        bootstrap_iterations=args.bootstrap,
        confidence=args.confidence,
        seed=args.seed,
    )
    
    # Print summary
    print("\n" + "-" * 60)
    print(metrics.summary_string())

    split_metrics = {}
    if args.split_year is not None or test_years:
        split_metrics = runner.compute_split_metrics(
            bootstrap_iterations=args.bootstrap,
            confidence=args.confidence,
            seed=args.seed,
        )
        print("\n" + "-" * 60)
        print("CALIBRATION / TESTING SPLIT")
        print("-" * 60)
        for split_name, split_metric in sorted(split_metrics.items()):
            print(
                f"{split_name.title()}: "
                f"{split_metric.total_tests} cases, "
                f"accuracy {split_metric.overall_accuracy_pct:.1f}%, "
                f"F1 {split_metric.classification.f1_score:.3f}, "
                f"MAE {split_metric.regression.mae:.3f}"
            )
    
    # Trend analysis (if requested or by default)
    if args.show_trend_analysis or not args.no_export:
        print("\n" + "-" * 60)
        print("TREND ANALYSIS")
        print("-" * 60)
        
        # Create trend analyzer
        trend_analyzer = TrendAnalyzer(
            historical_records=runner.data_loader.records,
            simulated_results=results,
        )
        
        # Compute and display trend comparisons
        comparisons = trend_analyzer.compute_all_comparisons()
        
        for pest_type, comparison in comparisons.items():
            if pest_type == "overall":
                continue
            print(f"\n{pest_type.upper()}:")
            print(f"  Trend Similarity Score: {comparison.trend_similarity_score:.1%}")
            print(f"  Correlation (Pearson r): {comparison.correlation.pearson_r:.3f} ({comparison.correlation.correlation_strength})")
            print(f"  Trend Direction Accuracy: {comparison.trend_direction.direction_accuracy:.1%}")
            print(f"  MAPE: {comparison.errors.mape_pct:.1f}%")
        
        # Overall
        overall = comparisons.get("overall")
        if overall:
            print(f"\nOVERALL:")
            print(f"  Trend Similarity Score: {overall.trend_similarity_score:.1%}")
            print(f"  Correlation (Pearson r): {overall.correlation.pearson_r:.3f}")
            print(f"  Direction Accuracy: {overall.trend_direction.direction_accuracy:.1%}")
    
    # Export reports if requested
    if not args.no_export:
        output_dir = args.output_dir or "outputs/validation"
        print(f"\n" + "-" * 60)
        print(f"Exporting reports to: {output_dir}")
        weather_sources = Counter(
            result.weather_stats.get("source", "unknown")
            for result in results
        )
        report_metadata = {
            "split": _split_metadata(args, test_years),
            "split_metrics": {
                split_name: split_metric.to_dict()
                for split_name, split_metric in split_metrics.items()
            },
            "weather": {
                "historical_weather_csv": args.historical_weather_csv,
                "require_historical_weather": args.require_historical_weather,
                "source_counts": dict(weather_sources),
                "coverage": weather_coverage,
            },
            "bootstrap": {
                "iterations": args.bootstrap,
                "confidence": args.confidence,
            },
            "calibration": (
                calibration.to_dict()
                if calibration
                else {
                    "enabled": False,
                    "requested": calibration_requested,
                    "reason": "not requested or no usable calibration split",
                }
            ),
            "science_notes": [
                (
                    "Use --historical-weather-csv to replace synthetic seasonal "
                    "profiles with observed hourly weather when available."
                ),
                (
                    "When calibration is enabled, curves are fit only from the "
                    "calibration split and then frozen before testing metrics "
                    "are computed."
                ),
            ],
        }
        
        if args.legacy_format:
            # Legacy format using ValidationReportGenerator
            report_gen = ValidationReportGenerator(results, metrics, report_metadata)
            files = report_gen.export_all(output_dir)
        else:
            # New comprehensive reports using ComparisonReportGenerator
            report_gen = ComparisonReportGenerator(
                validation_results=results,
                validation_metrics=metrics,
                historical_loader=runner.data_loader,
                metadata=report_metadata,
            )
            files = report_gen.export_all(output_dir)
        
        print("Generated files:")
        for report_type, filepath in files.items():
            print(f"  - {report_type}: {filepath}")
    
    print("\n" + "=" * 60)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")


def main():
    """Main entry point."""
    args = parse_args()
    setup_logging(args.verbose)
    
    # Parse pest types for non-validation commands
    if args.pest_type == "both":
        pest_types = None
    else:
        pest_types = [args.pest_type]
    
    years = _parse_years(args.years)
    
    # Handle different modes
    if args.data_summary:
        print_data_summary()
    elif args.list_cases:
        list_validation_cases(pest_types, years, args.max_cases)
    else:
        run_validation(args)


if __name__ == "__main__":
    main()
