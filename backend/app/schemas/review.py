from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import ReviewVerdict
from app.schemas._common import TimestampedRead


class ReviewCreate(BaseModel):
    manuscript_id: str
    work_id: Optional[str] = None
    reviewer_id: str
    verdict: ReviewVerdict
    summary: str = Field(min_length=1)
    written_report: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    literary_quality_score: Optional[int] = Field(default=None, ge=1, le=5)
    visual_potential_score: Optional[int] = Field(default=None, ge=1, le=5)
    market_potential_score: Optional[int] = Field(default=None, ge=1, le=5)
    originality_score: Optional[int] = Field(default=None, ge=1, le=5)
    editorial_effort_score: Optional[int] = Field(default=None, ge=1, le=5)


class ReviewUpdate(BaseModel):
    work_id: Optional[str] = None
    verdict: Optional[ReviewVerdict] = None
    summary: Optional[str] = Field(default=None, min_length=1)
    written_report: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    literary_quality_score: Optional[int] = Field(default=None, ge=1, le=5)
    visual_potential_score: Optional[int] = Field(default=None, ge=1, le=5)
    market_potential_score: Optional[int] = Field(default=None, ge=1, le=5)
    originality_score: Optional[int] = Field(default=None, ge=1, le=5)
    editorial_effort_score: Optional[int] = Field(default=None, ge=1, le=5)


class ReviewRead(TimestampedRead):
    manuscript_id: str
    work_id: Optional[str]
    reviewer_id: str
    reviewer_name: Optional[str] = None
    verdict: ReviewVerdict
    summary: str
    written_report: Optional[str]
    rating: Optional[int]
    literary_quality_score: Optional[int]
    visual_potential_score: Optional[int]
    market_potential_score: Optional[int]
    originality_score: Optional[int]
    editorial_effort_score: Optional[int]
