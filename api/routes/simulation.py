"""
MangoPoint API — Simulation Routes
====================================
POST /run-simulation endpoint for pest risk simulations.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
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
            weather_data = manual_series
            logger.info("Using manual weather override for simulation")
        else:
            weather_data = await weather_service.get_forecast(
                lat=lat,
                lon=lon,
                hours=request.hours,
            )

        # Run simulation
        result = await simulation_service.run_simulation(
            request=request,
            weather_data=weather_data,
        )

        # Optional per-hour gate diagnostics for scenario calibration
        if getattr(request, "debug_gates", False):
            try:
                diagnostics = compute_gate_diagnostics(
                    weather_data=weather_data,
                    pest_type=request.pest_type.value,
                    orchard_stage=request.orchard_stage.value,
                    sugar_index=result.metadata.sugar_index,
                    initial_rainfall_history=request.manual_weather_prefix_rain,
                )
                result.gate_diagnostics = diagnostics
            except Exception as diag_err:
                logger.warning(f"Could not compute gate diagnostics: {diag_err}")
        
        # Persist simulation run to database (background task)
        background_tasks.add_task(
            save_simulation_run,
            result=result,
            request=request,
            weather_data=weather_data,
        )
        
        # Check for alerts (background task)
        background_tasks.add_task(
            check_alerts,
            result=result,
            orchard_id=request.orchard_geojson.get("features", [{}])[0].get("properties", {}).get("name", "unknown"),
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
    weather_data: list,
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
                orchard_id=request.orchard_geojson.get("features", [{}])[0].get("properties", {}).get("name", "orchard"),
                orchard_geojson=request.orchard_geojson,
                bagged_tree_ids=request.bagged_tree_ids,
                hours=request.hours,
                random_seed=result.random_seed,
                risk_threshold=result.risk_threshold,
                weather_source="open-meteo" if weather_data else "synthetic",
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
) -> None:
    """Background task to check for and create alerts."""
    try:
        import numpy as np
        from ..core.database import async_session_maker
        
        # Extract risk and state from GeoJSON
        features = result.risk_geojson.get("features", [])
        if not features:
            return
        
        # tree_graph mode returns Point features without row/col — skip alert check
        if not all("row" in f.get("properties", {}) for f in features):
            logger.debug("Skipping alert check: features have no row/col (tree_graph mode)")
            return

        # Determine grid dimensions
        max_row = max(f["properties"]["row"] for f in features)
        max_col = max(f["properties"]["col"] for f in features)
        
        # Create arrays
        risk_grid = np.zeros((max_row + 1, max_col + 1))
        state_grid = np.zeros((max_row + 1, max_col + 1), dtype=int)
        tree_ids = np.full((max_row + 1, max_col + 1), "", dtype=object)
        
        state_map = {"empty": 0, "unbagged": 1, "bagged": 2, "infested": 3}
        
        for f in features:
            props = f["properties"]
            row, col = props["row"], props["col"]
            risk_grid[row, col] = props["risk"]
            state_grid[row, col] = state_map.get(props["state"], 0)
            tree_ids[row, col] = props.get("tree_id", "")
        
        # Check for alerts
        alerts = alert_service.check_for_alerts(
            risk_grid=risk_grid,
            state_grid=state_grid,
            tree_ids=tree_ids,
            orchard_id=orchard_id,
            simulation_run_id=result.run_id,
        )
        
        if alerts:
            # Try to create alerts in database, fall back to memory
            try:
                async with async_session_maker() as db:
                    for alert_data in alerts:
                        await alert_service.create_alert(db, alert_data, send_notifications=True)
                    await db.commit()
                    logger.info(f"Created {len(alerts)} alerts in database for simulation {result.run_id}")
            except Exception as db_err:
                logger.warning(f"Database unavailable, storing alerts in memory: {db_err}")
                for alert_data in alerts:
                    alert_service.store_alert_in_memory(alert_data)
                logger.info(f"Stored {len(alerts)} alerts in memory for simulation {result.run_id}")
        
    except Exception as e:
        logger.warning(f"Could not check/create alerts: {e}")


@router.get(
    "/runs",
    summary="List simulation runs",
    description="Get list of past simulation runs.",
)
async def list_simulation_runs(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List past simulation runs."""
    from sqlalchemy import select
    
    query = select(SimulationRun).order_by(SimulationRun.started_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    runs = result.scalars().all()
    
    return {
        "runs": [
            {
                "run_id": r.run_id,
                "pest_type": r.pest_type.value,
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
