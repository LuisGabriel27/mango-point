"""Lightweight History summaries and recoverable simulation deletion."""

from fastapi import HTTPException
from sqlalchemy import JSON, case, cast, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB

from db.models import SimulationRun
from utils.datetime_utils import format_rfc3339, utcnow_naive


def visible_simulation_runs():
    # Keep legacy NULL statuses visible, too.
    return SimulationRun.status.is_distinct_from("deleted")


def simulation_history_summary_query():
    """Select History fields without transferring full saved results to Python."""
    def json_has_content(value):
        # Match Python truthiness, including legacy JSON nulls/empty values.
        # Cast supports both JSON and JSONB databases without a schema change.
        empty_values = [cast(literal(value), JSONB) for value in (
            "null", "false", "0", '""', "[]", "{}",
        )]
        json_value = cast(value, JSON)
        return case(
            # Playback arrays can be very large. Count their entries without
            # converting the whole array into a new JSONB document.
            (func.json_typeof(json_value) == "array", func.json_array_length(json_value) > 0),
            else_=func.coalesce(cast(value, JSONB).not_in(empty_values), False),
        )

    simulation_mode = func.coalesce(
        func.nullif(SimulationRun.simulation_mode, ""),
        func.nullif(SimulationRun.result_metadata["simulation_mode"].as_string(), ""),
        func.nullif(SimulationRun.request_payload["simulation_mode"].as_string(), ""),
        "grid",
    ).label("simulation_mode")
    has_time_series = case(
        (json_has_content(SimulationRun.time_series), True),
        else_=json_has_content(SimulationRun.response_payload["time_series"]),
    ).label("has_time_series")
    return select(
        SimulationRun.run_id, SimulationRun.pest_type, SimulationRun.orchard_id,
        simulation_mode, SimulationRun.hours, SimulationRun.started_at,
        SimulationRun.status, SimulationRun.peak_risk, SimulationRun.cells_at_risk,
        SimulationRun.n_infested_final, SimulationRun.weather_source, has_time_series,
    ).where(visible_simulation_runs())


async def set_run_deleted(db, run_id: str, user_id: int, *, deleted: bool):
    run = (await db.execute(
        select(SimulationRun).where(SimulationRun.run_id == run_id).with_for_update()
    )).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    if run.status in {"running", "pending"}:
        raise HTTPException(status_code=409, detail="Wait for this simulation to finish before deleting it.")

    if deleted != (run.status == "deleted"):
        metadata = dict(run.result_metadata or {})
        audit = dict(metadata.get("history_deletion") or {})
        now = format_rfc3339(utcnow_naive())
        if deleted:
            audit = {"previous_status": run.status, "deleted_at": now, "deleted_by": user_id}
            run.status = "deleted"
        else:
            run.status = audit.get("previous_status", "completed")
            audit.update(restored_at=now, restored_by=user_id)
        metadata["history_deletion"] = audit
        run.result_metadata = metadata
    await db.commit()
    return {"run_id": run.run_id, "deleted": run.status == "deleted", "status": run.status}
