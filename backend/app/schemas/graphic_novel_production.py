from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import StreamStatus
from app.schemas._common import TimestampedRead

_DEFAULT = StreamStatus.NOT_PLANNED


class GraphicNovelProductionCreate(BaseModel):
    work_id: str
    volume_number: Optional[int] = Field(default=None, ge=0)
    issue_number: Optional[int] = Field(default=None, ge=0)
    script_status: StreamStatus = _DEFAULT
    storyboard_status: StreamStatus = _DEFAULT
    character_design_status: StreamStatus = _DEFAULT
    environment_design_status: StreamStatus = _DEFAULT
    page_layout_status: StreamStatus = _DEFAULT
    lettering_status: StreamStatus = _DEFAULT
    coloring_status: StreamStatus = _DEFAULT
    final_files_status: StreamStatus = _DEFAULT
    notes: Optional[str] = None


class GraphicNovelProductionUpdate(BaseModel):
    volume_number: Optional[int] = Field(default=None, ge=0)
    issue_number: Optional[int] = Field(default=None, ge=0)
    script_status: Optional[StreamStatus] = None
    storyboard_status: Optional[StreamStatus] = None
    character_design_status: Optional[StreamStatus] = None
    environment_design_status: Optional[StreamStatus] = None
    page_layout_status: Optional[StreamStatus] = None
    lettering_status: Optional[StreamStatus] = None
    coloring_status: Optional[StreamStatus] = None
    final_files_status: Optional[StreamStatus] = None
    notes: Optional[str] = None


class GraphicNovelProductionRead(TimestampedRead):
    work_id: str
    volume_number: Optional[int]
    issue_number: Optional[int]
    script_status: StreamStatus
    storyboard_status: StreamStatus
    character_design_status: StreamStatus
    environment_design_status: StreamStatus
    page_layout_status: StreamStatus
    lettering_status: StreamStatus
    coloring_status: StreamStatus
    final_files_status: StreamStatus
    notes: Optional[str]
