from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import MilestoneStatus, StudioDivision

if TYPE_CHECKING:
    from app.models.production_item import ProductionItem
    from app.models.story_world import StoryWorld
    from app.models.work import Work


class ProductionMilestone(BaseEntity, table=True):
    """A significant checkpoint in a Work's production (a delivery, a gate, a
    release). Production tasks can be grouped under a milestone."""

    __tablename__ = "production_milestones"

    title: str = Field(max_length=300, index=True)
    description: Optional[str] = Field(default=None)

    work_id: Optional[str] = Field(default=None, foreign_key="works.id", index=True)
    story_world_id: Optional[str] = Field(
        default=None, foreign_key="story_worlds.id", index=True
    )
    division: Optional[StudioDivision] = Field(default=None, index=True)

    status: MilestoneStatus = Field(default=MilestoneStatus.PLANNED, index=True)
    sequence_order: int = Field(default=0)
    target_date: Optional[date] = Field(default=None, index=True)
    reached_date: Optional[date] = Field(default=None)

    work: Optional["Work"] = Relationship()
    story_world: Optional["StoryWorld"] = Relationship()
    tasks: list["ProductionItem"] = Relationship(back_populates="milestone")
