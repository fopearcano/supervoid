from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    DependencyType,
    ProductionItemStatus,
    ProductionPriority,
    ProductionStage,
    ProductionTaskType,
    ProductionTrack,
    StudioDivision,
)
from app.schemas._common import TimestampedRead


class ProductionTaskCreate(BaseModel):
    """Create a production task. ``work_id`` is the primary project link; the
    creator is taken from the authenticated user."""

    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    work_id: str
    manuscript_id: Optional[str] = None
    story_world_id: Optional[str] = None
    division: Optional[StudioDivision] = None
    track: Optional[ProductionTrack] = None
    task_type: ProductionTaskType = ProductionTaskType.TASK
    priority: ProductionPriority = ProductionPriority.MEDIUM
    stage: Optional[ProductionStage] = None
    status: ProductionItemStatus = ProductionItemStatus.TODO
    assignee_id: Optional[str] = None
    reviewer_id: Optional[str] = None
    parent_id: Optional[str] = None
    milestone_id: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    estimated_effort: Optional[float] = Field(default=None, ge=0)
    acceptance_criteria: Optional[str] = None
    deliverable_asset: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = None


class ProductionTaskUpdate(BaseModel):
    """Patch a task. ``status`` changes go through validated transitions."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = None
    manuscript_id: Optional[str] = None
    story_world_id: Optional[str] = None
    division: Optional[StudioDivision] = None
    track: Optional[ProductionTrack] = None
    task_type: Optional[ProductionTaskType] = None
    priority: Optional[ProductionPriority] = None
    stage: Optional[ProductionStage] = None
    status: Optional[ProductionItemStatus] = None
    assignee_id: Optional[str] = None
    reviewer_id: Optional[str] = None
    parent_id: Optional[str] = None
    milestone_id: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    estimated_effort: Optional[float] = Field(default=None, ge=0)
    actual_effort: Optional[float] = Field(default=None, ge=0)
    blocked_reason: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    deliverable_asset: Optional[str] = Field(default=None, max_length=500)
    revision_number: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None


class ProductionTaskRead(TimestampedRead):
    title: Optional[str]
    description: Optional[str]
    work_id: Optional[str]
    manuscript_id: Optional[str]
    story_world_id: Optional[str]
    division: Optional[StudioDivision]
    track: Optional[ProductionTrack]
    task_type: ProductionTaskType
    priority: ProductionPriority
    stage: Optional[ProductionStage]
    status: ProductionItemStatus
    assignee_id: Optional[str]
    assignee_name: Optional[str] = None
    creator_id: Optional[str]
    creator_name: Optional[str] = None
    reviewer_id: Optional[str]
    reviewer_name: Optional[str] = None
    parent_id: Optional[str]
    milestone_id: Optional[str]
    start_date: Optional[date]
    due_date: Optional[date]
    completed_date: Optional[date]
    estimated_effort: Optional[float]
    actual_effort: Optional[float]
    blocked_reason: Optional[str]
    acceptance_criteria: Optional[str]
    deliverable_asset: Optional[str]
    revision_number: int
    notes: Optional[str]


class ProductionTaskDetail(ProductionTaskRead):
    """Read plus derived workflow state for a single task."""

    is_blocked: bool = False
    blocked_by_dependencies: bool = False
    unmet_dependency_ids: list[str] = Field(default_factory=list)
    depends_on_ids: list[str] = Field(default_factory=list)
    dependent_ids: list[str] = Field(default_factory=list)
    subtask_count: int = 0
    allowed_transitions: list[ProductionItemStatus] = Field(default_factory=list)


class StatusTransitionRequest(BaseModel):
    to_status: ProductionItemStatus
    note: Optional[str] = None


class DependencyCreate(BaseModel):
    depends_on_id: str
    type: DependencyType = DependencyType.FINISH_TO_START
    note: Optional[str] = None


class DependencyRead(TimestampedRead):
    task_id: str
    depends_on_id: str
    type: DependencyType
    note: Optional[str]
    # Convenience, filled by the router.
    depends_on_title: Optional[str] = None
    depends_on_status: Optional[ProductionItemStatus] = None
    satisfied: Optional[bool] = None


class ProductionActivityRead(TimestampedRead):
    task_id: Optional[str]
    actor_id: Optional[str]
    type: str
    field: Optional[str]
    from_status: Optional[ProductionItemStatus]
    to_status: Optional[ProductionItemStatus]
    summary: Optional[str]
    detail: Optional[str]
