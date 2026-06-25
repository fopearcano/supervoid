from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import LicenceReviewState, LicenceType
from app.schemas._common import TimestampedRead


class LicenceCreate(BaseModel):
    rights_holder: Optional[str] = Field(default=None, max_length=300)
    licence_type: LicenceType = LicenceType.PROPRIETARY
    source: Optional[str] = Field(default=None, max_length=300)
    territory: Optional[str] = Field(default=None, max_length=200)
    permitted_uses: Optional[str] = None
    attribution_requirements: Optional[str] = None
    expiration_date: Optional[date] = None
    evidence_storage_key: Optional[str] = Field(default=None, max_length=400)
    review_state: LicenceReviewState = LicenceReviewState.NOT_REVIEWED
    notes: Optional[str] = None


class LicenceUpdate(BaseModel):
    rights_holder: Optional[str] = Field(default=None, max_length=300)
    licence_type: Optional[LicenceType] = None
    source: Optional[str] = Field(default=None, max_length=300)
    territory: Optional[str] = Field(default=None, max_length=200)
    permitted_uses: Optional[str] = None
    attribution_requirements: Optional[str] = None
    expiration_date: Optional[date] = None
    evidence_storage_key: Optional[str] = Field(default=None, max_length=400)
    review_state: Optional[LicenceReviewState] = None
    notes: Optional[str] = None


class LicenceRead(TimestampedRead):
    asset_id: str
    rights_holder: Optional[str]
    licence_type: LicenceType
    source: Optional[str]
    territory: Optional[str]
    permitted_uses: Optional[str]
    attribution_requirements: Optional[str]
    expiration_date: Optional[date]
    evidence_storage_key: Optional[str]
    review_state: LicenceReviewState
    notes: Optional[str]


class LicenceWarningRead(BaseModel):
    licence_id: str
    asset_id: str
    licence_type: str
    expiration_date: Optional[str]
    status: str
    days_remaining: Optional[int]
