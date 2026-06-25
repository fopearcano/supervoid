from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.models.enums import (
    ProductionPriority,
    ProductionTaskType,
    ProductionTrack,
    StudioDivision,
)


class TemplateMilestoneRead(BaseModel):
    key: str
    title: str
    offset_days: int


class TemplateTaskRead(BaseModel):
    key: str
    title: str
    track: ProductionTrack
    task_type: ProductionTaskType
    priority: ProductionPriority
    offset_days: int
    milestone: Optional[str]
    depends_on: list[str]
    acceptance_criteria: Optional[str]


class ProductionTemplateRead(BaseModel):
    key: str
    name: str
    division: StudioDivision
    description: str
    milestones: list[TemplateMilestoneRead]
    tasks: list[TemplateTaskRead]


class ApplyTemplateRequest(BaseModel):
    template_key: str
    base_date: Optional[date] = None
    story_world_id: Optional[str] = None


class ApplyTemplateResult(BaseModel):
    template_key: str
    work_id: str
    milestone_ids: list[str]
    task_ids: list[str]
    dependency_ids: list[str]
