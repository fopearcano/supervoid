from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import ContractStatus, RightsExclusivity
from app.schemas._common import TimestampedRead


class ContractCreate(BaseModel):
    manuscript_id: str
    work_id: Optional[str] = None
    author_id: str
    status: ContractStatus = ContractStatus.DRAFT
    advance_amount: Optional[Decimal] = Field(default=None, ge=0)
    royalty_rate: Optional[float] = Field(default=None, ge=0, le=1)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    rights_territory: Optional[str] = Field(default=None, max_length=100)
    signed_at: Optional[datetime] = None
    expiration_date: Optional[date] = None
    terms: Optional[str] = None
    # depth
    rights_holder: Optional[str] = Field(default=None, max_length=200)
    exclusivity: RightsExclusivity = RightsExclusivity.UNSPECIFIED
    effective_date: Optional[date] = None
    term_start_date: Optional[date] = None
    term_end_date: Optional[date] = None
    option_start_date: Optional[date] = None
    option_end_date: Optional[date] = None
    option_exercised: bool = False
    reversion_conditions: Optional[str] = None
    reversion_date: Optional[date] = None
    sublicensable: bool = False
    territory_coverage: list[str] = Field(default_factory=list)
    language_coverage: list[str] = Field(default_factory=list)


class ContractUpdate(BaseModel):
    work_id: Optional[str] = None
    status: Optional[ContractStatus] = None
    advance_amount: Optional[Decimal] = Field(default=None, ge=0)
    royalty_rate: Optional[float] = Field(default=None, ge=0, le=1)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    rights_territory: Optional[str] = Field(default=None, max_length=100)
    signed_at: Optional[datetime] = None
    expiration_date: Optional[date] = None
    terms: Optional[str] = None
    rights_holder: Optional[str] = Field(default=None, max_length=200)
    exclusivity: Optional[RightsExclusivity] = None
    effective_date: Optional[date] = None
    term_start_date: Optional[date] = None
    term_end_date: Optional[date] = None
    option_start_date: Optional[date] = None
    option_end_date: Optional[date] = None
    option_exercised: Optional[bool] = None
    reversion_conditions: Optional[str] = None
    reversion_date: Optional[date] = None
    sublicensable: Optional[bool] = None
    territory_coverage: Optional[list[str]] = None
    language_coverage: Optional[list[str]] = None


class ContractRead(TimestampedRead):
    manuscript_id: str
    work_id: Optional[str]
    author_id: str
    status: ContractStatus
    advance_amount: Optional[Decimal]
    royalty_rate: Optional[float]
    currency: str
    rights_territory: Optional[str]
    signed_at: Optional[datetime]
    expiration_date: Optional[date]
    terms: Optional[str]
    rights_holder: Optional[str]
    exclusivity: RightsExclusivity
    effective_date: Optional[date]
    term_start_date: Optional[date]
    term_end_date: Optional[date]
    option_start_date: Optional[date]
    option_end_date: Optional[date]
    option_exercised: bool
    reversion_conditions: Optional[str]
    reversion_date: Optional[date]
    sublicensable: bool
    territory_coverage: list[str]
    language_coverage: list[str]
