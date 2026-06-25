from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import StorySeriesStatus
from app.schemas._common import TimestampedRead


class StorySeriesCreate(BaseModel):
    story_world_id: str
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    sequence_order: int = 0
    status: StorySeriesStatus = StorySeriesStatus.PLANNED


class StorySeriesUpdate(BaseModel):
    story_world_id: Optional[str] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = None
    sequence_order: Optional[int] = None
    status: Optional[StorySeriesStatus] = None


class StorySeriesRead(TimestampedRead):
    story_world_id: str
    title: str
    description: Optional[str]
    sequence_order: int
    status: StorySeriesStatus
