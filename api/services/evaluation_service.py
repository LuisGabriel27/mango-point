"""
MangoPoint API — Evaluation Service
=====================================
Compares simulation predictions against ground truth observations.
Computes precision, recall, F1-score, and spatial overlap metrics.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple, Sequence
import numpy as np

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models import InfestationRecord, SimulationRun, Tree
from ..models.schemas import ConfusionMatrix, EvaluationResponse

logger = logging.getLogger(__name__)


class EvaluationService:
    """
    Service for evaluating simulation predictions against ground truth.
    
    Methods:
    - Convert predictions to binary risk map
    - Compare with observation points
    - Compute confusion matrix and metrics
    """
    
    async def evaluate(
        self,
        db: AsyncSession,
        simulation_run_id: Optional[str] = None,
        time_window_start: Optional[datetime] = None,
        time_window_end: Optional[datetime] = None,
        risk_threshold: float = 0.5,
    ) -> EvaluationResponse:
        """
        Evaluate simulation predictions against observations.
        """
        # Get simulation run
        simulation_run = None
        risk_data = None
        
        if simulation_run_id:
            result = await db.execute(
                select(SimulationRun).where(SimulationRun.run_id == simulation_run_id)
            )
            simulation_run = result.scalar_one_or_none()
            
            if simulation_run and simulation_run.output_geojson:
                risk_data = simulation_run.output_geojson
        
        # Get infestation records within time window
        obs_query = select(InfestationRecord)
        
        if time_window_start:
            obs_query = obs_query.where(InfestationRecord.record_date >= time_window_start)
        if time_window_end:
            obs_query = obs_query.where(InfestationRecord.record_date <= time_window_end)
        
        result = await db.execute(obs_query)
        observations = result.scalars().all()
        
        if not observations:
            logger.warning("No observations found for evaluation")
            return EvaluationResponse(
                simulation_run_id=simulation_run_id,
                evaluation_timestamp=datetime.utcnow().isoformat() + "Z",
                precision=0.0,
                recall=0.0,
                f1_score=0.0,
                accuracy=0.0,
                spatial_overlap_percentage=0.0,
                confusion_matrix=ConfusionMatrix(
                    true_positives=0,
                    true_negatives=0,
                    false_positives=0,
                    false_negatives=0,
                ),
                total_predictions=0,
                total_observations=0,
                matched_cells=0,
            )
        
        # Get tree records for spatial matching
        trees_query = select(Tree)
        if simulation_run and simulation_run.orchard_id:
            # Try to match orchard by name (orchard_id in simulation_run is a string label)
            pass  # query all trees for now
        
        result = await db.execute(trees_query)
        trees = result.scalars().all()
        
        # Compute metrics
        metrics = self._compute_spatial_metrics(
            observations=observations,
            trees=trees,
            risk_data=risk_data,
            risk_threshold=risk_threshold,
        )
        
        return EvaluationResponse(
            simulation_run_id=simulation_run_id,
            evaluation_timestamp=datetime.utcnow().isoformat() + "Z",
            **metrics,
        )
    
    def _compute_spatial_metrics(
        self,
        observations: Sequence[InfestationRecord],
        trees: Sequence[Tree],
        risk_data: Optional[Dict[str, Any]],
        risk_threshold: float,
    ) -> Dict[str, Any]:
        """
        Compute spatial comparison metrics.
        
        Approach:
        1. Create binary prediction map (risk >= threshold)
        2. Map observations to tree positions
        3. Compute confusion matrix
        4. Calculate precision, recall, F1, spatial overlap
        """
        # Build tree lookup by tree_id
        tree_lookup = {}
        for tree in trees:
            tree_lookup[tree.tree_id] = tree
        
        # Extract predicted risk by cell (from GeoJSON output)
        predicted_risk = {}
        if risk_data and isinstance(risk_data, dict):
            features = risk_data.get("features", [])
            for feature in features:
                props = feature.get("properties", {})
                row = props.get("row")
                col = props.get("col")
                risk = props.get("risk", 0)
                if row is not None and col is not None:
                    predicted_risk[(row, col)] = risk
        
        # Map observation tree_ids to cells using tree_id from GeoJSON output
        observed_cells = set()
        for obs in observations:
            tree_id_str = str(obs.tree_id)
            # Match tree_id from observations to tree_id in risk GeoJSON features
            if risk_data and isinstance(risk_data, dict):
                for feature in risk_data.get("features", []):
                    props = feature.get("properties", {})
                    if props.get("tree_id") == tree_id_str:
                        row = props.get("row")
                        col = props.get("col")
                        if row is not None and col is not None:
                            observed_cells.add((row, col))
                        break
        
        # Compute confusion matrix over all cells in prediction
        tp = 0
        fp = 0
        fn = 0
        tn = 0
        
        all_cells = set(predicted_risk.keys())
        
        for cell_key in all_cells:
            risk = predicted_risk.get(cell_key, 0)
            predicted_positive = risk >= risk_threshold
            actual_positive = cell_key in observed_cells
            
            if predicted_positive and actual_positive:
                tp += 1
            elif predicted_positive and not actual_positive:
                fp += 1
            elif not predicted_positive and actual_positive:
                fn += 1
            else:
                tn += 1
        
        # Calculate metrics
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        accuracy = (tp + tn) / len(all_cells) if len(all_cells) > 0 else 0.0
        
        # Spatial overlap: intersection over union
        predicted_positive_cells = {k for k, v in predicted_risk.items() if v >= risk_threshold}
        if predicted_positive_cells or observed_cells:
            intersection = len(predicted_positive_cells & observed_cells)
            union = len(predicted_positive_cells | observed_cells)
            spatial_overlap = intersection / union if union > 0 else 0.0
        else:
            spatial_overlap = 1.0
        
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1_score, 4),
            "accuracy": round(accuracy, 4),
            "spatial_overlap_percentage": round(spatial_overlap * 100, 2),
            "confusion_matrix": ConfusionMatrix(
                true_positives=tp,
                true_negatives=tn,
                false_positives=fp,
                false_negatives=fn,
            ),
            "total_predictions": len(predicted_risk),
            "total_observations": len(observations),
            "matched_cells": tp,
        }
    
    def evaluate_from_arrays(
        self,
        predicted_risk: np.ndarray,
        observed_infestation: np.ndarray,
        risk_threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Evaluate using numpy arrays directly.
        For use with in-memory simulation results.
        """
        # Binary prediction
        predicted_binary = (predicted_risk >= risk_threshold).astype(int)
        observed_binary = (observed_infestation > 0).astype(int)
        
        # Confusion matrix
        tp = int(((predicted_binary == 1) & (observed_binary == 1)).sum())
        fp = int(((predicted_binary == 1) & (observed_binary == 0)).sum())
        fn = int(((predicted_binary == 0) & (observed_binary == 1)).sum())
        tn = int(((predicted_binary == 0) & (observed_binary == 0)).sum())
        
        # Metrics
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        total = tp + tn + fp + fn
        accuracy = (tp + tn) / total if total > 0 else 0.0
        
        # Spatial overlap (IoU)
        intersection = tp
        union = tp + fp + fn
        spatial_overlap = intersection / union if union > 0 else 1.0
        
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1_score, 4),
            "accuracy": round(accuracy, 4),
            "spatial_overlap_percentage": round(spatial_overlap * 100, 2),
            "confusion_matrix": {
                "true_positives": tp,
                "true_negatives": tn,
                "false_positives": fp,
                "false_negatives": fn,
            },
            "total_predictions": int(predicted_binary.sum()),
            "total_observations": int(observed_binary.sum()),
            "matched_cells": tp,
        }


# Singleton instance
evaluation_service = EvaluationService()
