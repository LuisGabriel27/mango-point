"""
MangoPoint Validation — Metrics Calculator
===========================================
Computes evaluation metrics for model validation against historical data.

Supports two types of evaluation:
1. Classification Metrics: For categorical risk level predictions
   - Accuracy, Precision, Recall, F1-Score
   - Confusion matrix
   
2. Regression Metrics: For numeric risk score predictions
   - Mean Absolute Error (MAE)
   - Root Mean Square Error (RMSE)
   - Coefficient of Determination (R²)
   - Normalized error metrics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Dict, Tuple, Optional, Sequence
import math
import random


@dataclass
class ConfusionMatrix:
    """
    Confusion matrix for multi-class or binary classification.
    
    For outbreak prediction (binary):
        - True Positive (TP): Correctly predicted outbreak (HIGH risk)
        - True Negative (TN): Correctly predicted no outbreak (LOW/MEDIUM risk)
        - False Positive (FP): Incorrectly predicted outbreak (over-warning)
        - False Negative (FN): Missed outbreak (under-warning - dangerous!)
    """
    true_positives: int = 0
    true_negatives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    
    # For multi-class: class-wise counts
    class_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    @property
    def total(self) -> int:
        """Total number of predictions."""
        return (
            self.true_positives + self.true_negatives +
            self.false_positives + self.false_negatives
        )
    
    def add_prediction(
        self,
        actual: str,
        predicted: str,
        positive_class: str = "High",
    ) -> None:
        """
        Add a single prediction to the confusion matrix.
        
        Parameters
        ----------
        actual : str
            Actual class label
        predicted : str
            Predicted class label
        positive_class : str
            Label for the "positive" class (default: "High")
        """
        # Binary classification tracking
        actual_pos = actual == positive_class
        pred_pos = predicted == positive_class
        
        if actual_pos and pred_pos:
            self.true_positives += 1
        elif not actual_pos and not pred_pos:
            self.true_negatives += 1
        elif pred_pos and not actual_pos:
            self.false_positives += 1
        else:  # actual_pos and not pred_pos
            self.false_negatives += 1
        
        # Multi-class tracking
        if actual not in self.class_counts:
            self.class_counts[actual] = {}
        if predicted not in self.class_counts[actual]:
            self.class_counts[actual][predicted] = 0
        self.class_counts[actual][predicted] += 1


@dataclass
class ClassificationMetrics:
    """
    Classification metrics for categorical risk level predictions.
    
    Attributes
    ----------
    accuracy : float
        Overall prediction accuracy (correct / total)
    precision : float
        Precision for outbreak detection (TP / (TP + FP))
    recall : float
        Recall/Sensitivity for outbreak detection (TP / (TP + FN))
    f1_score : float
        Harmonic mean of precision and recall
    specificity : float
        True negative rate (TN / (TN + FP))
    confusion_matrix : ConfusionMatrix
        Full confusion matrix data
    n_samples : int
        Total number of validation samples
    """
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    specificity: float = 0.0
    confusion_matrix: Optional[ConfusionMatrix] = None
    n_samples: int = 0
    
    # Per-class metrics (for multi-class evaluation)
    per_class_accuracy: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for serialization."""
        result = {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "specificity": self.specificity,
            "n_samples": self.n_samples,
        }
        if self.confusion_matrix:
            result["true_positives"] = self.confusion_matrix.true_positives
            result["true_negatives"] = self.confusion_matrix.true_negatives
            result["false_positives"] = self.confusion_matrix.false_positives
            result["false_negatives"] = self.confusion_matrix.false_negatives
        if self.per_class_accuracy:
            for cls, acc in self.per_class_accuracy.items():
                result[f"accuracy_{cls.lower()}"] = acc
        return result


@dataclass
class RegressionMetrics:
    """
    Regression metrics for numeric risk score predictions.
    
    Attributes
    ----------
    mae : float
        Mean Absolute Error
    rmse : float
        Root Mean Square Error
    r_squared : float
        Coefficient of Determination (R²)
    normalized_mae : float
        MAE normalized by actual value range
    mean_actual : float
        Mean of actual values
    mean_predicted : float
        Mean of predicted values
    n_samples : int
        Number of samples
    """
    mae: float = 0.0
    rmse: float = 0.0
    r_squared: float = 0.0
    normalized_mae: float = 0.0
    mean_actual: float = 0.0
    mean_predicted: float = 0.0
    n_samples: int = 0
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for serialization."""
        return {
            "mae": self.mae,
            "rmse": self.rmse,
            "r_squared": self.r_squared,
            "normalized_mae": self.normalized_mae,
            "mean_actual": self.mean_actual,
            "mean_predicted": self.mean_predicted,
            "n_samples": self.n_samples,
        }


@dataclass
class ValidationMetrics:
    """
    Complete validation metrics combining classification and regression.
    
    Attributes
    ----------
    classification : ClassificationMetrics
        Metrics for categorical predictions
    regression : RegressionMetrics
        Metrics for numeric predictions
    total_tests : int
        Total number of validation tests
    correct_predictions : int
        Number of correct categorical predictions
    incorrect_predictions : int
        Number of incorrect categorical predictions
    overall_accuracy_pct : float
        Overall accuracy as percentage
    """
    classification: ClassificationMetrics = field(default_factory=ClassificationMetrics)
    regression: RegressionMetrics = field(default_factory=RegressionMetrics)
    total_tests: int = 0
    correct_predictions: int = 0
    incorrect_predictions: int = 0
    overall_accuracy_pct: float = 0.0
    
    # Breakdown by pest type
    fruit_fly_metrics: Optional[ClassificationMetrics] = None
    cecid_fly_metrics: Optional[ClassificationMetrics] = None
    confidence_intervals: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, any]:
        """Convert to dictionary for serialization."""
        result = {
            "total_tests": self.total_tests,
            "correct_predictions": self.correct_predictions,
            "incorrect_predictions": self.incorrect_predictions,
            "overall_accuracy_pct": self.overall_accuracy_pct,
            "classification": self.classification.to_dict(),
            "regression": self.regression.to_dict(),
        }
        if self.fruit_fly_metrics:
            result["fruit_fly_metrics"] = self.fruit_fly_metrics.to_dict()
        if self.cecid_fly_metrics:
            result["cecid_fly_metrics"] = self.cecid_fly_metrics.to_dict()
        if self.confidence_intervals:
            result["confidence_intervals"] = self.confidence_intervals
        return result
    
    def summary_string(self) -> str:
        """Generate a human-readable summary string."""
        lines = [
            "=" * 60,
            "VALIDATION METRICS SUMMARY",
            "=" * 60,
            f"Total Tests:          {self.total_tests}",
            f"Correct Predictions:  {self.correct_predictions}",
            f"Incorrect Predictions: {self.incorrect_predictions}",
            f"Overall Accuracy:     {self.overall_accuracy_pct:.1f}%",
            "",
            "Classification Metrics:",
            f"  Precision:          {self.classification.precision:.3f}",
            f"  Recall:             {self.classification.recall:.3f}",
            f"  F1-Score:           {self.classification.f1_score:.3f}",
            f"  Specificity:        {self.classification.specificity:.3f}",
            "",
            "Regression Metrics:",
            f"  MAE:                {self.regression.mae:.3f}",
            f"  RMSE:               {self.regression.rmse:.3f}",
            f"  R²:                 {self.regression.r_squared:.3f}",
            "=" * 60,
        ]
        if self.confidence_intervals:
            lines.insert(-1, "")
            lines.insert(-1, "Bootstrap Confidence Intervals:")
            for metric_name in (
                "overall_accuracy_pct",
                "precision",
                "recall",
                "f1_score",
                "mae",
                "rmse",
            ):
                interval = self.confidence_intervals.get(metric_name)
                if not interval:
                    continue
                label = metric_name.replace("_", " ").title()
                lines.insert(
                    -1,
                    f"  {label}: {interval['lower']:.3f} to {interval['upper']:.3f} "
                    f"({interval['confidence']:.0%})",
                )
        return "\n".join(lines)


def compute_classification_metrics(
    actual_labels: Sequence[str],
    predicted_labels: Sequence[str],
    positive_class: str = "High",
) -> ClassificationMetrics:
    """
    Compute classification metrics from predicted vs actual labels.
    
    Parameters
    ----------
    actual_labels : sequence of str
        Actual risk level labels (e.g., "Low", "Medium", "High")
    predicted_labels : sequence of str
        Predicted risk level labels
    positive_class : str
        Label for the "positive" class for precision/recall (default: "High")
    
    Returns
    -------
    ClassificationMetrics
        Computed metrics
    
    Raises
    ------
    ValueError
        If sequences have different lengths
    """
    if len(actual_labels) != len(predicted_labels):
        raise ValueError(
            f"Label sequences must have same length. "
            f"Got {len(actual_labels)} actual vs {len(predicted_labels)} predicted."
        )
    
    n = len(actual_labels)
    if n == 0:
        return ClassificationMetrics(n_samples=0)
    
    # Build confusion matrix
    cm = ConfusionMatrix()
    for actual, predicted in zip(actual_labels, predicted_labels):
        cm.add_prediction(actual, predicted, positive_class)
    
    # Compute metrics
    tp = cm.true_positives
    tn = cm.true_negatives
    fp = cm.false_positives
    fn = cm.false_negatives
    
    # Accuracy: (TP + TN) / Total
    accuracy = (tp + tn) / n if n > 0 else 0.0
    
    # Precision: TP / (TP + FP)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    
    # Recall (Sensitivity): TP / (TP + FN)
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    
    # F1-Score: 2 * (Precision * Recall) / (Precision + Recall)
    f1 = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0 else 0.0
    )
    
    # Specificity: TN / (TN + FP)
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    
    # Per-class accuracy
    per_class_acc = {}
    unique_classes = set(actual_labels) | set(predicted_labels)
    for cls in unique_classes:
        cls_correct = sum(
            1 for a, p in zip(actual_labels, predicted_labels)
            if a == cls and p == cls
        )
        cls_total = sum(1 for a in actual_labels if a == cls)
        per_class_acc[cls] = cls_correct / cls_total if cls_total > 0 else 0.0
    
    return ClassificationMetrics(
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1_score=f1,
        specificity=specificity,
        confusion_matrix=cm,
        n_samples=n,
        per_class_accuracy=per_class_acc,
    )


def compute_regression_metrics(
    actual_values: Sequence[float],
    predicted_values: Sequence[float],
) -> RegressionMetrics:
    """
    Compute regression metrics from predicted vs actual numeric values.
    
    Parameters
    ----------
    actual_values : sequence of float
        Actual numeric values (e.g., CPTD or infestation %)
    predicted_values : sequence of float
        Predicted numeric values (e.g., risk scores)
    
    Returns
    -------
    RegressionMetrics
        Computed metrics
    
    Raises
    ------
    ValueError
        If sequences have different lengths
    """
    if len(actual_values) != len(predicted_values):
        raise ValueError(
            f"Value sequences must have same length. "
            f"Got {len(actual_values)} actual vs {len(predicted_values)} predicted."
        )
    
    n = len(actual_values)
    if n == 0:
        return RegressionMetrics(n_samples=0)
    
    actual = list(actual_values)
    predicted = list(predicted_values)
    
    # Mean values
    mean_actual = sum(actual) / n
    mean_predicted = sum(predicted) / n
    
    # MAE: Mean Absolute Error
    mae = sum(abs(a - p) for a, p in zip(actual, predicted)) / n
    
    # RMSE: Root Mean Square Error
    mse = sum((a - p) ** 2 for a, p in zip(actual, predicted)) / n
    rmse = math.sqrt(mse)
    
    # R²: Coefficient of Determination
    # R² = 1 - (SS_res / SS_tot)
    ss_res = sum((a - p) ** 2 for a, p in zip(actual, predicted))
    ss_tot = sum((a - mean_actual) ** 2 for a in actual)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    
    # Normalized MAE (as percentage of actual range)
    actual_range = max(actual) - min(actual) if len(actual) > 1 else 1.0
    normalized_mae = mae / actual_range if actual_range > 0 else 0.0
    
    return RegressionMetrics(
        mae=mae,
        rmse=rmse,
        r_squared=r_squared,
        normalized_mae=normalized_mae,
        mean_actual=mean_actual,
        mean_predicted=mean_predicted,
        n_samples=n,
    )


def compute_full_metrics(
    results: List[Dict],
    positive_class: str = "High",
) -> ValidationMetrics:
    """
    Compute complete validation metrics from a list of validation results.
    
    Parameters
    ----------
    results : list of dict
        Validation results, each containing:
        - 'actual_level': Actual risk level string
        - 'predicted_level': Predicted risk level string
        - 'actual_value': Actual numeric value
        - 'predicted_value': Predicted numeric value
        - 'pest_type': Pest type ('cecid' or 'fruitfly')
        - 'match': Whether prediction was correct (bool)
    positive_class : str
        Label for positive class in classification
    
    Returns
    -------
    ValidationMetrics
        Complete metrics
    """
    if not results:
        return ValidationMetrics()
    
    # Extract data
    actual_labels = [r["actual_level"] for r in results]
    predicted_labels = [r["predicted_level"] for r in results]
    actual_values = [r["actual_value"] for r in results]
    predicted_values = [r["predicted_value"] for r in results]
    matches = [r["match"] for r in results]
    
    # Overall counts
    total = len(results)
    correct = sum(matches)
    incorrect = total - correct
    accuracy_pct = (correct / total * 100) if total > 0 else 0.0
    
    # Classification metrics
    cls_metrics = compute_classification_metrics(
        actual_labels, predicted_labels, positive_class
    )
    
    # Regression metrics
    reg_metrics = compute_regression_metrics(actual_values, predicted_values)
    
    # Per-pest-type metrics
    fruit_fly_results = [r for r in results if r.get("pest_type") == "fruitfly"]
    cecid_fly_results = [r for r in results if r.get("pest_type") == "cecid"]
    
    fruit_fly_metrics = None
    if fruit_fly_results:
        fruit_fly_metrics = compute_classification_metrics(
            [r["actual_level"] for r in fruit_fly_results],
            [r["predicted_level"] for r in fruit_fly_results],
            positive_class,
        )
    
    cecid_fly_metrics = None
    if cecid_fly_results:
        cecid_fly_metrics = compute_classification_metrics(
            [r["actual_level"] for r in cecid_fly_results],
            [r["predicted_level"] for r in cecid_fly_results],
            positive_class,
        )
    
    return ValidationMetrics(
        classification=cls_metrics,
        regression=reg_metrics,
        total_tests=total,
        correct_predictions=correct,
        incorrect_predictions=incorrect,
        overall_accuracy_pct=accuracy_pct,
        fruit_fly_metrics=fruit_fly_metrics,
        cecid_fly_metrics=cecid_fly_metrics,
    )


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Compute a percentile with linear interpolation."""
    if not values:
        return 0.0

    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])

    position = (len(ordered) - 1) * percentile
    lower_idx = math.floor(position)
    upper_idx = math.ceil(position)

    if lower_idx == upper_idx:
        return float(ordered[int(position)])

    lower = ordered[lower_idx]
    upper = ordered[upper_idx]
    fraction = position - lower_idx
    return float(lower + (upper - lower) * fraction)


def bootstrap_confidence_intervals(
    results: List[Dict[str, Any]],
    n_iterations: int = 500,
    confidence: float = 0.95,
    seed: int = 42,
    positive_class: str = "High",
) -> Dict[str, Dict[str, float]]:
    """
    Estimate confidence intervals for validation metrics by bootstrapping cases.

    The resampling unit is a validation case, so intervals represent uncertainty
    from the available historical observations rather than model process noise.
    """
    if not results or n_iterations <= 0:
        return {}

    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")

    rng = random.Random(seed)
    n = len(results)
    samples: Dict[str, List[float]] = {
        "overall_accuracy_pct": [],
        "precision": [],
        "recall": [],
        "f1_score": [],
        "specificity": [],
        "mae": [],
        "rmse": [],
        "r_squared": [],
    }

    for _ in range(n_iterations):
        resampled = [results[rng.randrange(n)] for _ in range(n)]
        metrics = compute_full_metrics(resampled, positive_class=positive_class)
        samples["overall_accuracy_pct"].append(metrics.overall_accuracy_pct)
        samples["precision"].append(metrics.classification.precision)
        samples["recall"].append(metrics.classification.recall)
        samples["f1_score"].append(metrics.classification.f1_score)
        samples["specificity"].append(metrics.classification.specificity)
        samples["mae"].append(metrics.regression.mae)
        samples["rmse"].append(metrics.regression.rmse)
        samples["r_squared"].append(metrics.regression.r_squared)

    alpha = 1.0 - confidence
    lower_q = alpha / 2.0
    upper_q = 1.0 - lower_q

    intervals: Dict[str, Dict[str, float]] = {}
    for metric_name, values in samples.items():
        intervals[metric_name] = {
            "mean": sum(values) / len(values),
            "lower": _percentile(values, lower_q),
            "upper": _percentile(values, upper_q),
            "confidence": confidence,
            "n_bootstrap": float(n_iterations),
        }

    return intervals


def risk_score_to_level(
    score: float,
    low_threshold: float = 0.30,
    high_threshold: float = 0.70,
) -> str:
    """
    Convert a numeric risk score to a categorical level.
    
    Parameters
    ----------
    score : float
        Risk score between 0 and 1
    low_threshold : float
        Threshold below which risk is "Low"
    high_threshold : float
        Threshold at or above which risk is "High"
    
    Returns
    -------
    str
        "Low", "Medium", or "High"
    """
    if score < low_threshold:
        return "Low"
    elif score < high_threshold:
        return "Medium"
    return "High"


def normalize_pest_value_to_risk(
    value: float,
    pest_type: str,
    use_managed: bool = True,
) -> float:
    """
    Normalize a raw pest metric value to a 0-1 risk score.
    
    Parameters
    ----------
    value : float
        Raw value (CPTD for fruit fly, % for cecid fly)
    pest_type : str
        'cecid' or 'fruitfly'
    use_managed : bool
        For fruit fly, whether using managed orchard scale
    
    Returns
    -------
    float
        Normalized risk score between 0 and 1
    """
    if pest_type == "fruitfly":
        # CPTD normalization: 0-40 flies/trap/day maps to 0-1
        # Based on BPI data: managed orchards peak around 30-35 CPTD
        max_cptd = 40.0 if use_managed else 65.0
        return min(1.0, value / max_cptd)
    else:
        # Cecid fly: infestation percentage (0-100%) maps to 0-1
        # Most values in historical data are 0-50%
        return min(1.0, value / 100.0)
