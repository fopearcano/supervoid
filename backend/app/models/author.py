from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity

if TYPE_CHECKING:
    from app.models.contract import Contract
    from app.models.editorial_note import EditorialNote
    from app.models.manuscript import Manuscript
    from app.models.work import Work


class Author(BaseEntity, table=True):
    __tablename__ = "authors"

    full_name: str = Field(max_length=200, index=True)
    pen_name: Optional[str] = Field(default=None, max_length=200, index=True)
    email: Optional[str] = Field(default=None, max_length=255, index=True)
    phone: Optional[str] = Field(default=None, max_length=50)
    website: Optional[str] = Field(default=None, max_length=300)
    country: Optional[str] = Field(default=None, max_length=100)
    biography: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)

    works: list["Work"] = Relationship(back_populates="author")
    manuscripts: list["Manuscript"] = Relationship(back_populates="author")
    contracts: list["Contract"] = Relationship(back_populates="author")
    editorial_notes: list["EditorialNote"] = Relationship(back_populates="author")
