from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import PublicationApprovalStatus

if TYPE_CHECKING:
    from app.models.user import User


class PublicationApproval(BaseEntity, table=True):
    """A publication approval request for a ``PublishedWork``.

    Publication is gated: an approval captures the validation snapshot (credits,
    licences, provenance) at request time and records who approved or rejected.
    A work can only be published once it has an APPROVED approval and validation
    still passes.
    """

    __tablename__ = "publication_approvals"

    published_work_id: str = Field(foreign_key="published_works.id", index=True)
    status: PublicationApprovalStatus = Field(
        default=PublicationApprovalStatus.PENDING, index=True
    )

    requested_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    decided_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    decided_at: Optional[datetime] = Field(default=None)

    # Snapshot of the validation result at request time and at decision time.
    validation: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    note: Optional[str] = Field(default=None)

    requested_by: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[PublicationApproval.requested_by_id]"}
    )
    decided_by: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[PublicationApproval.decided_by_id]"}
    )
