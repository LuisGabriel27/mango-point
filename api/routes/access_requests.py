"""Anonymous request submission and administrator-only review endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.core.security import get_current_active_user
from api.models.access_requests import (
    AccessRequestCreate, AccessRequestList, AccessRequestReceipt,
    AccessRequestResponse, AccessRequestUpdate, RequestStatus,
)
from api.services.access_request_service import create_request, list_requests, to_response, update_request
from db.models import AccessRequest, UserAccount, UserRoleEnum


router = APIRouter(prefix="/access-requests", tags=["Organization requests"])


async def require_request_admin(user: UserAccount = Depends(get_current_active_user)):
    if user.role != UserRoleEnum.ADMIN:
        raise HTTPException(403, "Only MangoPoint administrators can review organization requests.")
    if user.user_id <= 0:
        raise HTTPException(503, "Request review requires a saved administrator account and a database connection.")
    return user


@router.post("", status_code=201, response_model=AccessRequestReceipt)
async def submit_request(
    payload: AccessRequestCreate, request: Request, db: AsyncSession = Depends(get_db),
):
    """Save an inquiry. This never creates an account or grants system access."""
    client_address = request.client.host if request.client else "unknown"
    return await create_request(db, payload, client_address)


@router.get("", response_model=AccessRequestList)
async def review_requests(
    status: RequestStatus | None = None,
    search: str = Query(default="", max_length=100),
    limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0),
    _admin: UserAccount = Depends(require_request_admin), db: AsyncSession = Depends(get_db),
):
    return await list_requests(db, status=status, search=search.strip(), limit=limit, offset=offset)


@router.get("/{request_id}", response_model=AccessRequestResponse)
async def get_request(
    request_id: UUID,
    _admin: UserAccount = Depends(require_request_admin), db: AsyncSession = Depends(get_db),
):
    row = await db.get(AccessRequest, str(request_id))
    if row is None:
        raise HTTPException(404, "Request not found.")
    return to_response(row)


@router.patch("/{request_id}", response_model=AccessRequestResponse)
async def review_request(
    request_id: UUID, payload: AccessRequestUpdate,
    admin: UserAccount = Depends(require_request_admin), db: AsyncSession = Depends(get_db),
):
    """Record a review decision and private notes without provisioning access."""
    return await update_request(db, str(request_id), payload, admin.user_id)
