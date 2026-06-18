from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import ReviewVerdict

if TYPE_CHECKING:
    from app.models.manuscript import Manuscript
    from app.models.user import User
    from app.models.work import Work


class Review(BaseEntity, table=True):
    __tablename__ = "reviews"

    manuscript_id: str = Field(foreign_key="manuscripts.id", index=True)
    work_id: Optional[str] = Field(
        default=None, foreign_key="works.id", index=True
    )
    reviewer_id: str = Field(foreign_key="users.id", index=True)

    # ``verdict`` is the recommendation: accept / reject / revise / hold.
    verdict: ReviewVerdict = Field(index=True)
    summary: str
    written_report: Optional[str] = Field(default=None)

    # Quick 1–5 overall rating (kept for back-compat) plus a structured rubric.
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    literary_quality_score: Optional[int] = Field(default=None, ge=1, le=5)
    visual_potential_score: Optional[int] = Field(default=None, ge=1, le=5)
    market_potential_score: Optional[int] = Field(default=None, ge=1, le=5)
    originality_score: Optional[int] = Field(default=None, ge=1, le=5)
    editorial_effort_score: Optional[int] = Field(default=None, ge=1, le=5)

    manuscript: "Manuscript" = Relationship(back_populates="reviews")
    work: Optional["Work"] = Relationship(back_populates="reviews")
    reviewer: "User" = Relationship(back_populates="reviews")

    @property
    def reviewer_name(self) -> Optional[str]:
        return self.reviewer.full_name if self.reviewer is not None else None
