from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import IntegrationPointStatus, IntegrationPointType
from app.schemas._common import TimestampedRead


class IntegrationPointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: IntegrationPointType = IntegrationPointType.OTHER
    status: IntegrationPointStatus = IntegrationPointStatus.PLANNED
    endpoint: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = None


class IntegrationPointUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    type: Optional[IntegrationPointType] = None
    status: Optional[IntegrationPointStatus] = None
    endpoint: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = None


class IntegrationPointRead(TimestampedRead):
    name: str
    type: IntegrationPointType
    status: IntegrationPointStatus
    endpoint: Optional[str]
    notes: Optional[str]
