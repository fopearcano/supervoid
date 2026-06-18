from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import ContractStatus
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
