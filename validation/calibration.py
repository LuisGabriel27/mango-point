"""
Risk-score calibration for historical BPI validation.

The simulator produces a 0-1 risk score. BPI observations are monthly aggregate
field metrics, so this module fits a simple pest-specific mapping from raw
simulation score to the BPI-normalized observation scale using calibration
years, then applies the frozen mapping to held-out testing years.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .metrics import (
    normalize_pest_value_to_risk,
    normalized_risk_thresholds,
    risk_score_to_level,
)


def _clip01(value: float) -> float:
    """Clamp a numeric value to the risk-score interval."""
    return max(0.0, min(1.0, float(value)))


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2)


def _raw_score(result: Any) -> float:
    raw = getattr(result, "raw_predicted_risk", None)
    return float(raw if raw is not None else result.predicted_risk)


def _actual_score(result: Any) -> float:
    return normalize_pest_value_to_risk(
        result.case.actual_value,
        result.case.pest_type,
    )


def _mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
    if not actual:
        return 0.0
    return sum(abs(a - p) for a, p in zip(actual, predicted)) / len(actual)


def _fit_nonnegative_affine(
    raw_scores: Sequence[float],
    actual_scores: Sequence[float],
) -> Tuple[float, float, str]:
    """
    Fit y = scale*x + intercept, clamping negative slopes to preserve monotonicity.
    """
    if len(raw_scores) < 2:
        return 1.0, 0.0, "insufficient_cases_identity"

    x_mean = _mean(raw_scores)
    y_mean = _mean(actual_scores)
    variance = sum((x - x_mean) ** 2 for x in raw_scores)
    if variance <= 1e-12:
        return 0.0, _median(actual_scores), "constant_raw_scores_clamped_to_median"

    covariance = sum(
        (x - x_mean) * (y - y_mean)
        for x, y in zip(raw_scores, actual_scores)
    )
    scale = covariance / variance
    intercept = y_mean - scale * x_mean

    if scale < 0.0:
        return 0.0, y_mean, "negative_slope_clamped_to_mean"

    return float(scale), float(intercept), "nonnegative_affine"


@dataclass(frozen=True)
class PestCalibrationCurve:
    """Pest-specific mapping from raw simulation score to BPI-normalized score."""

    pest_type: str
    scale: float
    intercept: float
    low_threshold: float
    high_threshold: float
    n_cases: int
    mae_before: float
    mae_after: float
    method: str = "nonnegative_affine"
    note: str = ""
    raw_level_low_threshold: float | None = None
    raw_level_high_threshold: float | None = None
    level_method: str = "bpi_equivalent_thresholds"

    def apply(self, raw_score: float) -> float:
        """Apply the fitted calibration curve."""
        return _clip01(self.scale * float(raw_score) + self.intercept)

    def level(self, calibrated_score: float, raw_score: float | None = None) -> str:
        """Classify a calibrated score using BPI-equivalent thresholds."""
        if (
            raw_score is not None
            and self.raw_level_low_threshold is not None
            and self.raw_level_high_threshold is not None
        ):
            return risk_score_to_level(
                raw_score,
                low_threshold=self.raw_level_low_threshold,
                high_threshold=self.raw_level_high_threshold,
            )
        return risk_score_to_level(
            calibrated_score,
            low_threshold=self.low_threshold,
            high_threshold=self.high_threshold,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pest_type": self.pest_type,
            "scale": self.scale,
            "intercept": self.intercept,
            "low_threshold": self.low_threshold,
            "high_threshold": self.high_threshold,
            "n_cases": self.n_cases,
            "mae_before": self.mae_before,
            "mae_after": self.mae_after,
            "method": self.method,
            "note": self.note,
            "raw_level_low_threshold": self.raw_level_low_threshold,
            "raw_level_high_threshold": self.raw_level_high_threshold,
            "level_method": self.level_method,
        }


@dataclass(frozen=True)
class ValidationCalibration:
    """Container for all pest-specific validation calibration curves."""

    curves: Dict[str, PestCalibrationCurve]
    source_split: str = "calibration"
    method: str = "pest_specific_nonnegative_affine"

    @property
    def n_cases(self) -> int:
        return sum(curve.n_cases for curve in self.curves.values())

    def curve_for(self, pest_type: str) -> PestCalibrationCurve:
        """Return the curve for a pest, falling back to an identity curve."""
        if pest_type in self.curves:
            return self.curves[pest_type]
        return identity_curve(pest_type)

    def apply_score(self, raw_score: float, pest_type: str) -> float:
        return self.curve_for(pest_type).apply(raw_score)

    def predict_level(
        self,
        calibrated_score: float,
        pest_type: str,
        raw_score: float | None = None,
    ) -> str:
        return self.curve_for(pest_type).level(calibrated_score, raw_score=raw_score)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "source_split": self.source_split,
            "method": self.method,
            "n_cases": self.n_cases,
            "curves": {
                pest_type: curve.to_dict()
                for pest_type, curve in sorted(self.curves.items())
            },
        }


def identity_curve(pest_type: str) -> PestCalibrationCurve:
    """Return a no-op curve with BPI-equivalent classification thresholds."""
    low_threshold, high_threshold = normalized_risk_thresholds(pest_type)
    return PestCalibrationCurve(
        pest_type=pest_type,
        scale=1.0,
        intercept=0.0,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        n_cases=0,
        mae_before=0.0,
        mae_after=0.0,
        method="identity",
        note="No calibration curve was fitted for this pest type.",
    )


def _group_by_pest(results: Iterable[Any]) -> Dict[str, List[Any]]:
    grouped: Dict[str, List[Any]] = {}
    for result in results:
        grouped.setdefault(result.case.pest_type, []).append(result)
    return grouped


def _fit_raw_level_thresholds(
    raw_scores: Sequence[float],
    actual_levels: Sequence[str],
) -> Tuple[float, float, str]:
    """
    Fit raw-score class cut-points that maximize calibration agreement.

    The numeric risk calibration remains affine and is still used for MAE/RMSE.
    These thresholds only control the Low/Medium/High class label.
    """
    if len(raw_scores) < 2:
        return 0.30, 0.70, "insufficient_cases_default_thresholds"

    candidates = {0.0, 1.0}
    candidates.update(float(score) for score in raw_scores)
    for left in raw_scores:
        for right in raw_scores:
            candidates.add((float(left) + float(right)) / 2.0)

    best: Tuple[int, float, float] | None = None
    for low_threshold in sorted(candidates):
        for high_threshold in sorted(candidates):
            if high_threshold <= low_threshold:
                continue
            correct = 0
            for raw_score, actual_level in zip(raw_scores, actual_levels):
                predicted = risk_score_to_level(
                    raw_score,
                    low_threshold=low_threshold,
                    high_threshold=high_threshold,
                )
                if predicted == actual_level:
                    correct += 1
            if best is None or correct > best[0]:
                best = (correct, float(low_threshold), float(high_threshold))

    if best is None:
        return 0.30, 0.70, "default_thresholds"

    return best[1], best[2], "raw_score_class_thresholds_optimized_on_calibration"


def fit_risk_calibration(
    results: Sequence[Any],
    source_split: str = "calibration",
    min_cases: int = 2,
    optimize_level_thresholds: bool = False,
) -> ValidationCalibration:
    """
    Fit pest-specific calibration curves from completed validation results.

    Parameters
    ----------
    results:
        Completed validation results used as calibration evidence.
    source_split:
        Human-readable name of the split used for fitting.
    min_cases:
        Minimum cases required to fit an affine curve for a pest type. Pest
        types below this count keep an identity curve.
    """
    if not results:
        raise ValueError("Cannot fit calibration without validation results.")

    curves: Dict[str, PestCalibrationCurve] = {}
    for pest_type, pest_results in _group_by_pest(results).items():
        raw_scores = [_raw_score(result) for result in pest_results]
        actual_scores = [_actual_score(result) for result in pest_results]
        actual_levels = [result.case.actual_level for result in pest_results]
        low_threshold, high_threshold = normalized_risk_thresholds(pest_type)
        raw_level_low_threshold = None
        raw_level_high_threshold = None
        level_method = "bpi_equivalent_thresholds"

        if len(pest_results) < min_cases:
            scale = 1.0
            intercept = 0.0
            method = "identity"
            note = (
                f"Only {len(pest_results)} case(s) available; "
                f"minimum for fitted calibration is {min_cases}."
            )
        else:
            scale, intercept, method = _fit_nonnegative_affine(
                raw_scores,
                actual_scores,
            )
            note = ""
            if optimize_level_thresholds:
                (
                    raw_level_low_threshold,
                    raw_level_high_threshold,
                    level_method,
                ) = _fit_raw_level_thresholds(raw_scores, actual_levels)

        calibrated_scores = [
            _clip01(scale * raw_score + intercept)
            for raw_score in raw_scores
        ]
        curves[pest_type] = PestCalibrationCurve(
            pest_type=pest_type,
            scale=scale,
            intercept=intercept,
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            n_cases=len(pest_results),
            mae_before=_mae(actual_scores, raw_scores),
            mae_after=_mae(actual_scores, calibrated_scores),
            method=method,
            note=note,
            raw_level_low_threshold=raw_level_low_threshold,
            raw_level_high_threshold=raw_level_high_threshold,
            level_method=level_method,
        )

    return ValidationCalibration(
        curves=curves,
        source_split=source_split,
    )
