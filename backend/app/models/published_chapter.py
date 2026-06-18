from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity

if TYPE_CHECKING:
    from app.models.published_page import PublishedPage
    from app.models.published_volume import PublishedVolume


class PublishedChapter(BaseEntity, table=True):
    __tablename__ = "published_chapters"

    published_volume_id: str = Field(foreign_key="published_volumes.id", index=True)

    title: str = Field(max_length=300)
    chapter_number: int = Field(default=1, ge=0, index=True)
    public_description: Optional[str] = Field(default=None)

    music_track_id: Optional[str] = Field(
        default=None, foreign_key="public_media_assets.id"
    )
    video_intro_id: Optional[str] = Field(
        default=None, foreign_key="public_media_assets.id"
    )

    volume: "PublishedVolume" = Relationship(back_populates="chapters")
    pages: list["PublishedPage"] = Relationship(
        back_populates="chapter",
        sa_relationship_kwargs={"order_by": "PublishedPage.page_number"},
    )
