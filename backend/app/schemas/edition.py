from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    DistributionChannel,
    DistributionStatus,
    EditionFormat,
    EditionIdentifierType,
    PackageStatus,
)
from app.schemas._common import TimestampedRead


# --- Edition ---------------------------------------------------------------


class EditionCreate(BaseModel):
    work_id: str
    manuscript_id: Optional[str] = None
    production_record_id: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=300)
    format: EditionFormat = EditionFormat.TRADE_PAPERBACK
    language: str = Field(default="en", max_length=40)
    territory: str = Field(default="World", max_length=100)
    imprint: Optional[str] = Field(default=None, max_length=200)
    identifier: Optional[str] = Field(default=None, max_length=40)
    identifier_type: EditionIdentifierType = EditionIdentifierType.NONE
    trim_size: Optional[str] = Field(default=None, max_length=40)
    width_mm: Optional[float] = Field(default=None, ge=0)
    height_mm: Optional[float] = Field(default=None, ge=0)
    spine_mm: Optional[float] = Field(default=None, ge=0)
    page_count: Optional[int] = Field(default=None, ge=0)
    price: Optional[Decimal] = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    publication_date: Optional[date] = None
    distribution_status: DistributionStatus = DistributionStatus.PLANNED
    files: list[dict] = Field(default_factory=list)
    edition_metadata: dict = Field(default_factory=dict)
    notes: Optional[str] = None


class EditionUpdate(BaseModel):
    manuscript_id: Optional[str] = None
    production_record_id: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=300)
    format: Optional[EditionFormat] = None
    language: Optional[str] = Field(default=None, max_length=40)
    territory: Optional[str] = Field(default=None, max_length=100)
    imprint: Optional[str] = Field(default=None, max_length=200)
    identifier: Optional[str] = Field(default=None, max_length=40)
    identifier_type: Optional[EditionIdentifierType] = None
    trim_size: Optional[str] = Field(default=None, max_length=40)
    width_mm: Optional[float] = Field(default=None, ge=0)
    height_mm: Optional[float] = Field(default=None, ge=0)
    spine_mm: Optional[float] = Field(default=None, ge=0)
    page_count: Optional[int] = Field(default=None, ge=0)
    price: Optional[Decimal] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    publication_date: Optional[date] = None
    distribution_status: Optional[DistributionStatus] = None
    files: Optional[list[dict]] = None
    edition_metadata: Optional[dict] = None
    notes: Optional[str] = None


class EditionRead(TimestampedRead):
    work_id: str
    manuscript_id: Optional[str]
    production_record_id: Optional[str]
    title: Optional[str]
    format: EditionFormat
    language: str
    territory: str
    imprint: Optional[str]
    identifier: Optional[str]
    identifier_type: EditionIdentifierType
    trim_size: Optional[str]
    width_mm: Optional[float]
    height_mm: Optional[float]
    spine_mm: Optional[float]
    page_count: Optional[int]
    price: Optional[Decimal]
    currency: str
    publication_date: Optional[date]
    distribution_status: DistributionStatus
    files: list[dict]
    edition_metadata: dict
    notes: Optional[str]


# --- Distribution packages -------------------------------------------------


class DistributionPackageRead(TimestampedRead):
    edition_id: str
    channel: DistributionChannel
    status: PackageStatus
    manifest: dict
    checklist: list[dict]
    validation: dict
    notes: Optional[str]
    generated_by_id: Optional[str]


class EditionDetail(EditionRead):
    packages: list[DistributionPackageRead] = Field(default_factory=list)


class GeneratePackageRequest(BaseModel):
    notes: Optional[str] = None
