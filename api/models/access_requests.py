"""Public organization inquiries and administrator review schemas."""

import re
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RequestSector(str, Enum):
    GOVERNMENT = "government"
    COOPERATIVE = "cooperative"
    FARM = "farm"
    RESEARCH = "research"
    BUSINESS = "business"
    OTHER = "other"


class RequestInterest(str, Enum):
    DEMONSTRATION = "demonstration"
    LICENSE = "license"
    SUBSCRIPTION = "subscription"
    UNSURE = "unsure"


class RequestStatus(str, Enum):
    NEW = "new"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    CLOSED = "closed"


class AccessRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    submission_id: UUID
    organization: str = Field(min_length=2, max_length=200)
    sector: RequestSector
    contact_name: str = Field(min_length=2, max_length=150)
    email: str = Field(max_length=254)
    phone: str = Field(default="", max_length=50)
    location: str = Field(min_length=2, max_length=200)
    orchard_count: int | None = Field(default=None, ge=0, le=100000)
    interest: RequestInterest
    message: str = Field(min_length=10, max_length=2000)
    consent: Literal[True]
    # A hidden form field helps reject automated submissions without a
    # third-party service or forwarding applicant information elsewhere.
    website: str = Field(default="", max_length=0)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", value):
            raise ValueError("Enter a valid email address.")
        return value


class AccessRequestReceipt(BaseModel):
    reference: str
    created_at: str
    message: str = "Your request has been received. We will contact you using the details you provided."


class AccessRequestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int = Field(ge=1)
    status: RequestStatus
    notes: str = Field(default="", max_length=4000)


class AccessRequestResponse(BaseModel):
    request_id: str
    reference: str
    organization: str
    sector: RequestSector
    contact_name: str
    email: str
    phone: str
    location: str
    orchard_count: int | None
    interest: RequestInterest
    message: str
    status: RequestStatus
    notes: str
    version: int
    consent_version: str
    created_at: str
    updated_at: str
    reviewed_by_user_id: int | None


class AccessRequestList(BaseModel):
    requests: list[AccessRequestResponse]
    total: int
    counts: dict[str, int]
