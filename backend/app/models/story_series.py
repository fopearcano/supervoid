from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import StorySeriesStatus

if TYPE_CHECKING:
    from app.models.story_world import StoryWorld
    from app.models.work import Work


class StorySeries(BaseEntity, table=True):
    """An ordered series within a StoryWorld (a trilogy, a comic run, a season
    arc). Works belong to a series via ``story_series_id``.
    """

    __tablename__ = "story_series"

    story_world_id: str = Field(foreign_key="story_worlds.id", index=True)

    title: str = Field(max_length=300, index=True)
    description: Optional[str] = Field(default=None)
    sequence_order: int = Field(default=0, index=True)
    status: StorySeriesStatus = Field(default=StorySeriesStatus.PLANNED, index=True)

    world: "StoryWorld" = Relationship(back_populates="series")
    works: list["Work"] = Relationship(
        back_populates="story_series",
        sa_relationship_kwargs={"order_by": "Work.series_order"},
    )
