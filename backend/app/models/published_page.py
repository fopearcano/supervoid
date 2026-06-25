from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity

if TYPE_CHECKING:
    from app.models.public_hotspot import PublicHotspot
    from app.models.published_chapter import PublishedChapter
    from app.models.published_panel import PublishedPanel


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

    # Hand-off provenance — soft references to the private source, never exposed
    # through the public API. Used only to validate licence/provenance and to
    # record where the public derivative came from.
    source_gn_page_id: Optional[str] = Field(default=None, index=True)
    source_asset_version_id: Optional[str] = Field(default=None, index=True)

    chapter: "PublishedChapter" = Relationship(back_populates="pages")
    hotspots: list["PublicHotspot"] = Relationship(back_populates="page")
    panels: list["PublishedPanel"] = Relationship(
        back_populates="page",
        sa_relationship_kwargs={
            "order_by": "PublishedPanel.reading_order",
            "cascade": "all, delete-orphan",
        },
    )
