from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity

if TYPE_CHECKING:
    from app.models.public_hotspot import PublicHotspot
    from app.models.published_chapter import PublishedChapter


class PublishedPage(BaseEntity, table=True):
    __tablename__ = "published_pages"

    published_chapter_id: str = Field(
        foreign_key="published_chapters.id", index=True
    )

    page_number: int = Field(default=1, ge=0, index=True)
    image_path: str = Field(max_length=600)
    alt_text: Optional[str] = Field(default=None, max_length=600)
    width: Optional[int] = Field(default=None, ge=0)
    height: Optional[int] = Field(default=None, ge=0)

    music_track_id: Optional[str] = Field(
        default=None, foreign_key="public_media_assets.id"
    )
    video_overlay_id: Optional[str] = Field(
        default=None, foreign_key="public_media_assets.id"
    )

    chapter: "PublishedChapter" = Relationship(back_populates="pages")
    hotspots: list["PublicHotspot"] = Relationship(back_populates="page")
