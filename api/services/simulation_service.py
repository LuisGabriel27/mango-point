"""
MangoPoint API — Simulation Service
=====================================
Orchestrates pest risk simulations using the existing simulation engine.
Provides outputs in GeoJSON format for the REST API.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Type
import uuid
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.datetime_utils import format_rfc3339, utcnow_naive
from ..models.schemas import (
    PestTypeEnum,
    SimulationModeEnum,
    SimulationRequest,
    SimulationResponse,
    TimeSeriesSnapshot,
    TimestepEntry,
    SimulationMetadata,
)

logger = logging.getLogger(__name__)


class SimulationService:
    """
    Service for running pest dispersal simulations.
    
    Wraps the existing SimulationEngine to provide:
    - GeoJSON input/output
    - Time-series snapshots
    - Integration with weather service
    """
    
    def __init__(self):
        # Lazy import simulation modules to avoid circular imports
        self._engine_class: Optional[Type] = None
        self._grid_class: Optional[Type] = None
        self._weather_class: Optional[Type] = None
        self._cecid_gate: Optional[Type] = None
        self._fruit_fly_gate: Optional[Type] = None
        self._cell_state: Optional[Any] = None
        self._orchard_stage_enum: Optional[Any] = None
        self._gates = None
    
    def _load_modules(self):
        """Lazy load simulation modules."""
        if self._engine_class is None:
            try:
                # Import from parent package
                parent_dir = Path(__file__).parent.parent.parent
                sys.path.insert(0, str(parent_dir))
                
                from core.simulation_engine import SimulationEngine, SimulationResult
                from core.grid import OrchardGrid
                from utils.weather import WeatherTimeSeries
                from core.biological_rules import CecidFlyGate, FruitFlyGate
                from core.config import CellState, OrchardStage
                
                self._engine_class = SimulationEngine
                self._grid_class = OrchardGrid
                self._weather_class = WeatherTimeSeries
                self._cecid_gate = CecidFlyGate
                self._fruit_fly_gate = FruitFlyGate
                self._cell_state = CellState
                self._orchard_stage_enum = OrchardStage
                
            except ImportError as e:
                logger.error(f"Failed to import simulation modules: {e}")
                raise

    def _pest_is_active_for_stage(self, pest_type: PestTypeEnum, orchard_stage: str) -> bool:
        """Return whether the selected pest can biologically activate at the given stage."""
        stage = (orchard_stage or "").lower()
        if pest_type == PestTypeEnum.CECID:
            return stage == "fruitlet"
        if pest_type == PestTypeEnum.FRUITFLY:
            return stage == "mature"
        return False

    def _has_manual_infestation_source(self, tree_overrides: Optional[Dict[str, str]]) -> bool:
        """Check whether manual tree overrides already define infested source trees."""
        if not tree_overrides:
            return False
        source_statuses = {"infected", "infested"}
        return any(str(status).lower() in source_statuses for status in tree_overrides.values())

    def _seed_default_infestation(
        self,
        grid,
        pest_type: PestTypeEnum,
        orchard_stage: str,
        random_seed: int,
        tree_overrides: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Auto-seed infestation sources for demo runs when biologically appropriate.

        Returns the number of seeded trees.
        """
        if not self._pest_is_active_for_stage(pest_type, orchard_stage):
            logger.info(
                "Skipping auto-seeding: pest=%s is inactive during stage=%s",
                pest_type.value,
                orchard_stage,
            )
            return 0

        if self._has_manual_infestation_source(tree_overrides):
            logger.info("Skipping auto-seeding: manual infected tree overrides already provided")
            return 0

        tree_cells = list(zip(*np.where(grid.susceptible_mask)))
        if not tree_cells:
            center_r, center_c = grid.rows // 2, grid.cols // 2
            grid.infest(center_r, center_c)
            logger.info("Auto-seeded fallback infestation at center cell (%s, %s)", center_r, center_c)
            return 1

        max_seeds = min(3, len(tree_cells))
        rng = np.random.default_rng(random_seed)
        n_seeds = int(rng.integers(1, max_seeds + 1))
        chosen = rng.choice(len(tree_cells), size=n_seeds, replace=False)
        for idx in np.atleast_1d(chosen):
            sr, sc = tree_cells[int(idx)]
            grid.infest(sr, sc)
            logger.info("Auto-seeded infestation at tree cell (%s, %s)", sr, sc)

        return n_seeds
    
    async def run_simulation(
        self,
        request: SimulationRequest,
        weather_data: Optional[List[Dict[str, Any]]] = None,
    ) -> SimulationResponse:
        """
        Run a pest dispersal simulation.
        
        Parameters
        ----------
        request : SimulationRequest
            Simulation parameters including orchard GeoJSON
        weather_data : list[dict], optional
            Pre-fetched weather forecast data
            
        Returns
        -------
        SimulationResponse
            Complete simulation results with time-series GeoJSON
        """
        self._load_modules()
        
        run_id = f"sim_{uuid.uuid4().hex[:12]}"
        started_at = utcnow_naive()
        
        # Generate random seed for reproducibility
        if request.random_seed is not None:
            random_seed = request.random_seed
        else:
            random_seed = int(np.random.default_rng().integers(0, 2**31))
        
        # Set numpy random seed for reproducibility
        np.random.seed(random_seed)
        
        risk_threshold = request.risk_threshold if hasattr(request, 'risk_threshold') else 0.7
        
        # Get phenology parameters with defaults
        orchard_stage_str = getattr(request, 'orchard_stage', 'mature')
        if hasattr(orchard_stage_str, 'value'):
            orchard_stage_str = orchard_stage_str.value
        days_since_flowering = getattr(request, 'days_since_flowering', 60) or 60
        neighbor_threat = getattr(request, 'neighbor_threat', 0.0) or 0.0
        neighbor_direction = getattr(request, 'neighbor_direction', None)
        if neighbor_direction:
            neighbor_direction = neighbor_direction.strip().upper()
        
        simulation_mode = getattr(request, "simulation_mode", SimulationModeEnum.GRID)
        if hasattr(simulation_mode, "value"):
            simulation_mode = simulation_mode.value

        logger.info(
            "Starting simulation %s: pest=%s, mode=%s, hours=%d, seed=%d, "
            "threshold=%.2f, stage=%s, days_flowering=%d, neighbor_threat=%.2f",
            run_id, request.pest_type, simulation_mode, request.hours,
            random_seed, risk_threshold, orchard_stage_str,
            days_since_flowering, neighbor_threat,
        )

        # ── branch: tree_graph mode ──────────────────────────────
        if simulation_mode == SimulationModeEnum.TREE_GRAPH.value:
            return await self._run_tree_graph_simulation(
                request=request,
                weather_data=weather_data,
                run_id=run_id,
                started_at=started_at,
                random_seed=random_seed,
                risk_threshold=risk_threshold,
                orchard_stage_str=orchard_stage_str,
                days_since_flowering=days_since_flowering,
                neighbor_threat=neighbor_threat,
                neighbor_direction=neighbor_direction,
            )

        try:
            # Create grid from GeoJSON
            grid, origin = self._create_grid_from_geojson(request.orchard_geojson)
            
            # Mark bagged trees
            if request.bagged_tree_ids:
                self._apply_bagging(grid, request.bagged_tree_ids)
            
            # Apply tree status overrides (from Tree Management modal)
            tree_overrides = getattr(request, 'tree_overrides', None)
            if tree_overrides:
                self._apply_tree_overrides(grid, tree_overrides)
            
            # Seed initial infestation
            if request.initial_infestation:
                for pos in request.initial_infestation:
                    r, c = pos.get("row", 0), pos.get("col", 0)
                    if 0 <= r < grid.rows and 0 <= c < grid.cols:
                        grid.infest(r, c)
            else:
                self._seed_default_infestation(
                    grid=grid,
                    pest_type=request.pest_type,
                    orchard_stage=orchard_stage_str,
                    random_seed=random_seed,
                    tree_overrides=tree_overrides,
                )
            
            # Create weather time series
            weather = self._create_weather(weather_data, request.hours)
            
            # Select pest gate based on type
            gates = self._get_gates(request.pest_type)
            
            # Convert orchard stage string to enum
            orchard_stage_map = {
                'dormant': self._orchard_stage_enum.DORMANT,
                'flowering': self._orchard_stage_enum.FLOWERING,
                'fruitlet': self._orchard_stage_enum.FRUITLET,
                'mature': self._orchard_stage_enum.MATURE,
            }
            orchard_stage = orchard_stage_map.get(orchard_stage_str, self._orchard_stage_enum.MATURE)
            
            # Apply neighbor threat — directional gradient when direction is given,
            # uniform otherwise (preserves original behaviour for existing callers).
            if neighbor_threat > 0:
                from core.config import DIRECTION_BEARING_MAP
                if neighbor_direction and neighbor_direction in DIRECTION_BEARING_MAP:
                    grid.set_neighbor_threat_directional(neighbor_direction, neighbor_threat)
                    grid.neighbor_bearing = DIRECTION_BEARING_MAP[neighbor_direction]
                    logger.info(
                        "Directional neighbor threat: direction=%s, bearing=%.0f°, threat=%.2f",
                        neighbor_direction, grid.neighbor_bearing, neighbor_threat,
                    )
                else:
                    grid.set_neighbor_threat_uniform(neighbor_threat)
            
            # Run simulation with phenology parameters
            assert self._engine_class is not None, "Modules not loaded"
            initial_rain_history = getattr(request, "manual_weather_prefix_rain", None)
            engine = self._engine_class(
                grid=grid,
                weather=weather,
                transition_mode="stochastic",
                gates=gates,
                orchard_stage=orchard_stage,
                days_since_flowering=days_since_flowering,
                initial_rainfall_history=initial_rain_history,
            )
            
            result = engine.run(n_steps=request.hours, progress=False)
            
            completed_at = utcnow_naive()
            duration = (completed_at - started_at).total_seconds()
            
            # Convert to time-series GeoJSON
            time_series = self._result_to_time_series(result, origin)
            
            # Final risk GeoJSON
            risk_geojson = self._grid_to_geojson(
                result.grid, 
                result.snapshots[-1]["risk"],
                origin,
            )
            
            # Calculate summary statistics
            peak_risk = float(result.risk_series.max())
            cells_at_risk = int((result.risk_series[-1] > risk_threshold).sum())
            n_infested_final = int(result.grid.infested_mask.sum())
            
            # Build timesteps array for research format
            timesteps = [
                TimestepEntry(
                    hour=ts.hour,
                    geojson=ts.risk_geojson,
                )
                for ts in time_series
            ]
            
            # Build metadata block
            metadata = SimulationMetadata(
                run_id=run_id,
                pest_type=request.pest_type.value,
                hours=request.hours,
                random_seed=random_seed,
                started_at=format_rfc3339(started_at),
                completed_at=format_rfc3339(completed_at),
                duration_seconds=duration,
                peak_risk=peak_risk,
                cells_at_risk=cells_at_risk,
                n_infested_final=n_infested_final,
                risk_threshold=risk_threshold,
                orchard_stage=orchard_stage_str,
                days_since_flowering=days_since_flowering,
                sugar_index=engine.sugar_index,
                neighbor_threat=neighbor_threat,
                simulation_mode="grid",
                neighbor_direction=neighbor_direction,
            )
            
            logger.info(
                f"Simulation {run_id} completed in {duration:.2f}s: "
                f"peak_risk={peak_risk:.2f}, cells_at_risk={cells_at_risk}, seed={random_seed}"
            )
            
            return SimulationResponse(
                run_id=run_id,
                pest_type=request.pest_type,
                hours=request.hours,
                started_at=format_rfc3339(started_at),
                completed_at=format_rfc3339(completed_at),
                status="completed",
                peak_risk=peak_risk,
                cells_at_risk=cells_at_risk,
                n_infested_final=n_infested_final,
                random_seed=random_seed,
                risk_threshold=risk_threshold,
                metadata=metadata,
                time_series=time_series,
                timesteps=timesteps,
                risk_geojson=risk_geojson,
            )
            
        except Exception as e:
            logger.error(f"Simulation {run_id} failed: {e}")
            raise
    
    def _create_grid_from_geojson(
        self,
        geojson: Dict[str, Any],
    ) -> Tuple[Any, Tuple[float, float]]:
        """Create an OrchardGrid from input GeoJSON (supports Point and Polygon features)."""
        import geopandas as gpd
        from shapely.geometry import shape, Point as ShapelyPoint
        
        # Extract features
        features = geojson.get("features", [])
        if not features:
            # If it's just a geometry, wrap it
            if "coordinates" in geojson:
                features = [{"type": "Feature", "geometry": geojson, "properties": {}}]
        
        # Detect geometry types
        geom_types = {f["geometry"]["type"] for f in features if "geometry" in f}
        is_point_data = geom_types <= {"Point", "MultiPoint"}
        
        # Create GeoDataFrame
        geometries = [shape(f["geometry"]) for f in features]
        properties = [f.get("properties", {}) for f in features]
        gdf = gpd.GeoDataFrame(properties, geometry=geometries, crs="EPSG:4326")
        
        # Get bounds
        bounds = gdf.total_bounds  # (minx, miny, maxx, maxy)
        origin_lon, origin_lat = bounds[0], bounds[1]
        max_lon, max_lat = bounds[2], bounds[3]
        
        # Calculate grid dimensions
        cell_size_m = 5.0   # meters per cell (small enough for individual trees)
        m_lat = 111_132.0
        m_lon = 111_132.0 * np.cos(np.radians((origin_lat + max_lat) / 2))
        
        cols = int(np.ceil((max_lon - origin_lon) * m_lon / cell_size_m)) + 4
        rows = int(np.ceil((max_lat - origin_lat) * m_lat / cell_size_m)) + 4
        
        # Ensure minimum size
        rows = max(rows, 10)
        cols = max(cols, 10)
        
        # Create grid
        assert self._grid_class is not None, "Modules not loaded"
        grid = self._grid_class(rows, cols, cell_size_m)
        grid.origin_lon = origin_lon - 2 * cell_size_m / m_lon
        grid.origin_lat = origin_lat - 2 * cell_size_m / m_lat
        
        assert self._cell_state is not None
        
        if is_point_data:
            # Point features → place each tree on the grid
            from spatial.gis_utils import lonlat_to_grid
            for idx, row in gdf.iterrows():
                lon, lat = row.geometry.x, row.geometry.y
                r, c = lonlat_to_grid(
                    lon, lat, grid.origin_lon, grid.origin_lat,
                    cell_size_m, m_lat, m_lon,
                )
                if 0 <= r < grid.rows and 0 <= c < grid.cols:
                    grid.set_state(r, c, self._cell_state.UNBAGGED)
                    # Store tree ID if available
                    tree_id = row.get("Tree_ID") or row.get("tree_id") or row.get("fid")
                    if tree_id is not None:
                        grid.tree_ids[r, c] = str(tree_id)
        else:
            # Polygon features → rasterize boundary
            farm_poly = gdf.union_all()
            for r in range(grid.rows):
                for c in range(grid.cols):
                    lon = grid.origin_lon + (c + 0.5) * cell_size_m / m_lon
                    lat = grid.origin_lat + (r + 0.5) * cell_size_m / m_lat
                    if farm_poly.contains(ShapelyPoint(lon, lat)):
                        grid.set_state(r, c, self._cell_state.UNBAGGED)
        
        return grid, (origin_lon, origin_lat)
    
    def _apply_bagging(self, grid, bagged_tree_ids: List[str]) -> None:
        """Mark specified trees as bagged."""
        assert self._cell_state is not None, "Modules not loaded"
        bagged_set = set(bagged_tree_ids)
        
        for r in range(grid.rows):
            for c in range(grid.cols):
                if grid.tree_ids[r, c] in bagged_set:
                    if grid.state[r, c] == self._cell_state.UNBAGGED:
                        grid.state[r, c] = self._cell_state.BAGGED
    
    def _apply_tree_overrides(self, grid, tree_overrides: Dict[str, str]) -> None:
        """Apply manual tree status overrides from Tree Management modal.
        
        Parameters
        ----------
        grid : OrchardGrid
            The grid to modify
        tree_overrides : dict
            Dict mapping tree_id (str) -> status (str)
            Valid statuses: healthy, infected, bagged, dead, history_infected, suspect
        """
        assert self._cell_state is not None, "Modules not loaded"
        
        # Map status strings to CellState values
        status_map = {
            'healthy': self._cell_state.UNBAGGED,
            'unbagged': self._cell_state.UNBAGGED,
            'infected': self._cell_state.INFESTED,
            'infested': self._cell_state.INFESTED,
            'bagged': self._cell_state.BAGGED,
            'dead': self._cell_state.DEAD,
            'history_infected': self._cell_state.HISTORY_INFECTED,
            'suspect': self._cell_state.SUSPECT,
        }
        
        for r in range(grid.rows):
            for c in range(grid.cols):
                tree_id = str(grid.tree_ids[r, c])
                if tree_id in tree_overrides:
                    new_status = tree_overrides[tree_id].lower()
                    if new_status in status_map:
                        grid.state[r, c] = status_map[new_status]
                        logger.info(f"Tree {tree_id} at ({r},{c}) set to {new_status}")
    
    def _create_weather(
        self,
        weather_data: Optional[List[Dict[str, Any]]],
        hours: int,
    ) -> Any:
        """Create WeatherTimeSeries from data or generate synthetic."""
        import pandas as pd
        
        assert self._weather_class is not None, "Modules not loaded"
        if weather_data and len(weather_data) >= hours:
            # Use provided weather data
            df = pd.DataFrame(weather_data)
            df["datetime"] = pd.to_datetime(df["datetime"])
            # Rename column to match WeatherTimeSeries expected format
            if "wind_direction_deg" in df.columns and "wind_dir_deg" not in df.columns:
                df = df.rename(columns={"wind_direction_deg": "wind_dir_deg"})
            return self._weather_class.from_dataframe(df)
        else:
            # Generate synthetic weather
            return self._weather_class.synthetic(hours=hours)
    
    def _get_gates(self, pest_type: PestTypeEnum) -> list:
        """Get appropriate dispersal gates for pest type.
        
        Always includes both gates for realistic spread modelling.
        The selected pest_type is listed first (primary agent).
        """
        assert self._cecid_gate is not None and self._fruit_fly_gate is not None, "Modules not loaded"
        if pest_type == PestTypeEnum.CECID:
            return [self._cecid_gate(), self._fruit_fly_gate()]
        elif pest_type == PestTypeEnum.FRUITFLY:
            return [self._fruit_fly_gate(), self._cecid_gate()]
        else:
            return [self._cecid_gate(), self._fruit_fly_gate()]
    
    def _result_to_time_series(
        self,
        result,
        origin: Tuple[float, float],
    ) -> List[TimeSeriesSnapshot]:
        """Convert simulation result to time-series snapshots."""
        time_series = []
        
        # Sample snapshots — include first, last, and intermediate steps
        total = len(result)
        n_samples = min(total, 12)
        step_size = max(1, total // n_samples)
        
        for i in range(0, total, step_size):
            snap = result.snapshots[i]
            
            # Create GeoJSON for this timestep (use snapshot state, not final)
            risk_geojson = self._grid_to_geojson(
                result.grid,
                snap["risk"],
                origin,
                state_override=snap["state"],
            )
            
            dt = snap["datetime"]
            dt_str = format_rfc3339(dt) if hasattr(dt, "isoformat") else str(dt)
            
            time_series.append(TimeSeriesSnapshot(
                timestep=snap["timestep"],
                datetime=dt_str,
                hour=snap["hour"],
                risk_geojson=risk_geojson,
                n_infested=snap["n_infested"],
                n_new=snap["n_new"],
                weather={
                    "wind_speed_ms": snap["weather"]["wind_speed_ms"],
                    "wind_dir_deg": snap["weather"]["wind_dir_deg"],
                    "temperature_c": snap["weather"]["temperature_c"],
                },
            ))
        
        # Always include final snapshot
        if len(result) - 1 not in range(0, len(result), step_size):
            final = result.snapshots[-1]
            dt = final["datetime"]
            dt_str = format_rfc3339(dt) if hasattr(dt, "isoformat") else str(dt)
            
            time_series.append(TimeSeriesSnapshot(
                timestep=final["timestep"],
                datetime=dt_str,
                hour=final["hour"],
                risk_geojson=self._grid_to_geojson(result.grid, final["risk"], origin, state_override=final["state"]),
                n_infested=final["n_infested"],
                n_new=final["n_new"],
                weather={
                    "wind_speed_ms": final["weather"]["wind_speed_ms"],
                    "wind_dir_deg": final["weather"]["wind_dir_deg"],
                    "temperature_c": final["weather"]["temperature_c"],
                },
            ))
        
        return time_series
    
    def _grid_to_geojson(
        self,
        grid,
        risk: np.ndarray,
        origin: Tuple[float, float],
        state_override: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Convert grid risk to GeoJSON FeatureCollection.
        
        Parameters
        ----------
        state_override : optional 2-D array
            If provided, use this state array instead of grid.state.
            Used for time-series snapshots where the state differs from
            the final grid state.
        """
        cell_size_m = grid.cell_size_m
        m_lat = 111_132.0
        m_lon = 111_132.0 * np.cos(np.radians(grid.origin_lat + grid.rows * cell_size_m / m_lat / 2))
        
        state = state_override if state_override is not None else grid.state
        
        features = []
        assert self._cell_state is not None, "Modules not loaded"
        
        for r in range(grid.rows):
            for c in range(grid.cols):
                if state[r, c] == self._cell_state.EMPTY:
                    continue
                
                # Calculate cell bounds
                lon_min = grid.origin_lon + c * cell_size_m / m_lon
                lon_max = grid.origin_lon + (c + 1) * cell_size_m / m_lon
                lat_min = grid.origin_lat + r * cell_size_m / m_lat
                lat_max = grid.origin_lat + (r + 1) * cell_size_m / m_lat
                
                # Cell state
                state_name = self._cell_state(state[r, c]).name.lower()
                
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [lon_min, lat_min],
                            [lon_max, lat_min],
                            [lon_max, lat_max],
                            [lon_min, lat_max],
                            [lon_min, lat_min],
                        ]],
                    },
                    "properties": {
                        "row": r,
                        "col": c,
                        "risk": float(risk[r, c]),
                        "state": state_name,
                        "tree_id": str(grid.tree_ids[r, c]) if grid.tree_ids[r, c] else None,
                    },
                }
                features.append(feature)
        
        return {
            "type": "FeatureCollection",
            "features": features,
        }


    # ════════════════════════════════════════════════════════════
    #  tree_graph mode — private implementation
    # ════════════════════════════════════════════════════════════

    async def _run_tree_graph_simulation(
        self,
        request: SimulationRequest,
        weather_data: Optional[List[Dict[str, Any]]],
        run_id: str,
        started_at,
        random_seed: int,
        risk_threshold: float,
        orchard_stage_str: str,
        days_since_flowering: int,
        neighbor_threat: float,
        neighbor_direction: Optional[str] = None,
    ) -> SimulationResponse:
        """Execute the crown-aware tree-graph simulation."""
        self._load_modules()

        try:
            from core.tree_graph_model import (
                TreeGraphEngine,
                TreeState,
                build_tree_graph_from_lonlat,
            )
            from core.config import (
                TG_ALPHA,
                TG_BETA,
                TG_DEFAULT_CROWN_RADIUS_M,
                TG_LAMBDA0,
                TG_MAX_NEIGHBOR_DIST_M,
                TG_WIND_BIAS,
            )
        except ImportError as exc:
            logger.error("Failed to import tree_graph modules: %s", exc)
            raise

        # ── resolve per-run constants (request overrides env defaults) ───
        lambda0 = float(request.tg_lambda0 or TG_LAMBDA0)
        alpha   = float(request.tg_alpha   or TG_ALPHA)
        beta    = float(request.tg_beta    or TG_BETA)
        wind_bias = float(request.tg_wind_bias or TG_WIND_BIAS)
        max_dist  = float(request.tg_max_neighbor_dist_m or TG_MAX_NEIGHBOR_DIST_M)
        crown_fallback = float(request.crown_radius_m or TG_DEFAULT_CROWN_RADIUS_M)

        logger.info(
            "tree_graph params: lambda0=%.3f, alpha=%.3f, beta=%.3f, "
            "wind_bias=%.3f, max_dist=%.1f m, crown_fallback=%.2f m",
            lambda0, alpha, beta, wind_bias, max_dist, crown_fallback,
        )

        # ── build graph from GeoJSON ──────────────────────────────
        geojson = request.orchard_geojson
        features = geojson.get("features", [])
        point_features = [
            f for f in features
            if f.get("geometry", {}).get("type") == "Point"
        ]
        if not point_features:
            raise ValueError(
                "tree_graph mode requires Point features in orchard_geojson. "
                "Polygon-only GeoJSON is not supported in this mode."
            )

        # Derive bounding box and metre-per-degree scale (same as grid mode)
        lons = [f["geometry"]["coordinates"][0] for f in point_features]
        lats = [f["geometry"]["coordinates"][1] for f in point_features]
        origin_lon = min(lons)
        origin_lat = min(lats)
        mid_lat = (origin_lat + max(lats)) / 2.0
        m_lat = 111_132.0
        m_lon = 111_132.0 * np.cos(np.radians(mid_lat))

        graph = build_tree_graph_from_lonlat(
            features=point_features,
            origin_lon=origin_lon,
            origin_lat=origin_lat,
            m_lat=m_lat,
            m_lon=m_lon,
            default_crown_radius=crown_fallback,
            max_dist=max_dist,
            bagged_ids=list(request.bagged_tree_ids or []),
        )

        if not graph.nodes:
            raise ValueError("No valid Point trees found in orchard_geojson.")

        # ── apply tree overrides ──────────────────────────────────
        tree_overrides = getattr(request, "tree_overrides", None) or {}
        if tree_overrides:
            state_map = {
                "healthy": TreeState.SUSCEPTIBLE,
                "unbagged": TreeState.SUSCEPTIBLE,
                "infected": TreeState.INFESTED,
                "infested": TreeState.INFESTED,
                "bagged": TreeState.BAGGED,
                "dead": TreeState.DEAD,
            }
            for node in graph.nodes:
                if node.tree_id in tree_overrides:
                    new_status = tree_overrides[node.tree_id].lower()
                    if new_status in state_map:
                        node.state = state_map[new_status]
                        logger.debug(
                            "tree_graph override: tree %s → %s",
                            node.tree_id, new_status,
                        )

        # ── seed initial infestation ──────────────────────────────
        seed_ids = list(request.initial_infestation_tree_ids or [])
        if seed_ids:
            id_to_node = {n.tree_id: n for n in graph.nodes}
            for tid in seed_ids:
                if tid in id_to_node:
                    id_to_node[tid].state = TreeState.INFESTED
                else:
                    logger.warning(
                        "initial_infestation_tree_id %r not found in graph", tid
                    )
        else:
            # Auto-seed: same logic as grid mode
            n_seeded = self._seed_tree_graph_infestation(
                graph=graph,
                pest_type=request.pest_type,
                orchard_stage=orchard_stage_str,
                random_seed=random_seed,
                tree_overrides=tree_overrides,
            )
            logger.info("tree_graph auto-seeded %d infested tree(s)", n_seeded)

        # ── weather & biological gates ────────────────────────────
        weather = self._create_weather(weather_data, request.hours)
        gates   = self._get_gates(request.pest_type)

        assert self._orchard_stage_enum is not None
        stage_map = {
            "dormant":   self._orchard_stage_enum.DORMANT,
            "flowering": self._orchard_stage_enum.FLOWERING,
            "fruitlet":  self._orchard_stage_enum.FRUITLET,
            "mature":    self._orchard_stage_enum.MATURE,
        }
        orchard_stage = stage_map.get(orchard_stage_str, self._orchard_stage_enum.MATURE)

        # ── run engine ────────────────────────────────────────────
        engine = TreeGraphEngine(
            graph=graph,
            weather=weather,
            transition_mode="stochastic",
            gates=gates,
            orchard_stage=orchard_stage,
            days_since_flowering=days_since_flowering,
            lambda0=lambda0,
            alpha=alpha,
            beta=beta,
            wind_bias=wind_bias,
            pest_type=request.pest_type.value,
            neighbor_threat=neighbor_threat,
            neighbor_direction=neighbor_direction,
            initial_rainfall_history=getattr(request, "manual_weather_prefix_rain", None),
        )
        result = engine.run(n_steps=request.hours, progress=False)

        completed_at = utcnow_naive()
        duration = (completed_at - started_at).total_seconds()

        # ── summary statistics ────────────────────────────────────
        all_final_risks = result.snapshots[-1]["risks"] if result.snapshots else []
        peak_risk = float(max(all_final_risks)) if all_final_risks else 0.0
        cells_at_risk = int(
            sum(1 for r in all_final_risks if r > risk_threshold)
        )
        n_infested_final = result.graph.n_infested() if result.graph else 0

        # ── convert to time-series ────────────────────────────────
        time_series = self._tg_result_to_time_series(result, graph)
        risk_geojson = self._tg_snapshot_to_geojson(
            graph=result.graph or graph,
            states=result.snapshots[-1]["states"] if result.snapshots else [],
            risks=result.snapshots[-1]["risks"] if result.snapshots else [],
        )

        timesteps = [
            TimestepEntry(hour=ts.hour, geojson=ts.risk_geojson)
            for ts in time_series
        ]

        # ── metadata ──────────────────────────────────────────────
        metadata = SimulationMetadata(
            run_id=run_id,
            pest_type=request.pest_type.value,
            hours=request.hours,
            random_seed=random_seed,
            started_at=format_rfc3339(started_at),
            completed_at=format_rfc3339(completed_at),
            duration_seconds=duration,
            peak_risk=peak_risk,
            cells_at_risk=cells_at_risk,
            n_infested_final=n_infested_final,
            risk_threshold=risk_threshold,
            orchard_stage=orchard_stage_str,
            days_since_flowering=days_since_flowering,
            sugar_index=engine.sugar_index,
            neighbor_threat=neighbor_threat,
            simulation_mode="tree_graph",
            neighbor_direction=neighbor_direction,
            tg_n_trees=len(graph.nodes),
            tg_n_edges=graph.edge_count(),
            tg_lambda0=lambda0,
            tg_alpha=alpha,
            tg_beta=beta,
            tg_wind_bias=wind_bias,
            tg_max_neighbor_dist_m=max_dist,
            tg_default_crown_radius_m=crown_fallback,
        )

        logger.info(
            "tree_graph %s completed in %.2fs: n_trees=%d, n_edges=%d, "
            "peak_risk=%.2f, n_infested=%d, seed=%d",
            run_id, duration, len(graph.nodes), graph.edge_count(),
            peak_risk, n_infested_final, random_seed,
        )

        return SimulationResponse(
            run_id=run_id,
            pest_type=request.pest_type,
            hours=request.hours,
            started_at=format_rfc3339(started_at),
            completed_at=format_rfc3339(completed_at),
            status="completed",
            peak_risk=peak_risk,
            cells_at_risk=cells_at_risk,
            n_infested_final=n_infested_final,
            random_seed=random_seed,
            risk_threshold=risk_threshold,
            metadata=metadata,
            time_series=time_series,
            timesteps=timesteps,
            risk_geojson=risk_geojson,
        )

    def _seed_tree_graph_infestation(
        self,
        graph,
        pest_type: PestTypeEnum,
        orchard_stage: str,
        random_seed: int,
        tree_overrides: Optional[Dict[str, str]],
    ) -> int:
        """Auto-seed infestation for tree_graph mode (mirrors grid behaviour)."""
        from core.tree_graph_model import TreeState

        if not self._pest_is_active_for_stage(pest_type, orchard_stage):
            return 0
        if self._has_manual_infestation_source(tree_overrides):
            return 0

        susceptible = [
            n for n in graph.nodes if n.state == TreeState.SUSCEPTIBLE
        ]
        if not susceptible:
            # Fallback: infest first node if no susceptible trees
            if graph.nodes:
                graph.nodes[0].state = TreeState.INFESTED
                return 1
            return 0

        max_seeds = min(3, len(susceptible))
        rng = np.random.default_rng(random_seed)
        n_seeds = int(rng.integers(1, max_seeds + 1))
        chosen = rng.choice(len(susceptible), size=n_seeds, replace=False)
        for idx in np.atleast_1d(chosen):
            susceptible[int(idx)].state = TreeState.INFESTED
        return n_seeds

    def _tg_result_to_time_series(
        self,
        result,
        graph,
    ) -> List[TimeSeriesSnapshot]:
        """Convert TreeGraphResult snapshots to TimeSeriesSnapshot list."""
        time_series: List[TimeSeriesSnapshot] = []
        total = len(result)
        if total == 0:
            return time_series

        n_samples = min(total, 12)
        step_size = max(1, total // n_samples)
        sampled_indices = list(range(0, total, step_size))
        # Always include final snapshot
        if (total - 1) not in sampled_indices:
            sampled_indices.append(total - 1)

        for i in sampled_indices:
            snap = result.snapshots[i]
            dt = snap["datetime"]
            dt_str = format_rfc3339(dt) if hasattr(dt, "isoformat") else str(dt)

            risk_geojson = self._tg_snapshot_to_geojson(
                graph=result.graph or graph,
                states=snap["states"],
                risks=snap["risks"],
            )
            time_series.append(TimeSeriesSnapshot(
                timestep=snap["timestep"],
                datetime=dt_str,
                hour=snap["hour"],
                risk_geojson=risk_geojson,
                n_infested=snap["n_infested"],
                n_new=snap["n_new"],
                weather={
                    "wind_speed_ms":  snap["weather"]["wind_speed_ms"],
                    "wind_dir_deg":   snap["weather"]["wind_dir_deg"],
                    "temperature_c":  snap["weather"]["temperature_c"],
                },
            ))

        return time_series

    def _tg_snapshot_to_geojson(
        self,
        graph,
        states: List[int],
        risks: List[float],
    ) -> Dict[str, Any]:
        """
        Render a tree_graph snapshot as a GeoJSON FeatureCollection of Points.

        Each feature carries:
          tree_id, risk, state (name), crown_radius_m, index
        """
        from core.tree_graph_model import TreeState

        state_names = {
            TreeState.SUSCEPTIBLE: "unbagged",
            TreeState.BAGGED:      "bagged",
            TreeState.INFESTED:    "infested",
            TreeState.DEAD:        "dead",
        }

        features = []
        for node in graph.nodes:
            idx = node.index
            state_val = states[idx] if idx < len(states) else node.state
            risk_val  = risks[idx]  if idx < len(risks)  else 0.0
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [node.lon, node.lat],
                },
                "properties": {
                    "tree_id":       node.tree_id,
                    "risk":          round(float(risk_val), 6),
                    "state":         state_names.get(state_val, "unknown"),
                    "crown_radius_m": node.crown_radius,
                    "index":         idx,
                },
            })

        return {"type": "FeatureCollection", "features": features}


# Singleton instance
simulation_service = SimulationService()
