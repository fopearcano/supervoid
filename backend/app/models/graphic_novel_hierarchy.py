"""The detailed graphic-novel production hierarchy.

``GraphicNovelProduction`` remains the high-level per-Work summary; this module
adds the breakdown beneath it::

    GraphicNovelProduction
    └── GraphicNovelVolume
        └── GraphicNovelChapter
            └── GraphicNovelSequence
                └── GraphicNovelPage
                    └── GraphicNovelPanel
                        └── GraphicNovelPanelElement

Every level carries a stable ``position`` (for drag/reorder) and a status.
Characters and locations are linked by referencing existing
``KnowledgeEntity`` rows — never duplicated here.
"""
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
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

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.graphic_novel_production import GraphicNovelProduction
    from app.models.knowledge_entity import KnowledgeEntity


class GraphicNovelVolume(BaseEntity, table=True):
    __tablename__ = "gn_volumes"

    production_id: str = Field(foreign_key="graphic_novel_productions.id", index=True)
    volume_number: int = Field(default=1, index=True)
    title: Optional[str] = Field(default=None, max_length=300)
    synopsis: Optional[str] = Field(default=None)
    status: GNStatus = Field(default=GNStatus.PLANNED, index=True)
    position: int = Field(default=0, index=True)

    production: "GraphicNovelProduction" = Relationship(back_populates="volumes")
    chapters: list["GraphicNovelChapter"] = Relationship(
        back_populates="volume",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class GraphicNovelChapter(BaseEntity, table=True):
    __tablename__ = "gn_chapters"

    volume_id: str = Field(foreign_key="gn_volumes.id", index=True)
    chapter_number: int = Field(default=1, index=True)
    title: Optional[str] = Field(default=None, max_length=300)
    synopsis: Optional[str] = Field(default=None)
    status: GNStatus = Field(default=GNStatus.PLANNED, index=True)
    position: int = Field(default=0, index=True)

    volume: "GraphicNovelVolume" = Relationship(back_populates="chapters")
    sequences: list["GraphicNovelSequence"] = Relationship(
        back_populates="chapter",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class GraphicNovelSequence(BaseEntity, table=True):
    __tablename__ = "gn_sequences"

    chapter_id: str = Field(foreign_key="gn_chapters.id", index=True)
    sequence_number: int = Field(default=1, index=True)
    title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = Field(default=None)
    status: GNStatus = Field(default=GNStatus.PLANNED, index=True)
    position: int = Field(default=0, index=True)

    chapter: "GraphicNovelChapter" = Relationship(back_populates="sequences")
    pages: list["GraphicNovelPage"] = Relationship(
        back_populates="sequence",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class GraphicNovelPage(BaseEntity, table=True):
    __tablename__ = "gn_pages"

    sequence_id: str = Field(foreign_key="gn_sequences.id", index=True)
    page_number: int = Field(default=1, index=True)
    position: int = Field(default=0, index=True)
    status: GNStatus = Field(default=GNStatus.PLANNED, index=True)

    # Spread membership: pages sharing a spread_id form a two-page spread.
    spread_id: Optional[str] = Field(default=None, index=True)
    page_side: PageSide = Field(default=PageSide.SINGLE, index=True)

    script: Optional[str] = Field(default=None)
    visual_brief: Optional[str] = Field(default=None)
    dialogue_summary: Optional[str] = Field(default=None)

    lettering_status: StreamStatus = Field(default=StreamStatus.NOT_PLANNED)
    colour_status: StreamStatus = Field(default=StreamStatus.NOT_PLANNED)
    final_status: StreamStatus = Field(default=StreamStatus.NOT_PLANNED, index=True)

    # Print geometry (millimetres).
    print_width_mm: Optional[float] = Field(default=None, ge=0)
    print_height_mm: Optional[float] = Field(default=None, ge=0)
    bleed_mm: Optional[float] = Field(default=None, ge=0)
    safe_area_mm: Optional[float] = Field(default=None, ge=0)

    # The page's primary art asset (Asset Library).
    master_asset_id: Optional[str] = Field(
        default=None, foreign_key="assets.id", index=True
    )

    # Deliberate public-reader curation. The mapping/published page is set by an
    # editor during hand-off; the public reader is never written automatically.
    curation_status: CurationStatus = Field(
        default=CurationStatus.NOT_READY, index=True
    )
    published_page_id: Optional[str] = Field(
        default=None, foreign_key="published_pages.id", index=True
    )

    sequence: "GraphicNovelSequence" = Relationship(back_populates="pages")
    master_asset: Optional["Asset"] = Relationship()
    panels: list["GraphicNovelPanel"] = Relationship(
        back_populates="page",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    entity_links: list["GraphicNovelPageEntityLink"] = Relationship(
        back_populates="page",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class GraphicNovelPanel(BaseEntity, table=True):
    __tablename__ = "gn_panels"

    page_id: str = Field(foreign_key="gn_pages.id", index=True)
    panel_number: int = Field(default=1, index=True)
    position: int = Field(default=0, index=True)
    status: GNStatus = Field(default=GNStatus.PLANNED, index=True)

    # Normalised panel rectangle on the page (0..1).
    x: float = Field(default=0.0, ge=0, le=1)
    y: float = Field(default=0.0, ge=0, le=1)
    width: float = Field(default=1.0, ge=0, le=1)
    height: float = Field(default=1.0, ge=0, le=1)

    script_beat: Optional[str] = Field(default=None)
    dialogue: Optional[str] = Field(default=None)
    captions: Optional[str] = Field(default=None)
    sound_effects: Optional[str] = Field(default=None)

    camera_framing: Optional[CameraFraming] = Field(default=None, index=True)
    camera_angle: Optional[CameraAngle] = Field(default=None, index=True)
    lens_metadata: Optional[str] = Field(default=None, max_length=200)

    continuity_notes: Optional[str] = Field(default=None)

    # Storyboard vs final art versions (Asset Library) for comparison. Plain FK
    # columns (no relationships) to avoid multi-FK ambiguity on asset_versions.
    storyboard_asset_version_id: Optional[str] = Field(
        default=None, foreign_key="asset_versions.id", index=True
    )
    final_asset_version_id: Optional[str] = Field(
        default=None, foreign_key="asset_versions.id", index=True
    )

    approval_status: AssetApprovalStatus = Field(
        default=AssetApprovalStatus.DRAFT, index=True
    )

    page: "GraphicNovelPage" = Relationship(back_populates="panels")
    elements: list["GraphicNovelPanelElement"] = Relationship(
        back_populates="panel",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class GraphicNovelPanelElement(BaseEntity, table=True):
    """A character, prop, location or text element inside a panel. Characters,
    props and locations reference a ``KnowledgeEntity`` (no duplication); text
    elements carry their own content."""

    __tablename__ = "gn_panel_elements"

    panel_id: str = Field(foreign_key="gn_panels.id", index=True)
    element_type: PanelElementType = Field(index=True)
    position: int = Field(default=0, index=True)

    entity_id: Optional[str] = Field(
        default=None, foreign_key="knowledge_entities.id", index=True
    )
    text_content: Optional[str] = Field(default=None)
    asset_version_id: Optional[str] = Field(
        default=None, foreign_key="asset_versions.id", index=True
    )
    label: Optional[str] = Field(default=None, max_length=200)

    # Optional normalised placement within the panel.
    x: Optional[float] = Field(default=None, ge=0, le=1)
    y: Optional[float] = Field(default=None, ge=0, le=1)
    width: Optional[float] = Field(default=None, ge=0, le=1)
    height: Optional[float] = Field(default=None, ge=0, le=1)

    panel: "GraphicNovelPanel" = Relationship(back_populates="elements")
    entity: Optional["KnowledgeEntity"] = Relationship()

    @property
    def entity_name(self) -> Optional[str]:
        return self.entity.name if self.entity is not None else None


class GraphicNovelPageEntityLink(BaseEntity, table=True):
    """A knowledge-graph entity (character, location, …) associated with a page.
    References ``KnowledgeEntity`` directly — characters/locations are not
    duplicated into the production hierarchy."""

    __tablename__ = "gn_page_entity_links"

    page_id: str = Field(foreign_key="gn_pages.id", index=True)
    entity_id: str = Field(foreign_key="knowledge_entities.id", index=True)
    role: Optional[str] = Field(default=None, max_length=120)
    position: int = Field(default=0)

    page: "GraphicNovelPage" = Relationship(back_populates="entity_links")
    entity: Optional["KnowledgeEntity"] = Relationship()

    @property
    def entity_name(self) -> Optional[str]:
        return self.entity.name if self.entity is not None else None
