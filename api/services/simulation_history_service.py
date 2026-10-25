"""Recoverable History deletion using existing status and metadata columns."""

from fastapi import HTTPException
from sqlalchemy import select

from db.models import SimulationRun
from utils.datetime_utils import format_rfc3339, utcnow_naive


def visible_simulation_runs():
    # Keep legacy NULL statuses visible, too.
    return SimulationRun.status.is_distinct_from("deleted")


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
