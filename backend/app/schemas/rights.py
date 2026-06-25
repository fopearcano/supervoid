from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    ChainOfTitleType,
    OptionPeriodStatus,
    RightScope,
    RightsEvidenceKind,
    RightsExclusivity,
    RightsWindowStatus,
    RightStatus,
)
from app.schemas._common import TimestampedRead


# --- Rights profile --------------------------------------------------------


class RightsCreate(BaseModel):
    work_id: str
    territory: str = Field(default="World", max_length=100)
    language: str = Field(default="all", max_length=40)
    print_rights: RightStatus = RightStatus.AVAILABLE
    ebook_rights: RightStatus = RightStatus.AVAILABLE
    audiobook_rights: RightStatus = RightStatus.AVAILABLE
    film_rights: RightStatus = RightStatus.AVAILABLE
    adaptation_rights: RightStatus = RightStatus.AVAILABLE
    merchandising_rights: RightStatus = RightStatus.AVAILABLE
    holder: Optional[str] = Field(default=None, max_length=200)
    expiration_date: Optional[date] = None
    notes: Optional[str] = None
    # depth
    rights_holder: Optional[str] = Field(default=None, max_length=200)
    rights_holder_contact_id: Optional[str] = None
    exclusivity: RightsExclusivity = RightsExclusivity.UNSPECIFIED
    term_start_date: Optional[date] = None
    term_end_date: Optional[date] = None
    sublicensable: bool = False
    sublicense_terms: Optional[str] = None
    reversion_conditions: Optional[str] = None
    reversion_date: Optional[date] = None
    adaptation_constraints: Optional[str] = None
    merchandising_constraints: Optional[str] = None
    territory_coverage: list[str] = Field(default_factory=list)
    language_coverage: list[str] = Field(default_factory=list)
    reminder_date: Optional[date] = None


class RightsUpdate(BaseModel):
    territory: Optional[str] = Field(default=None, max_length=100)
    language: Optional[str] = Field(default=None, max_length=40)
    print_rights: Optional[RightStatus] = None
    ebook_rights: Optional[RightStatus] = None
    audiobook_rights: Optional[RightStatus] = None
    film_rights: Optional[RightStatus] = None
    adaptation_rights: Optional[RightStatus] = None
    merchandising_rights: Optional[RightStatus] = None
    holder: Optional[str] = Field(default=None, max_length=200)
    expiration_date: Optional[date] = None
    notes: Optional[str] = None
    rights_holder: Optional[str] = Field(default=None, max_length=200)
    rights_holder_contact_id: Optional[str] = None
    exclusivity: Optional[RightsExclusivity] = None
    term_start_date: Optional[date] = None
    term_end_date: Optional[date] = None
    sublicensable: Optional[bool] = None
    sublicense_terms: Optional[str] = None
    reversion_conditions: Optional[str] = None
    reversion_date: Optional[date] = None
    adaptation_constraints: Optional[str] = None
    merchandising_constraints: Optional[str] = None
    territory_coverage: Optional[list[str]] = None
    language_coverage: Optional[list[str]] = None
    reminder_date: Optional[date] = None


class RightsRead(TimestampedRead):
    work_id: str
    territory: str
    language: str
    print_rights: RightStatus
    ebook_rights: RightStatus
    audiobook_rights: RightStatus
    film_rights: RightStatus
    adaptation_rights: RightStatus
    merchandising_rights: RightStatus
    holder: Optional[str]
    expiration_date: Optional[date]
    notes: Optional[str]
    rights_holder: Optional[str]
    rights_holder_contact_id: Optional[str]
    exclusivity: RightsExclusivity
    term_start_date: Optional[date]
    term_end_date: Optional[date]
    sublicensable: bool
    sublicense_terms: Optional[str]
    reversion_conditions: Optional[str]
    reversion_date: Optional[date]
    adaptation_constraints: Optional[str]
    merchandising_constraints: Optional[str]
    territory_coverage: list[str]
    language_coverage: list[str]
    reminder_date: Optional[date]


# --- Term windows ----------------------------------------------------------


class RightsWindowCreate(BaseModel):
    scope: RightScope = RightScope.ALL
    territory: str = Field(default="World", max_length=100)
    language: str = Field(default="all", max_length=40)
    exclusivity: RightsExclusivity = RightsExclusivity.UNSPECIFIED
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    status: RightsWindowStatus = RightsWindowStatus.PLANNED
    notes: Optional[str] = None


class RightsWindowRead(TimestampedRead):
    rights_id: str
    scope: RightScope
    territory: str
    language: str
    exclusivity: RightsExclusivity
    starts_on: Optional[date]
    ends_on: Optional[date]
    status: RightsWindowStatus
    notes: Optional[str]


# --- Option periods --------------------------------------------------------


class RightsOptionCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    scope: RightScope = RightScope.ALL
    holder: Optional[str] = Field(default=None, max_length=200)
    option_start: Optional[date] = None
    option_end: Optional[date] = None
    exercise_deadline: Optional[date] = None
    fee: Optional[Decimal] = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    status: OptionPeriodStatus = OptionPeriodStatus.OPEN
    notes: Optional[str] = None


class RightsOptionRead(TimestampedRead):
    rights_id: str
    label: str
    scope: RightScope
    holder: Optional[str]
    option_start: Optional[date]
    option_end: Optional[date]
    exercise_deadline: Optional[date]
    fee: Optional[Decimal]
    currency: str
    status: OptionPeriodStatus
    notes: Optional[str]


# --- Chain of title --------------------------------------------------------


class ChainOfTitleCreate(BaseModel):
    position: int = 0
    entry_type: ChainOfTitleType = ChainOfTitleType.ASSIGNMENT
    from_party: Optional[str] = Field(default=None, max_length=200)
    to_party: Optional[str] = Field(default=None, max_length=200)
    effective_date: Optional[date] = None
    instrument: Optional[str] = Field(default=None, max_length=300)
    reference: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = None


class ChainOfTitleRead(TimestampedRead):
    rights_id: str
    position: int
    entry_type: ChainOfTitleType
    from_party: Optional[str]
    to_party: Optional[str]
    effective_date: Optional[date]
    instrument: Optional[str]
    reference: Optional[str]
    notes: Optional[str]


# --- Evidence --------------------------------------------------------------


class RightsEvidenceCreate(BaseModel):
    kind: RightsEvidenceKind = RightsEvidenceKind.CONTRACT
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    asset_id: Optional[str] = None
    document_ref: Optional[str] = Field(default=None, max_length=400)
    dated_on: Optional[date] = None


class RightsEvidenceRead(TimestampedRead):
    rights_id: str
    kind: RightsEvidenceKind
    title: str
    description: Optional[str]
    asset_id: Optional[str]
    document_ref: Optional[str]
    dated_on: Optional[date]


# --- Status history --------------------------------------------------------


class RightsStatusHistoryCreate(BaseModel):
    scope: RightScope = RightScope.ALL
    from_status: Optional[RightStatus] = None
    to_status: RightStatus
    note: Optional[str] = None


class RightsStatusHistoryRead(TimestampedRead):
    rights_id: str
    scope: RightScope
    from_status: Optional[RightStatus]
    to_status: RightStatus
    note: Optional[str]
    changed_by_id: Optional[str]
    changed_at: datetime


# --- Detail (profile + children) -------------------------------------------


class RightsDetail(RightsRead):
    windows: list[RightsWindowRead] = Field(default_factory=list)
    options: list[RightsOptionRead] = Field(default_factory=list)
    chain_of_title: list[ChainOfTitleRead] = Field(default_factory=list)
    evidence: list[RightsEvidenceRead] = Field(default_factory=list)
    status_history: list[RightsStatusHistoryRead] = Field(default_factory=list)


# --- Reminders / warnings --------------------------------------------------


class RightsWarningRead(BaseModel):
    source: str
    source_id: str
    work_id: Optional[str]
    kind: str
    scope: Optional[str]
    due_date: str
    days_remaining: int
    status: str
    message: str
