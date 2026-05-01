"""
MangoPoint API — Validation Routes
===================================
API endpoints for historical model validation.

These endpoints allow running validation against BPI Guimaras historical
pest monitoring data without modifying the core simulation system.

Endpoints:
    GET  /validation/historical-data    - Get summary of historical data
    GET  /validation/cases              - List available validation cases
    POST /validation/run                - Run validation batch
"""

import logging
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.validation_service import validation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/validation", tags=["Validation"])


# ═══════════════════════════════════════════════
#  Request/Response Schemas
# ═══════════════════════════════════════════════

class ValidationRequest(BaseModel):
    """Request schema for POST /validation/run."""
    max_cases: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Maximum number of validation cases to run"
    )
    pest_types: Optional[List[str]] = Field(
        default=None,
        description="Filter by pest type: ['cecid'], ['fruitfly'], or both"
    )
    years: Optional[List[int]] = Field(
        default=None,
        description="Filter by specific years (e.g., [2023, 2024])"
    )
    split_year: Optional[int] = Field(
        default=None,
        description="Use years before this as calibration and this year or later as testing",
    )
    test_years: Optional[List[int]] = Field(
        default=None,
        description="Explicit years reserved for testing; other selected years become calibration",
    )
    calibrate: bool = Field(
        default=False,
        description="Fit pest-specific calibration on the calibration split before scoring",
    )
    hours: int = Field(
        default=48,
        ge=24,
        le=168,
        description="Simulation duration per case (hours)"
    )
    monte_carlo_runs: int = Field(
        default=30,
        ge=10,
        le=100,
        description="Number of Monte Carlo runs for risk estimation"
    )
    seed: int = Field(
        default=42,
        description="Random seed for reproducibility"
    )


class ClassificationMetricsResponse(BaseModel):
    """Classification metrics response."""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    specificity: float
    n_samples: int = 0
    true_positives: int = 0
    true_negatives: int = 0
    false_positives: int = 0
    false_negatives: int = 0


class RegressionMetricsResponse(BaseModel):
    """Regression metrics response."""
    mae: float
    rmse: float
    r_squared: float
    normalized_mae: float = 0.0
    mean_actual: float = 0.0
    mean_predicted: float = 0.0
    n_samples: int = 0


class ConfusionMatrixResponse(BaseModel):
    """Binary outbreak confusion matrix response."""
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int


class ValidationSummaryResponse(BaseModel):
    """Validation summary response."""
    total_tests: int
    correct_predictions: int
    incorrect_predictions: int
    overall_accuracy_pct: float


class ValidationResultItem(BaseModel):
    """Single validation result item."""
    case_id: str
    year: Optional[int] = None
    month: Optional[int] = None
    date: str
    pest_type: str
    orchard_stage: Optional[str] = None
    season: Optional[str] = None
    actual_level: str
    predicted_level: str
    match: bool
    actual_value: float
    actual_normalized: Optional[float] = None
    predicted_risk: float
    raw_predicted_risk: Optional[float] = None
    raw_predicted_level: Optional[str] = None
    calibration_applied: bool = False


class ValidationResponse(BaseModel):
    """Response schema for validation run."""
    status: str
    started_at: str
    completed_at: str
    duration_seconds: float
    summary: ValidationSummaryResponse
    classification_metrics: ClassificationMetricsResponse
    regression_metrics: RegressionMetricsResponse
    confusion_matrix: ConfusionMatrixResponse
    fruit_fly_metrics: Optional[ClassificationMetricsResponse] = None
    cecid_fly_metrics: Optional[ClassificationMetricsResponse] = None
    split: Optional[Dict[str, Any]] = None
    split_metrics: Optional[Dict[str, Any]] = None
    calibration: Optional[Dict[str, Any]] = None
    weather: Optional[Dict[str, Any]] = None
    results: List[ValidationResultItem]


class HistoricalDataSummary(BaseModel):
    """Historical data summary response."""
    n_records: int
    years: List[int]
    year_range: str
    fruit_fly_risk_distribution: dict
    cecid_fly_risk_distribution: dict
    fruit_fly_relevant_records: int
    cecid_fly_relevant_records: int


class ValidationCaseItem(BaseModel):
    """Single validation case item."""
    case_id: str
    year: int
    month: int
    date: str
    pest_type: str
    orchard_stage: str
    actual_value: float
    actual_level: str
    weather_scenario: str
    season: str


class ValidationCasesResponse(BaseModel):
    """Response for listing validation cases."""
    total_cases: int
    cases: List[ValidationCaseItem]


# ═══════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════

@router.get(
    "/historical-data",
    response_model=HistoricalDataSummary,
    summary="Get historical data summary",
    description="""
    Get a summary of the historical BPI Guimaras pest monitoring data
    available for validation.
    
    **Data Source:** Bureau of Plant Industry - Guimaras Research and Development Center
    
    **Data Range:** 2022-2025 monthly pest monitoring records
    
    **Metrics:**
    - Fruit Fly: Catch Per Trap per Day (CPTD)
    - Cecid Fly: Infestation percentage
    """,
)
async def get_historical_data_summary():
    """Get summary of historical validation data."""
    try:
        return await validation_service.get_historical_data_summary()
    except Exception as e:
        logger.error(f"Failed to get historical data summary: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load historical data: {str(e)}"
        )


@router.get(
    "/cases",
    response_model=ValidationCasesResponse,
    summary="List validation cases",
    description="""
    List available validation cases without running them.
    
    Validation cases are generated from historical records where the pest
    activity is biologically relevant:
    - Fruit Fly: MATURE stage (May-July, when fruit is ripe)
    - Cecid Fly: FRUITLET stage (March-April, when young fruitlets form)
    
    Use this endpoint to preview cases before running full validation.
    """,
)
async def list_validation_cases(
    max_cases: Optional[int] = Query(None, ge=1, le=100, description="Maximum cases to return"),
    pest_types: Optional[str] = Query(None, description="Comma-separated pest types: cecid,fruitfly"),
    years: Optional[str] = Query(None, description="Comma-separated years: 2023,2024"),
):
    """List available validation cases."""
    try:
        # Parse comma-separated filters
        pest_types_list = pest_types.split(",") if pest_types else None
        years_list = [int(y.strip()) for y in years.split(",")] if years else None
        
        return await validation_service.get_validation_cases(
            max_cases=max_cases,
            pest_types=pest_types_list,
            years=years_list,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {e}")
    except Exception as e:
        logger.error(f"Failed to list validation cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/run",
    response_model=ValidationResponse,
    summary="Run validation batch",
    description="""
    Run historical validation against the simulation model.
    
    **Process:**
    1. Loads historical pest monitoring records from BPI Guimaras
    2. Generates weather scenarios matching historical climate conditions
    3. Runs simulation for each validation case using the existing engine
    4. Optionally calibrates risk scores using calibration years
    5. Compares predicted risk levels with actual recorded pest levels
    6. Computes evaluation metrics (accuracy, precision, recall, F1, MAE, RMSE)
    
    **Note:** This operation may take several minutes depending on the number
    of cases and Monte Carlo runs configured.
    
    **Risk Classification Thresholds:**
    - Fruit Fly CPTD: LOW < 8, MEDIUM 8-20, HIGH > 20
    - Cecid Fly %: LOW < 5%, MEDIUM 5-15%, HIGH > 15%
    """,
)
async def run_validation(request: ValidationRequest):
    """Run historical validation."""
    try:
        logger.info(
            f"Starting validation: max_cases={request.max_cases}, "
            f"pest_types={request.pest_types}, years={request.years}"
        )
        
        result = await validation_service.run_validation(
            max_cases=request.max_cases,
            pest_types=request.pest_types,
            years=request.years,
            split_year=request.split_year,
            test_years=request.test_years,
            calibrate=request.calibrate,
            hours=request.hours,
            monte_carlo_runs=request.monte_carlo_runs,
            seed=request.seed,
        )
        
        logger.info(
            f"Validation complete: {result['summary']['total_tests']} cases, "
            f"{result['summary']['overall_accuracy_pct']}% accuracy"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Validation failed: {str(e)}"
        )


@router.get(
    "/metrics-explanation",
    summary="Get explanation of validation metrics",
    description="Returns documentation for interpreting validation metrics.",
)
async def get_metrics_explanation():
    """Get explanation of validation metrics."""
    return {
        "classification_metrics": {
            "accuracy": {
                "name": "Overall Accuracy",
                "description": "Percentage of correct predictions (predicted level matches actual level)",
                "range": "0-1 (or 0-100%)",
                "interpretation": "Higher is better. 0.8+ indicates strong predictions."
            },
            "precision": {
                "name": "Precision",
                "description": "When model predicts HIGH risk, how often is it correct?",
                "formula": "True Positives / (True Positives + False Positives)",
                "interpretation": "High precision = fewer false alarms"
            },
            "recall": {
                "name": "Recall (Sensitivity)",
                "description": "Of all actual HIGH risk cases, how many did the model detect?",
                "formula": "True Positives / (True Positives + False Negatives)",
                "interpretation": "High recall = fewer missed outbreaks (critical for pest management)"
            },
            "f1_score": {
                "name": "F1-Score",
                "description": "Harmonic mean of precision and recall",
                "formula": "2 * (Precision * Recall) / (Precision + Recall)",
                "interpretation": "Balanced measure; 0.7+ is good"
            },
            "specificity": {
                "name": "Specificity",
                "description": "Of all actual LOW/MEDIUM risk cases, how many were correctly identified?",
                "formula": "True Negatives / (True Negatives + False Positives)",
                "interpretation": "High specificity = correctly identifies safe periods"
            },
        },
        "regression_metrics": {
            "mae": {
                "name": "Mean Absolute Error",
                "description": "Average absolute difference between predicted and actual risk scores",
                "interpretation": "Lower is better. In 0-1 scale, 0.1 means ~10% average error"
            },
            "rmse": {
                "name": "Root Mean Square Error",
                "description": "Square root of average squared differences",
                "interpretation": "Lower is better. Penalizes large errors more than MAE"
            },
            "r_squared": {
                "name": "R-squared (Coefficient of Determination)",
                "description": "Proportion of variance in actual values explained by predictions",
                "range": "0-1",
                "interpretation": "Higher is better. 0.7+ indicates good fit"
            },
        },
        "risk_thresholds": {
            "fruit_fly": {
                "metric": "Catch Per Trap per Day (CPTD)",
                "LOW": "< 8 flies/trap/day",
                "MEDIUM": "8-20 flies/trap/day",
                "HIGH": "> 20 flies/trap/day"
            },
            "cecid_fly": {
                "metric": "Infestation Percentage",
                "LOW": "< 5%",
                "MEDIUM": "5-15%",
                "HIGH": "> 15%"
            }
        },
        "calibration": {
            "description": (
                "When requested with a calibration/testing split, the API fits "
                "pest-specific score curves on calibration years and applies "
                "those frozen curves before computing reported metrics."
            ),
            "raw_output": "raw_predicted_risk preserves the uncalibrated simulator score",
        }
    }
