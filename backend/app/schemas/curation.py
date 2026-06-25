"""Private admin (CMS) schemas for curating the public reader projection.

Unlike ``schemas/public_reader`` (public-safe reads only), these expose the full
editable surface — status, scheduling, soft source references, approval and
history — and are reached exclusively through the authenticated curation API.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    HotspotType,
    MediaAssetType,
    PanelTransition,
    PublicationAction,
    PublicationApprovalStatus,
    PublishedStatus,
)
from app.schemas._common import TimestampedRead


# --- PublishedWork ---------------------------------------------------------


class PublishedWorkCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    slug: Optional[str] = Field(default=None, max_length=200)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    public_synopsis: Optional[str] = None
    cover_image: Optional[str] = Field(default=None, max_length=600)
    author_credit: Optional[str] = Field(default=None, max_length=300)
    artist_credit: Optional[str] = Field(default=None, max_length=300)
    tags: list[str] = Field(default_factory=list)


class CreateFromWorkRequest(BaseModel):
    source_work_id: str


class PublishedWorkUpdate(BaseModel):
    slug: Optional[str] = Field(default=None, max_length=200)
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    public_synopsis: Optional[str] = None
    cover_image: Optional[str] = Field(default=None, max_length=600)
    author_credit: Optional[str] = Field(default=None, max_length=300)
    artist_credit: Optional[str] = Field(default=None, max_length=300)
    tags: Optional[list[str]] = None
    music_track_id: Optional[str] = None
    video_intro_id: Optional[str] = None


class PublishedWorkAdminRead(TimestampedRead):
    source_work_id: Optional[str]
    slug: str
    title: str
    subtitle: Optional[str]
    public_synopsis: Optional[str]
    cover_image: Optional[str]
    status: PublishedStatus
    publication_date: Optional[date]
    author_credit: Optional[str]
    artist_credit: Optional[str]
    tags: list[str]
    music_track_id: Optional[str]
    video_intro_id: Optional[str]


# --- lifecycle -------------------------------------------------------------


class ScheduleRequest(BaseModel):
    publication_date: date
    note: Optional[str] = None


class SetVisibilityRequest(BaseModel):
    # PUBLISHED is reached only through the gated publish endpoint; visibility
    # here covers the non-public states.
    status: PublishedStatus
    note: Optional[str] = None


class ApprovalDecisionRequest(BaseModel):
    note: Optional[str] = None


class ValidationIssue(BaseModel):
    code: str
    severity: str  # "error" | "warning"
    message: str
    target_id: Optional[str] = None


class PublicationValidationRead(BaseModel):
    ok: bool
    errors: int
    warnings: int
    issues: list[ValidationIssue]


class PublicationApprovalRead(TimestampedRead):
    published_work_id: str
    status: PublicationApprovalStatus
    requested_by_id: Optional[str]
    decided_by_id: Optional[str]
    decided_at: Optional[datetime]
    validation: dict
    note: Optional[str]


class PublicationEventRead(TimestampedRead):
    published_work_id: str
    action: PublicationAction
    actor_id: Optional[str]
    from_status: Optional[PublishedStatus]
    to_status: Optional[PublishedStatus]
    note: Optional[str]
    detail: dict


# --- PublishedVolume -------------------------------------------------------


class PublishedVolumeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    volume_number: int = Field(default=1, ge=0)
    public_description: Optional[str] = None
    cover_image: Optional[str] = Field(default=None, max_length=600)
    publication_date: Optional[date] = None
    music_track_id: Optional[str] = None


class PublishedVolumeUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    volume_number: Optional[int] = Field(default=None, ge=0)
    public_description: Optional[str] = None
    cover_image: Optional[str] = Field(default=None, max_length=600)
    publication_date: Optional[date] = None
    music_track_id: Optional[str] = None


class PublishedVolumeAdminRead(TimestampedRead):
    published_work_id: str
    title: str
    volume_number: int
    public_description: Optional[str]
    cover_image: Optional[str]
    publication_date: Optional[date]
    music_track_id: Optional[str]


# --- PublishedChapter ------------------------------------------------------


class PublishedChapterCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    chapter_number: int = Field(default=1, ge=0)
    public_description: Optional[str] = None
    music_track_id: Optional[str] = None
    video_intro_id: Optional[str] = None


class PublishedChapterUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    chapter_number: Optional[int] = Field(default=None, ge=0)
    public_description: Optional[str] = None
    music_track_id: Optional[str] = None
    video_intro_id: Optional[str] = None


class PublishedChapterAdminRead(TimestampedRead):
    published_volume_id: str
    title: str
    chapter_number: int
    public_description: Optional[str]
    music_track_id: Optional[str]
    video_intro_id: Optional[str]


# --- PublishedPage ---------------------------------------------------------


class PublishedPageCreate(BaseModel):
    page_number: int = Field(default=1, ge=0)
    image_path: str = Field(min_length=1, max_length=600)
    alt_text: Optional[str] = Field(default=None, max_length=600)
    width: Optional[int] = Field(default=None, ge=0)
    height: Optional[int] = Field(default=None, ge=0)
    music_track_id: Optional[str] = None
    video_overlay_id: Optional[str] = None


class PublishedPageUpdate(BaseModel):
    page_number: Optional[int] = Field(default=None, ge=0)
    image_path: Optional[str] = Field(default=None, min_length=1, max_length=600)
    alt_text: Optional[str] = Field(default=None, max_length=600)
    width: Optional[int] = Field(default=None, ge=0)
    height: Optional[int] = Field(default=None, ge=0)
    music_track_id: Optional[str] = None
    video_overlay_id: Optional[str] = None


class PublishedPageAdminRead(TimestampedRead):
    published_chapter_id: str
    page_number: int
    image_path: str
    alt_text: Optional[str]
    width: Optional[int]
    height: Optional[int]
    music_track_id: Optional[str]
    video_overlay_id: Optional[str]
    source_gn_page_id: Optional[str]
    source_asset_version_id: Optional[str]


# --- PublishedPanel --------------------------------------------------------


class PublishedPanelCreate(BaseModel):
    panel_number: int = Field(default=1, ge=0)
    reading_order: int = Field(default=0, ge=0)
    x: float = Field(default=0.0, ge=0, le=1)
    y: float = Field(default=0.0, ge=0, le=1)
    width: float = Field(default=1.0, ge=0, le=1)
    height: float = Field(default=1.0, ge=0, le=1)
    focus_x: Optional[float] = Field(default=None, ge=0, le=1)
    focus_y: Optional[float] = Field(default=None, ge=0, le=1)
    focus_width: Optional[float] = Field(default=None, ge=0, le=1)
    focus_height: Optional[float] = Field(default=None, ge=0, le=1)
    transition: PanelTransition = PanelTransition.CUT
    transition_duration_ms: int = Field(default=600, ge=0, le=10000)
    caption: Optional[str] = None
    alt_text: Optional[str] = Field(default=None, max_length=600)
    audio_track_id: Optional[str] = None
    video_id: Optional[str] = None


class PublishedPanelUpdate(BaseModel):
    panel_number: Optional[int] = Field(default=None, ge=0)
    reading_order: Optional[int] = Field(default=None, ge=0)
    x: Optional[float] = Field(default=None, ge=0, le=1)
    y: Optional[float] = Field(default=None, ge=0, le=1)
    width: Optional[float] = Field(default=None, ge=0, le=1)
    height: Optional[float] = Field(default=None, ge=0, le=1)
    focus_x: Optional[float] = Field(default=None, ge=0, le=1)
    focus_y: Optional[float] = Field(default=None, ge=0, le=1)
    focus_width: Optional[float] = Field(default=None, ge=0, le=1)
    focus_height: Optional[float] = Field(default=None, ge=0, le=1)
    transition: Optional[PanelTransition] = None
    transition_duration_ms: Optional[int] = Field(default=None, ge=0, le=10000)
    caption: Optional[str] = None
    alt_text: Optional[str] = Field(default=None, max_length=600)
    audio_track_id: Optional[str] = None
    video_id: Optional[str] = None


class PublishedPanelAdminRead(TimestampedRead):
    published_page_id: str
    panel_number: int
    reading_order: int
    x: float
    y: float
    width: float
    height: float
    focus_x: Optional[float]
    focus_y: Optional[float]
    focus_width: Optional[float]
    focus_height: Optional[float]
    transition: PanelTransition
    transition_duration_ms: int
    caption: Optional[str]
    alt_text: Optional[str]
    audio_track_id: Optional[str]
    video_id: Optional[str]
    source_panel_id: Optional[str]


# --- PublicMediaAsset ------------------------------------------------------


class PublicMediaAssetCreate(BaseModel):
    type: MediaAssetType = MediaAssetType.IMAGE
    title: str = Field(min_length=1, max_length=300)
    file_path: str = Field(min_length=1, max_length=600)
    poster_image: Optional[str] = Field(default=None, max_length=600)
    duration: Optional[float] = Field(default=None, ge=0)
    loop: bool = False
    credits: Optional[str] = Field(default=None, max_length=400)
    public_visibility: bool = True


class PublicMediaAssetUpdate(BaseModel):
    type: Optional[MediaAssetType] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    file_path: Optional[str] = Field(default=None, min_length=1, max_length=600)
    poster_image: Optional[str] = Field(default=None, max_length=600)
    duration: Optional[float] = Field(default=None, ge=0)
    loop: Optional[bool] = None
    credits: Optional[str] = Field(default=None, max_length=400)
    public_visibility: Optional[bool] = None


class PublicMediaAssetAdminRead(TimestampedRead):
    type: MediaAssetType
    title: str
    file_path: str
    poster_image: Optional[str]
    duration: Optional[float]
    loop: bool
    credits: Optional[str]
    public_visibility: bool


# --- PublicHotspot ---------------------------------------------------------


class PublicHotspotCreate(BaseModel):
    type: HotspotType = HotspotType.INFO
    published_panel_id: Optional[str] = None
    x: float = Field(default=0.0, ge=0, le=100)
    y: float = Field(default=0.0, ge=0, le=100)
    width: float = Field(default=10.0, ge=0, le=100)
    height: float = Field(default=10.0, ge=0, le=100)
    title: str = Field(min_length=1, max_length=300)
    content: Optional[str] = None
    target_url: Optional[str] = Field(default=None, max_length=600)
    audio_track_id: Optional[str] = None
    video_id: Optional[str] = None


class PublicHotspotUpdate(BaseModel):
    type: Optional[HotspotType] = None
    published_panel_id: Optional[str] = None
    x: Optional[float] = Field(default=None, ge=0, le=100)
    y: Optional[float] = Field(default=None, ge=0, le=100)
    width: Optional[float] = Field(default=None, ge=0, le=100)
    height: Optional[float] = Field(default=None, ge=0, le=100)
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    content: Optional[str] = None
    target_url: Optional[str] = Field(default=None, max_length=600)
    audio_track_id: Optional[str] = None
    video_id: Optional[str] = None


class PublicHotspotAdminRead(TimestampedRead):
    published_page_id: str
    published_panel_id: Optional[str]
    type: HotspotType
    x: float
    y: float
    width: float
    height: float
    title: str
    content: Optional[str]
    target_url: Optional[str]
    audio_track_id: Optional[str]
    video_id: Optional[str]


# --- controlled hand-off ---------------------------------------------------


class PageHandoffRequest(BaseModel):
    """A controlled hand-off from a private GraphicNovelPage to a public page.

    ``public_media_asset_id`` is the **explicitly selected public derivative** —
    a private file is never used. ``source_asset_version_id`` records which
    private asset version the derivative came from, for licence/provenance
    validation.
    """

    gn_page_id: str
    public_media_asset_id: str
    chapter_id: str
    page_number: Optional[int] = Field(default=None, ge=0)
    alt_text: Optional[str] = Field(default=None, max_length=600)
    import_panels: bool = True
    source_asset_version_id: Optional[str] = None
