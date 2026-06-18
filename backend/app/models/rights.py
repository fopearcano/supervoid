from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import RightStatus

if TYPE_CHECKING:
    from app.models.work import Work


class Rights(BaseEntity, table=True):
    """A rights profile for a Work, scoped to a territory and language.

    Each licensable right (print, ebook, audiobook, film, adaptation,
    merchandising) carries its own ``RightStatus`` so the rights desk can
    see at a glance what is available, optioned, licensed or sold for a
    given territory/language window.
    """

    __tablename__ = "rights"

    work_id: str = Field(foreign_key="works.id", index=True)

    territory: str = Field(default="World", max_length=100, index=True)
    language: str = Field(default="all", max_length=40, index=True)

    print_rights: RightStatus = Field(default=RightStatus.AVAILABLE)
    ebook_rights: RightStatus = Field(default=RightStatus.AVAILABLE)
    audiobook_rights: RightStatus = Field(default=RightStatus.AVAILABLE)
    film_rights: RightStatus = Field(default=RightStatus.AVAILABLE)
    adaptation_rights: RightStatus = Field(default=RightStatus.AVAILABLE)
    merchandising_rights: RightStatus = Field(default=RightStatus.AVAILABLE)

    holder: Optional[str] = Field(default=None, max_length=200)
    expiration_date: Optional[date] = Field(default=None, index=True)
    notes: Optional[str] = Field(default=None)

    work: "Work" = Relationship(back_populates="rights")
