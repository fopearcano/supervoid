from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity, utcnow
from app.models.enums import (
    ChainOfTitleType,
    OptionPeriodStatus,
    RightScope,
    RightsEvidenceKind,
    RightsExclusivity,
    RightsWindowStatus,
    RightStatus,
)

if TYPE_CHECKING:
    from app.models.work import Work


class Rights(BaseEntity, table=True):
    """A rights profile for a Work, scoped to a territory and language.

    Each licensable right (print, ebook, audiobook, film, adaptation,
    merchandising) carries its own ``RightStatus``. The profile is deepened for
    an operating studio: a headline term window, exclusivity, sublicensing,
    reversion, and multi-territory/language coverage — with term windows, option
    periods, chain of title, evidence and status history held as child rows.
    """

    __tablename__ = "rights"

    work_id: str = Field(foreign_key="works.id", index=True)

    territory: str = Field(default="World", max_length=100, index=True)
    language: str = Field(default="all", max_length=40, index=True)

    print_rights: RightStatus = Field(default=RightStatus.AVAILABLE)
    ebook_rights: RightStatus = Field(default=RightStatus.AVAILABLE)
    audiobook_rights: RightStatus = Field(default=RightStatus.AVAILABLE)
    film_rights: RightStatus = Field(default=RightStatus.AVAILABLE)
    adaptation_rights: RightStatus = Field(default=RightStatus.AVAILABLE)
    merchandising_rights: RightStatus = Field(default=RightStatus.AVAILABLE)

    holder: Optional[str] = Field(default=None, max_length=200)
    expiration_date: Optional[date] = Field(default=None, index=True)
    notes: Optional[str] = Field(default=None)

    # --- depth (additive; existing rows stay valid) ---
    # The party that holds the right, optionally linked to a CRM contact.
    rights_holder: Optional[str] = Field(default=None, max_length=200)
    rights_holder_contact_id: Optional[str] = Field(
        default=None, foreign_key="contacts.id", index=True
    )
    exclusivity: RightsExclusivity = Field(
        default=RightsExclusivity.UNSPECIFIED, index=True
    )
    # Headline term window (granular per-scope windows live in RightsWindow).
    term_start_date: Optional[date] = Field(default=None, index=True)
    term_end_date: Optional[date] = Field(default=None, index=True)

    sublicensable: bool = Field(default=False, index=True)
    sublicense_terms: Optional[str] = Field(default=None)

    reversion_conditions: Optional[str] = Field(default=None)
    reversion_date: Optional[date] = Field(default=None, index=True)

    adaptation_constraints: Optional[str] = Field(default=None)
    merchandising_constraints: Optional[str] = Field(default=None)

    # Multi-territory / multi-language coverage beyond the headline pair.
    territory_coverage: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    language_coverage: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )

    # Date to surface a reminder for this profile (in addition to derived ones).
    reminder_date: Optional[date] = Field(default=None, index=True)

    work: "Work" = Relationship(back_populates="rights")
    windows: list["RightsWindow"] = Relationship(
        back_populates="rights",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    options: list["RightsOption"] = Relationship(
        back_populates="rights",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    chain_of_title: list["ChainOfTitleEntry"] = Relationship(
        back_populates="rights",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    evidence: list["RightsEvidence"] = Relationship(
        back_populates="rights",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    status_history: list["RightsStatusHistory"] = Relationship(
        back_populates="rights",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class RightsWindow(BaseEntity, table=True):
    """A time-bounded grant of a specific right in a territory/language."""

    __tablename__ = "rights_windows"

    rights_id: str = Field(foreign_key="rights.id", index=True)
    scope: RightScope = Field(default=RightScope.ALL, index=True)
    territory: str = Field(default="World", max_length=100)
    language: str = Field(default="all", max_length=40)
    exclusivity: RightsExclusivity = Field(default=RightsExclusivity.UNSPECIFIED)
    starts_on: Optional[date] = Field(default=None, index=True)
    ends_on: Optional[date] = Field(default=None, index=True)
    status: RightsWindowStatus = Field(default=RightsWindowStatus.PLANNED, index=True)
    notes: Optional[str] = Field(default=None)

    rights: "Rights" = Relationship(back_populates="windows")


class RightsOption(BaseEntity, table=True):
    """An option period during which a counterparty may take up a right."""

    __tablename__ = "rights_options"

    rights_id: str = Field(foreign_key="rights.id", index=True)
    label: str = Field(max_length=200)
    scope: RightScope = Field(default=RightScope.ALL, index=True)
    holder: Optional[str] = Field(default=None, max_length=200)
    option_start: Optional[date] = Field(default=None)
    option_end: Optional[date] = Field(default=None, index=True)
    exercise_deadline: Optional[date] = Field(default=None, index=True)
    fee: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2, ge=0)
    currency: str = Field(default="USD", max_length=3)
    status: OptionPeriodStatus = Field(default=OptionPeriodStatus.OPEN, index=True)
    notes: Optional[str] = Field(default=None)

    rights: "Rights" = Relationship(back_populates="options")


class ChainOfTitleEntry(BaseEntity, table=True):
    """One link in the chain of title — how the right moved between parties."""

    __tablename__ = "chain_of_title_entries"

    rights_id: str = Field(foreign_key="rights.id", index=True)
    position: int = Field(default=0, index=True)
    entry_type: ChainOfTitleType = Field(
        default=ChainOfTitleType.ASSIGNMENT, index=True
    )
    from_party: Optional[str] = Field(default=None, max_length=200)
    to_party: Optional[str] = Field(default=None, max_length=200)
    effective_date: Optional[date] = Field(default=None, index=True)
    instrument: Optional[str] = Field(default=None, max_length=300)
    reference: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = Field(default=None)

    rights: "Rights" = Relationship(back_populates="chain_of_title")


class RightsEvidence(BaseEntity, table=True):
    """A document or artefact evidencing a right (optionally a stored asset)."""

    __tablename__ = "rights_evidence"

    rights_id: str = Field(foreign_key="rights.id", index=True)
    kind: RightsEvidenceKind = Field(default=RightsEvidenceKind.CONTRACT, index=True)
    title: str = Field(max_length=300)
    description: Optional[str] = Field(default=None)
    asset_id: Optional[str] = Field(default=None, foreign_key="assets.id", index=True)
    document_ref: Optional[str] = Field(default=None, max_length=400)
    dated_on: Optional[date] = Field(default=None)

    rights: "Rights" = Relationship(back_populates="evidence")


class RightsStatusHistory(BaseEntity, table=True):
    """An append-only record of a status change for a right scope."""

    __tablename__ = "rights_status_history"

    rights_id: str = Field(foreign_key="rights.id", index=True)
    scope: RightScope = Field(default=RightScope.ALL, index=True)
    from_status: Optional[RightStatus] = Field(default=None)
    to_status: RightStatus = Field(default=RightStatus.AVAILABLE)
    note: Optional[str] = Field(default=None)
    changed_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    changed_at: datetime = Field(default_factory=utcnow)

    rights: "Rights" = Relationship(back_populates="status_history")
