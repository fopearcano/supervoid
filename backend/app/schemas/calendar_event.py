from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import CalendarEventStatus, CalendarEventType
from app.schemas._common import TimestampedRead


class PublishingCalendarEventCreate(BaseModel):
    work_id: Optional[str] = None
    title: str = Field(min_length=1, max_length=300)
    event_type: CalendarEventType = CalendarEventType.OTHER
    date: date
    description: Optional[str] = None
    status: CalendarEventStatus = CalendarEventStatus.PLANNED


class PublishingCalendarEventUpdate(BaseModel):
    work_id: Optional[str] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    event_type: Optional[CalendarEventType] = None
    date: Optional[date] = None
    description: Optional[str] = None
    status: Optional[CalendarEventStatus] = None


class PublishingCalendarEventRead(TimestampedRead):
    work_id: Optional[str]
    title: str
    event_type: CalendarEventType
    date: date
    description: Optional[str]
    status: CalendarEventStatus
