"""Public, read-only schemas for the SUPERVOID Graphic Novel Webviewer.

Every field here is explicitly public. There is intentionally **no** route
from these schemas to private editorial data — no contracts, rights, workflow,
editorial notes, production status, or private files. ``source_work_id`` from
the model is deliberately omitted.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.models.enums import (
    HotspotType,
    MediaAssetType,
    PanelTransition,
    PublishedStatus,
)
from app.schemas._common import ORMModel


class PublicMediaAssetRead(ORMModel):
    id: str
    type: MediaAssetType
    title: str
    file_path: str
    poster_image: Optional[str] = None
    duration: Optional[float] = None
    loop: bool = False
    credits: Optional[str] = None


class PublicHotspotRead(ORMModel):
    id: str
    type: HotspotType
    x: float
    y: float
    width: float
    height: float
    title: str
    content: Optional[str] = None
    target_url: Optional[str] = None
    audio_track: Optional[PublicMediaAssetRead] = None
    video: Optional[PublicMediaAssetRead] = None


class PublishedPanelRead(ORMModel):
    """A public, cinematic panel — normalised geometry and curator-approved
    public content only. Drives panel-by-panel reading."""

    id: str
    panel_number: int
    reading_order: int
    x: float
    y: float
    width: float
    height: float
    focus_x: Optional[float] = None
    focus_y: Optional[float] = None
    focus_width: Optional[float] = None
    focus_height: Optional[float] = None
    transition: PanelTransition
    transition_duration_ms: int
    caption: Optional[str] = None
    alt_text: Optional[str] = None
    audio_track: Optional[PublicMediaAssetRead] = None
    video: Optional[PublicMediaAssetRead] = None
    hotspots: list[PublicHotspotRead] = []


class PublishedPageRead(ORMModel):
    id: str
    page_number: int
    image_path: str
    alt_text: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    music_track: Optional[PublicMediaAssetRead] = None
    video_overlay: Optional[PublicMediaAssetRead] = None
    hotspots: list[PublicHotspotRead] = []
    panels: list[PublishedPanelRead] = []


class PublishedChapterSummary(ORMModel):
    id: str
    title: str
    chapter_number: int
    public_description: Optional[str] = None
    page_count: int = 0


class PublishedChapterRead(PublishedChapterSummary):
    music_track: Optional[PublicMediaAssetRead] = None
    video_intro: Optional[PublicMediaAssetRead] = None


class PublishedVolumeRead(ORMModel):
    id: str
    title: str
    volume_number: int
    public_description: Optional[str] = None
    cover_image: Optional[str] = None
    publication_date: Optional[date] = None
    music_track: Optional[PublicMediaAssetRead] = None
    chapters: list[PublishedChapterSummary] = []


class PublishedWorkSummary(ORMModel):
    id: str
    slug: str
    title: str
    subtitle: Optional[str] = None
    public_synopsis: Optional[str] = None
    cover_image: Optional[str] = None
    status: PublishedStatus
    publication_date: Optional[date] = None
    author_credit: Optional[str] = None
    artist_credit: Optional[str] = None
    tags: list[str] = []


class CatalogueItem(ORMModel):
    """A for-sale entry in the public Bookshop. Public commercial metadata only."""

    id: str
    slug: str
    title: str
    subtitle: Optional[str] = None
    public_synopsis: Optional[str] = None
    cover_image: Optional[str] = None
    author_credit: Optional[str] = None
    artist_credit: Optional[str] = None
    tags: list[str] = []
    price_cents: Optional[int] = None
    currency: str = "EUR"
    buy_url: Optional[str] = None
    format_label: Optional[str] = None


class PublishedWorkDetail(PublishedWorkSummary):
    music_track: Optional[PublicMediaAssetRead] = None
    video_intro: Optional[PublicMediaAssetRead] = None
    volumes: list[PublishedVolumeRead] = []
