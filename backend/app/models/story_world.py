from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import StoryWorldStatus

if TYPE_CHECKING:
    from app.models.author import Author
    from app.models.story_series import StorySeries
    from app.models.work import Work


class StoryWorld(BaseEntity, table=True):
    """An intellectual property / narrative universe — the top of the studio
    domain. A StoryWorld groups series and Works across every medium and
    division. Works still own production; the world owns identity and canon.
    """

    __tablename__ = "story_worlds"

    name: str = Field(max_length=300, index=True)
    slug: str = Field(max_length=200, unique=True, index=True)
    description: Optional[str] = Field(default=None)
    canon_summary: Optional[str] = Field(default=None)
    status: StoryWorldStatus = Field(default=StoryWorldStatus.DEVELOPING, index=True)
    visual_identity_notes: Optional[str] = Field(default=None)
    default_language: str = Field(default="en", max_length=10)

    # Creative owner of the IP (an Author). Nullable and decoupled so a world
    # can exist before a creator record does.
    owner_id: Optional[str] = Field(
        default=None, foreign_key="authors.id", index=True
    )

    # Optional parent world (e.g. a shared meta-universe containing sub-worlds).
    parent_id: Optional[str] = Field(
        default=None, foreign_key="story_worlds.id", index=True
    )

    owner: Optional["Author"] = Relationship(back_populates="owned_story_worlds")
    parent: Optional["StoryWorld"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "StoryWorld.id"},
    )
    children: list["StoryWorld"] = Relationship(back_populates="parent")
    series: list["StorySeries"] = Relationship(
        back_populates="world",
        sa_relationship_kwargs={"order_by": "StorySeries.sequence_order"},
    )
    works: list["Work"] = Relationship(back_populates="story_world")
