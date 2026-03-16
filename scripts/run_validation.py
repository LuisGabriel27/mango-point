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
    years = None
    if args.years:
        years = [int(y.strip()) for y in args.years.split(",")]
    
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
    print("\n" + "-" * 60)
    
    # Create and run validation
    runner = ValidationRunner(seed=args.seed)
    
    logger.info("Loading historical data...")
    runner.data_loader.load()
    
    logger.info("Generating validation cases...")
    cases = runner.generate_validation_cases(
        max_cases=args.max_cases,
        pest_types=pest_types,
        years=years,
    )
    print(f"Generated {len(cases)} validation cases")
    
    logger.info(f"Running validation ({len(cases)} cases)...")
    print("\nRunning simulations (this may take several minutes)...")
    
    def progress_callback(current, total):
        pct = current / total * 100
        bar_len = 30
        filled = int(bar_len * current / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  Progress: [{bar}] {current}/{total} ({pct:.0f}%)", end="", flush=True)
    
    results = runner.run_validation(
        hours=args.hours,
        monte_carlo_runs=args.monte_carlo,
        grid_size=args.grid_size,
        progress_callback=progress_callback,
    )
    
    print()  # New line after progress bar
    
    # Compute metrics
    metrics = runner.compute_metrics()
    
    # Print summary
    print("\n" + "-" * 60)
    print(metrics.summary_string())
    
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
        
        if args.legacy_format:
            # Legacy format using ValidationReportGenerator
            report_gen = ValidationReportGenerator(results, metrics)
            files = report_gen.export_all(output_dir)
        else:
            # New comprehensive reports using ComparisonReportGenerator
            report_gen = ComparisonReportGenerator(
                validation_results=results,
                validation_metrics=metrics,
                historical_loader=runner.data_loader,
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
    
    years = None
    if args.years:
        years = [int(y.strip()) for y in args.years.split(",")]
    
    # Handle different modes
    if args.data_summary:
        print_data_summary()
    elif args.list_cases:
        list_validation_cases(pest_types, years, args.max_cases)
    else:
        run_validation(args)


if __name__ == "__main__":
    main()
