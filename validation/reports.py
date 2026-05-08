"""
MangoPoint Validation — Report Generator
=========================================
Generates structured reports and exports for validation results.

This module provides:
1. CSV export of detailed validation results
2. JSON export with complete metrics
3. Summary report generation for research documentation
4. Data formatting for visualization/graphing
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .validation_runner import ValidationResult, ValidationRunner
    from .metrics import ValidationMetrics


class ValidationReportGenerator:
    """
    Generates comprehensive validation reports.
    
    Usage
    -----
        from validation import ValidationRunner, ValidationReportGenerator
        
        runner = ValidationRunner()
        results = runner.run_full_validation()
        metrics = runner.compute_metrics()
        
        report = ValidationReportGenerator(results, metrics)
        report.export_all("outputs/validation/")
    """
    
    def __init__(
        self,
        results: List["ValidationResult"],
        metrics: "ValidationMetrics",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the report generator.
        
        Parameters
        ----------
        results : list[ValidationResult]
            Validation results to report on
        metrics : ValidationMetrics
            Computed validation metrics
        metadata : dict, optional
            Additional metadata to include in reports
        """
        self.results = results
        self.metrics = metrics
        self.metadata = metadata or {}
        self._generated_at = datetime.now()
    
    def generate_summary_report(self) -> str:
        """
        Generate a text summary report for research documentation.
        
        Returns
        -------
        str
            Formatted text report
        """
        lines = [
            "=" * 70,
            "MANGOPOINT PEST SIMULATION MODEL VALIDATION REPORT",
            "=" * 70,
            "",
            f"Generated: {self._generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Data Source: BPI Guimaras Research and Development Center",
            "",
            "-" * 70,
            "OVERVIEW",
            "-" * 70,
            "",
            f"Total Validation Cases:    {self.metrics.total_tests}",
            f"Correct Predictions:       {self.metrics.correct_predictions}",
            f"Incorrect Predictions:     {self.metrics.incorrect_predictions}",
            f"Overall Accuracy:          {self.metrics.overall_accuracy_pct:.1f}%",
            "",
            *self._confidence_interval_lines(),
            "-" * 70,
            "CLASSIFICATION METRICS",
            "-" * 70,
            "",
            "For outbreak detection (HIGH risk = positive class):",
            "",
            f"  Precision:     {self.metrics.classification.precision:.3f}",
            f"    → When model predicts HIGH, it's correct {self.metrics.classification.precision*100:.1f}% of the time",
            "",
            f"  Recall:        {self.metrics.classification.recall:.3f}",
            f"    → Model detects {self.metrics.classification.recall*100:.1f}% of actual HIGH risk cases",
            "",
            f"  F1-Score:      {self.metrics.classification.f1_score:.3f}",
            f"    → Harmonic mean of precision and recall",
            "",
            f"  Specificity:   {self.metrics.classification.specificity:.3f}",
            f"    → Model correctly identifies {self.metrics.classification.specificity*100:.1f}% of non-outbreak cases",
            "",
        ]
        
        # Confusion matrix
        cm = self.metrics.classification.confusion_matrix
        if cm:
            lines.extend([
                "Confusion Matrix (Outbreak Detection):",
                "",
                "                    Predicted",
                "                 LOW/MED   HIGH",
                f"  Actual LOW/MED   {cm.true_negatives:4d}     {cm.false_positives:4d}",
                f"  Actual HIGH      {cm.false_negatives:4d}     {cm.true_positives:4d}",
                "",
            ])
        
        lines.extend([
            "-" * 70,
            "REGRESSION METRICS",
            "-" * 70,
            "",
            f"  Mean Absolute Error (MAE):     {self.metrics.regression.mae:.4f}",
            f"  Root Mean Square Error (RMSE): {self.metrics.regression.rmse:.4f}",
            f"  R² (Coefficient of Determination): {self.metrics.regression.r_squared:.4f}",
            f"  Normalized MAE:                {self.metrics.regression.normalized_mae:.4f}",
            "",
            f"  Mean Actual Value:             {self.metrics.regression.mean_actual:.4f}",
            f"  Mean Predicted Value:          {self.metrics.regression.mean_predicted:.4f}",
            "",
        ])
        
        # Per-pest-type breakdown
        if self.metrics.fruit_fly_metrics:
            lines.extend([
                "-" * 70,
                "FRUIT FLY (Bactrocera) VALIDATION",
                "-" * 70,
                "",
                f"  Cases:     {self.metrics.fruit_fly_metrics.n_samples}",
                f"  Accuracy:  {self.metrics.fruit_fly_metrics.accuracy:.1%}",
                f"  Precision: {self.metrics.fruit_fly_metrics.precision:.3f}",
                f"  Recall:    {self.metrics.fruit_fly_metrics.recall:.3f}",
                f"  F1-Score:  {self.metrics.fruit_fly_metrics.f1_score:.3f}",
                "",
            ])
        
        if self.metrics.cecid_fly_metrics:
            lines.extend([
                "-" * 70,
                "CECID FLY (Gall Midge) VALIDATION",
                "-" * 70,
                "",
                f"  Cases:     {self.metrics.cecid_fly_metrics.n_samples}",
                f"  Accuracy:  {self.metrics.cecid_fly_metrics.accuracy:.1%}",
                f"  Precision: {self.metrics.cecid_fly_metrics.precision:.3f}",
                f"  Recall:    {self.metrics.cecid_fly_metrics.recall:.3f}",
                f"  F1-Score:  {self.metrics.cecid_fly_metrics.f1_score:.3f}",
                "",
            ])
        
        # Interpretation
        lines.extend([
            "-" * 70,
            "INTERPRETATION",
            "-" * 70,
            "",
            self._generate_interpretation(),
            "",
            "-" * 70,
            "NOTES",
            "-" * 70,
            "",
            "1. Historical data from BPI Guimaras (2022-2025 monitoring records)",
            "2. Fruit Fly metric: Catch Per Trap per Day (CPTD)",
            "   - LOW: < 8, MEDIUM: 8-20, HIGH: > 20 flies/trap/day",
            "3. Cecid Fly metric: Infestation percentage",
            "   - LOW: < 5%, MEDIUM: 5-15%, HIGH: > 15%",
            f"4. Weather source: {self._weather_note()}",
            "5. Monte Carlo ensemble used for risk estimation",
            "6. Confidence intervals use case-level bootstrap resampling",
            f"7. Risk calibration: {self._calibration_note()}",
            "",
            "=" * 70,
        ])
        
        return "\n".join(lines)

    def _confidence_interval_lines(self) -> List[str]:
        """Format bootstrap confidence intervals for text reports."""
        if not self.metrics.confidence_intervals:
            return []

        lines = [
            "Bootstrap Confidence Intervals:",
        ]
        for metric_name in ("overall_accuracy_pct", "precision", "recall", "f1_score"):
            interval = self.metrics.confidence_intervals.get(metric_name)
            if not interval:
                continue
            label = metric_name.replace("_", " ").title()
            lines.append(
                f"  {label}: {interval['lower']:.3f} to "
                f"{interval['upper']:.3f} ({interval['confidence']:.0%})"
            )
        lines.append("")
        return lines

    def _weather_note(self) -> str:
        """Describe weather inputs from report metadata."""
        weather = self.metadata.get("weather", {})
        source_counts = weather.get("source_counts", {})
        if source_counts:
            source_text = ", ".join(
                f"{source} ({count} cases)"
                for source, count in sorted(source_counts.items())
            )
        else:
            source_text = "not recorded"

        coverage = weather.get("coverage", {})
        coverage_text = ""
        if coverage:
            ready = coverage.get("historical_ready_cases", 0)
            total = coverage.get("total_cases", 0)
            fallback = coverage.get("fallback_cases", 0)
            coverage_text = (
                f"; historical coverage {ready}/{total} cases, "
                f"fallback {fallback}"
            )

        if weather.get("historical_weather_csv"):
            return (
                "historical hourly CSV where available; seasonal synthetic "
                f"profile fallback. Sources: {source_text}{coverage_text}"
            )
        return f"seasonal synthetic profiles. Sources: {source_text}{coverage_text}"

    def _calibration_note(self) -> str:
        """Describe risk-score calibration from report metadata."""
        calibration = self.metadata.get("calibration", {})
        if not calibration.get("enabled"):
            return "not applied"

        curve_count = len(calibration.get("curves", {}))
        return (
            f"{calibration.get('method', 'calibration')} fit on "
            f"{calibration.get('source_split', 'calibration')} "
            f"({curve_count} pest curve(s))"
        )
    
    def _generate_interpretation(self) -> str:
        """Generate interpretation text based on metrics."""
        acc = self.metrics.overall_accuracy_pct
        f1 = self.metrics.classification.f1_score
        recall = self.metrics.classification.recall
        
        interpretations = []
        
        # Overall accuracy interpretation
        if acc >= 80:
            interpretations.append(
                f"The model achieves strong overall accuracy ({acc:.1f}%), "
                "indicating reliable pest risk predictions."
            )
        elif acc >= 60:
            interpretations.append(
                f"The model achieves moderate accuracy ({acc:.1f}%). "
                "Predictions are generally useful but should be combined with field observation."
            )
        else:
            interpretations.append(
                f"The model shows limited accuracy ({acc:.1f}%). "
                "Further calibration with local data may improve predictions."
            )
        
        # F1-score interpretation
        if f1 >= 0.7:
            interpretations.append(
                f"The F1-score ({f1:.2f}) indicates good balance between "
                "detecting outbreaks and avoiding false alarms."
            )
        elif f1 >= 0.5:
            interpretations.append(
                f"The F1-score ({f1:.2f}) suggests moderate outbreak detection capability."
            )
        
        # Recall interpretation (critical for pest management)
        if recall >= 0.8:
            interpretations.append(
                f"High recall ({recall:.1%}) means the model catches most actual outbreaks, "
                "minimizing dangerous missed warnings."
            )
        elif recall < 0.5:
            interpretations.append(
                f"Low recall ({recall:.1%}) indicates some outbreaks may be missed. "
                "Consider adjusting risk thresholds for more conservative predictions."
            )
        
        return "\n".join(interpretations)
    
    def to_detailed_csv_data(self) -> List[Dict[str, Any]]:
        """
        Convert results to detailed CSV format.
        
        Returns
        -------
        list[dict]
            Rows for CSV export
        """
        rows = []
        for r in self.results:
            row = r.to_dict()
            # Add readable columns
            row["correct"] = "Yes" if r.match else "No"
            row["month_name"] = datetime(2000, r.case.month, 1).strftime("%B")
            rows.append(row)
        return rows
    
    def to_summary_csv_data(self) -> List[Dict[str, Any]]:
        """
        Convert to summary CSV format (one row per metric).
        
        Returns
        -------
        list[dict]
            Summary rows
        """
        rows = [
            {"metric": "total_tests", "value": self.metrics.total_tests},
            {"metric": "correct_predictions", "value": self.metrics.correct_predictions},
            {"metric": "incorrect_predictions", "value": self.metrics.incorrect_predictions},
            {"metric": "overall_accuracy_pct", "value": f"{self.metrics.overall_accuracy_pct:.2f}"},
            {"metric": "precision", "value": f"{self.metrics.classification.precision:.4f}"},
            {"metric": "recall", "value": f"{self.metrics.classification.recall:.4f}"},
            {"metric": "f1_score", "value": f"{self.metrics.classification.f1_score:.4f}"},
            {"metric": "specificity", "value": f"{self.metrics.classification.specificity:.4f}"},
            {"metric": "mae", "value": f"{self.metrics.regression.mae:.4f}"},
            {"metric": "rmse", "value": f"{self.metrics.regression.rmse:.4f}"},
            {"metric": "r_squared", "value": f"{self.metrics.regression.r_squared:.4f}"},
        ]
        for metric_name, interval in self.metrics.confidence_intervals.items():
            rows.append({
                "metric": f"{metric_name}_ci_lower",
                "value": f"{interval['lower']:.4f}",
            })
            rows.append({
                "metric": f"{metric_name}_ci_upper",
                "value": f"{interval['upper']:.4f}",
            })
        return rows
    
    def to_json_data(self) -> Dict[str, Any]:
        """
        Convert to JSON-serializable format.
        
        Returns
        -------
        dict
            Complete validation data
        """
        return {
            "generated_at": self._generated_at.isoformat(),
            "metadata": self.metadata,
            "summary": {
                "total_tests": self.metrics.total_tests,
                "correct_predictions": self.metrics.correct_predictions,
                "incorrect_predictions": self.metrics.incorrect_predictions,
                "overall_accuracy_pct": self.metrics.overall_accuracy_pct,
            },
            "classification_metrics": self.metrics.classification.to_dict(),
            "regression_metrics": self.metrics.regression.to_dict(),
            "validation_metrics": self.metrics.to_dict(),
            "results": [r.to_dict() for r in self.results],
        }
    
    def export_detailed_csv(self, filepath: str) -> None:
        """Export detailed results to CSV."""
        data = self.to_detailed_csv_data()
        if not data:
            return
        
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
    
    def export_summary_csv(self, filepath: str) -> None:
        """Export summary metrics to CSV."""
        data = self.to_summary_csv_data()
        
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["metric", "value"])
            writer.writeheader()
            writer.writerows(data)
    
    def export_json(self, filepath: str) -> None:
        """Export complete data to JSON."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_json_data(), f, indent=2)
    
    def export_text_report(self, filepath: str) -> None:
        """Export text summary report."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.generate_summary_report())
    
    def export_all(self, output_dir: str, prefix: str = "validation") -> Dict[str, str]:
        """
        Export all report formats to a directory.
        
        Parameters
        ----------
        output_dir : str
            Output directory path
        prefix : str
            Filename prefix
        
        Returns
        -------
        dict
            Mapping of report type to filepath
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = self._generated_at.strftime("%Y%m%d_%H%M%S")
        
        files = {
            "detailed_csv": output_path / f"{prefix}_results_{timestamp}.csv",
            "summary_csv": output_path / f"{prefix}_summary_{timestamp}.csv",
            "json": output_path / f"{prefix}_data_{timestamp}.json",
            "report": output_path / f"{prefix}_report_{timestamp}.txt",
        }
        
        self.export_detailed_csv(str(files["detailed_csv"]))
        self.export_summary_csv(str(files["summary_csv"]))
        self.export_json(str(files["json"]))
        self.export_text_report(str(files["report"]))
        
        return {k: str(v) for k, v in files.items()}
    
    def get_visualization_data(self) -> Dict[str, Any]:
        """
        Get data formatted for visualization/graphing.
        
        Returns data suitable for creating:
        - Predicted vs actual scatter plot
        - Time series of predictions
        - Confusion matrix heatmap
        
        Returns
        -------
        dict
            Data for various visualizations
        """
        from .metrics import normalize_pest_value_to_risk
        
        # Scatter plot data (predicted vs actual)
        scatter_data = []
        for r in self.results:
            actual_norm = normalize_pest_value_to_risk(
                r.case.actual_value, r.case.pest_type
            )
            scatter_data.append({
                "actual": actual_norm,
                "predicted": r.predicted_risk,
                "pest_type": r.case.pest_type,
                "date": r.case.date_str,
                "match": r.match,
            })
        
        # Time series data
        time_series = sorted(
            [{"date": r.case.date_str, 
              "year": r.case.year,
              "month": r.case.month,
              "actual_level": r.case.actual_level,
              "predicted_level": r.predicted_level,
              "actual_value": r.case.actual_value,
              "predicted_risk": r.predicted_risk,
              "pest_type": r.case.pest_type}
             for r in self.results],
            key=lambda x: (x["year"], x["month"])
        )
        
        # Confusion matrix data
        cm = self.metrics.classification.confusion_matrix
        confusion_data = {
            "matrix": [
                [cm.true_negatives, cm.false_positives],
                [cm.false_negatives, cm.true_positives],
            ] if cm else None,
            "labels": ["Low/Medium", "High"],
        }
        
        return {
            "scatter": scatter_data,
            "time_series": time_series,
            "confusion_matrix": confusion_data,
        }


# ─────────────────────────────────────────────
# Convenience Functions
# ─────────────────────────────────────────────

def export_validation_csv(
    results: List["ValidationResult"],
    filepath: str,
) -> None:
    """
    Export validation results to CSV file.
    
    Parameters
    ----------
    results : list[ValidationResult]
        Results to export
    filepath : str
        Output file path
    """
    if not results:
        return
    
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    data = [r.to_dict() for r in results]
    
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)


def export_validation_json(
    results: List["ValidationResult"],
    metrics: "ValidationMetrics",
    filepath: str,
) -> None:
    """
    Export validation results and metrics to JSON file.
    
    Parameters
    ----------
    results : list[ValidationResult]
        Results to export
    metrics : ValidationMetrics
        Computed metrics
    filepath : str
        Output file path
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_tests": metrics.total_tests,
            "correct_predictions": metrics.correct_predictions,
            "overall_accuracy_pct": metrics.overall_accuracy_pct,
        },
        "classification": metrics.classification.to_dict(),
        "regression": metrics.regression.to_dict(),
        "validation_metrics": metrics.to_dict(),
        "results": [r.to_dict() for r in results],
    }
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
