from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import StreamStatus

if TYPE_CHECKING:
    from app.models.graphic_novel_hierarchy import GraphicNovelVolume
    from app.models.work import Work


class GraphicNovelProduction(BaseEntity, table=True):
    """Visual-production tracking for a graphic-novel (or art-book) Work.

    One production record per Work, rolling up the status of every visual
    stream — script through final files — so a production manager has a
    single board for illustrated titles. Each stream reuses ``StreamStatus``
    (not_planned / pending / in_progress / blocked / complete).
    """

    __tablename__ = "graphic_novel_productions"

    work_id: str = Field(foreign_key="works.id", unique=True, index=True)

    volume_number: Optional[int] = Field(default=None, ge=0)
    issue_number: Optional[int] = Field(default=None, ge=0)

    script_status: StreamStatus = Field(default=StreamStatus.NOT_PLANNED, index=True)
    storyboard_status: StreamStatus = Field(default=StreamStatus.NOT_PLANNED)
    character_design_status: StreamStatus = Field(default=StreamStatus.NOT_PLANNED)
    environment_design_status: StreamStatus = Field(default=StreamStatus.NOT_PLANNED)
    page_layout_status: StreamStatus = Field(default=StreamStatus.NOT_PLANNED)
    lettering_status: StreamStatus = Field(default=StreamStatus.NOT_PLANNED)
    coloring_status: StreamStatus = Field(default=StreamStatus.NOT_PLANNED)
    final_files_status: StreamStatus = Field(default=StreamStatus.NOT_PLANNED)

    notes: Optional[str] = Field(default=None)

    work: "Work" = Relationship(back_populates="graphic_novel_production")
    volumes: list["GraphicNovelVolume"] = Relationship(
        back_populates="production",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
