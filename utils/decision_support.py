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

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
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


@dataclass
class ActionPlanItem:
    """A prioritized field task derived from the final simulation risk map."""
    priority: str
    action_type: str
    title: str
    timing: str
    zone: DecisionZone
    target_count: int
    max_risk: float
    scope_label: str
    rationale: str
    recommended_steps: List[str]
    tree_ids: List[str] = field(default_factory=list)
    cells: List[Dict[str, int]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly representation for APIs or dashboards."""
        return {
            "priority": self.priority,
            "action_type": self.action_type,
            "title": self.title,
            "timing": self.timing,
            "zone": int(self.zone),
            "zone_label": get_zone_label(self.zone),
            "target_count": self.target_count,
            "max_risk": self.max_risk,
            "scope_label": self.scope_label,
            "rationale": self.rationale,
            "recommended_steps": list(self.recommended_steps),
            "tree_ids": list(self.tree_ids),
            "cells": [dict(cell) for cell in self.cells],
        }


@dataclass(frozen=True)
class _RiskFeature:
    """Normalized view of a GeoJSON feature used by the action planner."""
    risk: float
    state: str
    zone: DecisionZone
    tree_id: Optional[str]
    cell: Optional[Dict[str, int]]
    centroid: Optional[Tuple[float, float]]


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
        DecisionZone.CRITICAL: "Critical: Targeted Action",
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
            "Urgent intervention required. Confirm field signs, then apply "
            "appropriate targeted control such as bagging, sanitation, or "
            "approved treatment to prevent further spread."
        ),
    }
    return descriptions.get(zone, "")


def _coerce_risk(value: Any) -> float:
    """Convert risk values to a clamped 0..1 float."""
    try:
        risk = float(value)
    except (TypeError, ValueError):
        risk = 0.0
    return max(0.0, min(1.0, risk))


def _feature_tree_id(props: Dict[str, Any]) -> Optional[str]:
    """Extract a stable tree identifier from common GeoJSON property names."""
    for key in ("tree_id", "Tree_ID", "id", "fid"):
        value = props.get(key)
        if value is not None and value != "":
            return str(value)
    return None


def _feature_cell(props: Dict[str, Any]) -> Optional[Dict[str, int]]:
    """Extract grid row/col if the feature came from grid mode."""
    row = props.get("row")
    col = props.get("col")
    if row is None or col is None:
        return None
    try:
        return {"row": int(row), "col": int(col)}
    except (TypeError, ValueError):
        return None


def _feature_centroid(feature: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Return a rough feature centroid as (lon, lat) when geometry is usable."""
    geometry = feature.get("geometry", {}) or {}
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")

    try:
        if geom_type == "Point" and isinstance(coords, (list, tuple)) and len(coords) >= 2:
            return float(coords[0]), float(coords[1])

        if geom_type == "Polygon" and coords and coords[0]:
            ring = coords[0]
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring = ring[:-1]
            lons = [float(point[0]) for point in ring]
            lats = [float(point[1]) for point in ring]
            if lons and lats:
                return sum(lons) / len(lons), sum(lats) / len(lats)
    except (TypeError, ValueError, IndexError):
        return None

    return None


def _collect_risk_features(
    risk_geojson: Dict[str, Any],
    thresholds: ZoneThresholds,
) -> List[_RiskFeature]:
    """Normalize active GeoJSON features into planner-ready records."""
    features: List[_RiskFeature] = []
    for feature in (risk_geojson or {}).get("features", []):
        props = feature.get("properties", {}) or {}
        state = str(props.get("state", "unbagged")).lower()
        if state in ("dead", "empty"):
            continue

        risk = _coerce_risk(props.get("risk", 0))
        zone = classify_risk_zone(risk, thresholds)
        features.append(
            _RiskFeature(
                risk=risk,
                state=state,
                zone=zone,
                tree_id=_feature_tree_id(props),
                cell=_feature_cell(props),
                centroid=_feature_centroid(feature),
            )
        )
    return features


def _dedupe_tree_ids(features: Sequence[_RiskFeature], limit: int) -> List[str]:
    """Return unique tree IDs in risk-priority order."""
    seen = set()
    tree_ids: List[str] = []
    for feature in sorted(features, key=lambda item: item.risk, reverse=True):
        if not feature.tree_id or feature.tree_id in seen:
            continue
        seen.add(feature.tree_id)
        tree_ids.append(feature.tree_id)
        if len(tree_ids) >= limit:
            break
    return tree_ids


def _target_cells(features: Sequence[_RiskFeature], limit: int) -> List[Dict[str, int]]:
    """Return grid cells in risk-priority order."""
    cells: List[Dict[str, int]] = []
    seen = set()
    for feature in sorted(features, key=lambda item: item.risk, reverse=True):
        if not feature.cell:
            continue
        key = (feature.cell["row"], feature.cell["col"])
        if key in seen:
            continue
        seen.add(key)
        cells.append(dict(feature.cell))
        if len(cells) >= limit:
            break
    return cells


def _scope_label(features: Sequence[_RiskFeature]) -> str:
    """Summarize which trees/cells a plan item targets."""
    tree_ids = _dedupe_tree_ids(features, limit=6)
    total_tree_ids = len({feature.tree_id for feature in features if feature.tree_id})
    if tree_ids:
        extra = total_tree_ids - len(tree_ids)
        suffix = f" and {extra} more" if extra > 0 else ""
        return f"{total_tree_ids} tree(s): {', '.join(tree_ids)}{suffix}"

    cells = [feature.cell for feature in features if feature.cell]
    if cells:
        rows = [cell["row"] for cell in cells]
        cols = [cell["col"] for cell in cells]
        return (
            f"{len(cells)} grid cell(s), rows {min(rows)}-{max(rows)}, "
            f"cols {min(cols)}-{max(cols)}"
        )

    return f"{len(features)} mapped feature(s)"


def _pest_label(pest_type: Optional[str]) -> str:
    value = str(pest_type or "").strip().lower().replace("-", "_")
    if value in {"cecid", "cecid_fly", "cecid fly"}:
        return "Cecid fly"
    if value in {"fruitfly", "fruit_fly", "fruit fly"}:
        return "Fruit fly"
    if not value:
        return "Pest"
    return value.replace("_", " ").title()


def _critical_steps(pest_type: Optional[str]) -> List[str]:
    pest_label = _pest_label(pest_type).lower()
    if "cecid" in pest_label:
        return [
            "Inspect flagged fruitlet-stage trees, canopy interiors, and recent rain-affected low spots.",
            "Tag confirmed trees and nearby susceptible fruitlets for bagging or approved targeted control.",
            "Record per-tree observations before final treatment decisions.",
        ]
    if "fruit fly" in pest_label:
        return [
            "Check flagged mature-fruit trees, traps, and fallen fruit around the affected area.",
            "Remove fallen or damaged fruit and prioritize sanitation around confirmed hotspots.",
            "Use approved targeted control only where field confirmation supports it.",
        ]
    return [
        "Inspect flagged trees and adjacent susceptible trees.",
        "Confirm pest signs before treatment decisions.",
        "Record field observations and update the simulator inputs.",
    ]


def _monitor_steps(pest_type: Optional[str]) -> List[str]:
    pest_label = _pest_label(pest_type).lower()
    if "cecid" in pest_label:
        return [
            "Scout fruitlets on early-warning trees for swelling, galling, or adult activity.",
            "Recheck the same trees after the next favorable weather window.",
            "Escalate to targeted control only if field observations confirm pest pressure.",
        ]
    if "fruit fly" in pest_label:
        return [
            "Check traps and mature fruit on early-warning trees.",
            "Remove suspect fallen fruit during the inspection round.",
            "Repeat scouting if warm, humid, or rainy conditions continue.",
        ]
    return [
        "Inspect early-warning trees and nearby susceptible trees.",
        "Record observations for calibration and follow-up.",
        "Escalate only when observed pest signs confirm the model signal.",
    ]


def _routine_steps(pest_type: Optional[str]) -> List[str]:
    pest_label = _pest_label(pest_type)
    return [
        f"Keep routine {pest_label.lower()} scouting on the normal farm schedule.",
        "Update orchard observations when field signs are found.",
        "Run a new forecast after major weather changes or growth-stage changes.",
    ]


def _protected_steps() -> List[str]:
    return [
        "Verify bagging coverage and replace torn or missing bags on flagged trees.",
        "Inspect nearby unprotected trees for fresh pest signs.",
        "Record protection status and field observations after the inspection.",
    ]


def build_action_plan(
    risk_geojson: Dict[str, Any],
    pest_type: Optional[str] = None,
    orchard_stage: Optional[str] = None,
    thresholds: Optional[ZoneThresholds] = None,
    max_targets: int = 12,
) -> List[ActionPlanItem]:
    """
    Build a prioritized field action plan from a completed simulation map.

    The planner intentionally stays at the operational level: inspect,
    confirm, contain, sanitize, bag, or apply approved targeted control. It
    does not choose pesticide products, rates, or spray intervals; that belongs
    to the separate pesticide-treatment workflow.
    """
    if thresholds is None:
        thresholds = ZoneThresholds()

    max_targets = max(int(max_targets or 0), 1)
    features = _collect_risk_features(risk_geojson, thresholds)
    if not features:
        return []

    protected_watch = [
        feature for feature in features
        if feature.state == "bagged" and feature.zone != DecisionZone.NO_ACTION
    ]
    actionable_features = [
        feature for feature in features
        if feature.state != "bagged"
    ]
    critical = [
        feature for feature in actionable_features
        if feature.zone == DecisionZone.CRITICAL
    ]
    monitor = [
        feature for feature in actionable_features
        if feature.zone == DecisionZone.MONITOR
    ]
    safe = [
        feature for feature in actionable_features
        if feature.zone == DecisionZone.NO_ACTION
    ]
    pest_label = _pest_label(pest_type)
    stage_text = (
        str(orchard_stage).replace("_", " ").title()
        if orchard_stage
        else "current stage"
    )

    items: List[ActionPlanItem] = []

    if critical:
        critical_sorted = sorted(critical, key=lambda item: item.risk, reverse=True)
        max_risk = critical_sorted[0].risk
        priority = "Urgent" if max_risk >= 0.85 or len(critical) >= 10 else "High"
        items.append(
            ActionPlanItem(
                priority=priority,
                action_type="targeted_control",
                title="Confirm and contain critical-risk trees",
                timing="Today / next field round",
                zone=DecisionZone.CRITICAL,
                target_count=len(critical),
                max_risk=max_risk,
                scope_label=_scope_label(critical_sorted),
                rationale=(
                    f"{len(critical)} active tree/cell(s) reached the critical "
                    f"risk threshold for {pest_label} during {stage_text}."
                ),
                recommended_steps=_critical_steps(pest_type),
                tree_ids=_dedupe_tree_ids(critical_sorted, max_targets),
                cells=_target_cells(critical_sorted, max_targets),
            )
        )

    if monitor:
        monitor_sorted = sorted(monitor, key=lambda item: item.risk, reverse=True)
        max_risk = monitor_sorted[0].risk
        priority = "High" if not critical else "Medium"
        timing = "Within 24 hours" if not critical else "After critical trees are checked"
        items.append(
            ActionPlanItem(
                priority=priority,
                action_type="inspection",
                title="Inspect early-warning trees",
                timing=timing,
                zone=DecisionZone.MONITOR,
                target_count=len(monitor),
                max_risk=max_risk,
                scope_label=_scope_label(monitor_sorted),
                rationale=(
                    f"{len(monitor)} active tree/cell(s) are below the critical "
                    f"threshold but high enough to justify inspection."
                ),
                recommended_steps=_monitor_steps(pest_type),
                tree_ids=_dedupe_tree_ids(monitor_sorted, max_targets),
                cells=_target_cells(monitor_sorted, max_targets),
            )
        )

    if protected_watch:
        protected_sorted = sorted(protected_watch, key=lambda item: item.risk, reverse=True)
        max_risk = protected_sorted[0].risk
        protected_zone = protected_sorted[0].zone
        items.append(
            ActionPlanItem(
                priority="Medium",
                action_type="protection_check",
                title="Verify protected flagged trees",
                timing="During the next field round",
                zone=protected_zone,
                target_count=len(protected_watch),
                max_risk=max_risk,
                scope_label=_scope_label(protected_sorted),
                rationale=(
                    f"{len(protected_watch)} protected tree/cell(s) still show "
                    "monitoring or critical risk and should be checked for bagging integrity."
                ),
                recommended_steps=_protected_steps(),
                tree_ids=_dedupe_tree_ids(protected_sorted, max_targets),
                cells=_target_cells(protected_sorted, max_targets),
            )
        )

    if not critical and not monitor and not protected_watch:
        safe_sorted = sorted(safe, key=lambda item: item.risk, reverse=True)
        max_risk = safe_sorted[0].risk if safe_sorted else 0.0
        items.append(
            ActionPlanItem(
                priority="Routine",
                action_type="routine_monitoring",
                title="Continue routine scouting",
                timing="Next regular scouting round",
                zone=DecisionZone.NO_ACTION,
                target_count=len(safe),
                max_risk=max_risk,
                scope_label=_scope_label(safe_sorted),
                rationale=(
                    f"No active tree/cell reached the monitoring threshold for {pest_label}."
                ),
                recommended_steps=_routine_steps(pest_type),
                tree_ids=_dedupe_tree_ids(safe_sorted, max_targets),
                cells=_target_cells(safe_sorted, max_targets),
            )
        )

    return items


def format_action_plan(items: Sequence[ActionPlanItem]) -> List[Dict[str, Any]]:
    """Format action-plan items as plain dictionaries."""
    return [item.as_dict() for item in items]


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
