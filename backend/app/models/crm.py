"""Relationship memory — a private studio CRM.

Organizations, contacts (with roles and tags), logged interactions and a light
opportunity pipeline. This is a **manual record** of relationships: nothing here
scrapes external sources or sends communication automatically. Consent and
contact preferences are recorded, never assumed.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity, utcnow
from app.models.enums import (
    ConsentStatus,
    ContactRoleKind,
    InteractionDirection,
    InteractionKind,
    OpportunityKind,
    OpportunityStatus,
    OrganizationKind,
)


class Organization(BaseEntity, table=True):
    """A company or body the studio deals with — publisher, distributor,
    printer, festival, agency, media outlet, etc."""

    __tablename__ = "organizations"

    name: str = Field(max_length=240, index=True)
    kind: OrganizationKind = Field(default=OrganizationKind.OTHER, index=True)
    website: Optional[str] = Field(default=None, max_length=400)
    email: Optional[str] = Field(default=None, max_length=240)
    phone: Optional[str] = Field(default=None, max_length=80)
    country: Optional[str] = Field(default=None, max_length=100, index=True)
    city: Optional[str] = Field(default=None, max_length=120)
    source_of_introduction: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = Field(default=None)

    contacts: list["Contact"] = Relationship(back_populates="organization")


class Contact(BaseEntity, table=True):
    """A person the studio knows. Roles, tags, interactions and opportunities
    hang off the contact; consent/preferences gate any outreach (by humans)."""

    __tablename__ = "contacts"

    full_name: str = Field(max_length=240, index=True)
    organization_id: Optional[str] = Field(
        default=None, foreign_key="organizations.id", index=True
    )
    title: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=240, index=True)
    phone: Optional[str] = Field(default=None, max_length=80)
    country: Optional[str] = Field(default=None, max_length=100)

    source_of_introduction: Optional[str] = Field(default=None, max_length=300)
    interests: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    # Works this contact is relevant to (work ids; resolved on read).
    relevant_work_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    follow_up_date: Optional[date] = Field(default=None, index=True)

    # Consent & preferences — recorded, never assumed. ``do_not_contact`` is a
    # hard stop for any human outreach; the system never contacts anyone itself.
    consent_status: ConsentStatus = Field(default=ConsentStatus.UNKNOWN, index=True)
    do_not_contact: bool = Field(default=False, index=True)
    preferred_channel: Optional[str] = Field(default=None, max_length=60)
    consent_notes: Optional[str] = Field(default=None)

    notes: Optional[str] = Field(default=None)

    organization: Optional["Organization"] = Relationship(back_populates="contacts")
    roles: list["ContactRole"] = Relationship(
        back_populates="contact",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    tag_links: list["ContactTagLink"] = Relationship(
        back_populates="contact",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    interactions: list["Interaction"] = Relationship(
        back_populates="contact",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    opportunities: list["Opportunity"] = Relationship(back_populates="contact")


class ContactRole(BaseEntity, table=True):
    """A role a contact plays (a person can be both a journalist and a festival
    organiser). Supports publishers, distributors, printers, journalists,
    reviewers, festivals, translators, artists, agents and collaborators."""

    __tablename__ = "contact_roles"

    contact_id: str = Field(foreign_key="contacts.id", index=True)
    role: ContactRoleKind = Field(default=ContactRoleKind.OTHER, index=True)
    organization_id: Optional[str] = Field(
        default=None, foreign_key="organizations.id", index=True
    )
    title: Optional[str] = Field(default=None, max_length=200)
    is_primary: bool = Field(default=False)
    notes: Optional[str] = Field(default=None)

    contact: "Contact" = Relationship(back_populates="roles")


class Interaction(BaseEntity, table=True):
    """A logged touchpoint — email, call, meeting, event, submission or note.

    Purely a manual record of something that happened (or a note to self). The
    system never sends anything; ``direction`` records who reached out.
    """

    __tablename__ = "interactions"

    contact_id: Optional[str] = Field(
        default=None, foreign_key="contacts.id", index=True
    )
    organization_id: Optional[str] = Field(
        default=None, foreign_key="organizations.id", index=True
    )
    kind: InteractionKind = Field(default=InteractionKind.NOTE, index=True)
    direction: InteractionDirection = Field(
        default=InteractionDirection.OUTBOUND, index=True
    )
    subject: Optional[str] = Field(default=None, max_length=300)
    body: Optional[str] = Field(default=None)
    occurred_at: datetime = Field(default_factory=utcnow, index=True)
    work_id: Optional[str] = Field(default=None, foreign_key="works.id", index=True)
    follow_up_date: Optional[date] = Field(default=None, index=True)

    # Attached evidence: an internal asset and/or an external reference.
    asset_id: Optional[str] = Field(default=None, foreign_key="assets.id", index=True)
    attachment_ref: Optional[str] = Field(default=None, max_length=400)

    created_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )

    contact: Optional["Contact"] = Relationship(back_populates="interactions")


class Opportunity(BaseEntity, table=True):
    """A light pipeline item — a rights sale, co-edition, review, festival
    submission, translation deal, distribution or collaboration in progress."""

    __tablename__ = "opportunities"

    title: str = Field(max_length=300, index=True)
    kind: OpportunityKind = Field(default=OpportunityKind.OTHER, index=True)
    status: OpportunityStatus = Field(default=OpportunityStatus.LEAD, index=True)
    organization_id: Optional[str] = Field(
        default=None, foreign_key="organizations.id", index=True
    )
    contact_id: Optional[str] = Field(
        default=None, foreign_key="contacts.id", index=True
    )
    work_id: Optional[str] = Field(default=None, foreign_key="works.id", index=True)
    value: Optional[Decimal] = Field(
        default=None, max_digits=12, decimal_places=2, ge=0
    )
    currency: str = Field(default="USD", max_length=3)
    expected_close_date: Optional[date] = Field(default=None, index=True)
    source: Optional[str] = Field(default=None, max_length=300)
    owner_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    notes: Optional[str] = Field(default=None)

    contact: Optional["Contact"] = Relationship(back_populates="opportunities")


class ContactTag(BaseEntity, table=True):
    """A reusable label applied to contacts (e.g. 'genre-fit', 'vip', 'lapsed')."""

    __tablename__ = "contact_tags"

    name: str = Field(max_length=80, unique=True, index=True)
    slug: str = Field(max_length=80, unique=True, index=True)
    color: Optional[str] = Field(default=None, max_length=20)
    description: Optional[str] = Field(default=None, max_length=300)

    tag_links: list["ContactTagLink"] = Relationship(
        back_populates="tag",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ContactTagLink(BaseEntity, table=True):
    """Join row attaching a tag to a contact (many-to-many)."""

    __tablename__ = "contact_tag_links"

    contact_id: str = Field(foreign_key="contacts.id", index=True)
    tag_id: str = Field(foreign_key="contact_tags.id", index=True)

    contact: "Contact" = Relationship(back_populates="tag_links")
    tag: "ContactTag" = Relationship(back_populates="tag_links")
