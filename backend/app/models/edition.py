"""Editions and distribution packages.

An ``Edition`` is a concrete, sellable manifestation of a Work — a format /
language / territory with its own identifier, dimensions, price, files and
metadata. It connects to the existing ``ProductionRecord`` (kept intact for
backward compatibility) rather than replacing it. ``DistributionPackage``
records a generated, validated export package for a channel (ONIX, KDP, Ingram,
GlobalComix, press kit, ARC) — packages and checklists, never direct uploads.
"""
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import (
    DistributionChannel,
    DistributionStatus,
    EditionFormat,
    EditionIdentifierType,
    PackageStatus,
)

if TYPE_CHECKING:
    from app.models.work import Work


class Edition(BaseEntity, table=True):
    """A concrete edition of a Work (format/language/territory)."""

    __tablename__ = "editions"

    work_id: str = Field(foreign_key="works.id", index=True)
    manuscript_id: Optional[str] = Field(
        default=None, foreign_key="manuscripts.id", index=True
    )
    # Connects to the existing production summary without replacing it.
    production_record_id: Optional[str] = Field(
        default=None, foreign_key="production_records.id", index=True
    )

    title: Optional[str] = Field(default=None, max_length=300)
    format: EditionFormat = Field(default=EditionFormat.TRADE_PAPERBACK, index=True)
    language: str = Field(default="en", max_length=40, index=True)
    territory: str = Field(default="World", max_length=100, index=True)
    imprint: Optional[str] = Field(default=None, max_length=200)

    identifier: Optional[str] = Field(default=None, max_length=40, index=True)
    identifier_type: EditionIdentifierType = Field(
        default=EditionIdentifierType.NONE, index=True
    )

    # Dimensions.
    trim_size: Optional[str] = Field(default=None, max_length=40)  # e.g. "6x9in"
    width_mm: Optional[float] = Field(default=None, ge=0)
    height_mm: Optional[float] = Field(default=None, ge=0)
    spine_mm: Optional[float] = Field(default=None, ge=0)
    page_count: Optional[int] = Field(default=None, ge=0)

    price: Optional[Decimal] = Field(
        default=None, max_digits=10, decimal_places=2, ge=0
    )
    currency: str = Field(default="USD", max_length=3)
    publication_date: Optional[date] = Field(default=None, index=True)

    distribution_status: DistributionStatus = Field(
        default=DistributionStatus.PLANNED, index=True
    )

    # Files: list of {role, asset_id?, path?, format} dicts. Metadata: free-form
    # catalogue metadata (description, keywords, categories/BISAC, contributors,
    # age rating, reading direction, …).
    files: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    edition_metadata: dict = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    notes: Optional[str] = Field(default=None)

    work: "Work" = Relationship(back_populates="editions")
    distribution_packages: list["DistributionPackage"] = Relationship(
        back_populates="edition",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class DistributionPackage(BaseEntity, table=True):
    """A generated, validated export package for a distribution channel.

    The manifest and checklist are persisted; the package is *prepared and
    validated*, not uploaded. Real uploads would require a separate, tested
    adapter (see the integration hub).
    """

    __tablename__ = "distribution_packages"

    edition_id: str = Field(foreign_key="editions.id", index=True)
    channel: DistributionChannel = Field(index=True)
    status: PackageStatus = Field(default=PackageStatus.GENERATED, index=True)

    manifest: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    checklist: list = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    validation: dict = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    notes: Optional[str] = Field(default=None)
    generated_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )

    edition: "Edition" = Relationship(back_populates="distribution_packages")
