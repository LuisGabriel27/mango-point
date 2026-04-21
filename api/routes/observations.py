"""
MangoPoint API — Observation Routes
=====================================
POST /submit-observation endpoint for ground truth data.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..core.database import (
    database_unavailable_http_exception,
    get_db,
    is_database_unavailable,
)
from ..models.schemas import ObservationSubmission, ObservationResponse, PestTypeEnum
from db.models import InfestationRecord, Tree, Pest, PestType
from utils.datetime_utils import format_rfc3339, utcnow_naive

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/observations", tags=["Observations"])


@router.post(
    "/submit-observation",
    response_model=ObservationResponse,
    summary="Submit pest observation",
    description="""
    Submit a ground truth pest observation for model validation.
    
    **Inputs:**
    - `tree_id`: ID of the affected tree
    - `observed_pest`: Type of pest observed (cecid or fruitfly)
    - `timestamp`: When the observation was made
    - `severity`: Severity level from 0 (minimal) to 1 (severe)
    
    **Optional:**
    - `observer_id`: ID of the person making the observation
    - `notes`: Additional observation notes
    - `image_url`: URL to observation image
    - `lon`, `lat`: Observation coordinates
    """,
)
async def submit_observation(
    observation: ObservationSubmission,
    db: AsyncSession = Depends(get_db),
) -> ObservationResponse:
    """
    Record a pest observation for model evaluation.
    
    Observations are compared against predictions to compute
    precision, recall, and F1 scores.
    """
    try:
        # Map pest type schema enum to pest DB lookup
        pest_name_map = {
            PestTypeEnum.CECID: "Mango Cecid Fly",
            PestTypeEnum.FRUITFLY: "Oriental Fruit Fly",
        }
        
        # Find the pest record
        pest_name = pest_name_map[observation.observed_pest]
        result = await db.execute(
            select(Pest).where(Pest.name == pest_name)
        )
        pest = result.scalar_one_or_none()
        
        if not pest:
            raise HTTPException(
                status_code=400,
                detail=f"Pest '{pest_name}' not found in database. Run seed_pests.py first.",
            )
        
        # Check if tree exists
        result = await db.execute(
            select(Tree).where(Tree.tree_id == int(observation.tree_id))
        )
        tree = result.scalar_one_or_none()
        
        if not tree:
            raise HTTPException(
                status_code=400,
                detail=f"Tree ID {observation.tree_id} not found in database.",
            )
        
        # Create infestation record
        record = InfestationRecord(
            tree_id=tree.tree_id,
            pest_id=pest.pest_id,
            simulation_id=0,  # 0 indicates ground-truth observation, not from simulation
            record_date=observation.timestamp,
            infected_status=True,
            infestation_level=observation.severity * 100 if observation.severity else None,
        )
        
        db.add(record)
        await db.flush()
        await db.commit()
        
        logger.info(
            f"Observation recorded: {observation.observed_pest} on tree {observation.tree_id} "
            f"(severity: {observation.severity})"
        )
        
        return ObservationResponse(
            id=record.infestation_id,
            tree_id=str(record.tree_id),
            observed_pest=observation.observed_pest,
            timestamp=format_rfc3339(record.record_date) if record.record_date else format_rfc3339(utcnow_naive()),
            severity=observation.severity,
            created_at=format_rfc3339(utcnow_naive()),
        )
        
    except HTTPException:
        raise
    except IntegrityError as e:
        await db.rollback()
        logger.error(f"Database integrity error: {e}")
        raise HTTPException(
            status_code=400,
            detail="Invalid data. Check that tree_id exists.",
        )
    except Exception as e:
        await db.rollback()
        if is_database_unavailable(e):
            raise database_unavailable_http_exception() from e
        logger.error(f"Failed to submit observation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to record observation: {str(e)}",
        )


@router.get(
    "/list",
    summary="List observations",
    description="Retrieve list of pest observations.",
)
async def list_observations(
    tree_id: Optional[str] = Query(None, description="Filter by tree ID"),
    pest_type: Optional[PestTypeEnum] = Query(None, description="Filter by pest type"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List observations with optional filters."""
    query = select(InfestationRecord).order_by(InfestationRecord.record_date.desc())
    
    if tree_id:
        query = query.where(InfestationRecord.tree_id == int(tree_id))
    if pest_type:
        # Look up pest ID by name
        pest_name_map = {
            PestTypeEnum.CECID: "Mango Cecid Fly",
            PestTypeEnum.FRUITFLY: "Oriental Fruit Fly",
        }
        pest_result = await db.execute(
            select(Pest).where(Pest.name == pest_name_map[pest_type])
        )
        pest = pest_result.scalar_one_or_none()
        if pest:
            query = query.where(InfestationRecord.pest_id == pest.pest_id)
    if start_date:
        query = query.where(InfestationRecord.record_date >= start_date)
    if end_date:
        query = query.where(InfestationRecord.record_date <= end_date)
    
    query = query.limit(limit).offset(offset)
    
    result = await db.execute(query)
    records = result.scalars().all()
    
    # Load pest names for display
    pest_result = await db.execute(select(Pest))
    pests = {p.pest_id: p.name for p in pest_result.scalars().all()}
    
    pest_type_reverse = {
        "Mango Cecid Fly": "cecid",
        "Oriental Fruit Fly": "fruitfly",
    }
    
    return {
        "observations": [
            {
                "id": r.infestation_id,
                "tree_id": str(r.tree_id),
                "observed_pest": pest_type_reverse.get(pests.get(r.pest_id, ""), "unknown"),
                "timestamp": format_rfc3339(r.record_date) if r.record_date else None,
                "severity": float(r.infestation_level or 0) / 100.0,
                "created_at": format_rfc3339(r.record_date) if r.record_date else None,
            }
            for r in records
        ],
        "count": len(records),
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/{observation_id}",
    summary="Get observation details",
    description="Get details of a specific observation.",
)
async def get_observation(
    observation_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific observation by ID."""
    result = await db.execute(
        select(InfestationRecord).where(InfestationRecord.infestation_id == observation_id)
    )
    obs = result.scalar_one_or_none()
    
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    
    # Get pest name
    pest_result = await db.execute(
        select(Pest).where(Pest.pest_id == obs.pest_id)
    )
    pest = pest_result.scalar_one_or_none()
    pest_name = pest.name if pest else "unknown"
    
    pest_type_reverse = {
        "Mango Cecid Fly": "cecid",
        "Oriental Fruit Fly": "fruitfly",
    }
    
    return {
        "id": obs.infestation_id,
        "tree_id": str(obs.tree_id),
        "observed_pest": pest_type_reverse.get(pest_name, "unknown"),
        "timestamp": format_rfc3339(obs.record_date) if obs.record_date else None,
        "severity": float(obs.infestation_level or 0) / 100.0,
        "created_at": format_rfc3339(obs.record_date) if obs.record_date else None,
    }


@router.delete(
    "/{observation_id}",
    summary="Delete observation",
    description="Delete an observation record.",
)
async def delete_observation(
    observation_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete an observation."""
    result = await db.execute(
        select(InfestationRecord).where(InfestationRecord.infestation_id == observation_id)
    )
    obs = result.scalar_one_or_none()
    
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    
    await db.delete(obs)
    await db.commit()
    
    return {"message": f"Observation {observation_id} deleted"}
