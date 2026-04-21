"""
MangoPoint API — Validation Service
====================================
Service layer for running historical validation against the simulation model.

This service wraps the validation module to provide async API compatibility.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from utils.datetime_utils import utcnow_naive

# Add parent path for validation module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)


def _round_float(value: Any, digits: int = 4) -> Any:
    """Round floats while leaving other value types untouched."""
    return round(value, digits) if isinstance(value, float) else value


def _round_mapping(data: Dict[str, Any], digits: int = 4) -> Dict[str, Any]:
    """Round float values in a shallow mapping for JSON responses."""
    return {key: _round_float(value, digits) for key, value in data.items()}


class ValidationService:
    """
    Service for running model validation against historical data.
    
    This service provides async wrapper methods around the validation
    module for use in the FastAPI endpoints.
    """
    
    def __init__(self):
        self._validation_loaded = False
        self._ValidationRunner = None
        self._ValidationReportGenerator = None
        self._normalize_pest_value_to_risk = None
    
    def _load_validation_modules(self):
        """Lazy load validation modules."""
        if self._validation_loaded:
            return
        
        try:
            from validation import (
                ValidationRunner,
                ValidationReportGenerator,
                normalize_pest_value_to_risk,
            )
            
            self._ValidationRunner = ValidationRunner
            self._ValidationReportGenerator = ValidationReportGenerator
            self._normalize_pest_value_to_risk = normalize_pest_value_to_risk
            self._validation_loaded = True
            logger.info("Validation modules loaded")
            
        except ImportError as e:
            logger.error(f"Failed to load validation modules: {e}")
            raise
    
    async def run_validation(
        self,
        max_cases: Optional[int] = None,
        pest_types: Optional[List[str]] = None,
        years: Optional[List[int]] = None,
        hours: int = 48,
        monte_carlo_runs: int = 30,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """
        Run historical validation.
        
        Parameters
        ----------
        max_cases : int, optional
            Maximum number of validation cases
        pest_types : list[str], optional
            Filter by pest type ('cecid', 'fruitfly')
        years : list[int], optional
            Filter by years
        hours : int
            Simulation duration per case
        monte_carlo_runs : int
            Number of Monte Carlo runs
        seed : int
            Random seed for reproducibility
        
        Returns
        -------
        dict
            Validation results and metrics
        """
        self._load_validation_modules()
        
        started_at = utcnow_naive()
        
        # Create and run validation
        runner = self._ValidationRunner(seed=seed)
        results = runner.run_full_validation(
            max_cases=max_cases,
            pest_types=pest_types,
            years=years,
            hours=hours,
            monte_carlo_runs=monte_carlo_runs,
        )
        
        # Compute metrics
        metrics = runner.compute_metrics()
        classification = _round_mapping(metrics.classification.to_dict())
        regression = _round_mapping(metrics.regression.to_dict())
        confusion_matrix = metrics.classification.confusion_matrix
        
        completed_at = utcnow_naive()
        duration = (completed_at - started_at).total_seconds()
        
        # Format response
        return {
            "status": "completed",
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_seconds": duration,
            "summary": {
                "total_tests": metrics.total_tests,
                "correct_predictions": metrics.correct_predictions,
                "incorrect_predictions": metrics.incorrect_predictions,
                "overall_accuracy_pct": round(metrics.overall_accuracy_pct, 2),
            },
            "classification_metrics": classification,
            "regression_metrics": regression,
            "confusion_matrix": {
                "true_positives": confusion_matrix.true_positives if confusion_matrix else 0,
                "true_negatives": confusion_matrix.true_negatives if confusion_matrix else 0,
                "false_positives": confusion_matrix.false_positives if confusion_matrix else 0,
                "false_negatives": confusion_matrix.false_negatives if confusion_matrix else 0,
            },
            "fruit_fly_metrics": (
                _round_mapping(metrics.fruit_fly_metrics.to_dict())
                if metrics.fruit_fly_metrics else None
            ),
            "cecid_fly_metrics": (
                _round_mapping(metrics.cecid_fly_metrics.to_dict())
                if metrics.cecid_fly_metrics else None
            ),
            "results": [
                {
                    "case_id": r.case.case_id,
                    "year": r.case.year,
                    "month": r.case.month,
                    "date": r.case.date_str,
                    "pest_type": r.case.pest_type,
                    "orchard_stage": r.case.orchard_stage,
                    "season": r.case.season,
                    "actual_level": r.case.actual_level,
                    "predicted_level": r.predicted_level,
                    "match": r.match,
                    "actual_value": round(r.case.actual_value, 2),
                    "actual_normalized": round(
                        self._normalize_pest_value_to_risk(r.case.actual_value, r.case.pest_type),
                        4,
                    ),
                    "predicted_risk": round(r.predicted_risk, 4),
                }
                for r in results
            ],
        }
    
    async def get_historical_data_summary(self) -> Dict[str, Any]:
        """
        Get summary of available historical data.
        
        Returns
        -------
        dict
            Data summary
        """
        self._load_validation_modules()
        
        from validation import HistoricalDataLoader
        
        loader = HistoricalDataLoader()
        loader.load()
        
        return loader.summary()
    
    async def get_validation_cases(
        self,
        max_cases: Optional[int] = None,
        pest_types: Optional[List[str]] = None,
        years: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Get available validation cases without running them.
        
        Parameters
        ----------
        max_cases : int, optional
            Maximum cases to return
        pest_types : list[str], optional
            Filter by pest type
        years : list[int], optional
            Filter by years
        
        Returns
        -------
        dict
            Available validation cases
        """
        self._load_validation_modules()
        
        runner = self._ValidationRunner()
        cases = runner.generate_validation_cases(
            max_cases=max_cases,
            pest_types=pest_types,
            years=years,
        )
        
        return {
            "total_cases": len(cases),
            "cases": [c.to_dict() for c in cases],
        }


# Singleton instance
validation_service = ValidationService()
