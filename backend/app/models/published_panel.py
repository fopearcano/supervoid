from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import PanelTransition

if TYPE_CHECKING:
    from app.models.public_hotspot import PublicHotspot
    from app.models.published_page import PublishedPage


class PublishedPanel(BaseEntity, table=True):
    """A public, curated panel for cinematic reading.

    Carries the normalised panel rectangle (0..1) from the private
    ``GraphicNovelPanel`` — geometry only, never a private file. The page's
    public image is shown focused on each panel in reading order; everything
    here is public-safe (coordinates, curator-approved caption, public media).
    """

    __tablename__ = "published_panels"

    published_page_id: str = Field(foreign_key="published_pages.id", index=True)

    panel_number: int = Field(default=1, index=True)
    reading_order: int = Field(default=0, index=True)

    # Normalised panel rectangle on the page (0..1).
    x: float = Field(default=0.0, ge=0, le=1)
    y: float = Field(default=0.0, ge=0, le=1)
    width: float = Field(default=1.0, ge=0, le=1)
    height: float = Field(default=1.0, ge=0, le=1)

    # Optional focus crop (0..1); when set the cinematic view frames this rect
    # instead of the panel rectangle.
    focus_x: Optional[float] = Field(default=None, ge=0, le=1)
    focus_y: Optional[float] = Field(default=None, ge=0, le=1)
    focus_width: Optional[float] = Field(default=None, ge=0, le=1)
    focus_height: Optional[float] = Field(default=None, ge=0, le=1)

    transition: PanelTransition = Field(default=PanelTransition.CUT)
    transition_duration_ms: int = Field(default=600, ge=0, le=10000)

    # Curator-approved public text and an accessibility fallback description.
    caption: Optional[str] = Field(default=None)
    alt_text: Optional[str] = Field(default=None, max_length=600)

    # Panel-level audio / video (public media).
    audio_track_id: Optional[str] = Field(
        default=None, foreign_key="public_media_assets.id"
    )
    video_id: Optional[str] = Field(
        default=None, foreign_key="public_media_assets.id"
    )

    # Soft back-reference to the private source panel; never exposed publicly.
    source_panel_id: Optional[str] = Field(default=None, index=True)

    page: "PublishedPage" = Relationship(back_populates="panels")
    hotspots: list["PublicHotspot"] = Relationship(back_populates="panel")
