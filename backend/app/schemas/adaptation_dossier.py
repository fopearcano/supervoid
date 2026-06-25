from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    AdaptationStatus,
    Medium,
    RightsClearanceState,
    StudioDivision,
)
from app.schemas._common import TimestampedRead
from app.schemas.work import WorkRead


class AdaptationDossierCreate(BaseModel):
    source_work_id: str
    target_work_id: Optional[str] = None
    target_medium: Medium
    target_division: StudioDivision = StudioDivision.PICTURES
    status: AdaptationStatus = AdaptationStatus.PROPOSED
    logline: Optional[str] = None
    format: Optional[str] = Field(default=None, max_length=200)
    intended_scope: Optional[str] = Field(default=None, max_length=200)
    rights_clearance: RightsClearanceState = RightsClearanceState.NOT_STARTED
    creative_notes: Optional[str] = None
    source_revision: Optional[str] = Field(default=None, max_length=120)


class AdaptationDossierUpdate(BaseModel):
    target_work_id: Optional[str] = None
    target_medium: Optional[Medium] = None
    target_division: Optional[StudioDivision] = None
    status: Optional[AdaptationStatus] = None
    logline: Optional[str] = None
    format: Optional[str] = Field(default=None, max_length=200)
    intended_scope: Optional[str] = Field(default=None, max_length=200)
    rights_clearance: Optional[RightsClearanceState] = None
    creative_notes: Optional[str] = None
    source_revision: Optional[str] = Field(default=None, max_length=120)


class AdaptationDossierRead(TimestampedRead):
    source_work_id: str
    source_work_title: Optional[str] = None
    target_work_id: Optional[str]
    target_work_title: Optional[str] = None
    target_medium: Medium
    target_division: StudioDivision
    status: AdaptationStatus
    logline: Optional[str]
    format: Optional[str]
    intended_scope: Optional[str]
    rights_clearance: RightsClearanceState
    creative_notes: Optional[str]
    source_revision: Optional[str]


class WorkTransmediaOverview(BaseModel):
    """A Work-centred view of its IP placement and adaptation web."""

    work: WorkRead
    story_world: Optional["StoryWorldRead"] = None
    story_series: Optional["StorySeriesRead"] = None
    source_work: Optional[WorkRead] = None
    derived_works: list[WorkRead] = []
    adaptation_dossiers: list[AdaptationDossierRead] = []


from app.schemas.story_series import StorySeriesRead  # noqa: E402
from app.schemas.story_world import StoryWorldRead  # noqa: E402

WorkTransmediaOverview.model_rebuild()
