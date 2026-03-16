"""
MangoPoint Validation — Trend Analysis
=======================================
Compares temporal patterns between simulated and actual BPI monitoring data.

This module provides statistical methods for quantifying how well the simulation
captures real-world pest behavior patterns observed in BPI data:
  - Correlation analysis (Pearson, Spearman)
  - Trend direction accuracy
  - Seasonal pattern matching
  - Error rate calculations (MAPE, RMSE relative)
  - Trend similarity scoring

The trend analysis does NOT modify any simulation algorithms.
It reads historical data and simulation outputs, then computes comparison metrics.

Usage Example
-------------
    from validation.trend_analysis import TrendAnalyzer
    from validation import HistoricalDataLoader
    
    # Load historical data
    loader = HistoricalDataLoader()
    loader.load()
    
    # Create analyzer with simulated results
    analyzer = TrendAnalyzer(
        historical_records=loader.records,
        simulated_results=validation_results,
    )
    
    # Compute comparison metrics
    trend_metrics = analyzer.compute_all_comparisons()
    report = analyzer.generate_comparison_report()
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple, Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .historical_data import HistoricalRecord
    from .validation_runner import ValidationResult


@dataclass
class CorrelationMetrics:
    """
    Correlation metrics between simulated and actual values.
    
    Attributes
    ----------
    pearson_r : float
        Pearson correlation coefficient (-1 to 1)
    pearson_p : float
        P-value for Pearson correlation
    spearman_rho : float
        Spearman rank correlation coefficient
    spearman_p : float
        P-value for Spearman correlation
    kendall_tau : float
        Kendall's tau correlation coefficient
    n_samples : int
        Number of data points used
    """
    pearson_r: float = 0.0
    pearson_p: float = 1.0
    spearman_rho: float = 0.0
    spearman_p: float = 1.0
    kendall_tau: float = 0.0
    n_samples: int = 0
    
    @property
    def correlation_strength(self) -> str:
        """Interpret correlation strength."""
        r = abs(self.pearson_r)
        if r >= 0.8:
            return "Very Strong"
        elif r >= 0.6:
            return "Strong"
        elif r >= 0.4:
            return "Moderate"
        elif r >= 0.2:
            return "Weak"
        return "Very Weak"
    
    @property
    def is_significant(self) -> bool:
        """Check if correlation is statistically significant (p < 0.05)."""
        return self.pearson_p < 0.05
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pearson_r": self.pearson_r,
            "pearson_p": self.pearson_p,
            "spearman_rho": self.spearman_rho,
            "spearman_p": self.spearman_p,
            "kendall_tau": self.kendall_tau,
            "n_samples": self.n_samples,
            "correlation_strength": self.correlation_strength,
            "is_significant": self.is_significant,
        }


@dataclass
class TrendDirectionMetrics:
    """
    Metrics for trend direction accuracy.
    
    Measures how well the simulation captures increasing/decreasing trends.
    
    Attributes
    ----------
    direction_accuracy : float
        Fraction of correct trend direction predictions
    n_correct_directions : int
        Number of correctly predicted trend directions
    n_total_transitions : int
        Total number of month-to-month transitions
    up_trend_precision : float
        Precision for detecting increasing trends
    up_trend_recall : float
        Recall for detecting increasing trends
    down_trend_precision : float
        Precision for detecting decreasing trends
    down_trend_recall : float
        Recall for detecting decreasing trends
    """
    direction_accuracy: float = 0.0
    n_correct_directions: int = 0
    n_total_transitions: int = 0
    up_trend_precision: float = 0.0
    up_trend_recall: float = 0.0
    down_trend_precision: float = 0.0
    down_trend_recall: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction_accuracy": self.direction_accuracy,
            "direction_accuracy_pct": self.direction_accuracy * 100,
            "n_correct_directions": self.n_correct_directions,
            "n_total_transitions": self.n_total_transitions,
            "up_trend_precision": self.up_trend_precision,
            "up_trend_recall": self.up_trend_recall,
            "down_trend_precision": self.down_trend_precision,
            "down_trend_recall": self.down_trend_recall,
        }


@dataclass
class ErrorMetrics:
    """
    Error metrics for quantifying prediction accuracy.
    
    Attributes
    ----------
    mae : float
        Mean Absolute Error
    mape : float
        Mean Absolute Percentage Error (as decimal)
    rmse : float
        Root Mean Square Error
    relative_rmse : float
        RMSE normalized by mean actual value
    max_error : float
        Maximum absolute error
    mean_bias : float
        Mean bias (systematic over/under prediction)
    """
    mae: float = 0.0
    mape: float = 0.0
    rmse: float = 0.0
    relative_rmse: float = 0.0
    max_error: float = 0.0
    mean_bias: float = 0.0
    
    @property
    def mape_pct(self) -> float:
        """MAPE as percentage."""
        return self.mape * 100
    
    @property
    def relative_rmse_pct(self) -> float:
        """Relative RMSE as percentage."""
        return self.relative_rmse * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "mae": self.mae,
            "mape": self.mape,
            "mape_pct": self.mape_pct,
            "rmse": self.rmse,
            "relative_rmse": self.relative_rmse,
            "relative_rmse_pct": self.relative_rmse_pct,
            "max_error": self.max_error,
            "mean_bias": self.mean_bias,
        }


@dataclass
class SeasonalPatternMetrics:
    """
    Metrics for seasonal pattern matching.
    
    Attributes
    ----------
    wet_season_correlation : float
        Correlation during wet season (Jun-Nov)
    dry_season_correlation : float
        Correlation during dry season (Dec-May)
    peak_month_match : bool
        Whether simulation captures the peak month correctly
    actual_peak_month : int
        Actual peak month from BPI data
    predicted_peak_month : int
        Predicted peak month from simulation
    seasonal_amplitude_ratio : float
        Ratio of simulated to actual seasonal amplitude
    """
    wet_season_correlation: float = 0.0
    dry_season_correlation: float = 0.0
    peak_month_match: bool = False
    actual_peak_month: int = 0
    predicted_peak_month: int = 0
    seasonal_amplitude_ratio: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "wet_season_correlation": self.wet_season_correlation,
            "dry_season_correlation": self.dry_season_correlation,
            "peak_month_match": self.peak_month_match,
            "actual_peak_month": self.actual_peak_month,
            "predicted_peak_month": self.predicted_peak_month,
            "seasonal_amplitude_ratio": self.seasonal_amplitude_ratio,
        }


@dataclass
class TrendComparisonResult:
    """
    Complete trend comparison result between simulated and actual data.
    
    Attributes
    ----------
    pest_type : str
        Type of pest being compared ('cecid' or 'fruitfly')
    correlation : CorrelationMetrics
        Correlation analysis results
    trend_direction : TrendDirectionMetrics
        Trend direction accuracy results
    errors : ErrorMetrics
        Error quantification results
    seasonal : SeasonalPatternMetrics
        Seasonal pattern matching results
    trend_similarity_score : float
        Overall trend similarity score (0-1)
    n_comparisons : int
        Number of data points compared
    """
    pest_type: str = ""
    correlation: CorrelationMetrics = field(default_factory=CorrelationMetrics)
    trend_direction: TrendDirectionMetrics = field(default_factory=TrendDirectionMetrics)
    errors: ErrorMetrics = field(default_factory=ErrorMetrics)
    seasonal: SeasonalPatternMetrics = field(default_factory=SeasonalPatternMetrics)
    trend_similarity_score: float = 0.0
    n_comparisons: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pest_type": self.pest_type,
            "correlation": self.correlation.to_dict(),
            "trend_direction": self.trend_direction.to_dict(),
            "errors": self.errors.to_dict(),
            "seasonal": self.seasonal.to_dict(),
            "trend_similarity_score": self.trend_similarity_score,
            "n_comparisons": self.n_comparisons,
        }


def compute_pearson_correlation(x: Sequence[float], y: Sequence[float]) -> Tuple[float, float]:
    """
    Compute Pearson correlation coefficient without scipy.
    
    Returns (correlation, p-value estimate)
    """
    n = len(x)
    if n < 3:
        return 0.0, 1.0
    
    x_arr = np.array(x)
    y_arr = np.array(y)
    
    x_mean = np.mean(x_arr)
    y_mean = np.mean(y_arr)
    
    x_std = np.std(x_arr, ddof=1)
    y_std = np.std(y_arr, ddof=1)
    
    if x_std == 0 or y_std == 0:
        return 0.0, 1.0
    
    r = np.corrcoef(x_arr, y_arr)[0, 1]
    
    # Approximate p-value using t-distribution
    if abs(r) >= 1.0:
        p = 0.0 if r != 0 else 1.0
    else:
        t_stat = r * math.sqrt((n - 2) / (1 - r**2))
        # Very rough p-value approximation
        # For proper p-values, scipy.stats would be needed
        p = 2 * min(0.5, math.exp(-0.5 * abs(t_stat)))  # Rough approximation
    
    return float(r), float(p)


def compute_spearman_correlation(x: Sequence[float], y: Sequence[float]) -> Tuple[float, float]:
    """
    Compute Spearman rank correlation without scipy.
    
    Returns (correlation, p-value estimate)
    """
    n = len(x)
    if n < 3:
        return 0.0, 1.0
    
    # Convert to ranks
    x_ranks = np.argsort(np.argsort(x)) + 1
    y_ranks = np.argsort(np.argsort(y)) + 1
    
    # Compute Pearson correlation on ranks
    return compute_pearson_correlation(x_ranks.tolist(), y_ranks.tolist())


def compute_kendall_tau(x: Sequence[float], y: Sequence[float]) -> float:
    """
    Compute Kendall's tau correlation coefficient without scipy.
    """
    n = len(x)
    if n < 2:
        return 0.0
    
    concordant = 0
    discordant = 0
    
    for i in range(n):
        for j in range(i + 1, n):
            x_sign = np.sign(x[j] - x[i])
            y_sign = np.sign(y[j] - y[i])
            
            if x_sign == y_sign and x_sign != 0:
                concordant += 1
            elif x_sign != y_sign and x_sign != 0 and y_sign != 0:
                discordant += 1
    
    total_pairs = n * (n - 1) / 2
    if total_pairs == 0:
        return 0.0
    
    return (concordant - discordant) / total_pairs


class TrendAnalyzer:
    """
    Analyzes temporal trends between simulated and actual BPI data.
    
    This class provides comprehensive trend comparison including:
    1. Correlation analysis (Pearson, Spearman, Kendall)
    2. Trend direction accuracy (up/down/stable predictions)
    3. Error metrics (MAE, MAPE, RMSE)
    4. Seasonal pattern matching
    5. Overall similarity scoring
    
    Usage
    -----
        analyzer = TrendAnalyzer(
            historical_records=bpi_records,
            simulated_results=validation_results,
        )
        
        # Get overall comparison
        comparison = analyzer.compute_all_comparisons()
        
        # Get pest-specific analysis
        fruit_fly_analysis = analyzer.analyze_pest_type("fruitfly")
        cecid_analysis = analyzer.analyze_pest_type("cecid")
    """
    
    def __init__(
        self,
        historical_records: Optional[List["HistoricalRecord"]] = None,
        simulated_results: Optional[List["ValidationResult"]] = None,
    ):
        """
        Initialize the trend analyzer.
        
        Parameters
        ----------
        historical_records : list[HistoricalRecord], optional
            BPI historical monitoring records
        simulated_results : list[ValidationResult], optional
            Results from validation runs
        """
        self.historical_records = historical_records or []
        self.simulated_results = simulated_results or []
        
        # Build lookup dictionaries for efficient matching
        self._historical_by_date: Dict[str, "HistoricalRecord"] = {}
        self._simulated_by_case: Dict[str, "ValidationResult"] = {}
        
        self._build_lookups()
    
    def _build_lookups(self) -> None:
        """Build lookup dictionaries for data matching."""
        for record in self.historical_records:
            key = f"{record.year}-{record.month:02d}"
            self._historical_by_date[key] = record
        
        for result in self.simulated_results:
            self._simulated_by_case[result.case.case_id] = result
    
    def set_historical_data(self, records: List["HistoricalRecord"]) -> None:
        """Set or update historical records."""
        self.historical_records = records
        self._build_lookups()
    
    def set_simulated_results(self, results: List["ValidationResult"]) -> None:
        """Set or update simulated results."""
        self.simulated_results = results
        self._build_lookups()
    
    def get_matched_pairs(
        self,
        pest_type: Optional[str] = None,
    ) -> List[Tuple[float, float, str]]:
        """
        Get matched pairs of (actual_value, predicted_value, date).
        
        Parameters
        ----------
        pest_type : str, optional
            Filter by pest type ('cecid' or 'fruitfly')
        
        Returns
        -------
        list of tuples
            Each tuple is (actual, predicted, date_str)
        """
        pairs = []
        
        for result in self.simulated_results:
            if pest_type and result.case.pest_type != pest_type:
                continue
            
            # Get actual value from the validation case (which came from historical data)
            actual = result.case.actual_value
            predicted = result.predicted_risk
            
            # Normalize to same scale
            # For cecid: infestation_pct (0-100) → risk (0-1)
            # For fruitfly: CPTD → scaled to comparable range
            if result.case.pest_type == "cecid":
                # Cecid: actual is already in percentage, predicted is 0-1 risk
                actual_normalized = actual / 100.0  # Convert to 0-1
            else:
                # Fruitfly: actual CPTD, normalized to 0-1 (assuming max ~40 CPTD)
                actual_normalized = min(1.0, actual / 40.0)
            
            pairs.append((actual_normalized, predicted, result.case.date_str))
        
        return pairs
    
    def compute_correlation(
        self,
        pest_type: Optional[str] = None,
    ) -> CorrelationMetrics:
        """
        Compute correlation metrics between simulated and actual values.
        
        Parameters
        ----------
        pest_type : str, optional
            Filter by pest type
        
        Returns
        -------
        CorrelationMetrics
            Correlation analysis results
        """
        pairs = self.get_matched_pairs(pest_type)
        
        if len(pairs) < 3:
            return CorrelationMetrics(n_samples=len(pairs))
        
        actual = [p[0] for p in pairs]
        predicted = [p[1] for p in pairs]
        
        pearson_r, pearson_p = compute_pearson_correlation(actual, predicted)
        spearman_rho, spearman_p = compute_spearman_correlation(actual, predicted)
        kendall_tau = compute_kendall_tau(actual, predicted)
        
        return CorrelationMetrics(
            pearson_r=pearson_r,
            pearson_p=pearson_p,
            spearman_rho=spearman_rho,
            spearman_p=spearman_p,
            kendall_tau=kendall_tau,
            n_samples=len(pairs),
        )
    
    def compute_trend_direction_accuracy(
        self,
        pest_type: Optional[str] = None,
    ) -> TrendDirectionMetrics:
        """
        Compute trend direction accuracy metrics.
        
        Measures how well the simulation captures increasing/decreasing trends
        from one time period to the next.
        
        Parameters
        ----------
        pest_type : str, optional
            Filter by pest type
        
        Returns
        -------
        TrendDirectionMetrics
            Trend direction accuracy results
        """
        pairs = self.get_matched_pairs(pest_type)
        
        if len(pairs) < 2:
            return TrendDirectionMetrics()
        
        # Sort by date
        pairs = sorted(pairs, key=lambda p: p[2])
        
        n_correct = 0
        n_up_tp = 0  # True positives for up trends
        n_up_fp = 0  # False positives for up trends
        n_up_fn = 0  # False negatives for up trends
        n_down_tp = 0
        n_down_fp = 0
        n_down_fn = 0
        
        for i in range(1, len(pairs)):
            prev_actual, prev_pred, _ = pairs[i - 1]
            curr_actual, curr_pred, _ = pairs[i]
            
            actual_direction = np.sign(curr_actual - prev_actual)
            pred_direction = np.sign(curr_pred - prev_pred)
            
            if actual_direction == pred_direction:
                n_correct += 1
            
            # Up trend (increasing)
            if actual_direction > 0:  # Actual is up
                if pred_direction > 0:
                    n_up_tp += 1
                else:
                    n_up_fn += 1
            else:
                if pred_direction > 0:
                    n_up_fp += 1
            
            # Down trend (decreasing)
            if actual_direction < 0:  # Actual is down
                if pred_direction < 0:
                    n_down_tp += 1
                else:
                    n_down_fn += 1
            else:
                if pred_direction < 0:
                    n_down_fp += 1
        
        n_transitions = len(pairs) - 1
        
        up_precision = n_up_tp / (n_up_tp + n_up_fp) if (n_up_tp + n_up_fp) > 0 else 0.0
        up_recall = n_up_tp / (n_up_tp + n_up_fn) if (n_up_tp + n_up_fn) > 0 else 0.0
        down_precision = n_down_tp / (n_down_tp + n_down_fp) if (n_down_tp + n_down_fp) > 0 else 0.0
        down_recall = n_down_tp / (n_down_tp + n_down_fn) if (n_down_tp + n_down_fn) > 0 else 0.0
        
        return TrendDirectionMetrics(
            direction_accuracy=n_correct / n_transitions if n_transitions > 0 else 0.0,
            n_correct_directions=n_correct,
            n_total_transitions=n_transitions,
            up_trend_precision=up_precision,
            up_trend_recall=up_recall,
            down_trend_precision=down_precision,
            down_trend_recall=down_recall,
        )
    
    def compute_error_metrics(
        self,
        pest_type: Optional[str] = None,
    ) -> ErrorMetrics:
        """
        Compute error metrics between simulated and actual values.
        
        Parameters
        ----------
        pest_type : str, optional
            Filter by pest type
        
        Returns
        -------
        ErrorMetrics
            Error quantification results
        """
        pairs = self.get_matched_pairs(pest_type)
        
        if not pairs:
            return ErrorMetrics()
        
        actual = np.array([p[0] for p in pairs])
        predicted = np.array([p[1] for p in pairs])
        
        errors = predicted - actual
        abs_errors = np.abs(errors)
        
        # MAE
        mae = float(np.mean(abs_errors))
        
        # MAPE (avoid division by zero)
        with np.errstate(divide='ignore', invalid='ignore'):
            pct_errors = np.where(
                actual != 0,
                abs_errors / np.abs(actual),
                0.0
            )
        mape = float(np.mean(pct_errors))
        
        # RMSE
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        
        # Relative RMSE
        mean_actual = float(np.mean(np.abs(actual)))
        relative_rmse = rmse / mean_actual if mean_actual > 0 else 0.0
        
        # Max error
        max_error = float(np.max(abs_errors))
        
        # Mean bias
        mean_bias = float(np.mean(errors))
        
        return ErrorMetrics(
            mae=mae,
            mape=mape,
            rmse=rmse,
            relative_rmse=relative_rmse,
            max_error=max_error,
            mean_bias=mean_bias,
        )
    
    def compute_seasonal_patterns(
        self,
        pest_type: Optional[str] = None,
    ) -> SeasonalPatternMetrics:
        """
        Compute seasonal pattern matching metrics.
        
        Analyzes how well the simulation captures wet/dry season patterns.
        
        Parameters
        ----------
        pest_type : str, optional
            Filter by pest type
        
        Returns
        -------
        SeasonalPatternMetrics
            Seasonal pattern analysis results
        """
        pairs = self.get_matched_pairs(pest_type)
        
        if len(pairs) < 6:  # Need at least some seasonal coverage
            return SeasonalPatternMetrics()
        
        # Group by season
        wet_pairs = []  # June-November
        dry_pairs = []  # December-May
        
        for actual, predicted, date_str in pairs:
            year_month = date_str.split("-")
            month = int(year_month[1])
            
            if month in [6, 7, 8, 9, 10, 11]:
                wet_pairs.append((actual, predicted))
            else:
                dry_pairs.append((actual, predicted))
        
        # Compute seasonal correlations
        wet_corr = 0.0
        if len(wet_pairs) >= 3:
            wet_actual = [p[0] for p in wet_pairs]
            wet_pred = [p[1] for p in wet_pairs]
            wet_corr, _ = compute_pearson_correlation(wet_actual, wet_pred)
        
        dry_corr = 0.0
        if len(dry_pairs) >= 3:
            dry_actual = [p[0] for p in dry_pairs]
            dry_pred = [p[1] for p in dry_pairs]
            dry_corr, _ = compute_pearson_correlation(dry_actual, dry_pred)
        
        # Find peak months
        # Group by month
        actual_by_month: Dict[int, List[float]] = {}
        pred_by_month: Dict[int, List[float]] = {}
        
        for actual, predicted, date_str in pairs:
            month = int(date_str.split("-")[1])
            if month not in actual_by_month:
                actual_by_month[month] = []
                pred_by_month[month] = []
            actual_by_month[month].append(actual)
            pred_by_month[month].append(predicted)
        
        # Find peak month (highest average)
        actual_peak_month = max(
            actual_by_month.keys(),
            key=lambda m: np.mean(actual_by_month[m])
        ) if actual_by_month else 0
        
        pred_peak_month = max(
            pred_by_month.keys(),
            key=lambda m: np.mean(pred_by_month[m])
        ) if pred_by_month else 0
        
        # Seasonal amplitude (max - min monthly average)
        if actual_by_month:
            actual_monthly_means = [np.mean(v) for v in actual_by_month.values()]
            actual_amplitude = max(actual_monthly_means) - min(actual_monthly_means)
        else:
            actual_amplitude = 0.0
        
        if pred_by_month:
            pred_monthly_means = [np.mean(v) for v in pred_by_month.values()]
            pred_amplitude = max(pred_monthly_means) - min(pred_monthly_means)
        else:
            pred_amplitude = 0.0
        
        amplitude_ratio = pred_amplitude / actual_amplitude if actual_amplitude > 0 else 0.0
        
        return SeasonalPatternMetrics(
            wet_season_correlation=wet_corr,
            dry_season_correlation=dry_corr,
            peak_month_match=actual_peak_month == pred_peak_month,
            actual_peak_month=actual_peak_month,
            predicted_peak_month=pred_peak_month,
            seasonal_amplitude_ratio=amplitude_ratio,
        )
    
    def compute_trend_similarity_score(
        self,
        correlation: CorrelationMetrics,
        trend_direction: TrendDirectionMetrics,
        errors: ErrorMetrics,
        seasonal: SeasonalPatternMetrics,
    ) -> float:
        """
        Compute overall trend similarity score (0-1).
        
        Combines multiple metrics into a single score:
        - 40% weight: Correlation (Pearson r)
        - 25% weight: Trend direction accuracy
        - 20% weight: Error (inverted MAPE)
        - 15% weight: Seasonal pattern (peak match + correlations)
        
        Returns
        -------
        float
            Similarity score between 0 (no similarity) and 1 (perfect match)
        """
        # Correlation component (convert -1 to 1 range to 0-1)
        corr_score = (correlation.pearson_r + 1) / 2
        
        # Direction accuracy component (already 0-1)
        direction_score = trend_direction.direction_accuracy
        
        # Error component (inverted - lower error = higher score)
        # Cap MAPE at 100% for scoring
        mape_capped = min(errors.mape, 1.0)
        error_score = 1 - mape_capped
        
        # Seasonal component
        seasonal_score = 0.0
        n_seasonal_components = 0
        
        if seasonal.wet_season_correlation != 0 or seasonal.dry_season_correlation != 0:
            seasonal_corr_avg = (
                (seasonal.wet_season_correlation + 1) / 2 +
                (seasonal.dry_season_correlation + 1) / 2
            ) / 2
            seasonal_score += seasonal_corr_avg
            n_seasonal_components += 1
        
        if seasonal.peak_month_match:
            seasonal_score += 1.0
            n_seasonal_components += 1
        elif seasonal.actual_peak_month != 0:
            # Partial credit if within 1 month
            month_diff = abs(seasonal.actual_peak_month - seasonal.predicted_peak_month)
            if month_diff == 1 or month_diff == 11:  # Account for year wrap
                seasonal_score += 0.5
            n_seasonal_components += 1
        
        if n_seasonal_components > 0:
            seasonal_score /= n_seasonal_components
        
        # Weighted combination
        total_score = (
            0.40 * corr_score +
            0.25 * direction_score +
            0.20 * error_score +
            0.15 * seasonal_score
        )
        
        return min(1.0, max(0.0, total_score))
    
    def analyze_pest_type(self, pest_type: str) -> TrendComparisonResult:
        """
        Perform complete trend analysis for a specific pest type.
        
        Parameters
        ----------
        pest_type : str
            Pest type ('cecid' or 'fruitfly')
        
        Returns
        -------
        TrendComparisonResult
            Complete trend comparison results
        """
        correlation = self.compute_correlation(pest_type)
        trend_direction = self.compute_trend_direction_accuracy(pest_type)
        errors = self.compute_error_metrics(pest_type)
        seasonal = self.compute_seasonal_patterns(pest_type)
        
        similarity_score = self.compute_trend_similarity_score(
            correlation, trend_direction, errors, seasonal
        )
        
        return TrendComparisonResult(
            pest_type=pest_type,
            correlation=correlation,
            trend_direction=trend_direction,
            errors=errors,
            seasonal=seasonal,
            trend_similarity_score=similarity_score,
            n_comparisons=correlation.n_samples,
        )
    
    def compute_all_comparisons(self) -> Dict[str, TrendComparisonResult]:
        """
        Compute trend comparisons for all pest types.
        
        Returns
        -------
        dict
            Keys are pest types, values are TrendComparisonResult
        """
        results = {}
        
        # Determine which pest types have data
        pest_types = set(r.case.pest_type for r in self.simulated_results)
        
        for pest_type in pest_types:
            results[pest_type] = self.analyze_pest_type(pest_type)
        
        # Also compute overall (combined)
        overall_correlation = self.compute_correlation()
        overall_direction = self.compute_trend_direction_accuracy()
        overall_errors = self.compute_error_metrics()
        overall_seasonal = self.compute_seasonal_patterns()
        
        overall_similarity = self.compute_trend_similarity_score(
            overall_correlation, overall_direction, overall_errors, overall_seasonal
        )
        
        results["overall"] = TrendComparisonResult(
            pest_type="overall",
            correlation=overall_correlation,
            trend_direction=overall_direction,
            errors=overall_errors,
            seasonal=overall_seasonal,
            trend_similarity_score=overall_similarity,
            n_comparisons=overall_correlation.n_samples,
        )
        
        return results
    
    def generate_comparison_report(self) -> str:
        """
        Generate a text report comparing simulated and actual trends.
        
        Returns
        -------
        str
            Formatted comparison report
        """
        comparisons = self.compute_all_comparisons()
        
        lines = [
            "=" * 70,
            "TREND COMPARISON ANALYSIS REPORT",
            "=" * 70,
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Comparisons: {comparisons.get('overall', TrendComparisonResult()).n_comparisons}",
            "",
        ]
        
        for pest_type, result in comparisons.items():
            lines.extend([
                "-" * 70,
                f"{pest_type.upper()} ANALYSIS",
                "-" * 70,
                "",
                f"  Trend Similarity Score: {result.trend_similarity_score:.1%}",
                "",
                "  CORRELATION:",
                f"    Pearson r:        {result.correlation.pearson_r:.3f} ({result.correlation.correlation_strength})",
                f"    Spearman rho:     {result.correlation.spearman_rho:.3f}",
                f"    Kendall tau:      {result.correlation.kendall_tau:.3f}",
                f"    Significant:      {'Yes' if result.correlation.is_significant else 'No'}",
                "",
                "  TREND DIRECTION:",
                f"    Accuracy:         {result.trend_direction.direction_accuracy:.1%}",
                f"    Correct/Total:    {result.trend_direction.n_correct_directions}/{result.trend_direction.n_total_transitions}",
                "",
                "  ERROR METRICS:",
                f"    MAE:              {result.errors.mae:.4f}",
                f"    MAPE:             {result.errors.mape_pct:.1f}%",
                f"    RMSE:             {result.errors.rmse:.4f}",
                f"    Relative RMSE:    {result.errors.relative_rmse_pct:.1f}%",
                f"    Mean Bias:        {result.errors.mean_bias:+.4f}",
                "",
                "  SEASONAL PATTERNS:",
                f"    Wet Season Corr:  {result.seasonal.wet_season_correlation:.3f}",
                f"    Dry Season Corr:  {result.seasonal.dry_season_correlation:.3f}",
                f"    Peak Month Match: {'Yes' if result.seasonal.peak_month_match else 'No'}",
                f"    Actual Peak:      Month {result.seasonal.actual_peak_month}",
                f"    Predicted Peak:   Month {result.seasonal.predicted_peak_month}",
                "",
            ])
        
        lines.extend([
            "=" * 70,
            "INTERPRETATION GUIDE",
            "=" * 70,
            "",
            "Trend Similarity Score:",
            "  > 0.80: Excellent - simulation captures real-world patterns well",
            "  0.60-0.80: Good - simulation captures major trends",
            "  0.40-0.60: Moderate - some patterns captured, room for improvement",
            "  < 0.40: Poor - significant discrepancy with observed data",
            "",
            "Correlation Strength:",
            "  > 0.80: Very Strong",
            "  0.60-0.80: Strong",
            "  0.40-0.60: Moderate",
            "  0.20-0.40: Weak",
            "  < 0.20: Very Weak",
            "",
            "=" * 70,
        ])
        
        return "\n".join(lines)
    
    def get_monthly_comparison_table(
        self,
        pest_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get month-by-month comparison data for tabular display.
        
        Returns
        -------
        list of dicts
            Each dict has date, actual, predicted, error, match info
        """
        pairs = self.get_matched_pairs(pest_type)
        
        table = []
        for actual, predicted, date_str in pairs:
            error = predicted - actual
            abs_error = abs(error)
            
            # Determine match status
            # Consider a match if within 0.2 (20% risk)
            match = abs_error <= 0.2
            
            table.append({
                "date": date_str,
                "actual_normalized": actual,
                "predicted_risk": predicted,
                "error": error,
                "abs_error": abs_error,
                "match": match,
            })
        
        return sorted(table, key=lambda x: x["date"])
