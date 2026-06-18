from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import DraftStatus, WorkflowStatus, WorkType
from app.schemas._common import TimestampedRead


class ManuscriptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    synopsis: Optional[str] = None
    work_type: WorkType = Field(default=WorkType.BOOK)
    genre: Optional[str] = Field(default=None, max_length=100)
    language: str = Field(default="en", max_length=10)
    word_count: Optional[int] = Field(default=None, ge=0)
    status: WorkflowStatus = Field(default=WorkflowStatus.SUBMITTED)
    author_id: str
    work_id: Optional[str] = None
    version: str = Field(default="1", max_length=40)
    draft_status: DraftStatus = Field(default=DraftStatus.OUTLINE)
    submission_date: Optional[date] = None
    file_name: Optional[str] = Field(default=None, max_length=300)
    file_format: Optional[str] = Field(default=None, max_length=40)
    file_path: Optional[str] = Field(default=None, max_length=500)


class ManuscriptUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    synopsis: Optional[str] = None
    work_type: Optional[WorkType] = None
    genre: Optional[str] = Field(default=None, max_length=100)
    language: Optional[str] = Field(default=None, max_length=10)
    word_count: Optional[int] = Field(default=None, ge=0)
    status: Optional[WorkflowStatus] = None
    work_id: Optional[str] = None
    version: Optional[str] = Field(default=None, max_length=40)
    draft_status: Optional[DraftStatus] = None
    submission_date: Optional[date] = None
    file_name: Optional[str] = Field(default=None, max_length=300)
    file_format: Optional[str] = Field(default=None, max_length=40)
    file_path: Optional[str] = Field(default=None, max_length=500)


class ManuscriptRead(TimestampedRead):
    title: str
    subtitle: Optional[str]
    synopsis: Optional[str]
    work_type: WorkType
    genre: Optional[str]
    language: str
    word_count: Optional[int]
    status: WorkflowStatus
    author_id: str
    work_id: Optional[str]
    version: str
    draft_status: DraftStatus
    submission_date: Optional[date]
    file_name: Optional[str]
    file_format: Optional[str]
    file_path: Optional[str]
