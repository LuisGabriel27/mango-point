"""
MangoPoint API — Simulation Routes
====================================
POST /run-simulation endpoint for pest risk simulations.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.schemas import SimulationRequest, SimulationResponse
from db.models import SimulationRun, PestType
from ..services.simulation_service import simulation_service
from ..services.weather_service import weather_service
from ..services.alert_service import alert_service
from ..core.config import settings
from utils.datetime_utils import format_rfc3339

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["Simulation"])


def _orchard_id_from_geojson(
    orchard_geojson: Dict[str, Any],
    default: str = "unknown",
) -> str:
    """Extract a stable orchard identifier from common GeoJSON properties."""
    features = orchard_geojson.get("features", []) if orchard_geojson else []
    if not features:
        return default

    first_feature = features[0] or {}
    props = first_feature.get("properties", {}) or {}
    for key in ("orchard_id", "Orchard_ID", "name", "Name", "id"):
        value = props.get(key)
        if value not in (None, ""):
            return str(value)

    feature_id = first_feature.get("id")
    if feature_id not in (None, ""):
        return str(feature_id)

    return default


def _orchard_id_from_request(
    request: SimulationRequest,
    default: str = "unknown",
) -> str:
    """Prefer explicit multi-orchard ID, then fall back to GeoJSON metadata."""
    if request.orchard_id:
        return str(request.orchard_id)
    return _orchard_id_from_geojson(request.orchard_geojson, default=default)


def _feature_centroid(feature: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Return a GeoJSON feature centroid as ``(lon, lat)`` when possible."""
    geometry = feature.get("geometry", {}) or {}
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    try:
        if geom_type == "Point" and isinstance(coordinates, (list, tuple)):
            return float(coordinates[0]), float(coordinates[1])

        if geom_type == "Polygon" and coordinates:
            ring = coordinates[0]
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring = ring[:-1]
            if not ring:
                return None
            lon = sum(float(point[0]) for point in ring) / len(ring)
            lat = sum(float(point[1]) for point in ring) / len(ring)
            return lon, lat
    except (TypeError, ValueError, IndexError):
        return None

    return None


def _tag_weather_source(
    weather_data: Optional[List[Dict[str, Any]]],
    source: str,
) -> Optional[List[Dict[str, Any]]]:
    """Return weather entries tagged with their source for persistence."""
    if weather_data is None:
        return None
    return [
        {**entry, "source": source} if isinstance(entry, dict) else entry
        for entry in weather_data
    ]


def _weather_source_from_data(
    weather_data: Optional[List[Dict[str, Any]]],
    default: str = "synthetic",
) -> str:
    """Infer a weather source from tagged hourly weather entries."""
    if not weather_data:
        return "synthetic"

    sources = {
        str(entry.get("source"))
        for entry in weather_data
        if isinstance(entry, dict) and entry.get("source")
    }
    if len(sources) == 1:
        return next(iter(sources))
    if len(sources) > 1:
        return "mixed"
    return default


def _infer_weather_source(
    request: SimulationRequest,
    weather_data: Optional[List[Dict[str, Any]]],
    explicit_source: Optional[str] = None,
) -> str:
    """Determine the persisted weather_source value for a simulation run."""
    if explicit_source:
        return explicit_source

    if (
        request.manual_weather_series
        or request.manual_weather_blocks
        or request.manual_weather
    ):
        return "manual"

    return _weather_source_from_data(weather_data, default="open-meteo")


@router.post(
    "/run-simulation",
    response_model=SimulationResponse,
    summary="Run pest dispersal simulation",
    description="""
    Run a cellular automata pest dispersal simulation for the specified orchard.
    
    **Inputs:**
    - `pest_type`: Type of pest to simulate (cecid or fruitfly)
    - `orchard_geojson`: GeoJSON polygon defining the orchard boundary
    - `bagged_tree_ids`: List of tree IDs that are protected by bagging
    - `hours`: Simulation duration (default: 48 hours)
    - `initial_infestation`: Optional list of initial infestation points
    
    **Returns:**
    - Time-series risk GeoJSON showing pest spread over time
    - Summary statistics (peak risk, cells at risk, etc.)
    """,
)
async def run_simulation(
    request: SimulationRequest,
    background_tasks: BackgroundTasks,
) -> SimulationResponse:
    """
    Execute a pest dispersal simulation.
    
    The simulation uses cellular automata with biological gate logic
    to model pest spread based on weather conditions.
    """
    try:
        # Fetch weather data
        logger.info(f"Fetching weather forecast for simulation")
        
        # Extract center point from GeoJSON for weather lookup
        features = request.orchard_geojson.get("features", [])
        if features:
            geom_type = features[0].get("geometry", {}).get("type", "")
            if geom_type == "Point":
                # Point features: average all tree coordinates
                lons, lats = [], []
                for f in features:
                    c = f.get("geometry", {}).get("coordinates", [0, 0])
                    lons.append(c[0])
                    lats.append(c[1])
                lon = sum(lons) / len(lons)
                lat = sum(lats) / len(lats)
            else:
                # Polygon features: use first coordinate ring
                coords = features[0].get("geometry", {}).get("coordinates", [[[0, 0]]])
                if coords and coords[0]:
                    lon = coords[0][0][0]
                    lat = coords[0][0][1]
                else:
                    lon, lat = settings.DEFAULT_LON, settings.DEFAULT_LAT
        else:
            lon, lat = settings.DEFAULT_LON, settings.DEFAULT_LAT
        
        # Get weather forecast — or use manual override if any of the
        # manual_weather* fields are populated (precedence: series > blocks > constant)
        from utils.weather_builder import build_weather_series, compute_gate_diagnostics

        manual_series = build_weather_series(request)
        if manual_series is not None:
            weather_source = "manual"
            weather_data = _tag_weather_source(manual_series, weather_source)
            logger.info("Using manual weather override for simulation")
        else:
            weather_data = await weather_service.get_forecast(
                lat=lat,
                lon=lon,
                hours=request.hours,
            )
            weather_source = _weather_source_from_data(weather_data, default="open-meteo")

        # Run simulation
        result = await simulation_service.run_simulation(
            request=request,
            weather_data=weather_data,
        )

        gate_diagnostics = None
        try:
            gate_diagnostics = compute_gate_diagnostics(
                weather_data=weather_data,
                pest_type=request.pest_type.value,
                orchard_stage=request.orchard_stage.value,
                sugar_index=result.metadata.sugar_index,
                initial_rainfall_history=request.manual_weather_prefix_rain,
            )
            # Optional per-hour gate diagnostics for scenario calibration
            if getattr(request, "debug_gates", False):
                diagnostics = gate_diagnostics
                result.gate_diagnostics = diagnostics
        except Exception as diag_err:
            logger.warning(f"Could not compute gate diagnostics: {diag_err}")
        
        # Persist simulation run to database (background task)
        background_tasks.add_task(
            save_simulation_run,
            result=result,
            request=request,
            weather_data=weather_data,
            weather_source=weather_source,
        )
        
        # Check for alerts (background task)
        background_tasks.add_task(
            check_alerts,
            result=result,
            orchard_id=_orchard_id_from_request(request),
            gate_diagnostics=gate_diagnostics,
            pest_type=request.pest_type.value,
            orchard_stage=request.orchard_stage.value,
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Simulation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Simulation failed: {str(e)}",
        )


def _build_manual_weather(overrides: dict, hours: int) -> list:
    """Backward-compat shim — delegates to ``utils.weather_builder``."""
    from utils.weather_builder import _series_from_constant
    return _series_from_constant(overrides or {}, hours)


async def save_simulation_run(
    result: SimulationResponse,
    request: SimulationRequest,
    weather_data: Optional[List[Dict[str, Any]]],
    weather_source: Optional[str] = None,
) -> None:
    """Background task to persist simulation run."""
    try:
        from ..core.database import async_session_maker
        
        async with async_session_maker() as db:
            pest_type_map = {
                "cecid": PestType.CECID_FLY,
                "fruitfly": PestType.FRUIT_FLY,
            }
            
            run = SimulationRun(
                run_id=result.run_id,
                pest_type=pest_type_map.get(request.pest_type.value, PestType.CECID_FLY),
                orchard_id=_orchard_id_from_request(request, default="orchard"),
                orchard_geojson=request.orchard_geojson,
                bagged_tree_ids=request.bagged_tree_ids,
                treatment_applications=[
                    t.model_dump(mode="json") if hasattr(t, "model_dump") else dict(t)
                    for t in (request.treatment_applications or [])
                ],
                hours=request.hours,
                random_seed=result.random_seed,
                risk_threshold=result.risk_threshold,
                weather_source=_infer_weather_source(request, weather_data, weather_source),
                weather_data=weather_data,
                output_geojson=result.risk_geojson,
                peak_risk=result.peak_risk,
                cells_at_risk=result.cells_at_risk,
                n_infested_final=result.n_infested_final,
                started_at=datetime.fromisoformat(result.started_at.replace("Z", "+00:00")),
                completed_at=datetime.fromisoformat(result.completed_at.replace("Z", "+00:00")) if result.completed_at else None,
                status="completed",
            )
            
            if run.completed_at and run.started_at:
                run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
            
            db.add(run)
            await db.commit()
            logger.info(f"Saved simulation run {result.run_id}")
        
    except Exception as e:
        logger.warning(f"Could not save simulation run (database may not be configured): {e}")


async def check_alerts(
    result: SimulationResponse,
    orchard_id: str,
    gate_diagnostics: Optional[List[Dict[str, Any]]] = None,
    pest_type: Optional[str] = None,
    orchard_stage: Optional[str] = None,
) -> None:
    """Background task to check for and create alerts."""
    try:
        import numpy as np

        gate_alerts = alert_service.check_gate_condition_alerts(
            diagnostics=gate_diagnostics,
            orchard_id=orchard_id,
            simulation_run_id=result.run_id,
            pest_type=pest_type,
            orchard_stage=orchard_stage,
        )
        await _persist_or_store_alerts(
            alerts=gate_alerts,
            run_id=result.run_id,
            alert_kind="gate condition",
        )
        
        # Extract risk and state from GeoJSON
        features = result.risk_geojson.get("features", [])
        if not features:
            return
        
        # tree_graph mode returns Point features without row/col.
        if not all(
            "row" in f.get("properties", {}) and "col" in f.get("properties", {})
            for f in features
        ):
            alerts = alert_service.check_tree_feature_alerts(
                features=features,
                orchard_id=orchard_id,
                simulation_run_id=result.run_id,
                risk_threshold=result.risk_threshold,
            )
            await _persist_or_store_alerts(
                alerts=alerts,
                run_id=result.run_id,
                alert_kind="tree risk",
            )
            return

        # Determine grid dimensions
        max_row = max(int(f["properties"]["row"]) for f in features)
        max_col = max(int(f["properties"]["col"]) for f in features)
        
        # Create arrays
        risk_grid = np.zeros((max_row + 1, max_col + 1))
        state_grid = np.zeros((max_row + 1, max_col + 1), dtype=int)
        tree_ids = np.full((max_row + 1, max_col + 1), "", dtype=object)
        lon_grid = np.full((max_row + 1, max_col + 1), np.nan, dtype=float)
        lat_grid = np.full((max_row + 1, max_col + 1), np.nan, dtype=float)
        
        state_map = {"empty": 0, "unbagged": 1, "bagged": 2, "infested": 3}
        
        for f in features:
            props = f["properties"]
            row, col = int(props["row"]), int(props["col"])
            risk_grid[row, col] = props["risk"]
            state_grid[row, col] = state_map.get(str(props["state"]).lower(), 0)
            tree_ids[row, col] = props.get("tree_id", "")
            centroid = _feature_centroid(f)
            if centroid is not None:
                lon_grid[row, col], lat_grid[row, col] = centroid
        
        # Check for alerts
        alerts = alert_service.check_for_alerts(
            risk_grid=risk_grid,
            state_grid=state_grid,
            tree_ids=tree_ids,
            orchard_id=orchard_id,
            simulation_run_id=result.run_id,
            risk_threshold=result.risk_threshold,
            lon_grid=lon_grid,
            lat_grid=lat_grid,
        )
        
        if alerts:
            await _persist_or_store_alerts(
                alerts=alerts,
                run_id=result.run_id,
                alert_kind="grid risk",
            )
        
    except Exception as e:
        logger.warning(f"Could not check/create alerts: {e}")


async def _persist_or_store_alerts(
    alerts: List[Any],
    run_id: str,
    alert_kind: str,
) -> None:
    """Persist alerts, falling back to memory when the database is unavailable."""
    if not alerts:
        return

    try:
        from ..core.database import async_session_maker

        async with async_session_maker() as db:
            for alert_data in alerts:
                await alert_service.create_alert(db, alert_data, send_notifications=True)
            await db.commit()
            logger.info(
                "Created %d %s alert(s) in database for simulation %s",
                len(alerts),
                alert_kind,
                run_id,
            )
    except Exception as db_err:
        logger.warning(
            "Database unavailable, storing %s alert(s) in memory: %s",
            alert_kind,
            db_err,
        )
        for alert_data in alerts:
            alert_service.store_alert_in_memory(alert_data)
        logger.info(
            "Stored %d %s alert(s) in memory for simulation %s",
            len(alerts),
            alert_kind,
            run_id,
        )


@router.get(
    "/runs",
    summary="List simulation runs",
    description="Get list of past simulation runs.",
)
async def list_simulation_runs(
    orchard_id: Optional[str] = Query(None, description="Filter runs by orchard ID"),
    limit: int = Query(20, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List past simulation runs."""
    from sqlalchemy import select
    
    query = select(SimulationRun)
    if orchard_id:
        query = query.where(SimulationRun.orchard_id == orchard_id)
    query = query.order_by(SimulationRun.started_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    runs = result.scalars().all()
    
    return {
        "runs": [
            {
                "run_id": r.run_id,
                "pest_type": r.pest_type.value,
                "orchard_id": r.orchard_id,
                "hours": r.hours,
                "started_at": format_rfc3339(r.started_at) if r.started_at else None,
                "status": r.status,
                "peak_risk": r.peak_risk,
                "cells_at_risk": r.cells_at_risk,
            }
            for r in runs
        ],
        "total": len(runs),
    }


@router.get(
    "/runs/{run_id}",
    summary="Get simulation run details",
    description="Get detailed results for a specific simulation run.",
)
async def get_simulation_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific simulation run."""
    from sqlalchemy import select
    
    query = select(SimulationRun).where(SimulationRun.run_id == run_id)
    result = await db.execute(query)
    run = result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    
    return {
        "run_id": run.run_id,
        "pest_type": run.pest_type.value,
        "orchard_id": run.orchard_id,
        "hours": run.hours,
        "started_at": format_rfc3339(run.started_at) if run.started_at else None,
        "completed_at": format_rfc3339(run.completed_at) if run.completed_at else None,
        "duration_seconds": run.duration_seconds,
        "status": run.status,
        "peak_risk": run.peak_risk,
        "cells_at_risk": run.cells_at_risk,
        "n_infested_final": run.n_infested_final,
        "weather_source": run.weather_source,
        "risk_geojson": run.output_geojson,
    }
