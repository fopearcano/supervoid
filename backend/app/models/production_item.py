from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import (
    DependencyType,
    ProductionItemStatus,
    ProductionPriority,
    ProductionStage,
    ProductionTaskType,
    ProductionTrack,
    StudioDivision,
)

if TYPE_CHECKING:
    from app.models.approval_request import ApprovalRequest
    from app.models.manuscript import Manuscript
    from app.models.production_milestone import ProductionMilestone
    from app.models.story_world import StoryWorld
    from app.models.user import User
    from app.models.work import Work


class ProductionItem(BaseEntity, table=True):
    """A unit of production work.

    Originally a publishing-stage checklist item, it has evolved into a general
    production **task** spanning publishing, graphic novels, film, audio and
    interactive work — while staying backward compatible: the original columns
    (``manuscript_id``, ``stage``, ``status``, ``due_date``, ``notes``,
    ``assignee_id``) and the ``/production-items`` endpoints keep working.

    ``work_id`` is now the primary project relationship; ``manuscript_id`` is
    optional. The richer task surface lives at ``/production-tasks``.
    """

    __tablename__ = "production_items"

    # --- Identity / description (new) ---
    title: Optional[str] = Field(default=None, max_length=300, index=True)
    description: Optional[str] = Field(default=None)

    # --- Project relationships ---
    # work_id is the primary link; manuscript_id is now optional (was required).
    work_id: Optional[str] = Field(default=None, foreign_key="works.id", index=True)
    manuscript_id: Optional[str] = Field(
        default=None, foreign_key="manuscripts.id", index=True
    )
    story_world_id: Optional[str] = Field(
        default=None, foreign_key="story_worlds.id", index=True
    )

    # --- Classification (new) ---
    division: Optional[StudioDivision] = Field(default=None, index=True)
    track: Optional[ProductionTrack] = Field(default=None, index=True)
    task_type: ProductionTaskType = Field(default=ProductionTaskType.TASK, index=True)
    priority: ProductionPriority = Field(default=ProductionPriority.MEDIUM, index=True)

    # --- Legacy publishing stage (kept; now optional for non-publishing work) ---
    stage: Optional[ProductionStage] = Field(default=None, index=True)
    status: ProductionItemStatus = Field(
        default=ProductionItemStatus.PENDING, index=True
    )

    # --- People ---
    assignee_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)
    creator_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)
    reviewer_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)

    # --- Hierarchy & milestone ---
    parent_id: Optional[str] = Field(
        default=None, foreign_key="production_items.id", index=True
    )
    milestone_id: Optional[str] = Field(
        default=None, foreign_key="production_milestones.id", index=True
    )

    # --- Scheduling & effort (new) ---
    start_date: Optional[date] = Field(default=None, index=True)
    due_date: Optional[date] = Field(default=None, index=True)
    completed_date: Optional[date] = Field(default=None, index=True)
    estimated_effort: Optional[float] = Field(default=None, ge=0)
    actual_effort: Optional[float] = Field(default=None, ge=0)

    # --- Workflow detail (new) ---
    blocked_reason: Optional[str] = Field(default=None)
    acceptance_criteria: Optional[str] = Field(default=None)
    deliverable_asset: Optional[str] = Field(default=None, max_length=500)
    revision_number: int = Field(default=0, ge=0)

    notes: Optional[str] = Field(default=None)

    # --- Relationships ---
    manuscript: Optional["Manuscript"] = Relationship(
        back_populates="production_items"
    )
    work: Optional["Work"] = Relationship(back_populates="production_items")
    story_world: Optional["StoryWorld"] = Relationship()

    assignee: Optional["User"] = Relationship(
        back_populates="production_assignments",
        sa_relationship_kwargs={"foreign_keys": "[ProductionItem.assignee_id]"},
    )
    creator: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ProductionItem.creator_id]"},
    )
    reviewer: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ProductionItem.reviewer_id]"},
    )

    parent: Optional["ProductionItem"] = Relationship(
        back_populates="subtasks",
        sa_relationship_kwargs={"remote_side": "ProductionItem.id"},
    )
    subtasks: list["ProductionItem"] = Relationship(back_populates="parent")

    milestone: Optional["ProductionMilestone"] = Relationship(back_populates="tasks")

    approvals: list["ApprovalRequest"] = Relationship(
        back_populates="task",
        sa_relationship_kwargs={"foreign_keys": "[ApprovalRequest.task_id]"},
    )

    @property
    def assignee_name(self) -> Optional[str]:
        return self.assignee.full_name if self.assignee is not None else None

    @property
    def creator_name(self) -> Optional[str]:
        return self.creator.full_name if self.creator is not None else None

    @property
    def reviewer_name(self) -> Optional[str]:
        return self.reviewer.full_name if self.reviewer is not None else None


class ProductionDependency(BaseEntity, table=True):
    """A directed dependency: ``task`` depends on ``depends_on``.

    For ``finish_to_start`` (the default) the predecessor (``depends_on``) must
    reach a terminal state before the dependent (``task``) may be completed.
    """

    __tablename__ = "production_dependencies"

    task_id: str = Field(foreign_key="production_items.id", index=True)
    depends_on_id: str = Field(foreign_key="production_items.id", index=True)
    type: DependencyType = Field(default=DependencyType.FINISH_TO_START, index=True)
    note: Optional[str] = Field(default=None)

    task: "ProductionItem" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ProductionDependency.task_id]"},
    )
    depends_on: "ProductionItem" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[ProductionDependency.depends_on_id]"
        },
    )
