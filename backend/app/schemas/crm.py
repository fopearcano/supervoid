from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    ConsentStatus,
    ContactRoleKind,
    InteractionDirection,
    InteractionKind,
    OpportunityKind,
    OpportunityStatus,
    OrganizationKind,
)
from app.schemas._common import TimestampedRead


# --- Organization ----------------------------------------------------------


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    kind: OrganizationKind = OrganizationKind.OTHER
    website: Optional[str] = Field(default=None, max_length=400)
    email: Optional[str] = Field(default=None, max_length=240)
    phone: Optional[str] = Field(default=None, max_length=80)
    country: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=120)
    source_of_introduction: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = None


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=240)
    kind: Optional[OrganizationKind] = None
    website: Optional[str] = Field(default=None, max_length=400)
    email: Optional[str] = Field(default=None, max_length=240)
    phone: Optional[str] = Field(default=None, max_length=80)
    country: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=120)
    source_of_introduction: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = None


class OrganizationRead(TimestampedRead):
    name: str
    kind: OrganizationKind
    website: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    country: Optional[str]
    city: Optional[str]
    source_of_introduction: Optional[str]
    notes: Optional[str]


# --- Contact tags ----------------------------------------------------------


class ContactTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: Optional[str] = Field(default=None, max_length=20)
    description: Optional[str] = Field(default=None, max_length=300)


class ContactTagRead(TimestampedRead):
    name: str
    slug: str
    color: Optional[str]
    description: Optional[str]


# --- Contact roles ---------------------------------------------------------


class ContactRoleCreate(BaseModel):
    role: ContactRoleKind
    organization_id: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=200)
    is_primary: bool = False
    notes: Optional[str] = None


class ContactRoleRead(TimestampedRead):
    contact_id: str
    role: ContactRoleKind
    organization_id: Optional[str]
    title: Optional[str]
    is_primary: bool
    notes: Optional[str]


# --- Contact ---------------------------------------------------------------


class ContactCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=240)
    organization_id: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=240)
    phone: Optional[str] = Field(default=None, max_length=80)
    country: Optional[str] = Field(default=None, max_length=100)
    source_of_introduction: Optional[str] = Field(default=None, max_length=300)
    interests: list[str] = Field(default_factory=list)
    relevant_work_ids: list[str] = Field(default_factory=list)
    follow_up_date: Optional[date] = None
    consent_status: ConsentStatus = ConsentStatus.UNKNOWN
    do_not_contact: bool = False
    preferred_channel: Optional[str] = Field(default=None, max_length=60)
    consent_notes: Optional[str] = None
    notes: Optional[str] = None


class ContactUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=240)
    organization_id: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=240)
    phone: Optional[str] = Field(default=None, max_length=80)
    country: Optional[str] = Field(default=None, max_length=100)
    source_of_introduction: Optional[str] = Field(default=None, max_length=300)
    interests: Optional[list[str]] = None
    relevant_work_ids: Optional[list[str]] = None
    follow_up_date: Optional[date] = None
    consent_status: Optional[ConsentStatus] = None
    do_not_contact: Optional[bool] = None
    preferred_channel: Optional[str] = Field(default=None, max_length=60)
    consent_notes: Optional[str] = None
    notes: Optional[str] = None


class ContactRead(TimestampedRead):
    full_name: str
    organization_id: Optional[str]
    title: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    country: Optional[str]
    source_of_introduction: Optional[str]
    interests: list[str]
    relevant_work_ids: list[str]
    follow_up_date: Optional[date]
    consent_status: ConsentStatus
    do_not_contact: bool
    preferred_channel: Optional[str]
    consent_notes: Optional[str]
    notes: Optional[str]


class ContactDetail(ContactRead):
    organization: Optional[OrganizationRead] = None
    roles: list[ContactRoleRead] = Field(default_factory=list)
    tags: list[ContactTagRead] = Field(default_factory=list)


class TagAssignRequest(BaseModel):
    tag_id: str


# --- Interaction -----------------------------------------------------------


class InteractionCreate(BaseModel):
    contact_id: Optional[str] = None
    organization_id: Optional[str] = None
    kind: InteractionKind = InteractionKind.NOTE
    direction: InteractionDirection = InteractionDirection.OUTBOUND
    subject: Optional[str] = Field(default=None, max_length=300)
    body: Optional[str] = None
    occurred_at: Optional[datetime] = None
    work_id: Optional[str] = None
    follow_up_date: Optional[date] = None
    asset_id: Optional[str] = None
    attachment_ref: Optional[str] = Field(default=None, max_length=400)


class InteractionUpdate(BaseModel):
    kind: Optional[InteractionKind] = None
    direction: Optional[InteractionDirection] = None
    subject: Optional[str] = Field(default=None, max_length=300)
    body: Optional[str] = None
    occurred_at: Optional[datetime] = None
    work_id: Optional[str] = None
    follow_up_date: Optional[date] = None
    asset_id: Optional[str] = None
    attachment_ref: Optional[str] = Field(default=None, max_length=400)


class InteractionRead(TimestampedRead):
    contact_id: Optional[str]
    organization_id: Optional[str]
    kind: InteractionKind
    direction: InteractionDirection
    subject: Optional[str]
    body: Optional[str]
    occurred_at: datetime
    work_id: Optional[str]
    follow_up_date: Optional[date]
    asset_id: Optional[str]
    attachment_ref: Optional[str]
    created_by_id: Optional[str]


# --- Opportunity -----------------------------------------------------------


class OpportunityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    kind: OpportunityKind = OpportunityKind.OTHER
    status: OpportunityStatus = OpportunityStatus.LEAD
    organization_id: Optional[str] = None
    contact_id: Optional[str] = None
    work_id: Optional[str] = None
    value: Optional[Decimal] = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    expected_close_date: Optional[date] = None
    source: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = None


class OpportunityUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    kind: Optional[OpportunityKind] = None
    status: Optional[OpportunityStatus] = None
    organization_id: Optional[str] = None
    contact_id: Optional[str] = None
    work_id: Optional[str] = None
    value: Optional[Decimal] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    expected_close_date: Optional[date] = None
    source: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = None


class OpportunityRead(TimestampedRead):
    title: str
    kind: OpportunityKind
    status: OpportunityStatus
    organization_id: Optional[str]
    contact_id: Optional[str]
    work_id: Optional[str]
    value: Optional[Decimal]
    currency: str
    expected_close_date: Optional[date]
    source: Optional[str]
    owner_id: Optional[str]
    notes: Optional[str]
