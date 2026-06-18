from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import WorkStatus, WorkType

if TYPE_CHECKING:
    from app.models.author import Author
    from app.models.calendar_event import PublishingCalendarEvent
    from app.models.contract import Contract
    from app.models.editorial_note import EditorialNote
    from app.models.graphic_novel_production import GraphicNovelProduction
    from app.models.manuscript import Manuscript
    from app.models.production_item import ProductionItem
    from app.models.review import Review
    from app.models.rights import Rights


class Work(BaseEntity, table=True):
    """The central catalogue entity for SUPERVOID Publishing.

    A Work is the publishing *project* — a book, graphic novel, art book,
    essay or future adaptation candidate. It is the hub the rest of the
    domain hangs off: manuscripts (its text drafts), graphic-novel
    production, contracts, rights, production items, reviews, notes and
    calendar events all reference a Work.
    """

    __tablename__ = "works"

    title: str = Field(max_length=300, index=True)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    work_type: WorkType = Field(default=WorkType.BOOK, index=True)
    genre: Optional[str] = Field(default=None, max_length=100, index=True)
    status: WorkStatus = Field(default=WorkStatus.CONCEPT, index=True)

    synopsis: Optional[str] = Field(default=None)
    internal_pitch: Optional[str] = Field(default=None)
    target_audience: Optional[str] = Field(default=None, max_length=300)

    language: str = Field(default="en", max_length=10)
    word_count: Optional[int] = Field(default=None, ge=0)
    page_count: Optional[int] = Field(default=None, ge=0)

    author_id: str = Field(foreign_key="authors.id", index=True)
    author: "Author" = Relationship(back_populates="works")

    manuscripts: list["Manuscript"] = Relationship(back_populates="work")
    contracts: list["Contract"] = Relationship(back_populates="work")
    rights: list["Rights"] = Relationship(back_populates="work")
    production_items: list["ProductionItem"] = Relationship(back_populates="work")
    reviews: list["Review"] = Relationship(back_populates="work")
    editorial_notes: list["EditorialNote"] = Relationship(back_populates="work")
    calendar_events: list["PublishingCalendarEvent"] = Relationship(
        back_populates="work"
    )
    graphic_novel_production: Optional["GraphicNovelProduction"] = Relationship(
        back_populates="work",
        sa_relationship_kwargs={"uselist": False},
    )
