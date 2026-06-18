from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity

if TYPE_CHECKING:
    from app.models.published_chapter import PublishedChapter
    from app.models.published_work import PublishedWork


class PublishedVolume(BaseEntity, table=True):
    __tablename__ = "published_volumes"

    published_work_id: str = Field(foreign_key="published_works.id", index=True)

    title: str = Field(max_length=300)
    volume_number: int = Field(default=1, ge=0, index=True)
    public_description: Optional[str] = Field(default=None)
    cover_image: Optional[str] = Field(default=None, max_length=600)
    publication_date: Optional[date] = Field(default=None)

    music_track_id: Optional[str] = Field(
        default=None, foreign_key="public_media_assets.id"
    )

    work: "PublishedWork" = Relationship(back_populates="volumes")
    chapters: list["PublishedChapter"] = Relationship(
        back_populates="volume",
        sa_relationship_kwargs={"order_by": "PublishedChapter.chapter_number"},
    )
