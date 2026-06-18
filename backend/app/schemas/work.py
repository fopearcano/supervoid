from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import WorkStatus, WorkType
from app.schemas._common import TimestampedRead


class WorkCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    work_type: WorkType = Field(default=WorkType.BOOK)
    genre: Optional[str] = Field(default=None, max_length=100)
    status: WorkStatus = Field(default=WorkStatus.CONCEPT)
    synopsis: Optional[str] = None
    internal_pitch: Optional[str] = None
    target_audience: Optional[str] = Field(default=None, max_length=300)
    language: str = Field(default="en", max_length=10)
    word_count: Optional[int] = Field(default=None, ge=0)
    page_count: Optional[int] = Field(default=None, ge=0)
    author_id: str


class WorkUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    work_type: Optional[WorkType] = None
    genre: Optional[str] = Field(default=None, max_length=100)
    status: Optional[WorkStatus] = None
    synopsis: Optional[str] = None
    internal_pitch: Optional[str] = None
    target_audience: Optional[str] = Field(default=None, max_length=300)
    language: Optional[str] = Field(default=None, max_length=10)
    word_count: Optional[int] = Field(default=None, ge=0)
    page_count: Optional[int] = Field(default=None, ge=0)
    author_id: Optional[str] = None


class WorkRead(TimestampedRead):
    title: str
    subtitle: Optional[str]
    work_type: WorkType
    genre: Optional[str]
    status: WorkStatus
    synopsis: Optional[str]
    internal_pitch: Optional[str]
    target_audience: Optional[str]
    language: str
    word_count: Optional[int]
    page_count: Optional[int]
    author_id: str
