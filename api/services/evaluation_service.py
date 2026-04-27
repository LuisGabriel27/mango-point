"""
MangoPoint API — Evaluation Service
=====================================
Compares simulation predictions against ground truth observations.
Computes precision, recall, F1-score, and spatial overlap metrics.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, Sequence
import numpy as np

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, select

from db.models import InfestationRecord, SimulationRun
from ..models.schemas import ConfusionMatrix, EvaluationResponse
from utils.datetime_utils import format_rfc3339, utcnow_naive

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
        else:
            result = await db.execute(
                select(SimulationRun)
                .where(
                    SimulationRun.status == "completed",
                    SimulationRun.output_geojson.isnot(None),
                )
                .order_by(desc(SimulationRun.started_at), desc(SimulationRun.id))
                .limit(1)
            )
            simulation_run = result.scalar_one_or_none()

        if simulation_run and simulation_run.output_geojson:
            risk_data = simulation_run.output_geojson

        effective_run_id = simulation_run.run_id if simulation_run else simulation_run_id
        
        # Get ground-truth field observations within time window. Simulation
        # generated infestation rows carry a simulation_id; observations do not.
        obs_query = select(InfestationRecord).where(InfestationRecord.simulation_id.is_(None))
        
        if time_window_start:
            obs_query = obs_query.where(InfestationRecord.record_date >= time_window_start)
        if time_window_end:
            obs_query = obs_query.where(InfestationRecord.record_date <= time_window_end)
        
        result = await db.execute(obs_query)
        observations = result.scalars().all()
        
        if not observations:
            logger.warning("No observations found for evaluation")
            return EvaluationResponse(
                simulation_run_id=effective_run_id,
                evaluation_timestamp=format_rfc3339(utcnow_naive()),
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
        
        # Compute metrics
        metrics = self._compute_spatial_metrics(
            observations=observations,
            trees=[],
            risk_data=risk_data,
            risk_threshold=risk_threshold,
        )
        
        return EvaluationResponse(
            simulation_run_id=effective_run_id,
            evaluation_timestamp=format_rfc3339(utcnow_naive()),
            **metrics,
        )

    @staticmethod
    def _normalize_tree_id(value: Any) -> Optional[str]:
        """Normalize tree identifiers across DB ints and GeoJSON properties."""
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or normalized.lower() in {"none", "null"}:
            return None
        return normalized

    @classmethod
    def _feature_key(cls, props: Dict[str, Any]) -> Optional[tuple]:
        """Return the comparable unit key for one risk GeoJSON feature."""
        raw_tree_id = None
        for candidate in ("tree_id", "Tree_ID", "fid"):
            if candidate in props and props[candidate] is not None:
                raw_tree_id = props[candidate]
                break

        tree_id = cls._normalize_tree_id(raw_tree_id)
        if tree_id is not None:
            return ("tree", tree_id)

        row = props.get("row")
        col = props.get("col")
        if row is None or col is None:
            return None
        try:
            return ("cell", int(row), int(col))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _extract_predicted_risk(cls, risk_data: Optional[Dict[str, Any]]) -> Dict[tuple, float]:
        """
        Extract prediction units from grid or tree_graph GeoJSON.

        Grid output usually supplies row/col and tree_id. Tree-graph output
        supplies point features keyed by tree_id. Matching by tree_id first
        keeps both modes comparable against field observations.
        """
        predicted_risk: Dict[tuple, float] = {}
        if not risk_data or not isinstance(risk_data, dict):
            return predicted_risk

        for feature in risk_data.get("features", []):
            props = feature.get("properties", {}) if isinstance(feature, dict) else {}
            key = cls._feature_key(props)
            if key is None:
                continue
            try:
                risk = float(props.get("risk", 0.0) or 0.0)
            except (TypeError, ValueError):
                risk = 0.0
            predicted_risk[key] = max(predicted_risk.get(key, 0.0), risk)

        return predicted_risk
    
    def _compute_spatial_metrics(
        self,
        observations: Sequence[InfestationRecord],
        trees: Sequence[Any],
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
        _ = trees

        # Extract predicted risk by comparable unit. Grid and tree_graph both
        # prefer tree IDs; grid row/col is only used when no tree ID exists.
        predicted_risk = self._extract_predicted_risk(risk_data)

        # Map field observations to tree IDs. Unmatched observations are still
        # included in the universe so they correctly count as false negatives.
        observed_units = set()
        for obs in observations:
            tree_id = self._normalize_tree_id(getattr(obs, "tree_id", None))
            if tree_id is not None:
                observed_units.add(("tree", tree_id))
        
        # Compute confusion matrix over all comparable units.
        tp = 0
        fp = 0
        fn = 0
        tn = 0
        
        all_units = set(predicted_risk.keys()) | observed_units
        
        for unit_key in all_units:
            risk = predicted_risk.get(unit_key, 0.0)
            predicted_positive = risk >= risk_threshold
            actual_positive = unit_key in observed_units
            
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
        accuracy = (tp + tn) / len(all_units) if len(all_units) > 0 else 0.0
        
        # Spatial overlap: intersection over union
        predicted_positive_units = {k for k, v in predicted_risk.items() if v >= risk_threshold}
        if predicted_positive_units or observed_units:
            intersection = len(predicted_positive_units & observed_units)
            union = len(predicted_positive_units | observed_units)
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
