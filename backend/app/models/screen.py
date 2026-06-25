"""SUPERVOID Pictures — the screen-production bounded context.

Entered via ``AdaptationDossier`` (the publishing → screen seam) and structured
as::

    ScreenProject → ScreenUnit (Episode/Reel) → ScreenSequence → Scene → Shot

Kept deliberately self-contained (its own status vocabulary, all cross-context
references held by id) so it stays *extractable* into a separate SUPERVOID
Pictures service later — without another deployment or repository today.
Characters, storyboard panels, asset versions and rights are *referenced*
(by id), never duplicated.
"""
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import (
    AssetApprovalStatus,
    CameraAngle,
    CameraFraming,
    SceneEnvironment,
    SceneTimeOfDay,
    ScreenFormat,
    ScreenProjectStatus,
    ScreenStatus,
    ScreenUnitType,
    ShotMovement,
)

if TYPE_CHECKING:
    from app.models.knowledge_entity import KnowledgeEntity


class ScreenProject(BaseEntity, table=True):
    __tablename__ = "screen_projects"

    # Seam: a screen project is created from an approved adaptation dossier.
    dossier_id: str = Field(foreign_key="adaptation_dossiers.id", index=True)
    source_work_id: Optional[str] = Field(
        default=None, foreign_key="works.id", index=True
    )
    story_world_id: Optional[str] = Field(
        default=None, foreign_key="story_worlds.id", index=True
    )

    title: str = Field(max_length=300, index=True)
    format: ScreenFormat = Field(default=ScreenFormat.FILM, index=True)
    status: ScreenProjectStatus = Field(
        default=ScreenProjectStatus.DEVELOPMENT, index=True
    )
    logline: Optional[str] = Field(default=None)
    synopsis: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)

    units: list["ScreenUnit"] = Relationship(
        back_populates="project",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ScreenUnit(BaseEntity, table=True):
    """An episode (series) or reel / act / part (film, short, animation)."""

    __tablename__ = "screen_units"

    screen_project_id: str = Field(foreign_key="screen_projects.id", index=True)
    unit_type: ScreenUnitType = Field(default=ScreenUnitType.REEL, index=True)
    number: int = Field(default=1, index=True)
    title: Optional[str] = Field(default=None, max_length=300)
    synopsis: Optional[str] = Field(default=None)
    status: ScreenStatus = Field(default=ScreenStatus.PLANNED, index=True)
    position: int = Field(default=0, index=True)

    project: "ScreenProject" = Relationship(back_populates="units")
    sequences: list["ScreenSequence"] = Relationship(
        back_populates="unit",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ScreenSequence(BaseEntity, table=True):
    __tablename__ = "screen_sequences"

    unit_id: str = Field(foreign_key="screen_units.id", index=True)
    sequence_number: int = Field(default=1, index=True)
    title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = Field(default=None)
    status: ScreenStatus = Field(default=ScreenStatus.PLANNED, index=True)
    position: int = Field(default=0, index=True)

    unit: "ScreenUnit" = Relationship(back_populates="sequences")
    scenes: list["Scene"] = Relationship(
        back_populates="sequence",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Scene(BaseEntity, table=True):
    __tablename__ = "screen_scenes"

    sequence_id: str = Field(foreign_key="screen_sequences.id", index=True)
    scene_number: int = Field(default=1, index=True)
    position: int = Field(default=0, index=True)

    heading: Optional[str] = Field(default=None, max_length=400)
    location: Optional[str] = Field(default=None, max_length=300)
    environment: SceneEnvironment = Field(default=SceneEnvironment.INT, index=True)
    time_of_day: SceneTimeOfDay = Field(default=SceneTimeOfDay.DAY, index=True)
    synopsis: Optional[str] = Field(default=None)
    script_text: Optional[str] = Field(default=None)
    estimated_duration_seconds: Optional[float] = Field(default=None, ge=0)
    production_status: ScreenStatus = Field(default=ScreenStatus.PLANNED, index=True)
    continuity_notes: Optional[str] = Field(default=None)

    sequence: "ScreenSequence" = Relationship(back_populates="scenes")
    shots: list["Shot"] = Relationship(
        back_populates="scene",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    character_links: list["SceneCharacterLink"] = Relationship(
        back_populates="scene",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SceneCharacterLink(BaseEntity, table=True):
    """A character in a scene — references a ``KnowledgeEntity`` (no duplication)."""

    __tablename__ = "screen_scene_characters"

    scene_id: str = Field(foreign_key="screen_scenes.id", index=True)
    entity_id: str = Field(foreign_key="knowledge_entities.id", index=True)
    role: Optional[str] = Field(default=None, max_length=120)
    position: int = Field(default=0)

    scene: "Scene" = Relationship(back_populates="character_links")
    entity: Optional["KnowledgeEntity"] = Relationship()

    @property
    def entity_name(self) -> Optional[str]:
        return self.entity.name if self.entity is not None else None


class Shot(BaseEntity, table=True):
    __tablename__ = "screen_shots"

    scene_id: str = Field(foreign_key="screen_scenes.id", index=True)
    shot_number: int = Field(default=1, index=True)
    position: int = Field(default=0, index=True)

    framing: Optional[CameraFraming] = Field(default=None, index=True)
    camera_angle: Optional[CameraAngle] = Field(default=None, index=True)
    movement: Optional[ShotMovement] = Field(default=None, index=True)
    lens: Optional[str] = Field(default=None, max_length=120)
    duration_seconds: Optional[float] = Field(default=None, ge=0)

    blocking: Optional[str] = Field(default=None)
    lighting: Optional[str] = Field(default=None)
    dialogue: Optional[str] = Field(default=None)
    sound: Optional[str] = Field(default=None)
    music: Optional[str] = Field(default=None)
    vfx: Optional[str] = Field(default=None)

    # Primary storyboard reference (a graphic-novel panel). Additional panels
    # are mapped many-to-many via ScreenShotPanelLink.
    source_storyboard_panel_id: Optional[str] = Field(
        default=None, foreign_key="gn_panels.id", index=True
    )

    status: ScreenStatus = Field(default=ScreenStatus.PLANNED, index=True)
    approval: AssetApprovalStatus = Field(
        default=AssetApprovalStatus.DRAFT, index=True
    )

    scene: "Scene" = Relationship(back_populates="shots")
    asset_links: list["ScreenShotAssetLink"] = Relationship(
        back_populates="shot",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    panel_links: list["ScreenShotPanelLink"] = Relationship(
        back_populates="shot",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ScreenShotAssetLink(BaseEntity, table=True):
    """A linked asset version for a shot (storyboard, plate, render, …)."""

    __tablename__ = "screen_shot_assets"

    shot_id: str = Field(foreign_key="screen_shots.id", index=True)
    asset_version_id: str = Field(foreign_key="asset_versions.id", index=True)
    role: Optional[str] = Field(default=None, max_length=120)
    position: int = Field(default=0)

    shot: "Shot" = Relationship(back_populates="asset_links")


class ScreenShotPanelLink(BaseEntity, table=True):
    """Maps a graphic-novel storyboard panel to a shot (a panel may map to one
    or more shots)."""

    __tablename__ = "screen_shot_panels"

    shot_id: str = Field(foreign_key="screen_shots.id", index=True)
    panel_id: str = Field(foreign_key="gn_panels.id", index=True)
    role: Optional[str] = Field(default=None, max_length=120)
    position: int = Field(default=0)

    shot: "Shot" = Relationship(back_populates="panel_links")
