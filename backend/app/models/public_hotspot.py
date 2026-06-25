from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import HotspotType

if TYPE_CHECKING:
    from app.models.published_page import PublishedPage
    from app.models.published_panel import PublishedPanel


class PublicHotspot(BaseEntity, table=True):
    """A curated, public-only interactive region on a page (or panel).

    Coordinates are percentages of the page box (0–100) so the overlay scales
    responsively across the reader's modes and viewports. When
    ``published_panel_id`` is set the hotspot belongs to a panel (cinematic
    mode) rather than the page as a whole.
    """

    __tablename__ = "public_hotspots"

    published_page_id: str = Field(foreign_key="published_pages.id", index=True)
    published_panel_id: Optional[str] = Field(
        default=None, foreign_key="published_panels.id", index=True
    )

    type: HotspotType = Field(default=HotspotType.INFO, index=True)
    x: float = Field(default=0.0, ge=0, le=100)
    y: float = Field(default=0.0, ge=0, le=100)
    width: float = Field(default=10.0, ge=0, le=100)
    height: float = Field(default=10.0, ge=0, le=100)

    title: str = Field(max_length=300)
    content: Optional[str] = Field(default=None)
    target_url: Optional[str] = Field(default=None, max_length=600)

    audio_track_id: Optional[str] = Field(
        default=None, foreign_key="public_media_assets.id"
    )
    video_id: Optional[str] = Field(
        default=None, foreign_key="public_media_assets.id"
    )

    page: "PublishedPage" = Relationship(back_populates="hotspots")
    panel: Optional["PublishedPanel"] = Relationship(back_populates="hotspots")
