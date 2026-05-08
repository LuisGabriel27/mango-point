"""
MangoPoint Validation — Comparison Report Generator
====================================================
Generates comprehensive comparison reports between simulated and actual BPI data.

This module provides:
1. Side-by-side monthly comparisons with actual BPI values
2. Statistical summary with all validation metrics
3. Trend analysis visualization data
4. Research documentation exports (CSV, JSON, TXT)

The reporter integrates all validation components:
- ValidationRunner results
- SimulationAggregator metrics
- TrendAnalyzer comparisons
- Historical BPI data

Usage Example
-------------
    from validation.comparison_report import ComparisonReportGenerator
    from validation import ValidationRunner
    
    # Run validation
    runner = ValidationRunner()
    results = runner.run_full_validation()
    metrics = runner.compute_metrics()
    
    # Generate comprehensive report
    report_gen = ComparisonReportGenerator(
        validation_results=results,
        validation_metrics=metrics,
        historical_loader=runner.data_loader,
    )
    
    # Export all reports
    report_gen.export_all("outputs/validation/")
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .validation_runner import ValidationResult
    from .metrics import ValidationMetrics
    from .historical_data import HistoricalDataLoader
    from .trend_analysis import TrendComparisonResult


class ComparisonReportGenerator:
    """
    Generates comprehensive comparison reports for research documentation.
    
    This class creates detailed reports that:
    1. Compare simulated predictions with actual BPI observations
    2. Provide statistical validation metrics
    3. Analyze temporal trends and patterns
    4. Export data in multiple formats for analysis
    
    Report Types
    ------------
    - Summary Report: Human-readable validation summary
    - Comparison Table: Month-by-month actual vs predicted
    - Trend Analysis: Correlation and pattern analysis
    - Full Data Export: Complete data for external analysis
    
    Usage
    -----
        report_gen = ComparisonReportGenerator(
            validation_results=results,
            validation_metrics=metrics,
            historical_loader=data_loader,
        )
        
        # Export all reports to directory
        report_gen.export_all("outputs/validation/")
        
        # Get specific reports
        summary = report_gen.generate_summary_report()
        comparison_table = report_gen.get_comparison_table()
    """
    
    def __init__(
        self,
        validation_results: List["ValidationResult"],
        validation_metrics: "ValidationMetrics",
        historical_loader: Optional["HistoricalDataLoader"] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the report generator.
        
        Parameters
        ----------
        validation_results : list[ValidationResult]
            Results from ValidationRunner
        validation_metrics : ValidationMetrics
            Computed validation metrics
        historical_loader : HistoricalDataLoader, optional
            Loader containing historical BPI data
        metadata : dict, optional
            Additional run metadata such as split strategy and weather source.
        """
        self.results = validation_results
        self.metrics = validation_metrics
        self.historical_loader = historical_loader
        self.metadata = metadata or {}
        
        # Lazy-load trend analyzer
        self._trend_analyzer = None
        self._trend_comparisons = None
        
        # Metadata
        self._generated_at = datetime.now()
    
    def _get_trend_analyzer(self):
        """Get or create trend analyzer."""
        if self._trend_analyzer is None:
            from .trend_analysis import TrendAnalyzer
            
            historical_records = []
            if self.historical_loader:
                self.historical_loader.ensure_loaded()
                historical_records = self.historical_loader.records
            
            self._trend_analyzer = TrendAnalyzer(
                historical_records=historical_records,
                simulated_results=self.results,
            )
        
        return self._trend_analyzer
    
    def _get_trend_comparisons(self) -> Dict[str, "TrendComparisonResult"]:
        """Get or compute trend comparisons."""
        if self._trend_comparisons is None:
            analyzer = self._get_trend_analyzer()
            self._trend_comparisons = analyzer.compute_all_comparisons()
        return self._trend_comparisons
    
    # ── Report Generation Methods ───────────────────────────────
    
    def generate_summary_report(self) -> str:
        """
        Generate comprehensive summary report.
        
        Returns
        -------
        str
            Multi-page formatted text report
        """
        trend_comparisons = self._get_trend_comparisons()
        
        lines = [
            "=" * 75,
            "MANGOPOINT SIMULATION VALIDATION REPORT",
            "Comparison with BPI Guimaras Historical Monitoring Data (2022-2025)",
            "=" * 75,
            "",
            f"Report Generated: {self._generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Data Period: {self._get_data_period()}",
            "",
            "",
            "=" * 75,
            "SECTION 1: EXECUTIVE SUMMARY",
            "=" * 75,
            "",
        ]
        
        # Executive summary
        overall = trend_comparisons.get("overall")
        if overall:
            lines.extend([
                f"Overall Trend Similarity Score: {overall.trend_similarity_score:.1%}",
                f"Overall Correlation (Pearson r): {overall.correlation.pearson_r:.3f}",
                f"Total Validation Cases: {self.metrics.total_tests}",
                f"Classification Accuracy: {self.metrics.overall_accuracy_pct:.1f}%",
                "",
                "Key Findings:",
            ])
            
            # Add interpretation based on scores
            if overall.trend_similarity_score >= 0.80:
                lines.append("  [PASS] Simulation captures real-world pest patterns VERY WELL")
            elif overall.trend_similarity_score >= 0.60:
                lines.append("  [PASS] Simulation captures major trends SUCCESSFULLY")
            elif overall.trend_similarity_score >= 0.40:
                lines.append("  ~ Simulation captures SOME patterns, improvements possible")
            else:
                lines.append("  [FAIL] Significant discrepancy with observed data")
            
            if self.metrics.classification.recall >= 0.80:
                lines.append(f"  [PASS] High outbreak detection rate ({self.metrics.classification.recall:.0%})")
            if self.metrics.classification.precision >= 0.70:
                lines.append(f"  [PASS] Low false alarm rate (precision: {self.metrics.classification.precision:.0%})")
        
        # Section 2: Detailed Classification Metrics
        lines.extend([
            "",
            "",
            "=" * 75,
            "SECTION 2: CLASSIFICATION METRICS",
            "=" * 75,
            "",
            "For outbreak detection (HIGH risk = positive class):",
            "",
            f"  Total Cases:        {self.metrics.total_tests}",
            f"  Correct:            {self.metrics.correct_predictions}",
            f"  Incorrect:          {self.metrics.incorrect_predictions}",
            "",
            "  Classification Performance:",
            f"    Accuracy:         {self.metrics.overall_accuracy_pct:.1f}%",
            f"    Precision:        {self.metrics.classification.precision:.3f}",
            f"    Recall:           {self.metrics.classification.recall:.3f}",
            f"    F1-Score:         {self.metrics.classification.f1_score:.3f}",
            f"    Specificity:      {self.metrics.classification.specificity:.3f}",
            "",
        ])

        if self.metrics.confidence_intervals:
            lines.extend([
                "  Bootstrap Confidence Intervals:",
            ])
            for metric_name in ("overall_accuracy_pct", "precision", "recall", "f1_score"):
                interval = self.metrics.confidence_intervals.get(metric_name)
                if not interval:
                    continue
                label = metric_name.replace("_", " ").title()
                lines.append(
                    f"    {label}: {interval['lower']:.3f} to "
                    f"{interval['upper']:.3f} ({interval['confidence']:.0%})"
                )
            lines.append("")
        
        # Confusion matrix
        cm = self.metrics.classification.confusion_matrix
        if cm:
            lines.extend([
                "  Confusion Matrix:",
                "",
                "                        Predicted",
                "                   LOW/MEDIUM    HIGH",
                f"  Actual LOW/MED     {cm.true_negatives:5d}      {cm.false_positives:5d}",
                f"  Actual HIGH        {cm.false_negatives:5d}      {cm.true_positives:5d}",
                "",
            ])
        
        # Per-pest breakdown
        if self.metrics.fruit_fly_metrics:
            lines.extend([
                "",
                "  Fruit Fly (Bactrocera) Performance:",
                f"    Cases:     {self.metrics.fruit_fly_metrics.n_samples}",
                f"    Accuracy:  {self.metrics.fruit_fly_metrics.accuracy:.1%}",
                f"    F1-Score:  {self.metrics.fruit_fly_metrics.f1_score:.3f}",
                "",
            ])
        
        if self.metrics.cecid_fly_metrics:
            lines.extend([
                "  Cecid Fly (Gall Midge) Performance:",
                f"    Cases:     {self.metrics.cecid_fly_metrics.n_samples}",
                f"    Accuracy:  {self.metrics.cecid_fly_metrics.accuracy:.1%}",
                f"    F1-Score:  {self.metrics.cecid_fly_metrics.f1_score:.3f}",
                "",
            ])
        
        # Section 3: Regression Metrics
        lines.extend([
            "",
            "=" * 75,
            "SECTION 3: REGRESSION METRICS",
            "=" * 75,
            "",
            "Numeric prediction accuracy (risk score vs normalized actual):",
            "",
            f"  Mean Absolute Error (MAE):      {self.metrics.regression.mae:.4f}",
            f"  Root Mean Square Error (RMSE):  {self.metrics.regression.rmse:.4f}",
            f"  R² (Coefficient of Determination): {self.metrics.regression.r_squared:.4f}",
            f"  Normalized MAE:                 {self.metrics.regression.normalized_mae:.4f}",
            "",
            f"  Mean Actual Value:              {self.metrics.regression.mean_actual:.4f}",
            f"  Mean Predicted Value:           {self.metrics.regression.mean_predicted:.4f}",
            "",
        ])
        
        # Section 4: Trend Analysis
        lines.extend([
            "",
            "=" * 75,
            "SECTION 4: TREND ANALYSIS",
            "=" * 75,
            "",
        ])
        
        for pest_type, comparison in trend_comparisons.items():
            if pest_type == "overall":
                continue
            
            lines.extend([
                f"--- {pest_type.upper()} ---",
                "",
                f"  Trend Similarity Score: {comparison.trend_similarity_score:.1%}",
                "",
                "  Correlation Analysis:",
                f"    Pearson r:        {comparison.correlation.pearson_r:.3f} ({comparison.correlation.correlation_strength})",
                f"    Spearman rho:     {comparison.correlation.spearman_rho:.3f}",
                f"    Significant:      {'Yes (p<0.05)' if comparison.correlation.is_significant else 'No'}",
                "",
                "  Trend Direction Accuracy:",
                f"    Correct:          {comparison.trend_direction.n_correct_directions}/{comparison.trend_direction.n_total_transitions} ({comparison.trend_direction.direction_accuracy:.1%})",
                "",
                "  Seasonal Patterns:",
                f"    Wet Season r:     {comparison.seasonal.wet_season_correlation:.3f}",
                f"    Dry Season r:     {comparison.seasonal.dry_season_correlation:.3f}",
                f"    Peak Month Match: {'Yes' if comparison.seasonal.peak_month_match else 'No'}",
                f"                      (Actual: {comparison.seasonal.actual_peak_month}, Predicted: {comparison.seasonal.predicted_peak_month})",
                "",
            ])
        
        # Section 5: Monthly Comparison
        lines.extend([
            "",
            "=" * 75,
            "SECTION 5: MONTHLY COMPARISON (SAMPLE)",
            "=" * 75,
            "",
        ])
        
        # Show first 10 comparisons
        comparison_table = self.get_comparison_table()[:10]
        if comparison_table:
            lines.extend([
                "Date        | Pest      | Actual Level | Predicted | Match",
                "-" * 60,
            ])
            for row in comparison_table:
                match_symbol = "PASS" if row["match"] else "FAIL"
                lines.append(
                    f"{row['date']:11} | {row['pest_type']:9} | {row['actual_level']:12} | "
                    f"{row['predicted_level']:9} | {match_symbol}"
                )
            
            if len(self.results) > 10:
                lines.append(f"... and {len(self.results) - 10} more cases")
        
        # Section 6: Methodology
        lines.extend([
            "",
            "",
            "=" * 75,
            "SECTION 6: METHODOLOGY NOTES",
            "=" * 75,
            "",
            "Data Sources:",
            "  - Historical: BPI Guimaras Research and Development Center (2022-2025)",
            "  - Fruit Fly: Catch Per Trap per Day (CPTD) from pheromone traps",
            "  - Cecid Fly: Infestation percentage from fruit sampling",
            "",
            "Classification Thresholds:",
            "  Fruit Fly CPTD:  LOW < 8 | MEDIUM 8-20 | HIGH > 20 flies/trap/day",
            "  Cecid Fly %:     LOW < 5% | MEDIUM 5-15% | HIGH > 15%",
            "",
            "Simulation Configuration:",
            "  - Monte Carlo ensemble: 30 runs per scenario",
            f"  - Weather: {self._weather_methodology_note()}",
            f"  - Validation split: {self._split_methodology_note()}",
            f"  - Risk calibration: {self._calibration_methodology_note()}",
            "  - Grid: 20x20 cells (0.25 hectares)",
            "  - Duration: 48 hours per validation case",
            "",
            "Interpretation Guide:",
            "",
            "  Classification Accuracy:",
            "    > 80%: Excellent agreement with historical observations",
            "    60-80%: Good predictive capability",
            "    < 60%: Model refinement recommended",
            "",
            "  Trend Similarity:",
            "    > 0.80: Simulation captures patterns very well",
            "    0.60-0.80: Major trends captured",
            "    < 0.60: Temporal patterns need improvement",
            "",
            "  Recall (Sensitivity):",
            "    High recall (>0.8) is critical for early warning systems",
            "    Prioritized over precision for pest management applications",
            "",
            "Validation Limits:",
            "  - BPI pest observations are monthly aggregates, not tree-level forecasts.",
            "  - Synthetic weather validates plausibility more than true forecasting accuracy.",
            "  - When enabled, calibration aligns validation scores to BPI observations; it does not prove future field accuracy.",
            "",
            "=" * 75,
            "END OF REPORT",
            "=" * 75,
        ])
        
        return "\n".join(lines)
    
    def get_comparison_table(self) -> List[Dict[str, Any]]:
        """
        Get full comparison table with all validation results.
        
        Returns
        -------
        list of dicts
            Each dict contains case details and comparison info
        """
        table = []
        
        for result in self.results:
            table.append({
                "case_id": result.case.case_id,
                "date": result.case.date_str,
                "year": result.case.year,
                "month": result.case.month,
                "pest_type": result.case.pest_type,
                "orchard_stage": result.case.orchard_stage,
                "season": result.case.season,
                "split": result.case.split,
                "actual_value": result.case.actual_value,
                "actual_level": result.case.actual_level,
                "predicted_risk": result.predicted_risk,
                "predicted_level": result.predicted_level,
                "raw_predicted_risk": result.raw_predicted_risk,
                "raw_predicted_level": result.raw_predicted_level,
                "calibration_applied": result.calibration_applied,
                "calibration_method": result.calibration_method,
                "match": result.match,
                "error": result.error,
                "peak_risk": result.peak_risk,
                "simulation_time_s": result.simulation_time_s,
                "weather_source": result.weather_stats.get("source", "unknown"),
            })
        
        return sorted(table, key=lambda x: (x["year"], x["month"]))
    
    def get_monthly_aggregates(self) -> Dict[str, Dict[str, Any]]:
        """
        Get aggregated metrics by month across all years.
        
        Returns
        -------
        dict
            Keys are month names, values contain aggregate statistics
        """
        month_names = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ]
        
        aggregates = {name: {
            "n_cases": 0,
            "n_correct": 0,
            "mean_actual": [],
            "mean_predicted": [],
            "accuracy": 0.0,
        } for name in month_names}
        
        for result in self.results:
            month_name = month_names[result.case.month - 1]
            agg = aggregates[month_name]
            
            agg["n_cases"] += 1
            if result.match:
                agg["n_correct"] += 1
            
            # Normalize actual value
            if result.case.pest_type == "cecid":
                actual_norm = result.case.actual_value / 100.0
            else:
                actual_norm = min(1.0, result.case.actual_value / 40.0)
            
            agg["mean_actual"].append(actual_norm)
            agg["mean_predicted"].append(result.predicted_risk)
        
        # Compute aggregates
        for name, agg in aggregates.items():
            if agg["n_cases"] > 0:
                agg["accuracy"] = agg["n_correct"] / agg["n_cases"]
                agg["mean_actual"] = np.mean(agg["mean_actual"])
                agg["mean_predicted"] = np.mean(agg["mean_predicted"])
            else:
                agg["mean_actual"] = 0.0
                agg["mean_predicted"] = 0.0
        
        return aggregates
    
    def get_yearly_accuracy(self) -> Dict[int, float]:
        """
        Get accuracy breakdown by year.
        
        Returns
        -------
        dict
            Keys are years, values are accuracy percentages
        """
        yearly = {}
        
        for result in self.results:
            year = result.case.year
            if year not in yearly:
                yearly[year] = {"correct": 0, "total": 0}
            
            yearly[year]["total"] += 1
            if result.match:
                yearly[year]["correct"] += 1
        
        return {
            year: (counts["correct"] / counts["total"] * 100)
            for year, counts in yearly.items()
        }
    
    def _get_data_period(self) -> str:
        """Get date range string."""
        if not self.results:
            return "N/A"
        
        years = [r.case.year for r in self.results]
        return f"{min(years)}-{max(years)}"

    def _weather_methodology_note(self) -> str:
        """Describe weather source used in this validation run."""
        weather_meta = self.metadata.get("weather", {})
        source_counts = weather_meta.get("source_counts", {})
        if source_counts:
            parts = [
                f"{source} ({count} cases)"
                for source, count in sorted(source_counts.items())
            ]
            source_text = ", ".join(parts)
        else:
            source_text = "source not recorded"

        coverage = weather_meta.get("coverage", {})
        coverage_text = ""
        if coverage:
            ready = coverage.get("historical_ready_cases", 0)
            total = coverage.get("total_cases", 0)
            fallback = coverage.get("fallback_cases", 0)
            coverage_text = (
                f"; historical coverage {ready}/{total} cases, "
                f"fallback {fallback}"
            )

        if weather_meta.get("historical_weather_csv"):
            return (
                "hourly historical CSV where sufficient rows exist; "
                f"otherwise seasonal synthetic profiles. Sources: {source_text}{coverage_text}"
            )
        return (
            "seasonally calibrated synthetic profiles; no hourly historical "
            f"weather CSV supplied. Sources: {source_text}{coverage_text}"
        )

    def _split_methodology_note(self) -> str:
        """Describe calibration/testing split strategy."""
        split_meta = self.metadata.get("split", {})
        strategy = split_meta.get("strategy", "evaluation_only")
        if strategy == "explicit_test_years":
            return f"explicit test years {split_meta.get('test_years', [])}"
        if strategy == "split_year":
            return (
                f"{split_meta.get('calibration', 'calibration')} / "
                f"{split_meta.get('testing', 'testing')}"
            )
        return "no holdout split requested"

    def _calibration_methodology_note(self) -> str:
        """Describe risk-score calibration used in this validation run."""
        calibration_meta = self.metadata.get("calibration", {})
        if not calibration_meta.get("enabled"):
            return "not applied"

        curves = calibration_meta.get("curves", {})
        curve_parts = []
        for pest_type, curve in sorted(curves.items()):
            curve_parts.append(
                f"{pest_type} n={curve.get('n_cases', 0)} "
                f"MAE {curve.get('mae_before', 0.0):.3f}->{curve.get('mae_after', 0.0):.3f}"
            )
        curve_text = "; ".join(curve_parts) if curve_parts else "no pest curves"
        return (
            f"{calibration_meta.get('method', 'calibration')} fit on "
            f"{calibration_meta.get('source_split', 'calibration')} ({curve_text})"
        )
    
    # ── Export Methods ──────────────────────────────────────────
    
    def export_comparison_csv(self, filepath: str) -> None:
        """
        Export detailed comparison table to CSV.
        
        Parameters
        ----------
        filepath : str
            Output file path
        """
        table = self.get_comparison_table()
        
        if not table:
            return
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=table[0].keys())
            writer.writeheader()
            writer.writerows(table)
    
    def export_summary_csv(self, filepath: str) -> None:
        """
        Export summary metrics to CSV.
        
        Parameters
        ----------
        filepath : str
            Output file path
        """
        trend_comparisons = self._get_trend_comparisons()
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Build summary rows
        rows = []
        
        # Overall metrics
        rows.append({
            "category": "overall",
            "metric": "total_tests",
            "value": self.metrics.total_tests,
        })
        rows.append({
            "category": "overall",
            "metric": "accuracy_pct",
            "value": self.metrics.overall_accuracy_pct,
        })
        
        # Classification metrics
        for metric_name in ["precision", "recall", "f1_score", "specificity"]:
            rows.append({
                "category": "classification",
                "metric": metric_name,
                "value": getattr(self.metrics.classification, metric_name),
            })
        
        # Regression metrics
        for metric_name in ["mae", "rmse", "r_squared", "normalized_mae"]:
            rows.append({
                "category": "regression",
                "metric": metric_name,
                "value": getattr(self.metrics.regression, metric_name),
            })

        for metric_name, interval in self.metrics.confidence_intervals.items():
            rows.append({
                "category": "confidence_interval",
                "metric": f"{metric_name}_lower",
                "value": interval["lower"],
            })
            rows.append({
                "category": "confidence_interval",
                "metric": f"{metric_name}_upper",
                "value": interval["upper"],
            })

        calibration_meta = self.metadata.get("calibration", {})
        if calibration_meta.get("enabled"):
            for pest_type, curve in calibration_meta.get("curves", {}).items():
                for metric_name in ("scale", "intercept", "mae_before", "mae_after", "n_cases"):
                    rows.append({
                        "category": f"calibration_{pest_type}",
                        "metric": metric_name,
                        "value": curve.get(metric_name),
                    })
        
        # Trend analysis
        for pest_type, comparison in trend_comparisons.items():
            rows.append({
                "category": f"trend_{pest_type}",
                "metric": "similarity_score",
                "value": comparison.trend_similarity_score,
            })
            rows.append({
                "category": f"trend_{pest_type}",
                "metric": "pearson_r",
                "value": comparison.correlation.pearson_r,
            })
            rows.append({
                "category": f"trend_{pest_type}",
                "metric": "direction_accuracy",
                "value": comparison.trend_direction.direction_accuracy,
            })
        
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["category", "metric", "value"])
            writer.writeheader()
            writer.writerows(rows)
    
    def export_full_json(self, filepath: str) -> None:
        """
        Export complete validation data to JSON.
        
        Parameters
        ----------
        filepath : str
            Output file path
        """
        trend_comparisons = self._get_trend_comparisons()
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "metadata": {
                "generated_at": self._generated_at.isoformat(),
                "data_period": self._get_data_period(),
                "total_cases": len(self.results),
                "run_metadata": self.metadata,
            },
            "validation_metrics": self.metrics.to_dict(),
            "trend_comparisons": {
                pest_type: comparison.to_dict()
                for pest_type, comparison in trend_comparisons.items()
            },
            "comparison_table": self.get_comparison_table(),
            "monthly_aggregates": self.get_monthly_aggregates(),
            "yearly_accuracy": self.get_yearly_accuracy(),
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    
    def export_text_report(self, filepath: str) -> None:
        """
        Export full text report.
        
        Parameters
        ----------
        filepath : str
            Output file path
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        report = self.generate_summary_report()
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
    
    def export_all(self, output_dir: str, prefix: str = "validation") -> Dict[str, str]:
        """
        Export all report formats to a directory.
        
        Parameters
        ----------
        output_dir : str
            Output directory path
        prefix : str
            Filename prefix for all exports
        
        Returns
        -------
        dict
            Mapping of report type to file path
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = self._generated_at.strftime("%Y%m%d_%H%M%S")
        
        files = {}
        
        # Comparison table CSV
        comparison_path = output_dir / f"{prefix}_comparison_{timestamp}.csv"
        self.export_comparison_csv(str(comparison_path))
        files["comparison_csv"] = str(comparison_path)
        
        # Summary CSV
        summary_path = output_dir / f"{prefix}_summary_{timestamp}.csv"
        self.export_summary_csv(str(summary_path))
        files["summary_csv"] = str(summary_path)
        
        # Full JSON
        json_path = output_dir / f"{prefix}_full_{timestamp}.json"
        self.export_full_json(str(json_path))
        files["full_json"] = str(json_path)
        
        # Text report
        report_path = output_dir / f"{prefix}_report_{timestamp}.txt"
        self.export_text_report(str(report_path))
        files["text_report"] = str(report_path)
        
        return files
    
    # ── Visualization Data Methods ──────────────────────────────
    
    def get_chart_data_monthly_comparison(self) -> Dict[str, Any]:
        """
        Get data formatted for monthly comparison charts.
        
        Returns
        -------
        dict
            Data structure suitable for charting libraries
        """
        aggregates = self.get_monthly_aggregates()
        
        months = list(aggregates.keys())
        actual = [aggregates[m]["mean_actual"] for m in months]
        predicted = [aggregates[m]["mean_predicted"] for m in months]
        accuracy = [aggregates[m]["accuracy"] for m in months]
        
        return {
            "labels": months,
            "datasets": {
                "actual": actual,
                "predicted": predicted,
                "accuracy": accuracy,
            },
        }
    
    def get_chart_data_scatter(self) -> Dict[str, Any]:
        """
        Get data for actual vs predicted scatter plot.
        
        Returns
        -------
        dict
            Data points for scatter visualization
        """
        points = []
        
        for result in self.results:
            # Normalize actual value
            if result.case.pest_type == "cecid":
                actual_norm = result.case.actual_value / 100.0
            else:
                actual_norm = min(1.0, result.case.actual_value / 40.0)
            
            points.append({
                "x": actual_norm,
                "y": result.predicted_risk,
                "label": result.case.case_id,
                "pest_type": result.case.pest_type,
                "match": result.match,
            })
        
        return {
            "points": points,
            "x_label": "Actual (normalized)",
            "y_label": "Predicted Risk",
            "ideal_line": [[0, 0], [1, 1]],
        }
    
    def get_chart_data_time_series(
        self,
        pest_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get data for time series comparison chart.
        
        Parameters
        ----------
        pest_type : str, optional
            Filter by pest type
        
        Returns
        -------
        dict
            Time series data for charting
        """
        filtered = [
            r for r in self.results
            if pest_type is None or r.case.pest_type == pest_type
        ]
        
        # Sort by date
        sorted_results = sorted(filtered, key=lambda r: (r.case.year, r.case.month))
        
        dates = []
        actual = []
        predicted = []
        
        for result in sorted_results:
            dates.append(result.case.date_str)
            
            # Normalize actual value
            if result.case.pest_type == "cecid":
                actual_norm = result.case.actual_value / 100.0
            else:
                actual_norm = min(1.0, result.case.actual_value / 40.0)
            
            actual.append(actual_norm)
            predicted.append(result.predicted_risk)
        
        return {
            "labels": dates,
            "datasets": {
                "actual": actual,
                "predicted": predicted,
            },
            "pest_type": pest_type or "all",
        }
