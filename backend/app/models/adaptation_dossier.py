from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import (
    AdaptationStatus,
    Medium,
    RightsClearanceState,
    StudioDivision,
)

if TYPE_CHECKING:
    from app.models.work import Work


class AdaptationDossier(BaseEntity, table=True):
    """A development dossier for adapting a source Work into another medium /
    division (e.g. a graphic novel into a film). It tracks the adaptation
    *before and during* production; when a concrete target Work is created it is
    linked via ``target_work_id``. The dossier is the seam a future SUPERVOID
    Pictures/Interactive/Audio surface would build on.
    """

    __tablename__ = "adaptation_dossiers"

    source_work_id: str = Field(foreign_key="works.id", index=True)
    target_work_id: Optional[str] = Field(
        default=None, foreign_key="works.id", index=True
    )

    target_medium: Medium = Field(index=True)
    target_division: StudioDivision = Field(
        default=StudioDivision.PICTURES, index=True
    )
    status: AdaptationStatus = Field(default=AdaptationStatus.PROPOSED, index=True)

    logline: Optional[str] = Field(default=None)
    format: Optional[str] = Field(default=None, max_length=200)
    intended_scope: Optional[str] = Field(default=None, max_length=200)
    rights_clearance: RightsClearanceState = Field(
        default=RightsClearanceState.NOT_STARTED, index=True
    )
    creative_notes: Optional[str] = Field(default=None)
    source_revision: Optional[str] = Field(default=None, max_length=120)

    source_work: "Work" = Relationship(
        back_populates="adaptation_dossiers",
        sa_relationship_kwargs={"foreign_keys": "[AdaptationDossier.source_work_id]"},
    )
    target_work: Optional["Work"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[AdaptationDossier.target_work_id]"},
    )

    @property
    def source_work_title(self) -> Optional[str]:
        return self.source_work.title if self.source_work is not None else None

    @property
    def target_work_title(self) -> Optional[str]:
        return self.target_work.title if self.target_work is not None else None
