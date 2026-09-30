"""Ground-truth field observation routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import (
    database_unavailable_http_exception,
    get_db,
    is_database_unavailable,
)
from ..models.schemas import (
    ObservationBulkResponse,
    ObservationBulkSubmission,
    ObservationPresenceEnum,
    ObservationResponse,
    ObservationSubmission,
    PestTypeEnum,
)
from api.services.orchard_tree_service import ensure_tree_row
from db.models import InfestationRecord, Orchard, Pest, Tree
from utils.datetime_utils import format_rfc3339, utcnow_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/observations", tags=["Observations"])

PEST_NAMES = {
    PestTypeEnum.CECID: "Mango Cecid Fly",
    PestTypeEnum.FRUITFLY: "Oriental Fruit Fly",
}
PEST_TYPES_BY_NAME = {value: key for key, value in PEST_NAMES.items()}


def _database_datetime(value: datetime) -> datetime:
    """Normalize API timestamps for PostgreSQL TIMESTAMP columns."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


async def _get_pest(db: AsyncSession, pest_type: PestTypeEnum) -> Pest:
    pest = (
        await db.execute(select(Pest).where(Pest.name == PEST_NAMES[pest_type]))
    ).scalar_one_or_none()
    if pest is None:
        raise HTTPException(
            status_code=400,
            detail=f"Pest '{PEST_NAMES[pest_type]}' not found in database. Run seed_pests.py first.",
        )
    return pest


async def _get_orchard(db: AsyncSession, orchard_id: str) -> Orchard:
    query = select(Orchard).where(Orchard.orchard_uid == str(orchard_id))
    if str(orchard_id).isdigit():
        query = select(Orchard).where(or_(
            Orchard.orchard_uid == str(orchard_id),
            Orchard.orchard_id == int(orchard_id),
        ))
    orchard = (await db.execute(query)).scalar_one_or_none()
    if orchard is None:
        raise HTTPException(status_code=404, detail="Orchard not found")
    return orchard


async def _resolve_tree(
    db: AsyncSession,
    tree_id: str,
    orchard_id: Optional[str],
) -> tuple[Tree, Orchard]:
    external_id = str(tree_id).strip()
    if orchard_id:
        orchard = await _get_orchard(db, orchard_id)
        tree = await ensure_tree_row(db, orchard, external_id)
        if tree is None:
            raise HTTPException(
                status_code=400,
                detail=f"Tree ID {external_id} is not present in orchard {orchard.orchard_uid}.",
            )
        return tree, orchard

    # Backward compatibility for clients that submitted numeric database IDs
    # before public orchard IDs and GeoJSON tree labels were supported.
    if not external_id.isdigit():
        raise HTTPException(
            status_code=400,
            detail="orchard_id is required for non-numeric GeoJSON tree IDs.",
        )
    tree = (
        await db.execute(select(Tree).where(Tree.tree_id == int(external_id)))
    ).scalar_one_or_none()
    if tree is None:
        raise HTTPException(status_code=400, detail=f"Tree ID {external_id} not found in database.")
    orchard = (
        await db.execute(select(Orchard).where(Orchard.orchard_id == tree.orchard_id))
    ).scalar_one_or_none()
    if orchard is None:
        raise HTTPException(status_code=400, detail="The tree's orchard no longer exists.")
    if not tree.external_id:
        tree.external_id = external_id
    return tree, orchard


def _presence(record: InfestationRecord) -> ObservationPresenceEnum:
    value = getattr(record, "observation_status", None)
    if value in {member.value for member in ObservationPresenceEnum}:
        return ObservationPresenceEnum(value)
    return ObservationPresenceEnum.PRESENT if record.infected_status else ObservationPresenceEnum.ABSENT


def _severity(record: InfestationRecord) -> Optional[float]:
    if record.infestation_level is None:
        return None
    return float(record.infestation_level) / 100.0


def _to_response(
    record: InfestationRecord,
    *,
    pest_type: PestTypeEnum,
    orchard: Orchard,
    tree: Tree,
) -> ObservationResponse:
    timestamp = record.record_date or record.created_at or utcnow_naive()
    created_at = record.created_at or record.record_date or utcnow_naive()
    return ObservationResponse(
        id=record.infestation_id,
        tree_id=record.tree_external_id or tree.external_id or str(record.tree_id),
        database_tree_id=record.tree_id,
        orchard_id=orchard.orchard_uid or str(orchard.orchard_id),
        observed_pest=pest_type,
        timestamp=format_rfc3339(timestamp),
        presence=_presence(record),
        severity=_severity(record),
        affected_count=record.affected_count,
        inspected_count=record.inspected_count,
        method=record.observation_method,
        observer_id=record.observer_id,
        notes=record.notes,
        image_url=record.image_url,
        lon=record.observation_lon,
        lat=record.observation_lat,
        simulation_run_id=record.verification_run_id,
        forecast_risk=record.forecast_risk,
        forecast_lead_hours=record.forecast_lead_hours,
        created_at=format_rfc3339(created_at),
    )


def _new_record(
    observation: ObservationSubmission,
    *,
    tree: Tree,
    pest: Pest,
) -> InfestationRecord:
    presence = observation.presence.value
    infected = presence == ObservationPresenceEnum.PRESENT.value
    return InfestationRecord(
        tree_id=tree.tree_id,
        tree_external_id=tree.external_id or observation.tree_id,
        pest_id=pest.pest_id,
        simulation_id=None,
        record_date=_database_datetime(observation.timestamp),
        infected_status=infected,
        infestation_level=(observation.severity * 100.0 if observation.severity is not None else None),
        observation_status=presence,
        affected_count=observation.affected_count,
        inspected_count=observation.inspected_count,
        observation_method=(observation.method.value if observation.method else None),
        observer_id=observation.observer_id,
        notes=observation.notes,
        image_url=observation.image_url,
        observation_lon=observation.lon,
        observation_lat=observation.lat,
        verification_run_id=observation.simulation_run_id,
        forecast_risk=observation.forecast_risk,
        forecast_lead_hours=observation.forecast_lead_hours,
    )


@router.post(
    "/submit-observation",
    response_model=ObservationResponse,
    summary="Submit field verification",
)
async def submit_observation(
    observation: ObservationSubmission,
    db: AsyncSession = Depends(get_db),
) -> ObservationResponse:
    """Append one per-tree ground-truth inspection."""
    try:
        pest = await _get_pest(db, observation.observed_pest)
        tree, orchard = await _resolve_tree(db, observation.tree_id, observation.orchard_id)
        record = _new_record(observation, tree=tree, pest=pest)
        db.add(record)
        await db.flush()
        await db.commit()
        logger.info(
            "Field verification recorded: %s on %s/%s (%s)",
            observation.observed_pest.value,
            orchard.orchard_uid,
            observation.tree_id,
            observation.presence.value,
        )
        return _to_response(record, pest_type=observation.observed_pest, orchard=orchard, tree=tree)
    except HTTPException:
        raise
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Invalid observation data.") from exc
    except Exception as exc:
        await db.rollback()
        if is_database_unavailable(exc):
            raise database_unavailable_http_exception() from exc
        logger.error("Failed to submit observation: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record observation.") from exc


@router.post(
    "/bulk",
    response_model=ObservationBulkResponse,
    summary="Submit field verification for selected trees",
)
async def submit_observations_bulk(
    submission: ObservationBulkSubmission,
    db: AsyncSession = Depends(get_db),
) -> ObservationBulkResponse:
    """Append the same inspection result for a polygon/lasso tree selection."""
    try:
        pest = await _get_pest(db, submission.observed_pest)
        orchard = await _get_orchard(db, submission.orchard_id)
        responses: list[ObservationResponse] = []
        for external_id in submission.tree_ids:
            tree = await ensure_tree_row(db, orchard, external_id)
            if tree is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tree ID {external_id} is not present in orchard {orchard.orchard_uid}.",
                )
            observation = ObservationSubmission(
                tree_id=external_id,
                orchard_id=submission.orchard_id,
                observed_pest=submission.observed_pest,
                timestamp=submission.timestamp,
                presence=submission.presence,
                severity=submission.severity,
                affected_count=submission.affected_count,
                inspected_count=submission.inspected_count,
                method=submission.method,
                observer_id=submission.observer_id,
                notes=submission.notes,
                image_url=submission.image_url,
                simulation_run_id=submission.simulation_run_id,
                forecast_risk=submission.forecast_risk,
                forecast_lead_hours=submission.forecast_lead_hours,
            )
            record = _new_record(observation, tree=tree, pest=pest)
            db.add(record)
            await db.flush()
            responses.append(_to_response(
                record,
                pest_type=submission.observed_pest,
                orchard=orchard,
                tree=tree,
            ))
        await db.commit()
        return ObservationBulkResponse(observations=responses, count=len(responses))
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        if is_database_unavailable(exc):
            raise database_unavailable_http_exception() from exc
        logger.error("Failed to submit bulk observations: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to record selected-tree observations.") from exc


def _observation_query():
    return (
        select(InfestationRecord, Tree, Orchard, Pest)
        .join(Tree, Tree.tree_id == InfestationRecord.tree_id)
        .join(Orchard, Orchard.orchard_id == Tree.orchard_id)
        .join(Pest, Pest.pest_id == InfestationRecord.pest_id)
        .where(InfestationRecord.simulation_id.is_(None))
    )


@router.get("/list", summary="List field observations")
async def list_observations(
    orchard_id: Optional[str] = Query(None, description="Filter by public orchard ID"),
    tree_id: Optional[str] = Query(None, description="Filter by GeoJSON or database tree ID"),
    pest_type: Optional[PestTypeEnum] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = _observation_query()
    if orchard_id:
        if str(orchard_id).isdigit():
            query = query.where(or_(
                Orchard.orchard_uid == str(orchard_id),
                Orchard.orchard_id == int(orchard_id),
            ))
        else:
            query = query.where(Orchard.orchard_uid == str(orchard_id))
    if tree_id:
        normalized = str(tree_id).strip()
        filters = [Tree.external_id == normalized, InfestationRecord.tree_external_id == normalized]
        if normalized.isdigit():
            filters.append(Tree.tree_id == int(normalized))
        query = query.where(or_(*filters))
    if pest_type:
        query = query.where(Pest.name == PEST_NAMES[pest_type])
    if start_date:
        query = query.where(InfestationRecord.record_date >= _database_datetime(start_date))
    if end_date:
        query = query.where(InfestationRecord.record_date <= _database_datetime(end_date))

    rows = (
        await db.execute(
            query.order_by(
                InfestationRecord.record_date.desc(),
                InfestationRecord.infestation_id.desc(),
            ).limit(limit).offset(offset)
        )
    ).all()
    observations = [
        _to_response(
            record,
            pest_type=PEST_TYPES_BY_NAME.get(pest.name, PestTypeEnum.CECID),
            orchard=orchard,
            tree=tree,
        ).model_dump(mode="json")
        for record, tree, orchard, pest in rows
    ]
    return {"observations": observations, "count": len(observations), "limit": limit, "offset": offset}


@router.get("/{observation_id}", response_model=ObservationResponse, summary="Get field observation")
async def get_observation(
    observation_id: int,
    db: AsyncSession = Depends(get_db),
) -> ObservationResponse:
    row = (
        await db.execute(
            _observation_query().where(InfestationRecord.infestation_id == observation_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    record, tree, orchard, pest = row
    return _to_response(
        record,
        pest_type=PEST_TYPES_BY_NAME.get(pest.name, PestTypeEnum.CECID),
        orchard=orchard,
        tree=tree,
    )


@router.delete("/{observation_id}", summary="Delete field observation")
async def delete_observation(
    observation_id: int,
    db: AsyncSession = Depends(get_db),
):
    observation = (
        await db.execute(
            select(InfestationRecord).where(
                InfestationRecord.infestation_id == observation_id,
                InfestationRecord.simulation_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if observation is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    await db.delete(observation)
    await db.commit()
    return {"message": f"Observation {observation_id} deleted"}
