"""
MangoPoint API — Simulation Routes
====================================
POST /run-simulation endpoint for pest risk simulations.
"""

import logging
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.schemas import SimulationRequest, SimulationResponse
from db.models import Alert, AlertStatus, SimulationRun, PestType, InfestationRecord, Pest
from ..services.simulation_service import simulation_service
from ..services.weather_service import weather_service
from ..services.alert_service import alert_service
from ..core.config import settings
from utils.datetime_utils import format_rfc3339, parse_rfc3339

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


def _required_stage_name_for_pest(pest_type: Optional[str]) -> Optional[str]:
    """Return the phenology stage that can receive risk for the selected pest."""
    pest = str(pest_type or "").strip().lower().replace("-", "_")
    if pest in {"cecid", "cecid_fly", "cecid fly"}:
        return "fruitlet"
    if pest in {"fruitfly", "fruit_fly", "fruit fly"}:
        return "mature"
    return None


def _required_stage_value_for_pest(pest_type: Optional[str]) -> Optional[int]:
    stage = _required_stage_name_for_pest(pest_type)
    return {
        "dormant": 0,
        "flowering": 1,
        "fruitlet": 2,
        "mature": 3,
    }.get(stage)


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


def _model_to_json_dict(model: Any) -> Dict[str, Any]:
    """Serialize Pydantic v1/v2 models to plain JSON-compatible dicts."""
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def _timestamp_for_db(value: Optional[str]) -> Optional[datetime]:
    """Parse an RFC3339 timestamp and store it as naive UTC."""
    if not value:
        return None
    dt = parse_rfc3339(value)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _xlsx_col_name(index: int) -> str:
    """Return the Excel column name for a zero-based index."""
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _safe_sheet_name(name: str) -> str:
    cleaned = re.sub(r"[\[\]\:\*\?\/\\]", " ", str(name or "Sheet")).strip()
    return (cleaned or "Sheet")[:31]


def _cell_xml(value: Any, row_idx: int, col_idx: int) -> str:
    ref = f"{_xlsx_col_name(col_idx)}{row_idx}"
    if value is None:
        return f'<c r="{ref}"/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"><v>{value}</v></c>'
    if isinstance(value, datetime):
        value = format_rfc3339(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    text = xml_escape(str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def _sheet_xml(rows: List[List[Any]]) -> str:
    row_xml = []
    for r_idx, row in enumerate(rows, start=1):
        cells = "".join(_cell_xml(value, r_idx, c_idx) for c_idx, value in enumerate(row))
        row_xml.append(f'<row r="{r_idx}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        '</worksheet>'
    )


def _build_xlsx(sheets: List[Tuple[str, List[List[Any]]]]) -> bytes:
    """Build a simple XLSX workbook without external dependencies."""
    clean_sheets = [(_safe_sheet_name(name), rows or [["No data"]]) for name, rows in sheets]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(1, len(clean_sheets) + 1)
            )
            + "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            + "".join(
                f'<sheet name="{xml_escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
                for i, (name, _) in enumerate(clean_sheets, start=1)
            )
            + "</sheets></workbook>",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(clean_sheets) + 1)
            )
            + "</Relationships>",
        )
        for i, (_, rows) in enumerate(clean_sheets, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(rows))
    return output.getvalue()


def _xlsx_response(filename: str, sheets: List[Tuple[str, List[List[Any]]]]) -> StreamingResponse:
    data = _build_xlsx(sheets)
    safe_filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename).strip("_") or "export.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


def _jsonish(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return format_rfc3339(value)
    return json.dumps(value, ensure_ascii=False)


def _kv_rows(data: Dict[str, Any]) -> List[List[Any]]:
    rows = [["Field", "Value"]]
    for key, value in (data or {}).items():
        rows.append([key, _jsonish(value)])
    return rows


def _run_summary_row(run: SimulationRun) -> Dict[str, Any]:
    metadata = run.result_metadata or {}
    request_payload = run.request_payload or {}
    pest_value = run.pest_type.value if hasattr(run.pest_type, "value") else run.pest_type
    return {
        "run_id": run.run_id,
        "started_at": format_rfc3339(run.started_at) if run.started_at else None,
        "completed_at": format_rfc3339(run.completed_at) if run.completed_at else None,
        "orchard_id": run.orchard_id,
        "pest_type": pest_value,
        "simulation_mode": run.simulation_mode or metadata.get("simulation_mode") or request_payload.get("simulation_mode"),
        "hours": run.hours,
        "status": run.status,
        "peak_risk": run.peak_risk,
        "peak_risk_percent": round(run.peak_risk * 100, 2) if run.peak_risk is not None else None,
        "cells_at_risk": run.cells_at_risk,
        "n_infested_final": run.n_infested_final,
        "weather_source": run.weather_source,
        "orchard_stage": metadata.get("orchard_stage") or request_payload.get("orchard_stage"),
        "days_since_flowering": metadata.get("days_since_flowering") or request_payload.get("days_since_flowering"),
        "neighbor_threat": metadata.get("neighbor_threat") or request_payload.get("neighbor_threat"),
        "neighbor_direction": metadata.get("neighbor_direction") or request_payload.get("neighbor_direction"),
        "initial_seed_strategy": metadata.get("initial_seed_strategy"),
        "initial_seed_count": metadata.get("initial_seed_count"),
        "treatment_summary": metadata.get("treatment_summary"),
        "time_series_frames": len(run.time_series or []),
    }


def _dict_rows(dicts: List[Dict[str, Any]], headers: Optional[List[str]] = None) -> List[List[Any]]:
    if not dicts:
        return [["No data"]]
    if headers is None:
        headers = []
        for row in dicts:
            for key in row:
                if key not in headers:
                    headers.append(key)
    return [headers] + [[_jsonish(row.get(header)) for header in headers] for row in dicts]


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
    db: AsyncSession = Depends(get_db),
) -> SimulationResponse:
    """
    Execute a pest dispersal simulation.
    
    The simulation uses cellular automata with biological gate logic
    to model pest spread based on weather conditions.
    """
    try:
        # Merge field observations into tree_overrides when requested
        if request.use_observations_as_seeds:
            request = await _apply_observation_seeds(request, db)

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


async def _apply_observation_seeds(
    request: SimulationRequest,
    db: AsyncSession,
) -> SimulationRequest:
    """Query recent field observations and merge infected tree_ids into tree_overrides."""
    from datetime import timedelta
    from utils.datetime_utils import utcnow_naive

    try:
        cutoff = utcnow_naive() - timedelta(days=request.observations_lookback_days)
        result = await db.execute(
            select(InfestationRecord).where(
                InfestationRecord.infected_status == True,
                InfestationRecord.simulation_id.is_(None),
                InfestationRecord.record_date >= cutoff,
            )
        )
        records = result.scalars().all()
        if not records:
            return request

        observed_tree_ids = {str(r.tree_id) for r in records}
        existing_overrides = dict(request.tree_overrides or {})
        for tid in observed_tree_ids:
            if tid not in existing_overrides:
                existing_overrides[tid] = "infected"

        logger.info(
            "Seeded %d tree(s) from field observations (lookback %d days)",
            len(observed_tree_ids),
            request.observations_lookback_days,
        )
        return request.model_copy(update={"tree_overrides": existing_overrides})
    except Exception as e:
        logger.warning("Could not load observation seeds: %s", e)
        return request


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
            request_payload = _model_to_json_dict(request)
            response_payload = _model_to_json_dict(result)
            result_metadata = response_payload.get("metadata") or {}
            impact_assumptions = (
                request_payload.get("impact_assumptions")
                or (request_payload.get("dashboard_state") or {}).get("impact_assumptions")
            )
            
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
                simulation_mode=request.simulation_mode.value,
                hours=request.hours,
                random_seed=result.random_seed,
                risk_threshold=result.risk_threshold,
                weather_source=_infer_weather_source(request, weather_data, weather_source),
                weather_data=weather_data,
                output_geojson=result.risk_geojson,
                request_payload=request_payload,
                response_payload=response_payload,
                result_metadata=result_metadata,
                time_series=response_payload.get("time_series") or [],
                timesteps=response_payload.get("timesteps") or [],
                impact_assumptions=impact_assumptions,
                peak_risk=result.peak_risk,
                cells_at_risk=result.cells_at_risk,
                n_infested_final=result.n_infested_final,
                started_at=_timestamp_for_db(result.started_at),
                completed_at=_timestamp_for_db(result.completed_at),
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
            has_stage_context = any(
                "stage" in (f.get("properties", {}) or {})
                for f in features
            )
            alerts = alert_service.check_tree_feature_alerts(
                features=features,
                orchard_id=orchard_id,
                simulation_run_id=result.run_id,
                risk_threshold=result.risk_threshold,
                required_stage=(
                    _required_stage_name_for_pest(pest_type)
                    if has_stage_context
                    else None
                ),
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
        stage_grid = np.full((max_row + 1, max_col + 1), -1, dtype=int)
        has_stage_context = False
        
        state_map = {"empty": 0, "unbagged": 1, "bagged": 2, "infested": 3}
        stage_map = {"dormant": 0, "flowering": 1, "fruitlet": 2, "mature": 3}
        
        for f in features:
            props = f["properties"]
            row, col = int(props["row"]), int(props["col"])
            risk_grid[row, col] = props["risk"]
            state_grid[row, col] = state_map.get(str(props["state"]).lower(), 0)
            tree_ids[row, col] = props.get("tree_id", "")
            stage = stage_map.get(str(props.get("stage", "")).strip().lower())
            if stage is not None:
                stage_grid[row, col] = stage
                has_stage_context = True
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
            stage_grid=stage_grid if has_stage_context else None,
            required_stage_value=(
                _required_stage_value_for_pest(pest_type)
                if has_stage_context
                else None
            ),
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
            created_count = 0
            for alert_data in alerts:
                if await _active_duplicate_alert_exists(db, alert_data):
                    logger.info(
                        "Skipped duplicate active %s alert for orchard %s zone %s",
                        alert_kind,
                        alert_data.orchard_id,
                        alert_data.zone_name,
                    )
                    continue
                await alert_service.create_alert(db, alert_data, send_notifications=True)
                created_count += 1
            await db.commit()
            logger.info(
                "Created %d %s alert(s) in database for simulation %s",
                created_count,
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


async def _active_duplicate_alert_exists(db: AsyncSession, alert_data: Any) -> bool:
    """Return True when the same alert condition is already active."""
    result = await db.execute(
        select(Alert.alert_id)
        .where(
            Alert.status == AlertStatus.ACTIVE,
            Alert.orchard_id == alert_data.orchard_id,
            Alert.zone_name == alert_data.zone_name,
            Alert.message == alert_data.message,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


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
                "simulation_mode": (
                    r.simulation_mode
                    or (r.result_metadata or {}).get("simulation_mode")
                    or (r.request_payload or {}).get("simulation_mode")
                    or "grid"
                ),
                "hours": r.hours,
                "started_at": format_rfc3339(r.started_at) if r.started_at else None,
                "status": r.status,
                "peak_risk": r.peak_risk,
                "cells_at_risk": r.cells_at_risk,
                "n_infested_final": r.n_infested_final,
                "weather_source": r.weather_source,
                "has_time_series": bool(r.time_series or (r.response_payload or {}).get("time_series")),
            }
            for r in runs
        ],
        "total": len(runs),
    }


@router.get(
    "/runs/export",
    summary="Export simulation run history",
    description="Export saved simulation history as an Excel workbook.",
)
async def export_simulation_runs(
    orchard_id: Optional[str] = Query(None, description="Filter by orchard ID. Omit for all orchards."),
    period: str = Query("all", pattern="^(all|month)$", description="Export all dates or a specific month."),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    limit: int = Query(5000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Export saved run summaries with reproducibility fields."""
    query = select(SimulationRun)
    if orchard_id:
        query = query.where(SimulationRun.orchard_id == orchard_id)

    period_label = "all"
    if period == "month":
        if year is None or month is None:
            raise HTTPException(status_code=400, detail="year and month are required when period=month")
        query = query.where(
            extract("year", SimulationRun.started_at) == year,
            extract("month", SimulationRun.started_at) == month,
        )
        period_label = f"{year}-{month:02d}"

    query = query.order_by(SimulationRun.started_at.desc()).limit(limit)
    runs = (await db.execute(query)).scalars().all()

    summary_rows = [_run_summary_row(run) for run in runs]
    summary_headers = [
        "run_id", "started_at", "completed_at", "orchard_id", "pest_type",
        "simulation_mode", "hours", "status", "peak_risk", "peak_risk_percent",
        "cells_at_risk", "n_infested_final", "weather_source", "orchard_stage",
        "days_since_flowering", "neighbor_threat", "neighbor_direction",
        "initial_seed_strategy", "initial_seed_count", "treatment_summary",
        "time_series_frames",
    ]
    filter_rows = [
        ["Export Field", "Value"],
        ["Generated at", format_rfc3339(datetime.now(timezone.utc))],
        ["Orchard filter", orchard_id or "All orchards"],
        ["Period", period_label],
        ["Rows exported", len(runs)],
    ]
    filename = f"mangopoint_simulation_history_{orchard_id or 'all_orchards'}_{period_label}.xlsx"
    return _xlsx_response(
        filename,
        [
            ("History Summary", _dict_rows(summary_rows, summary_headers)),
            ("Export Filters", filter_rows),
        ],
    )


@router.get(
    "/runs/{run_id}/export",
    summary="Export one simulation run",
    description="Export one saved simulation with inputs, outputs, weather, and timeline.",
)
async def export_simulation_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Export a single saved run as a multi-sheet Excel workbook."""
    run = (await db.execute(select(SimulationRun).where(SimulationRun.run_id == run_id))).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Simulation run not found")

    response_payload = run.response_payload or {}
    metadata = run.result_metadata or response_payload.get("metadata") or {}
    request_payload = run.request_payload or {}
    time_series = run.time_series or response_payload.get("time_series") or []
    weather_data = run.weather_data or []
    risk_features = (run.output_geojson or response_payload.get("risk_geojson") or {}).get("features", [])

    summary = _run_summary_row(run)
    summary.update({
        "random_seed": run.random_seed,
        "risk_threshold": run.risk_threshold,
        "duration_seconds": run.duration_seconds,
        "loaded_from_history": True,
    })

    time_rows = [[
        "hour", "datetime", "n_infested", "n_new", "temperature_c", "humidity",
        "rainfall_mm", "wind_speed_ms", "wind_dir_deg",
    ]]
    for frame in time_series:
        weather = frame.get("weather") or {}
        time_rows.append([
            frame.get("hour"),
            frame.get("datetime"),
            frame.get("n_infested"),
            frame.get("n_new"),
            weather.get("temperature_c") or weather.get("temp_c"),
            weather.get("humidity"),
            weather.get("rainfall_mm") or weather.get("rain_mm"),
            weather.get("wind_speed_ms") or weather.get("wind_ms"),
            weather.get("wind_dir_deg") or weather.get("wind_direction_deg"),
        ])
    if len(time_rows) == 1:
        time_rows.append(["No time series saved", None, None, None, None, None, None, None, None])

    weather_rows = _dict_rows(weather_data if isinstance(weather_data, list) else [])

    feature_rows = [[
        "index", "tree_id", "risk", "state", "stage", "row", "col",
        "lon", "lat", "geometry_type",
    ]]
    for idx, feature in enumerate(risk_features[:10000], start=1):
        props = feature.get("properties") or {}
        centroid = _feature_centroid(feature)
        feature_rows.append([
            idx,
            props.get("tree_id") or props.get("Tree_ID") or feature.get("id"),
            props.get("risk"),
            props.get("state"),
            props.get("stage"),
            props.get("row"),
            props.get("col"),
            centroid[0] if centroid else None,
            centroid[1] if centroid else None,
            (feature.get("geometry") or {}).get("type"),
        ])
    if len(feature_rows) == 1:
        feature_rows.append(["No final risk features saved", None, None, None, None, None, None, None, None, None])

    filename = f"mangopoint_simulation_{run.run_id}.xlsx"
    return _xlsx_response(
        filename,
        [
            ("Summary", _kv_rows(summary)),
            ("Input Parameters", _kv_rows(request_payload)),
            ("Result Metadata", _kv_rows(metadata)),
            ("Time Series", time_rows),
            ("Weather Data", weather_rows),
            ("Final Risk Features", feature_rows),
        ],
    )


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

    request_payload = run.request_payload or {}
    response_payload = dict(run.response_payload or {})
    if response_payload:
        payload = response_payload
    else:
        metadata = run.result_metadata or {}
        if metadata:
            metadata = {
                **metadata,
                "simulation_mode": metadata.get("simulation_mode") or run.simulation_mode or "grid",
            }
        payload = {
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
            "random_seed": run.random_seed,
            "risk_threshold": run.risk_threshold,
            "metadata": metadata,
            "time_series": run.time_series or [],
            "timesteps": run.timesteps or [],
            "risk_geojson": run.output_geojson,
        }

    payload.setdefault("run_id", run.run_id)
    payload.setdefault("pest_type", run.pest_type.value)
    payload.setdefault("orchard_id", run.orchard_id)
    payload.setdefault("hours", run.hours)
    payload.setdefault("started_at", format_rfc3339(run.started_at) if run.started_at else None)
    payload.setdefault("completed_at", format_rfc3339(run.completed_at) if run.completed_at else None)
    payload.setdefault("duration_seconds", run.duration_seconds)
    payload.setdefault("status", run.status)
    payload.setdefault("peak_risk", run.peak_risk)
    payload.setdefault("cells_at_risk", run.cells_at_risk)
    payload.setdefault("n_infested_final", run.n_infested_final)
    payload.setdefault("random_seed", run.random_seed)
    payload.setdefault("risk_threshold", run.risk_threshold)
    payload.setdefault("risk_geojson", run.output_geojson)
    payload.setdefault("time_series", run.time_series or [])
    payload.setdefault("timesteps", run.timesteps or [])

    metadata = payload.get("metadata") or run.result_metadata or {}
    if isinstance(metadata, dict):
        metadata.setdefault("simulation_mode", run.simulation_mode or request_payload.get("simulation_mode") or "grid")
        payload["metadata"] = metadata

    payload["loaded_from_history"] = True
    payload["history"] = {
        "run_id": run.run_id,
        "orchard_id": run.orchard_id,
        "started_at": format_rfc3339(run.started_at) if run.started_at else None,
        "completed_at": format_rfc3339(run.completed_at) if run.completed_at else None,
        "duration_seconds": run.duration_seconds,
        "status": run.status,
        "weather_source": run.weather_source,
    }
    payload["orchard_id"] = run.orchard_id
    payload["weather_source"] = run.weather_source
    payload["weather_data"] = run.weather_data
    payload["request_payload"] = request_payload
    payload["input_parameters"] = request_payload
    payload["impact_assumptions"] = (
        run.impact_assumptions
        or request_payload.get("impact_assumptions")
        or (request_payload.get("dashboard_state") or {}).get("impact_assumptions")
    )

    return payload
