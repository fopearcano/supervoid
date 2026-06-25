from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    AssetApprovalStatus,
    CameraAngle,
    CameraFraming,
    CurationStatus,
    GNStatus,
    PageSide,
    PanelElementType,
    StreamStatus,
)
from app.schemas._common import TimestampedRead


# --- Volume / Chapter / Sequence -------------------------------------------


class VolumeCreate(BaseModel):
    volume_number: int = 1
    title: Optional[str] = Field(default=None, max_length=300)
    synopsis: Optional[str] = None
    status: GNStatus = GNStatus.PLANNED
    position: int = 0


class VolumeUpdate(BaseModel):
    volume_number: Optional[int] = None
    title: Optional[str] = Field(default=None, max_length=300)
    synopsis: Optional[str] = None
    status: Optional[GNStatus] = None
    position: Optional[int] = None


class VolumeRead(TimestampedRead):
    production_id: str
    volume_number: int
    title: Optional[str]
    synopsis: Optional[str]
    status: GNStatus
    position: int


class ChapterCreate(BaseModel):
    chapter_number: int = 1
    title: Optional[str] = Field(default=None, max_length=300)
    synopsis: Optional[str] = None
    status: GNStatus = GNStatus.PLANNED
    position: int = 0


class ChapterUpdate(BaseModel):
    chapter_number: Optional[int] = None
    title: Optional[str] = Field(default=None, max_length=300)
    synopsis: Optional[str] = None
    status: Optional[GNStatus] = None
    position: Optional[int] = None


class ChapterRead(TimestampedRead):
    volume_id: str
    chapter_number: int
    title: Optional[str]
    synopsis: Optional[str]
    status: GNStatus
    position: int


class SequenceCreate(BaseModel):
    sequence_number: int = 1
    title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = None
    status: GNStatus = GNStatus.PLANNED
    position: int = 0


class SequenceUpdate(BaseModel):
    sequence_number: Optional[int] = None
    title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = None
    status: Optional[GNStatus] = None
    position: Optional[int] = None


class SequenceRead(TimestampedRead):
    chapter_id: str
    sequence_number: int
    title: Optional[str]
    description: Optional[str]
    status: GNStatus
    position: int


# --- Panel element ---------------------------------------------------------


class PanelElementCreate(BaseModel):
    element_type: PanelElementType
    entity_id: Optional[str] = None
    text_content: Optional[str] = None
    asset_version_id: Optional[str] = None
    label: Optional[str] = Field(default=None, max_length=200)
    x: Optional[float] = Field(default=None, ge=0, le=1)
    y: Optional[float] = Field(default=None, ge=0, le=1)
    width: Optional[float] = Field(default=None, ge=0, le=1)
    height: Optional[float] = Field(default=None, ge=0, le=1)
    position: int = 0


class PanelElementUpdate(BaseModel):
    element_type: Optional[PanelElementType] = None
    entity_id: Optional[str] = None
    text_content: Optional[str] = None
    asset_version_id: Optional[str] = None
    label: Optional[str] = Field(default=None, max_length=200)
    x: Optional[float] = Field(default=None, ge=0, le=1)
    y: Optional[float] = Field(default=None, ge=0, le=1)
    width: Optional[float] = Field(default=None, ge=0, le=1)
    height: Optional[float] = Field(default=None, ge=0, le=1)
    position: Optional[int] = None


class PanelElementRead(TimestampedRead):
    panel_id: str
    element_type: PanelElementType
    entity_id: Optional[str]
    entity_name: Optional[str] = None
    text_content: Optional[str]
    asset_version_id: Optional[str]
    label: Optional[str]
    x: Optional[float]
    y: Optional[float]
    width: Optional[float]
    height: Optional[float]
    position: int


# --- Panel -----------------------------------------------------------------


class PanelCreate(BaseModel):
    panel_number: int = 1
    position: int = 0
    status: GNStatus = GNStatus.PLANNED
    x: float = Field(default=0.0, ge=0, le=1)
    y: float = Field(default=0.0, ge=0, le=1)
    width: float = Field(default=1.0, ge=0, le=1)
    height: float = Field(default=1.0, ge=0, le=1)
    script_beat: Optional[str] = None
    dialogue: Optional[str] = None
    captions: Optional[str] = None
    sound_effects: Optional[str] = None
    camera_framing: Optional[CameraFraming] = None
    camera_angle: Optional[CameraAngle] = None
    lens_metadata: Optional[str] = Field(default=None, max_length=200)
    continuity_notes: Optional[str] = None
    storyboard_asset_version_id: Optional[str] = None
    final_asset_version_id: Optional[str] = None
    approval_status: AssetApprovalStatus = AssetApprovalStatus.DRAFT


class PanelUpdate(BaseModel):
    panel_number: Optional[int] = None
    position: Optional[int] = None
    status: Optional[GNStatus] = None
    x: Optional[float] = Field(default=None, ge=0, le=1)
    y: Optional[float] = Field(default=None, ge=0, le=1)
    width: Optional[float] = Field(default=None, ge=0, le=1)
    height: Optional[float] = Field(default=None, ge=0, le=1)
    script_beat: Optional[str] = None
    dialogue: Optional[str] = None
    captions: Optional[str] = None
    sound_effects: Optional[str] = None
    camera_framing: Optional[CameraFraming] = None
    camera_angle: Optional[CameraAngle] = None
    lens_metadata: Optional[str] = Field(default=None, max_length=200)
    continuity_notes: Optional[str] = None
    storyboard_asset_version_id: Optional[str] = None
    final_asset_version_id: Optional[str] = None
    approval_status: Optional[AssetApprovalStatus] = None


class PanelRead(TimestampedRead):
    page_id: str
    panel_number: int
    position: int
    status: GNStatus
    x: float
    y: float
    width: float
    height: float
    script_beat: Optional[str]
    dialogue: Optional[str]
    captions: Optional[str]
    sound_effects: Optional[str]
    camera_framing: Optional[CameraFraming]
    camera_angle: Optional[CameraAngle]
    lens_metadata: Optional[str]
    continuity_notes: Optional[str]
    storyboard_asset_version_id: Optional[str]
    final_asset_version_id: Optional[str]
    approval_status: AssetApprovalStatus


class PanelDetail(PanelRead):
    elements: list[PanelElementRead] = Field(default_factory=list)


# --- Page ------------------------------------------------------------------


class PageEntityLinkCreate(BaseModel):
    entity_id: str
    role: Optional[str] = Field(default=None, max_length=120)
    position: int = 0


class PageEntityLinkRead(TimestampedRead):
    page_id: str
    entity_id: str
    entity_name: Optional[str] = None
    role: Optional[str]
    position: int


class PageCreate(BaseModel):
    page_number: int = 1
    position: int = 0
    status: GNStatus = GNStatus.PLANNED
    spread_id: Optional[str] = None
    page_side: PageSide = PageSide.SINGLE
    script: Optional[str] = None
    visual_brief: Optional[str] = None
    dialogue_summary: Optional[str] = None
    lettering_status: StreamStatus = StreamStatus.NOT_PLANNED
    colour_status: StreamStatus = StreamStatus.NOT_PLANNED
    final_status: StreamStatus = StreamStatus.NOT_PLANNED
    print_width_mm: Optional[float] = Field(default=None, ge=0)
    print_height_mm: Optional[float] = Field(default=None, ge=0)
    bleed_mm: Optional[float] = Field(default=None, ge=0)
    safe_area_mm: Optional[float] = Field(default=None, ge=0)
    master_asset_id: Optional[str] = None


class PageUpdate(BaseModel):
    page_number: Optional[int] = None
    position: Optional[int] = None
    status: Optional[GNStatus] = None
    spread_id: Optional[str] = None
    page_side: Optional[PageSide] = None
    script: Optional[str] = None
    visual_brief: Optional[str] = None
    dialogue_summary: Optional[str] = None
    lettering_status: Optional[StreamStatus] = None
    colour_status: Optional[StreamStatus] = None
    final_status: Optional[StreamStatus] = None
    print_width_mm: Optional[float] = Field(default=None, ge=0)
    print_height_mm: Optional[float] = Field(default=None, ge=0)
    bleed_mm: Optional[float] = Field(default=None, ge=0)
    safe_area_mm: Optional[float] = Field(default=None, ge=0)
    master_asset_id: Optional[str] = None
    curation_status: Optional[CurationStatus] = None
    published_page_id: Optional[str] = None


class PageRead(TimestampedRead):
    sequence_id: str
    page_number: int
    position: int
    status: GNStatus
    spread_id: Optional[str]
    page_side: PageSide
    script: Optional[str]
    visual_brief: Optional[str]
    dialogue_summary: Optional[str]
    lettering_status: StreamStatus
    colour_status: StreamStatus
    final_status: StreamStatus
    print_width_mm: Optional[float]
    print_height_mm: Optional[float]
    bleed_mm: Optional[float]
    safe_area_mm: Optional[float]
    master_asset_id: Optional[str]
    curation_status: CurationStatus
    published_page_id: Optional[str]
    panel_count: int = 0


class PageDetail(PageRead):
    panels: list[PanelDetail] = Field(default_factory=list)
    entity_links: list[PageEntityLinkRead] = Field(default_factory=list)


# --- shared / production-level ----------------------------------------------


class ReorderRequest(BaseModel):
    ordered_ids: list[str]


class ProductionProgressRead(BaseModel):
    pages_total: int
    pages_complete: int
    panels_total: int
    panels_approved: int
    lettering_complete: int
    colour_complete: int
    final_complete: int
    overall_pct: float
    panel_approval_pct: float


class ValidationIssueRead(BaseModel):
    level: str
    target_id: str
    message: str


class ReadinessRead(BaseModel):
    print_ready: bool
    digital_ready: bool
    print_issues: list[str]
    digital_issues: list[str]


class ComparisonRow(BaseModel):
    panel_id: str
    panel_number: int
    storyboard: Optional[dict]
    final: Optional[dict]


class CurationHandoffRead(BaseModel):
    committed: bool
    eligible: list[dict]
    ineligible: list[dict]


class TreeNode(BaseModel):
    id: str
    label: str
    kind: str
    status: str
    position: int
    children: list["TreeNode"] = Field(default_factory=list)
