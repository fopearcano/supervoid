from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import PublicationAction, PublishedStatus

if TYPE_CHECKING:
    from app.models.user import User


class PublicationEvent(BaseEntity, table=True):
    """An append-only record of a publication action on a ``PublishedWork``.

    Preserves publication history — create, schedule, approval, publish,
    unpublish, archive and page hand-off — so a work's public lifecycle is fully
    auditable. Never deleted when a work is unpublished.
    """

    __tablename__ = "publication_events"

    published_work_id: str = Field(foreign_key="published_works.id", index=True)
    action: PublicationAction = Field(index=True)
    actor_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)

    from_status: Optional[PublishedStatus] = Field(default=None)
    to_status: Optional[PublishedStatus] = Field(default=None)
    note: Optional[str] = Field(default=None)
    detail: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    actor: Optional["User"] = Relationship()
