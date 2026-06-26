from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import PublishedStatus

if TYPE_CHECKING:
    from app.models.published_volume import PublishedVolume


class PublishedWork(BaseEntity, table=True):
    """The public, reader-facing projection of a graphic novel.

    Created/updated from a private ``Work`` via the publication bridge, copying
    *only* public metadata. It carries no contracts, rights, editorial notes,
    workflow, production status, or private files — those simply do not exist
    on this model.
    """

    __tablename__ = "published_works"

    # Soft back-reference to the private Work it was published from. Never
    # exposed in the public API (see schemas).
    source_work_id: Optional[str] = Field(
        default=None, foreign_key="works.id", index=True
    )

    slug: str = Field(max_length=200, unique=True, index=True)
    title: str = Field(max_length=300, index=True)
    subtitle: Optional[str] = Field(default=None, max_length=300)
    public_synopsis: Optional[str] = Field(default=None)
    cover_image: Optional[str] = Field(default=None, max_length=600)
    status: PublishedStatus = Field(default=PublishedStatus.DRAFT, index=True)
    publication_date: Optional[date] = Field(default=None, index=True)
    author_credit: Optional[str] = Field(default=None, max_length=300)
    artist_credit: Optional[str] = Field(default=None, max_length=300)
    tags: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )

    # Public Bookshop (selling catalogue). A work appears in /public/catalogue
    # when it is PUBLISHED and ``for_sale``. ``buy_url`` is the external point of
    # sale the studio sets; price is stored in minor units + a currency code.
    for_sale: bool = Field(default=False)
    price_cents: Optional[int] = Field(default=None, ge=0)
    currency: str = Field(default="EUR", max_length=3)
    buy_url: Optional[str] = Field(default=None, max_length=600)
    format_label: Optional[str] = Field(default=None, max_length=80)

    # Optional work-level media (music/intro) — most specific level wins in
    # the reader (page > chapter > volume > work).
    music_track_id: Optional[str] = Field(
        default=None, foreign_key="public_media_assets.id"
    )
    video_intro_id: Optional[str] = Field(
        default=None, foreign_key="public_media_assets.id"
    )

    volumes: list["PublishedVolume"] = Relationship(
        back_populates="work",
        sa_relationship_kwargs={"order_by": "PublishedVolume.volume_number"},
    )
