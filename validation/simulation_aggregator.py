"""
MangoPoint Validation — Simulation Output Aggregator
=====================================================
Converts tree-level simulation outputs into metrics comparable to BPI monitoring data.

This module is a **non-invasive extension** that reads existing simulation outputs
and aggregates them into quantifiable metrics similar to the BPI dataset:
  - Percentage of infested trees per time period
  - Total infected trees count
  - Rate of infestation spread (R-spread)
  - Estimated pest density per area

The aggregator does NOT modify the simulation engine or its algorithms.
It simply reads the SimulationResult snapshots and computes derived metrics.

Usage Example
-------------
    from core.simulation_engine import SimulationEngine
    from validation.simulation_aggregator import SimulationAggregator
    
    # Run existing simulation
    result = engine.run()
    
    # Aggregate into BPI-comparable metrics
    aggregator = SimulationAggregator(result)
    metrics = aggregator.compute_all_metrics()
    
    # Get specific metrics
    infestation_pct = aggregator.get_infestation_percentage()
    spread_rate = aggregator.get_spread_rate()
    density = aggregator.get_pest_density()
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from core.simulation_engine import SimulationResult


@dataclass
class InfestationMetrics:
    """
    Time-series of infestation metrics from a simulation run.
    
    All metrics are computed per timestep and can be aggregated to
    daily, hourly, or custom time periods for comparison with BPI data.
    
    Attributes
    ----------
    timesteps : list[int]
        Timestep indices
    datetimes : list[datetime]
        Datetime for each timestep
    n_total_trees : int
        Total number of trees in the simulation (constant)
    n_infested_per_step : list[int]
        Number of infested trees at each timestep
    n_new_infested_per_step : list[int]
        Number of newly infested trees at each timestep
    infestation_pct_per_step : list[float]
        Percentage of infested trees at each timestep
    cumulative_spread : list[int]
        Cumulative count of infections over time
    """
    timesteps: List[int] = field(default_factory=list)
    datetimes: List[datetime] = field(default_factory=list)
    n_total_trees: int = 0
    n_infested_per_step: List[int] = field(default_factory=list)
    n_new_infested_per_step: List[int] = field(default_factory=list)
    infestation_pct_per_step: List[float] = field(default_factory=list)
    cumulative_spread: List[int] = field(default_factory=list)
    
    # Derived statistics
    peak_infestation_pct: float = 0.0
    peak_timestep: int = 0
    final_infestation_pct: float = 0.0
    total_new_infections: int = 0
    mean_spread_rate: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            "n_total_trees": self.n_total_trees,
            "n_timesteps": len(self.timesteps),
            "peak_infestation_pct": self.peak_infestation_pct,
            "peak_timestep": self.peak_timestep,
            "final_infestation_pct": self.final_infestation_pct,
            "total_new_infections": self.total_new_infections,
            "mean_spread_rate": self.mean_spread_rate,
        }


@dataclass
class SpreadRateMetrics:
    """
    Metrics quantifying the rate of pest spread in the simulation.
    
    Attributes
    ----------
    instantaneous_rate : list[float]
        New infections per timestep
    rolling_rate_3h : list[float]
        3-hour rolling average of spread rate
    rolling_rate_6h : list[float]
        6-hour rolling average of spread rate
    r_effective : float
        Effective reproduction number (avg new infections per infected tree)
    spread_velocity : float
        Approximate spread velocity in cells/hour
    doubling_time_hours : float
        Estimated time for infestation to double (if applicable)
    """
    instantaneous_rate: List[float] = field(default_factory=list)
    rolling_rate_3h: List[float] = field(default_factory=list)
    rolling_rate_6h: List[float] = field(default_factory=list)
    r_effective: float = 0.0
    spread_velocity: float = 0.0
    doubling_time_hours: float = float('inf')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "r_effective": self.r_effective,
            "spread_velocity_cells_per_hour": self.spread_velocity,
            "doubling_time_hours": self.doubling_time_hours,
            "max_instantaneous_rate": max(self.instantaneous_rate) if self.instantaneous_rate else 0,
            "mean_instantaneous_rate": np.mean(self.instantaneous_rate) if self.instantaneous_rate else 0,
        }


@dataclass
class DensityMetrics:
    """
    Pest density metrics per unit area.
    
    Converts simulation tree counts to area-based densities for
    comparison with BPI's per-hectare monitoring data.
    
    Attributes
    ----------
    total_area_m2 : float
        Total simulation area in square meters
    total_area_ha : float
        Total simulation area in hectares
    infested_area_m2 : float
        Area covered by infested trees
    infested_trees_per_ha : float
        Number of infested trees per hectare
    infestation_density : float
        Infested trees / total trees per unit area
    cluster_density : float
        Number of infestation clusters per hectare
    """
    total_area_m2: float = 0.0
    total_area_ha: float = 0.0
    infested_area_m2: float = 0.0
    infested_trees_per_ha: float = 0.0
    infestation_density: float = 0.0
    cluster_density: float = 0.0
    n_clusters: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_area_ha": self.total_area_ha,
            "infested_trees_per_ha": self.infested_trees_per_ha,
            "infestation_density": self.infestation_density,
            "cluster_density": self.cluster_density,
            "n_clusters": self.n_clusters,
        }


@dataclass
class AggregatedMetrics:
    """
    Complete set of aggregated metrics from a simulation run.
    
    Combines infestation, spread rate, and density metrics into
    a single container for BPI comparison analysis.
    """
    infestation: InfestationMetrics = field(default_factory=InfestationMetrics)
    spread_rate: SpreadRateMetrics = field(default_factory=SpreadRateMetrics)
    density: DensityMetrics = field(default_factory=DensityMetrics)
    
    # Metadata
    simulation_hours: int = 0
    grid_shape: Tuple[int, int] = (0, 0)
    cell_size_m: float = 5.0
    computed_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert complete metrics to dictionary."""
        return {
            "metadata": {
                "simulation_hours": self.simulation_hours,
                "grid_shape": list(self.grid_shape),
                "cell_size_m": self.cell_size_m,
                "computed_at": self.computed_at.isoformat(),
            },
            "infestation": self.infestation.to_dict(),
            "spread_rate": self.spread_rate.to_dict(),
            "density": self.density.to_dict(),
        }
    
    def get_bpi_comparable_summary(self) -> Dict[str, float]:
        """
        Get metrics in a format directly comparable to BPI monitoring data.
        
        Returns
        -------
        dict
            Keys align with BPI dataset columns:
            - 'infestation_pct': Comparable to cecid_fly_infestation_pct
            - 'estimated_cptd': Estimated catch per trap per day (for fruit fly)
            - 'trees_per_ha': Infested trees per hectare
            - 'spread_rate': Rate of spread (for trend analysis)
        """
        return {
            "infestation_pct": self.infestation.final_infestation_pct,
            "peak_infestation_pct": self.infestation.peak_infestation_pct,
            "total_infested_trees": self.infestation.n_infested_per_step[-1] if self.infestation.n_infested_per_step else 0,
            "trees_per_ha": self.density.infested_trees_per_ha,
            "r_effective": self.spread_rate.r_effective,
            "spread_velocity": self.spread_rate.spread_velocity,
        }


class SimulationAggregator:
    """
    Aggregates simulation output into BPI-comparable metrics.
    
    This class reads the SimulationResult object (without modifying it)
    and computes derived metrics that can be compared to BPI monitoring data.
    
    The aggregator supports:
    1. Time-series infestation metrics (per timestep and aggregated)
    2. Spread rate calculations (R-effective, velocity, doubling time)
    3. Spatial density metrics (per hectare, clustering analysis)
    4. BPI-compatible summary metrics for direct comparison
    
    Usage
    -----
        from validation.simulation_aggregator import SimulationAggregator
        
        # From simulation result
        aggregator = SimulationAggregator(simulation_result)
        metrics = aggregator.compute_all_metrics()
        
        # Get BPI-comparable summary
        bpi_metrics = metrics.get_bpi_comparable_summary()
    """
    
    def __init__(
        self,
        simulation_result: "SimulationResult",
        cell_size_m: float = 5.0,
    ):
        """
        Initialize the aggregator with a simulation result.
        
        Parameters
        ----------
        simulation_result : SimulationResult
            The result from SimulationEngine.run()
        cell_size_m : float
            Size of each grid cell in meters (default: 5.0)
        """
        self.result = simulation_result
        self.cell_size_m = cell_size_m
        self._metrics: Optional[AggregatedMetrics] = None
    
    def compute_all_metrics(self) -> AggregatedMetrics:
        """
        Compute all metrics from the simulation result.
        
        Returns
        -------
        AggregatedMetrics
            Complete set of aggregated metrics
        """
        if self._metrics is not None:
            return self._metrics
        
        # Get grid dimensions
        if self.result.snapshots:
            grid_shape = self.result.snapshots[0]["state"].shape
        elif self.result.grid is not None:
            grid_shape = (self.result.grid.rows, self.result.grid.cols)
        else:
            raise ValueError("Simulation result has no snapshots or grid")
        
        # Compute each metric category
        infestation = self._compute_infestation_metrics(grid_shape)
        spread_rate = self._compute_spread_rate_metrics(infestation)
        density = self._compute_density_metrics(grid_shape)
        
        self._metrics = AggregatedMetrics(
            infestation=infestation,
            spread_rate=spread_rate,
            density=density,
            simulation_hours=len(self.result.snapshots),
            grid_shape=grid_shape,
            cell_size_m=self.cell_size_m,
        )
        
        return self._metrics
    
    def _compute_infestation_metrics(
        self,
        grid_shape: Tuple[int, int],
    ) -> InfestationMetrics:
        """Compute time-series infestation metrics."""
        metrics = InfestationMetrics()
        
        from core.config import CellState
        
        # Count total trees (non-empty cells in first snapshot)
        if self.result.snapshots:
            first_state = self.result.snapshots[0]["state"]
            n_total = int(np.sum(first_state != CellState.EMPTY))
        else:
            n_total = grid_shape[0] * grid_shape[1]
        
        metrics.n_total_trees = n_total
        
        # Process each snapshot
        prev_infested = 0
        cumulative = 0
        peak_pct = 0.0
        peak_step = 0
        
        for snapshot in self.result.snapshots:
            step = snapshot["timestep"]
            dt = snapshot["datetime"]
            n_infested = snapshot["n_infested"]
            n_new = snapshot["n_new"]
            
            # Calculate percentage
            pct = (n_infested / n_total * 100) if n_total > 0 else 0.0
            
            # Track cumulative spread
            cumulative += n_new
            
            # Record metrics
            metrics.timesteps.append(step)
            metrics.datetimes.append(dt)
            metrics.n_infested_per_step.append(n_infested)
            metrics.n_new_infested_per_step.append(n_new)
            metrics.infestation_pct_per_step.append(pct)
            metrics.cumulative_spread.append(cumulative)
            
            # Track peak
            if pct > peak_pct:
                peak_pct = pct
                peak_step = step
            
            prev_infested = n_infested
        
        # Compute summary statistics
        metrics.peak_infestation_pct = peak_pct
        metrics.peak_timestep = peak_step
        metrics.final_infestation_pct = metrics.infestation_pct_per_step[-1] if metrics.infestation_pct_per_step else 0.0
        metrics.total_new_infections = cumulative
        
        # Mean spread rate (infections per hour)
        n_steps = len(metrics.timesteps)
        if n_steps > 1:
            metrics.mean_spread_rate = cumulative / n_steps
        
        return metrics
    
    def _compute_spread_rate_metrics(
        self,
        infestation: InfestationMetrics,
    ) -> SpreadRateMetrics:
        """Compute spread rate metrics."""
        metrics = SpreadRateMetrics()
        
        # Instantaneous rate = new infections per timestep
        metrics.instantaneous_rate = [
            float(n) for n in infestation.n_new_infested_per_step
        ]
        
        # Rolling averages
        rates = np.array(metrics.instantaneous_rate)
        n = len(rates)
        
        if n >= 3:
            metrics.rolling_rate_3h = list(
                np.convolve(rates, np.ones(3)/3, mode='valid')
            )
        if n >= 6:
            metrics.rolling_rate_6h = list(
                np.convolve(rates, np.ones(6)/6, mode='valid')
            )
        
        # Effective reproduction number (R)
        # R = average new infections per currently infected tree
        total_new = sum(infestation.n_new_infested_per_step)
        mean_infested = np.mean(infestation.n_infested_per_step) if infestation.n_infested_per_step else 1
        
        if mean_infested > 0 and n > 0:
            metrics.r_effective = total_new / (mean_infested * n)
        
        # Spread velocity (approximate cells/hour)
        # Based on spatial expansion rate
        if len(infestation.n_infested_per_step) >= 2:
            initial = infestation.n_infested_per_step[0]
            final = infestation.n_infested_per_step[-1]
            if final > initial and n > 0:
                # Approximate as sqrt of area expansion rate
                expansion_factor = final / max(initial, 1)
                metrics.spread_velocity = math.sqrt(expansion_factor - 1) / n
        
        # Doubling time
        if metrics.r_effective > 1:
            # Simple exponential model: doubling time = ln(2) / ln(R)
            metrics.doubling_time_hours = math.log(2) / math.log(metrics.r_effective)
        elif total_new > 0 and infestation.n_infested_per_step:
            # Alternative: based on observed growth
            initial = max(infestation.n_infested_per_step[0], 1)
            final = infestation.n_infested_per_step[-1]
            if final > initial * 2:
                growth_rate = math.log(final / initial) / n
                if growth_rate > 0:
                    metrics.doubling_time_hours = math.log(2) / growth_rate
        
        return metrics
    
    def _compute_density_metrics(
        self,
        grid_shape: Tuple[int, int],
    ) -> DensityMetrics:
        """Compute spatial density metrics."""
        metrics = DensityMetrics()
        
        # Calculate area
        rows, cols = grid_shape
        area_m2 = rows * cols * (self.cell_size_m ** 2)
        area_ha = area_m2 / 10000  # 1 hectare = 10,000 m²
        
        metrics.total_area_m2 = area_m2
        metrics.total_area_ha = area_ha
        
        # Get final state
        if self.result.grid is not None:
            final_state = self.result.grid.state
            final_infested = self.result.grid.infested_mask
        elif self.result.snapshots:
            final_state = self.result.snapshots[-1]["state"]
            from core.config import CellState
            final_infested = final_state == CellState.INFESTED
        else:
            return metrics
        
        # Count infested cells
        n_infested = int(np.sum(final_infested))
        
        # Infested area
        metrics.infested_area_m2 = n_infested * (self.cell_size_m ** 2)
        
        # Infested trees per hectare
        if area_ha > 0:
            metrics.infested_trees_per_ha = n_infested / area_ha
        
        # Infestation density (fraction of total)
        total_cells = rows * cols
        if total_cells > 0:
            metrics.infestation_density = n_infested / total_cells
        
        # Cluster analysis (using connected components)
        metrics.n_clusters, metrics.cluster_density = self._count_clusters(
            final_infested, area_ha
        )
        
        return metrics
    
    def _count_clusters(
        self,
        infested_mask: np.ndarray,
        area_ha: float,
    ) -> Tuple[int, float]:
        """
        Count infestation clusters using connected components.
        
        A cluster is a group of adjacent infested cells (8-connected).
        """
        try:
            from scipy import ndimage
            labeled, n_clusters = ndimage.label(infested_mask)
            cluster_density = n_clusters / area_ha if area_ha > 0 else 0
            return n_clusters, cluster_density
        except ImportError:
            # Fallback: simple count without scipy
            n_infested = int(np.sum(infested_mask))
            # Estimate clusters as 1 per 5 infested cells (rough approximation)
            n_clusters = max(1, n_infested // 5) if n_infested > 0 else 0
            cluster_density = n_clusters / area_ha if area_ha > 0 else 0
            return n_clusters, cluster_density
    
    # ── Time-period aggregation methods ─────────────────────────
    
    def aggregate_to_hourly(self) -> List[Dict[str, Any]]:
        """
        Aggregate metrics to hourly resolution.
        
        Returns list of hourly summaries.
        """
        metrics = self.compute_all_metrics()
        hourly = []
        
        for i, (step, dt, n_inf, n_new, pct) in enumerate(zip(
            metrics.infestation.timesteps,
            metrics.infestation.datetimes,
            metrics.infestation.n_infested_per_step,
            metrics.infestation.n_new_infested_per_step,
            metrics.infestation.infestation_pct_per_step,
        )):
            hourly.append({
                "hour": i,
                "datetime": dt,
                "n_infested": n_inf,
                "n_new": n_new,
                "infestation_pct": pct,
            })
        
        return hourly
    
    def aggregate_to_daily(self) -> List[Dict[str, Any]]:
        """
        Aggregate metrics to daily resolution.
        
        Returns list of daily summaries (24-hour periods).
        """
        hourly = self.aggregate_to_hourly()
        
        if not hourly:
            return []
        
        daily = []
        day_hours = []
        current_day = 0
        
        for h in hourly:
            day = h["hour"] // 24
            if day != current_day:
                if day_hours:
                    daily.append(self._aggregate_hours(day_hours, current_day))
                day_hours = []
                current_day = day
            day_hours.append(h)
        
        # Don't forget last day
        if day_hours:
            daily.append(self._aggregate_hours(day_hours, current_day))
        
        return daily
    
    def _aggregate_hours(
        self,
        hours: List[Dict[str, Any]],
        day: int,
    ) -> Dict[str, Any]:
        """Aggregate a list of hourly records into a daily summary."""
        return {
            "day": day,
            "start_datetime": hours[0]["datetime"],
            "end_datetime": hours[-1]["datetime"],
            "max_infestation_pct": max(h["infestation_pct"] for h in hours),
            "mean_infestation_pct": np.mean([h["infestation_pct"] for h in hours]),
            "final_n_infested": hours[-1]["n_infested"],
            "total_new_infections": sum(h["n_new"] for h in hours),
        }
    
    # ── BPI-comparable output methods ───────────────────────────
    
    def get_infestation_percentage(self) -> float:
        """
        Get final infestation percentage (comparable to BPI cecid_fly_infestation_pct).
        
        Returns
        -------
        float
            Percentage of trees infested (0-100)
        """
        metrics = self.compute_all_metrics()
        return metrics.infestation.final_infestation_pct
    
    def get_total_infested_trees(self) -> int:
        """
        Get total number of infested trees.
        
        Returns
        -------
        int
            Count of infested trees
        """
        metrics = self.compute_all_metrics()
        if metrics.infestation.n_infested_per_step:
            return metrics.infestation.n_infested_per_step[-1]
        return 0
    
    def get_spread_rate(self) -> float:
        """
        Get the effective spread rate (R-effective).
        
        Returns
        -------
        float
            R-effective value (>1 means spreading, <1 means declining)
        """
        metrics = self.compute_all_metrics()
        return metrics.spread_rate.r_effective
    
    def get_pest_density(self) -> float:
        """
        Get infested trees per hectare.
        
        Returns
        -------
        float
            Number of infested trees per hectare
        """
        metrics = self.compute_all_metrics()
        return metrics.density.infested_trees_per_ha
    
    def estimate_cptd(
        self,
        traps_per_ha: float = 2.0,
        capture_efficiency: float = 0.1,
    ) -> float:
        """
        Estimate Catch Per Trap Per Day (CPTD) for fruit fly comparison.
        
        This is a rough estimation based on infestation density.
        BPI uses actual trap catches, so this provides an approximate
        conversion for trend comparison (not absolute values).
        
        Parameters
        ----------
        traps_per_ha : float
            Number of traps per hectare (typical: 2-4)
        capture_efficiency : float
            Fraction of flies captured by traps (typical: 0.05-0.15)
        
        Returns
        -------
        float
            Estimated CPTD value
        """
        metrics = self.compute_all_metrics()
        
        # Simple model: CPTD proportional to infestation density
        # Calibrated to roughly match BPI ranges (0-40 CPTD)
        infestation_pct = metrics.infestation.final_infestation_pct
        
        # Map infestation percentage to CPTD range
        # 0% infestation → ~0 CPTD
        # 100% infestation → ~40 CPTD (peak observed in BPI data)
        estimated_cptd = infestation_pct * 0.4
        
        return estimated_cptd
    
    def get_summary_for_comparison(self) -> Dict[str, Any]:
        """
        Get a summary optimized for comparison with BPI data.
        
        Returns
        -------
        dict
            Summary with keys matching BPI analysis needs
        """
        metrics = self.compute_all_metrics()
        
        return {
            # Direct BPI-comparable metrics
            "infestation_pct": metrics.infestation.final_infestation_pct,
            "estimated_cptd": self.estimate_cptd(),
            
            # Additional context
            "peak_infestation_pct": metrics.infestation.peak_infestation_pct,
            "peak_timestep": metrics.infestation.peak_timestep,
            "total_new_infections": metrics.infestation.total_new_infections,
            "mean_spread_rate_per_hour": metrics.infestation.mean_spread_rate,
            
            # Spread metrics
            "r_effective": metrics.spread_rate.r_effective,
            "spread_velocity": metrics.spread_rate.spread_velocity,
            "doubling_time_hours": metrics.spread_rate.doubling_time_hours,
            
            # Density metrics
            "trees_per_ha": metrics.density.infested_trees_per_ha,
            "n_clusters": metrics.density.n_clusters,
            "cluster_density": metrics.density.cluster_density,
            
            # Metadata
            "simulation_hours": metrics.simulation_hours,
            "total_trees": metrics.infestation.n_total_trees,
            "final_infested_trees": self.get_total_infested_trees(),
        }
