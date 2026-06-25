from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    AdaptationStatus,
    AssetApprovalStatus,
    CameraAngle,
    CameraFraming,
    Medium,
    SceneEnvironment,
    SceneTimeOfDay,
    ScreenFormat,
    ScreenProjectStatus,
    ScreenStatus,
    ScreenUnitType,
    ShotMovement,
)
from app.schemas._common import TimestampedRead


# --- promotion / project creation ------------------------------------------


class DossierPromoteRequest(BaseModel):
    """Promote a Work (or graphic novel) into a Pictures adaptation dossier."""

    source_work_id: str
    target_medium: Medium = Medium.FILM
    logline: Optional[str] = None
    format: Optional[str] = Field(default=None, max_length=200)
    intended_scope: Optional[str] = Field(default=None, max_length=200)
    status: AdaptationStatus = AdaptationStatus.OPTIONED


class ProjectFromDossierRequest(BaseModel):
    format: ScreenFormat = ScreenFormat.FILM
    title: Optional[str] = Field(default=None, max_length=300)


# --- project / unit / sequence ---------------------------------------------


class ScreenProjectUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300)
    format: Optional[ScreenFormat] = None
    status: Optional[ScreenProjectStatus] = None
    logline: Optional[str] = None
    synopsis: Optional[str] = None
    notes: Optional[str] = None


class ScreenProjectRead(TimestampedRead):
    dossier_id: str
    source_work_id: Optional[str]
    story_world_id: Optional[str]
    title: str
    format: ScreenFormat
    status: ScreenProjectStatus
    logline: Optional[str]
    synopsis: Optional[str]
    notes: Optional[str]


class ScreenUnitCreate(BaseModel):
    unit_type: ScreenUnitType = ScreenUnitType.REEL
    number: int = 1
    title: Optional[str] = Field(default=None, max_length=300)
    synopsis: Optional[str] = None
    status: ScreenStatus = ScreenStatus.PLANNED
    position: int = 0


class ScreenUnitUpdate(BaseModel):
    unit_type: Optional[ScreenUnitType] = None
    number: Optional[int] = None
    title: Optional[str] = Field(default=None, max_length=300)
    synopsis: Optional[str] = None
    status: Optional[ScreenStatus] = None
    position: Optional[int] = None


class ScreenUnitRead(TimestampedRead):
    screen_project_id: str
    unit_type: ScreenUnitType
    number: int
    title: Optional[str]
    synopsis: Optional[str]
    status: ScreenStatus
    position: int


class ScreenSequenceCreate(BaseModel):
    sequence_number: int = 1
    title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = None
    status: ScreenStatus = ScreenStatus.PLANNED
    position: int = 0


class ScreenSequenceUpdate(BaseModel):
    sequence_number: Optional[int] = None
    title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = None
    status: Optional[ScreenStatus] = None
    position: Optional[int] = None


class ScreenSequenceRead(TimestampedRead):
    unit_id: str
    sequence_number: int
    title: Optional[str]
    description: Optional[str]
    status: ScreenStatus
    position: int


# --- scene -----------------------------------------------------------------


class SceneCharacterCreate(BaseModel):
    entity_id: str
    role: Optional[str] = Field(default=None, max_length=120)
    position: int = 0


class SceneCharacterRead(TimestampedRead):
    scene_id: str
    entity_id: str
    entity_name: Optional[str] = None
    role: Optional[str]
    position: int


class SceneCreate(BaseModel):
    scene_number: int = 1
    position: int = 0
    heading: Optional[str] = Field(default=None, max_length=400)
    location: Optional[str] = Field(default=None, max_length=300)
    environment: SceneEnvironment = SceneEnvironment.INT
    time_of_day: SceneTimeOfDay = SceneTimeOfDay.DAY
    synopsis: Optional[str] = None
    script_text: Optional[str] = None
    estimated_duration_seconds: Optional[float] = Field(default=None, ge=0)
    production_status: ScreenStatus = ScreenStatus.PLANNED
    continuity_notes: Optional[str] = None


class SceneUpdate(BaseModel):
    scene_number: Optional[int] = None
    position: Optional[int] = None
    heading: Optional[str] = Field(default=None, max_length=400)
    location: Optional[str] = Field(default=None, max_length=300)
    environment: Optional[SceneEnvironment] = None
    time_of_day: Optional[SceneTimeOfDay] = None
    synopsis: Optional[str] = None
    script_text: Optional[str] = None
    estimated_duration_seconds: Optional[float] = Field(default=None, ge=0)
    production_status: Optional[ScreenStatus] = None
    continuity_notes: Optional[str] = None


class SceneRead(TimestampedRead):
    sequence_id: str
    scene_number: int
    position: int
    heading: Optional[str]
    location: Optional[str]
    environment: SceneEnvironment
    time_of_day: SceneTimeOfDay
    synopsis: Optional[str]
    script_text: Optional[str]
    estimated_duration_seconds: Optional[float]
    production_status: ScreenStatus
    continuity_notes: Optional[str]
    shot_count: int = 0


class SceneDetail(SceneRead):
    shots: list["ShotRead"] = Field(default_factory=list)
    characters: list[SceneCharacterRead] = Field(default_factory=list)


# --- shot ------------------------------------------------------------------


class ShotCreate(BaseModel):
    shot_number: int = 1
    position: int = 0
    framing: Optional[CameraFraming] = None
    camera_angle: Optional[CameraAngle] = None
    movement: Optional[ShotMovement] = None
    lens: Optional[str] = Field(default=None, max_length=120)
    duration_seconds: Optional[float] = Field(default=None, ge=0)
    blocking: Optional[str] = None
    lighting: Optional[str] = None
    dialogue: Optional[str] = None
    sound: Optional[str] = None
    music: Optional[str] = None
    vfx: Optional[str] = None
    source_storyboard_panel_id: Optional[str] = None
    status: ScreenStatus = ScreenStatus.PLANNED
    approval: AssetApprovalStatus = AssetApprovalStatus.DRAFT


class ShotUpdate(BaseModel):
    shot_number: Optional[int] = None
    position: Optional[int] = None
    framing: Optional[CameraFraming] = None
    camera_angle: Optional[CameraAngle] = None
    movement: Optional[ShotMovement] = None
    lens: Optional[str] = Field(default=None, max_length=120)
    duration_seconds: Optional[float] = Field(default=None, ge=0)
    blocking: Optional[str] = None
    lighting: Optional[str] = None
    dialogue: Optional[str] = None
    sound: Optional[str] = None
    music: Optional[str] = None
    vfx: Optional[str] = None
    source_storyboard_panel_id: Optional[str] = None
    status: Optional[ScreenStatus] = None
    approval: Optional[AssetApprovalStatus] = None


class ShotRead(TimestampedRead):
    scene_id: str
    shot_number: int
    position: int
    framing: Optional[CameraFraming]
    camera_angle: Optional[CameraAngle]
    movement: Optional[ShotMovement]
    lens: Optional[str]
    duration_seconds: Optional[float]
    blocking: Optional[str]
    lighting: Optional[str]
    dialogue: Optional[str]
    sound: Optional[str]
    music: Optional[str]
    vfx: Optional[str]
    source_storyboard_panel_id: Optional[str]
    status: ScreenStatus
    approval: AssetApprovalStatus
    mapped_panel_ids: list[str] = Field(default_factory=list)
    asset_version_ids: list[str] = Field(default_factory=list)


class ShotPanelLinkCreate(BaseModel):
    panel_id: str
    role: Optional[str] = Field(default=None, max_length=120)


class ShotAssetLinkCreate(BaseModel):
    asset_version_id: str
    role: Optional[str] = Field(default=None, max_length=120)


# --- breakdown / references / export ---------------------------------------


class ReferencesRead(BaseModel):
    entities: list[dict]
    rights: list[dict]
    provenance: list[dict]


class StoryboardRef(BaseModel):
    page_id: str
    page_number: int
    panel_id: str
    panel_number: int


SceneDetail.model_rebuild()
