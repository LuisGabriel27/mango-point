"""
MangoPoint — Decision Support Layer
====================================
Post-processing and interpretation layer that transforms raw pest risk outputs
into actionable farm management recommendations and economic impact metrics.

This module is a pure interpretation layer:
  - Reads final risk values from completed simulation runs
  - Classifies risk into management recommendation zones
  - Computes loss prevention and economic metrics
  - Does NOT modify simulation engine, biological gates, phenology, or dispersal

Zone Classification:
  - Zone 1 (Green): "No Action Required" — risk < low_threshold
  - Zone 2 (Yellow/Orange): "Monitor / Manual Inspection" — low ≤ risk < high
  - Zone 3 (Red): "Critical: Spray / Bag Now" — risk ≥ high_threshold

Economic Metrics:
  - Pesticide Reduction %: How much pesticide use is avoided vs blanket spraying
  - Money Saved: Estimated cost savings from precision targeting (if cost data available)
"""

from dataclasses import dataclass
from typing import Optional
from enum import IntEnum

# Import thresholds from config (centralized, configurable)
from core.config import (
    DECISION_ZONE_LOW_THRESHOLD,
    DECISION_ZONE_HIGH_THRESHOLD,
    DECISION_ZONE_COLORS,
    PESTICIDE_COST_PER_HECTARE,
    CELL_AREA_HECTARES,
    CellState,
)


class DecisionZone(IntEnum):
    """Management recommendation zones based on pest risk levels."""
    NO_ACTION = 1      # Zone 1: Safe, no intervention needed
    MONITOR = 2        # Zone 2: Early warning, inspect but don't spray
    CRITICAL = 3       # Zone 3: Urgent action required


@dataclass
class ZoneThresholds:
    """Configurable risk thresholds for zone classification."""
    low: float = DECISION_ZONE_LOW_THRESHOLD
    high: float = DECISION_ZONE_HIGH_THRESHOLD
    
    def __post_init__(self):
        """Validate thresholds."""
        if not 0 <= self.low < self.high <= 1:
            raise ValueError(
                f"Invalid thresholds: low={self.low}, high={self.high}. "
                "Must satisfy 0 <= low < high <= 1"
            )


@dataclass
class DecisionMetrics:
    """Economic and decision support metrics computed from risk data."""
    # Area metrics (cell counts)
    total_farm_cells: int           # Total active (non-DEAD) cells
    zone_1_cells: int               # Cells requiring no action (safe)
    zone_2_cells: int               # Cells requiring monitoring
    zone_3_cells: int               # Cells requiring immediate spray
    
    # Percentage metrics
    spray_percentage: float         # % of farm requiring immediate spray
    monitor_percentage: float       # % of farm under monitoring
    safe_percentage: float          # % of farm safe (no action)
    pesticide_reduction: float      # % reduction vs blanket spraying
    
    # Economic metrics (optional, depends on cost data)
    area_not_sprayed_ha: Optional[float] = None     # Hectares not requiring spray
    estimated_savings: Optional[float] = None        # Money saved in PHP
    
    # Metadata
    thresholds_used: Optional[tuple] = None


def classify_risk_zone(
    risk_value: float,
    thresholds: Optional[ZoneThresholds] = None
) -> DecisionZone:
    """
    Classify a single risk value into a management recommendation zone.
    
    Parameters
    ----------
    risk_value : float
        Risk value between 0 and 1 from the simulation
    thresholds : ZoneThresholds, optional
        Custom thresholds (defaults to config values)
    
    Returns
    -------
    DecisionZone
        The recommended action zone (NO_ACTION, MONITOR, or CRITICAL)
    """
    if thresholds is None:
        thresholds = ZoneThresholds()
    
    if risk_value < thresholds.low:
        return DecisionZone.NO_ACTION
    elif risk_value < thresholds.high:
        return DecisionZone.MONITOR
    else:
        return DecisionZone.CRITICAL


def get_zone_color(zone: DecisionZone) -> str:
    """Get the display color for a decision zone."""
    color_map = {
        DecisionZone.NO_ACTION: DECISION_ZONE_COLORS["zone_1"],
        DecisionZone.MONITOR: DECISION_ZONE_COLORS["zone_2"],
        DecisionZone.CRITICAL: DECISION_ZONE_COLORS["zone_3"],
    }
    return color_map.get(zone, "#808080")  # Grey fallback


def get_zone_label(zone: DecisionZone) -> str:
    """Get a human-readable label for a decision zone."""
    labels = {
        DecisionZone.NO_ACTION: "No Action Required",
        DecisionZone.MONITOR: "Monitor / Inspect",
        DecisionZone.CRITICAL: "Critical: Spray Now",
    }
    return labels.get(zone, "Unknown")


def get_zone_description(zone: DecisionZone) -> str:
    """Get a detailed description for a decision zone."""
    descriptions = {
        DecisionZone.NO_ACTION: (
            "Risk level is below the action threshold. No pesticide application needed. "
            "Continue routine monitoring."
        ),
        DecisionZone.MONITOR: (
            "Early warning zone. Schedule manual inspection to verify pest presence. "
            "Prepare intervention equipment but do not spray yet."
        ),
        DecisionZone.CRITICAL: (
            "Urgent intervention required! Apply targeted pesticide treatment or "
            "fruit bagging immediately to prevent further spread."
        ),
    }
    return descriptions.get(zone, "")


def compute_decision_metrics(
    risk_geojson: dict,
    thresholds: Optional[ZoneThresholds] = None,
    pesticide_cost_per_ha: Optional[float] = None,
    cell_area_ha: Optional[float] = None,
) -> DecisionMetrics:
    """
    Compute decision support metrics from a risk GeoJSON.
    
    This function interprets the final risk map and produces actionable
    economic metrics. It does NOT modify any underlying simulation data.
    
    Parameters
    ----------
    risk_geojson : dict
        GeoJSON FeatureCollection with risk values in properties
    thresholds : ZoneThresholds, optional
        Custom zone thresholds (defaults to config values)
    pesticide_cost_per_ha : float, optional
        Cost of pesticide per hectare (defaults to config value)
    cell_area_ha : float, optional
        Area of each cell in hectares (defaults to config value)
    
    Returns
    -------
    DecisionMetrics
        Computed metrics for display in the Decision Support Summary
    """
    if thresholds is None:
        thresholds = ZoneThresholds()
    
    if pesticide_cost_per_ha is None:
        pesticide_cost_per_ha = PESTICIDE_COST_PER_HECTARE
    
    if cell_area_ha is None:
        cell_area_ha = CELL_AREA_HECTARES
    
    # Count cells by zone, excluding DEAD and EMPTY cells
    zone_1_count = 0  # Safe
    zone_2_count = 0  # Monitor
    zone_3_count = 0  # Critical
    total_active = 0
    
    features = risk_geojson.get("features", []) if risk_geojson else []
    
    for feat in features:
        props = feat.get("properties", {})
        state = props.get("state", "empty").lower()
        
        # Skip non-active cells (DEAD, EMPTY)
        if state in ("dead", "empty"):
            continue
        
        total_active += 1
        risk = props.get("risk", 0)
        zone = classify_risk_zone(risk, thresholds)
        
        if zone == DecisionZone.NO_ACTION:
            zone_1_count += 1
        elif zone == DecisionZone.MONITOR:
            zone_2_count += 1
        else:  # CRITICAL
            zone_3_count += 1
    
    # Compute percentages (handle division by zero)
    if total_active > 0:
        spray_pct = zone_3_count / total_active
        monitor_pct = zone_2_count / total_active
        safe_pct = zone_1_count / total_active
        # Pesticide reduction = 1 - (spray area / total area)
        # This represents how much pesticide is saved vs blanket spraying
        pesticide_reduction = 1.0 - spray_pct
    else:
        spray_pct = 0.0
        monitor_pct = 0.0
        safe_pct = 1.0
        pesticide_reduction = 1.0
    
    # Economic calculations (optional)
    area_not_sprayed = None
    money_saved = None
    
    if pesticide_cost_per_ha and cell_area_ha:
        # Area not requiring spray = (Zone 1 + Zone 2) cells × cell area
        cells_not_sprayed = zone_1_count + zone_2_count
        area_not_sprayed = cells_not_sprayed * cell_area_ha
        
        # Money saved = area not sprayed × cost per hectare
        money_saved = area_not_sprayed * pesticide_cost_per_ha
    
    return DecisionMetrics(
        total_farm_cells=total_active,
        zone_1_cells=zone_1_count,
        zone_2_cells=zone_2_count,
        zone_3_cells=zone_3_count,
        spray_percentage=spray_pct,
        monitor_percentage=monitor_pct,
        safe_percentage=safe_pct,
        pesticide_reduction=pesticide_reduction,
        area_not_sprayed_ha=area_not_sprayed,
        estimated_savings=money_saved,
        thresholds_used=(thresholds.low, thresholds.high),
    )


def classify_geojson_with_zones(
    risk_geojson: dict,
    thresholds: Optional[ZoneThresholds] = None,
) -> dict:
    """
    Add decision zone classification to a risk GeoJSON.
    
    This function adds a 'decision_zone' property to each feature without
    modifying the original 'risk' or 'state' values. The original data
    remains intact for the simulation engine.
    
    Parameters
    ----------
    risk_geojson : dict
        GeoJSON FeatureCollection with risk values
    thresholds : ZoneThresholds, optional
        Custom zone thresholds
    
    Returns
    -------
    dict
        Copy of GeoJSON with 'decision_zone' and 'zone_color' added to properties
    """
    if thresholds is None:
        thresholds = ZoneThresholds()
    
    # Deep copy to avoid modifying original
    import copy
    result = copy.deepcopy(risk_geojson)
    
    for feat in result.get("features", []):
        props = feat.get("properties", {})
        risk = props.get("risk", 0)
        
        # Classify and add zone info
        zone = classify_risk_zone(risk, thresholds)
        props["decision_zone"] = int(zone)
        props["zone_label"] = get_zone_label(zone)
        props["zone_color"] = get_zone_color(zone)
    
    return result


def format_metrics_summary(metrics: DecisionMetrics) -> dict:
    """
    Format metrics for display in the dashboard summary panel.
    
    Returns a dictionary with formatted strings ready for UI display.
    """
    summary = {
        "total_cells": f"{metrics.total_farm_cells:,}",
        "spray_cells": f"{metrics.zone_3_cells:,}",
        "monitor_cells": f"{metrics.zone_2_cells:,}",
        "safe_cells": f"{metrics.zone_1_cells:,}",
        "spray_percentage": f"{metrics.spray_percentage:.1%}",
        "monitor_percentage": f"{metrics.monitor_percentage:.1%}",
        "safe_percentage": f"{metrics.safe_percentage:.1%}",
        "pesticide_reduction": f"{metrics.pesticide_reduction:.1%}",
    }
    
    # Add economic metrics if available
    if metrics.estimated_savings is not None:
        summary["estimated_savings"] = f"₱{metrics.estimated_savings:,.0f}"
        summary["area_not_sprayed"] = f"{metrics.area_not_sprayed_ha:.4f} ha"
    else:
        summary["estimated_savings"] = "N/A (no cost data)"
        summary["area_not_sprayed"] = "N/A"
    
    return summary
