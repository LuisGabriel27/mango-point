"""
MangoPoint — Evaluation Module
================================
Computes model evaluation metrics by comparing simulation predictions
against ground truth pest observations.

Research-critical metrics:
    - True Positives (TP)
    - False Positives (FP)
    - True Negatives (TN)
    - False Negatives (FN)
    - Precision
    - Recall
    - F1-score
    - Spatial overlap percentage (IoU)

Usage
-----
    from evaluation import Evaluator
    
    evaluator = Evaluator(risk_threshold=0.7)
    metrics = evaluator.evaluate(
        predicted_risk=simulation_risk_grid,
        observed_infestation=observation_binary_grid,
    )
    print(f"F1-score: {metrics['f1_score']:.3f}")
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConfusionMatrix:
    """Confusion matrix for binary classification."""
    
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int
    
    @property
    def total(self) -> int:
        """Total number of predictions."""
        return self.true_positives + self.true_negatives + self.false_positives + self.false_negatives
    
    @property
    def precision(self) -> float:
        """Precision = TP / (TP + FP)."""
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0
    
    @property
    def recall(self) -> float:
        """Recall = TP / (TP + FN)."""
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0
    
    @property
    def f1_score(self) -> float:
        """F1-score = 2 * P * R / (P + R)."""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    
    @property
    def accuracy(self) -> float:
        """Accuracy = (TP + TN) / Total."""
        return (self.true_positives + self.true_negatives) / self.total if self.total > 0 else 0.0
    
    @property
    def specificity(self) -> float:
        """Specificity = TN / (TN + FP)."""
        denom = self.true_negatives + self.false_positives
        return self.true_negatives / denom if denom > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "true_positives": self.true_positives,
            "true_negatives": self.true_negatives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "accuracy": round(self.accuracy, 4),
            "specificity": round(self.specificity, 4),
        }


@dataclass
class EvaluationResult:
    """Complete evaluation result."""
    
    confusion_matrix: ConfusionMatrix
    spatial_overlap_percentage: float  # IoU × 100
    predicted_positive_count: int
    observed_positive_count: int
    matched_cells: int
    
    @property
    def precision(self) -> float:
        return self.confusion_matrix.precision
    
    @property
    def recall(self) -> float:
        return self.confusion_matrix.recall
    
    @property
    def f1_score(self) -> float:
        return self.confusion_matrix.f1_score
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "confusion_matrix": self.confusion_matrix.to_dict(),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "accuracy": round(self.confusion_matrix.accuracy, 4),
            "spatial_overlap_percentage": round(self.spatial_overlap_percentage, 2),
            "predicted_positive_count": self.predicted_positive_count,
            "observed_positive_count": self.observed_positive_count,
            "matched_cells": self.matched_cells,
        }
    
    def __repr__(self) -> str:
        return (
            f"EvaluationResult(\n"
            f"  Precision: {self.precision:.3f}\n"
            f"  Recall: {self.recall:.3f}\n"
            f"  F1-score: {self.f1_score:.3f}\n"
            f"  Spatial IoU: {self.spatial_overlap_percentage:.1f}%\n"
            f"  TP={self.confusion_matrix.true_positives}, "
            f"FP={self.confusion_matrix.false_positives}, "
            f"TN={self.confusion_matrix.true_negatives}, "
            f"FN={self.confusion_matrix.false_negatives}\n"
            f")"
        )


class Evaluator:
    """
    Evaluation engine for comparing simulation predictions
    against ground truth observations.
    
    Parameters
    ----------
    risk_threshold : float
        Threshold for converting continuous risk [0,1] to binary
        prediction. Default 0.7 (risk > 0.7 = positive prediction).
    
    Examples
    --------
    >>> evaluator = Evaluator(risk_threshold=0.7)
    >>> result = evaluator.evaluate(predicted_risk, observed_grid)
    >>> print(f"F1: {result.f1_score:.3f}")
    """
    
    def __init__(self, risk_threshold: float = 0.7):
        self.risk_threshold = risk_threshold
    
    def risk_to_binary(self, risk_grid: np.ndarray) -> np.ndarray:
        """
        Convert continuous risk grid [0,1] to binary prediction.
        
        Parameters
        ----------
        risk_grid : np.ndarray
            2D array of risk values in [0, 1]
            
        Returns
        -------
        np.ndarray
            Binary array where 1 = positive prediction (risk > threshold)
        """
        return (risk_grid > self.risk_threshold).astype(np.int32)
    
    def compute_confusion_matrix(
        self,
        predicted_binary: np.ndarray,
        observed_binary: np.ndarray,
    ) -> ConfusionMatrix:
        """
        Compute confusion matrix from binary predictions and observations.
        
        Parameters
        ----------
        predicted_binary : np.ndarray
            Binary prediction array (1 = predicted positive)
        observed_binary : np.ndarray
            Binary observation array (1 = actual positive)
            
        Returns
        -------
        ConfusionMatrix
            Confusion matrix with TP, FP, TN, FN counts
        """
        if predicted_binary.shape != observed_binary.shape:
            raise ValueError(
                f"Shape mismatch: predicted {predicted_binary.shape} != observed {observed_binary.shape}"
            )
        
        pred = predicted_binary.astype(bool)
        obs = observed_binary.astype(bool)
        
        tp = int((pred & obs).sum())
        fp = int((pred & ~obs).sum())
        tn = int((~pred & ~obs).sum())
        fn = int((~pred & obs).sum())
        
        return ConfusionMatrix(
            true_positives=tp,
            true_negatives=tn,
            false_positives=fp,
            false_negatives=fn,
        )
    
    def compute_spatial_overlap(
        self,
        predicted_binary: np.ndarray,
        observed_binary: np.ndarray,
    ) -> float:
        """
        Compute spatial overlap (Intersection over Union).
        
        IoU = |predicted ∩ observed| / |predicted ∪ observed|
        
        Parameters
        ----------
        predicted_binary : np.ndarray
            Binary prediction array
        observed_binary : np.ndarray
            Binary observation array
            
        Returns
        -------
        float
            IoU value in [0, 1]
        """
        pred = predicted_binary.astype(bool)
        obs = observed_binary.astype(bool)
        
        intersection = (pred & obs).sum()
        union = (pred | obs).sum()
        
        if union == 0:
            # Both empty = perfect match
            return 1.0
        
        return intersection / union
    
    def evaluate(
        self,
        predicted_risk: np.ndarray,
        observed_infestation: np.ndarray,
    ) -> EvaluationResult:
        """
        Evaluate simulation predictions against ground truth.
        
        Parameters
        ----------
        predicted_risk : np.ndarray
            2D array of predicted risk values [0, 1]
        observed_infestation : np.ndarray
            2D binary array (1 = observed infestation, 0 = no observation)
            
        Returns
        -------
        EvaluationResult
            Complete evaluation metrics
        """
        # Convert risk to binary
        predicted_binary = self.risk_to_binary(predicted_risk)
        observed_binary = (observed_infestation > 0).astype(np.int32)
        
        # Compute metrics
        cm = self.compute_confusion_matrix(predicted_binary, observed_binary)
        iou = self.compute_spatial_overlap(predicted_binary, observed_binary)
        
        result = EvaluationResult(
            confusion_matrix=cm,
            spatial_overlap_percentage=iou * 100,
            predicted_positive_count=int(predicted_binary.sum()),
            observed_positive_count=int(observed_binary.sum()),
            matched_cells=cm.true_positives,
        )
        
        logger.info(
            f"Evaluation completed: P={result.precision:.3f}, "
            f"R={result.recall:.3f}, F1={result.f1_score:.3f}, "
            f"IoU={result.spatial_overlap_percentage:.1f}%"
        )
        
        return result
    
    def evaluate_from_simulation_result(
        self,
        simulation_result: "SimulationResult",
        observed_infestation: np.ndarray,
        timestep: int = -1,
    ) -> EvaluationResult:
        """
        Evaluate simulation result at a specific timestep.
        
        Parameters
        ----------
        simulation_result : SimulationResult
            Result from SimulationEngine.run()
        observed_infestation : np.ndarray
            Ground truth binary array
        timestep : int
            Which timestep to evaluate (-1 = final)
            
        Returns
        -------
        EvaluationResult
            Evaluation metrics
        """
        risk_grid = simulation_result.snapshots[timestep]["risk"]
        return self.evaluate(risk_grid, observed_infestation)
    
    def evaluate_time_series(
        self,
        simulation_result: "SimulationResult",
        observed_infestation: np.ndarray,
    ) -> List[EvaluationResult]:
        """
        Evaluate all timesteps in a simulation.
        
        Parameters
        ----------
        simulation_result : SimulationResult
            Full simulation result with snapshots
        observed_infestation : np.ndarray
            Ground truth binary array
            
        Returns
        -------
        List[EvaluationResult]
            Evaluation result per timestep
        """
        results = []
        for i, snapshot in enumerate(simulation_result.snapshots):
            risk_grid = snapshot["risk"]
            result = self.evaluate(risk_grid, observed_infestation)
            results.append(result)
        return results


def create_observation_grid_from_points(
    observations: List[Dict[str, Any]],
    grid_shape: Tuple[int, int],
    cell_lookup: Dict[Tuple[int, int], Any],
) -> np.ndarray:
    """
    Create binary observation grid from point observations.
    
    Parameters
    ----------
    observations : list[dict]
        List of observation dicts with tree_id
    grid_shape : tuple
        (rows, cols) of the grid
    cell_lookup : dict
        Mapping from (row, col) to cell metadata (must have tree_id)
        
    Returns
    -------
    np.ndarray
        Binary grid where 1 = observed infestation
    """
    observed_grid = np.zeros(grid_shape, dtype=np.int32)
    
    # Build tree_id → cell position lookup
    tree_to_cell = {}
    for (row, col), cell in cell_lookup.items():
        if hasattr(cell, 'tree_id') and cell.tree_id:
            tree_to_cell[cell.tree_id] = (row, col)
    
    # Mark observed cells
    for obs in observations:
        tree_id = obs.get('tree_id')
        if tree_id and tree_id in tree_to_cell:
            row, col = tree_to_cell[tree_id]
            observed_grid[row, col] = 1
    
    return observed_grid


# ═══════════════════════════════════════════════════════════════
#  Demo / CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # Demo with synthetic data
    np.random.seed(42)
    
    rows, cols = 20, 20
    
    # Simulated risk grid (hot spot in center)
    predicted_risk = np.zeros((rows, cols))
    for r in range(8, 15):
        for c in range(8, 15):
            dist = np.sqrt((r - 11)**2 + (c - 11)**2)
            predicted_risk[r, c] = max(0, 1.0 - dist * 0.15)
    
    # Add some noise
    predicted_risk += np.random.uniform(0, 0.2, (rows, cols))
    predicted_risk = np.clip(predicted_risk, 0, 1)
    
    # Ground truth (slightly offset)
    observed = np.zeros((rows, cols), dtype=int)
    for r in range(9, 14):
        for c in range(9, 14):
            observed[r, c] = 1
    
    # Evaluate
    evaluator = Evaluator(risk_threshold=0.7)
    result = evaluator.evaluate(predicted_risk, observed)
    
    print("=" * 50)
    print("MangoPoint Evaluation Demo")
    print("=" * 50)
    print(result)
    print("\nFull metrics:")
    for k, v in result.to_dict().items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"    {kk}: {vv}")
        else:
            print(f"  {k}: {v}")
