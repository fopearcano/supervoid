from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import MilestoneStatus, StudioDivision
from app.schemas._common import TimestampedRead


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    division: Optional[StudioDivision] = None
    status: MilestoneStatus = MilestoneStatus.PLANNED
    sequence_order: int = 0
    target_date: Optional[date] = None
    reached_date: Optional[date] = None


class MilestoneUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = None
    division: Optional[StudioDivision] = None
    status: Optional[MilestoneStatus] = None
    sequence_order: Optional[int] = None
    target_date: Optional[date] = None
    reached_date: Optional[date] = None


class MilestoneRead(TimestampedRead):
    title: str
    description: Optional[str]
    work_id: Optional[str]
    story_world_id: Optional[str]
    division: Optional[StudioDivision]
    status: MilestoneStatus
    sequence_order: int
    target_date: Optional[date]
    reached_date: Optional[date]
    task_count: Optional[int] = None
