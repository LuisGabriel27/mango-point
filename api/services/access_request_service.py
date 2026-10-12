"""Durable intake, retry protection and private inquiry review."""

import hashlib
import hmac
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text, update

from api.core.config import settings
from api.models.access_requests import (
    AccessRequestCreate, AccessRequestList, AccessRequestReceipt,
    AccessRequestResponse, AccessRequestUpdate, RequestStatus,
)
from db.models import AccessRequest
from utils.datetime_utils import format_rfc3339, utcnow_naive


def to_response(row: AccessRequest) -> AccessRequestResponse:
    fields = {
        name: getattr(row, name)
        for name in AccessRequestResponse.model_fields
        if name not in {"created_at", "updated_at"}
    }
    return AccessRequestResponse(
        **fields, created_at=format_rfc3339(row.created_at),
        updated_at=format_rfc3339(row.updated_at),
    )


def receipt(row: AccessRequest) -> AccessRequestReceipt:
    return AccessRequestReceipt(
        reference=row.reference, created_at=format_rfc3339(row.created_at),
    )


async def create_request(db, payload: AccessRequestCreate, client_address: str):
    secret = (settings.AUTH_SECRET_KEY or "").strip()
    if not secret:
        raise HTTPException(503, "Request intake is temporarily unavailable. Please try again later.")
    client_hash = hmac.new(secret.encode(), client_address.encode(), hashlib.sha256).hexdigest()
    values = payload.model_dump(mode="json", exclude={"submission_id", "consent", "website"})
    payload_hash = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    request_id = str(payload.submission_id)

    # Serialize same-client submissions across workers. Quotas and accepted
    # request IDs survive process restarts; retrying a saved submission is free.
    if db.bind.dialect.name == "postgresql":
        request_lock = int.from_bytes(payload.submission_id.bytes[:8], "big", signed=True)
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": request_lock})
        lock_key = int.from_bytes(bytes.fromhex(client_hash[:16]), "big", signed=True)
        await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    existing = await db.get(AccessRequest, request_id)
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise HTTPException(409, "This submission was already received with different details. Start a new request.")
        return receipt(existing)

    recent_count = await db.scalar(select(func.count()).select_from(AccessRequest).where(
        AccessRequest.client_hash == client_hash,
        AccessRequest.created_at >= utcnow_naive() - timedelta(hours=1),
    ))
    if int(recent_count or 0) >= settings.ACCESS_REQUEST_LIMIT_PER_HOUR:
        raise HTTPException(429, "Too many requests. Please try again in an hour.", headers={"Retry-After": "3600"})

    now = utcnow_naive()
    row = AccessRequest(
        **values, request_id=request_id, reference=f"MP-{payload.submission_id.hex[:12].upper()}",
        payload_hash=payload_hash, client_hash=client_hash, status="new", notes="",
        version=1, consent_version="access-inquiry-v1", created_at=now, updated_at=now,
    )
    db.add(row)
    await db.commit()
    return receipt(row)


async def list_requests(db, *, status=None, search="", limit=25, offset=0):
    filters = []
    if status is not None:
        filters.append(AccessRequest.status == status.value)
    if search:
        filters.append(or_(*(
            column.icontains(search, autoescape=True)
            for column in (AccessRequest.organization, AccessRequest.contact_name,
                           AccessRequest.email, AccessRequest.reference)
        )))
    query = select(AccessRequest).where(*filters).order_by(
        AccessRequest.created_at.desc(), AccessRequest.request_id,
    ).limit(limit).offset(offset)
    rows = (await db.execute(query)).scalars().all()
    total = await db.scalar(select(func.count()).select_from(AccessRequest).where(*filters))
    groups = (await db.execute(select(AccessRequest.status, func.count()).group_by(AccessRequest.status))).all()
    counts = {item.value: 0 for item in RequestStatus}
    counts.update({group[0]: group[1] for group in groups})
    return AccessRequestList(requests=[to_response(row) for row in rows], total=total, counts=counts)


async def update_request(db, request_id: str, payload: AccessRequestUpdate, reviewer_id: int):
    row = await db.get(AccessRequest, request_id)
    if row is None:
        raise HTTPException(404, "Request not found.")
    result = await db.execute(update(AccessRequest).where(
        AccessRequest.request_id == request_id, AccessRequest.version == payload.expected_version,
    ).values(
        status=payload.status.value, notes=payload.notes, version=payload.expected_version + 1,
        reviewed_by_user_id=reviewer_id, updated_at=utcnow_naive(),
    ).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(409, "This request changed since you opened it. Reload it before saving.")
    await db.commit()
    await db.refresh(row)
    return to_response(row)
