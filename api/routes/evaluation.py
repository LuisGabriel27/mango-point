"""
MangoPoint API — Evaluation Routes
====================================
GET /evaluate endpoint for comparing predictions vs observations.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import (
    database_unavailable_http_exception,
    get_db,
    is_database_unavailable,
)
from ..models.schemas import EvaluationRequest, EvaluationResponse
from ..services.evaluation_service import evaluation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])


@router.get(
    "/evaluate",
    response_model=EvaluationResponse,
    summary="Evaluate model predictions",
    description="""
    Compare simulation predictions against ground truth observations.
    
    **Computes:**
    - **Precision**: True positives / (True positives + False positives)
    - **Recall**: True positives / (True positives + False negatives)
    - **F1-score**: Harmonic mean of precision and recall
    - **Spatial overlap**: Intersection over Union of risk areas
    
    **Parameters:**
    - `simulation_run_id`: Specific simulation to evaluate
    - `time_window_start/end`: Filter observations by time
    - `risk_threshold`: Threshold for binary risk classification (default: 0.5)
    """,
)
async def evaluate(
    simulation_run_id: Optional[str] = Query(
        None,
        description="Simulation run ID to evaluate",
    ),
    time_window_start: Optional[datetime] = Query(
        None,
        description="Start of evaluation time window",
    ),
    time_window_end: Optional[datetime] = Query(
        None,
        description="End of evaluation time window",
    ),
    risk_threshold: float = Query(
        0.5,
        ge=0.0,
        le=1.0,
        description="Risk threshold for binary classification",
    ),
    db: AsyncSession = Depends(get_db),
) -> EvaluationResponse:
    """
    Evaluate simulation predictions against ground truth observations.
    
    The evaluation compares:
    1. Predicted risk areas (risk >= threshold)
    2. Observed infestation locations
    
    This enables assessment of model accuracy for decision support.
    """
    try:
        result = await evaluation_service.evaluate(
            db=db,
            simulation_run_id=simulation_run_id,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            risk_threshold=risk_threshold,
        )
        
        logger.info(
            f"Evaluation completed: P={result.precision:.3f}, "
            f"R={result.recall:.3f}, F1={result.f1_score:.3f}"
        )
        
        return result
        
    except Exception as e:
        if is_database_unavailable(e):
            raise database_unavailable_http_exception() from e
        logger.error(f"Evaluation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Evaluation failed: {str(e)}",
        )


@router.get(
    "/evaluate/{simulation_id}",
    response_model=EvaluationResponse,
    summary="Evaluate specific simulation",
    description="""
    Evaluate a specific simulation run against ground truth observations.
    
    Uses risk threshold of 0.7 by default to create binary prediction map.
    
    **Returns:**
    - Confusion matrix (TP, FP, TN, FN)
    - Precision, Recall, F1-score
    - Spatial overlap percentage (IoU)
    """,
)
async def evaluate_simulation(
    simulation_id: str,
    risk_threshold: float = Query(
        0.7,
        ge=0.0,
        le=1.0,
        description="Risk threshold for binary classification (default: 0.7)",
    ),
    db: AsyncSession = Depends(get_db),
) -> EvaluationResponse:
    """
    Evaluate a specific simulation run by ID.
    
    Compares predicted risk areas (risk >= 0.7) against observed infestations.
    """
    try:
        result = await evaluation_service.evaluate(
            db=db,
            simulation_run_id=simulation_id,
            risk_threshold=risk_threshold,
        )
        
        logger.info(
            f"Evaluation for {simulation_id}: P={result.precision:.3f}, "
            f"R={result.recall:.3f}, F1={result.f1_score:.3f}"
        )
        
        return result
        
    except Exception as e:
        if is_database_unavailable(e):
            raise database_unavailable_http_exception() from e
        logger.error(f"Evaluation for {simulation_id} failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Evaluation failed: {str(e)}",
        )


@router.post(
    "/evaluate-inline",
    summary="Evaluate with inline data",
    description="Evaluate predictions using provided arrays (for testing).",
)
async def evaluate_inline(
    data: dict,
):
    """
    Evaluate using inline numpy-compatible data.
    
    Expects:
    - predicted_risk: 2D array of predicted risk values
    - observed_infestation: 2D binary array of observations
    - risk_threshold: Classification threshold
    """
    import numpy as np
    
    try:
        predicted_risk = np.array(data.get("predicted_risk", []))
        observed = np.array(data.get("observed_infestation", []))
        threshold = data.get("risk_threshold", 0.5)
        
        if predicted_risk.size == 0 or observed.size == 0:
            raise ValueError("Empty arrays provided")
        
        if predicted_risk.shape != observed.shape:
            raise ValueError("Array shapes must match")
        
        result = evaluation_service.evaluate_from_arrays(
            predicted_risk=predicted_risk,
            observed_infestation=observed,
            risk_threshold=threshold,
        )
        
        return {
            "evaluation_timestamp": datetime.utcnow().isoformat() + "Z",
            **result,
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Evaluation failed: {str(e)}",
        )


@router.get(
    "/metrics-history",
    summary="Get evaluation metrics history",
    description="Retrieve historical evaluation metrics across simulation runs.",
)
async def get_metrics_history(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get history of evaluation metrics.
    
    Useful for tracking model performance over time.
    """
    from sqlalchemy import select
    from db.models import SimulationRun
    
    # Get recent completed simulations
    query = (
        select(SimulationRun)
        .where(SimulationRun.status == "completed")
        .order_by(SimulationRun.started_at.desc())
        .limit(limit)
    )
    
    result = await db.execute(query)
    runs = result.scalars().all()
    
    # Evaluate each run
    metrics_history = []
    
    for run in runs:
        try:
            eval_result = await evaluation_service.evaluate(
                db=db,
                simulation_run_id=run.run_id,
                risk_threshold=0.5,
            )
            
            metrics_history.append({
                "run_id": run.run_id,
                "timestamp": run.started_at.isoformat() + "Z" if run.started_at else None,
                "precision": eval_result.precision,
                "recall": eval_result.recall,
                "f1_score": eval_result.f1_score,
                "spatial_overlap": eval_result.spatial_overlap_percentage,
            })
        except Exception as e:
            logger.warning(f"Could not evaluate run {run.run_id}: {e}")
    
    return {
        "history": metrics_history,
        "count": len(metrics_history),
    }
