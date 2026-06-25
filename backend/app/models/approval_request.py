from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import ApprovalDecision, ApprovalStatus

if TYPE_CHECKING:
    from app.models.production_item import ProductionItem
    from app.models.user import User


class ApprovalRequest(BaseEntity, table=True):
    """A human approval gate for a deliverable or production task.

    The decision is always made by the assigned human ``approver`` (or an
    admin) — the system never auto-approves. ``target_type`` / ``target_id``
    generalise the target beyond production tasks (e.g. a Work or a published
    deliverable); ``task_id`` is the convenience link for the common case.
    """

    __tablename__ = "approval_requests"

    requested_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    approver_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )

    task_id: Optional[str] = Field(
        default=None, foreign_key="production_items.id", index=True
    )
    target_type: Optional[str] = Field(default=None, max_length=60, index=True)
    target_id: Optional[str] = Field(default=None, index=True)

    title: Optional[str] = Field(default=None, max_length=300)
    description: Optional[str] = Field(default=None)

    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING, index=True)
    decision: Optional[ApprovalDecision] = Field(default=None)
    comments: Optional[str] = Field(default=None)
    decided_at: Optional[datetime] = Field(default=None)

    requested_by: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ApprovalRequest.requested_by_id]"},
    )
    approver: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ApprovalRequest.approver_id]"},
    )
    task: Optional["ProductionItem"] = Relationship(
        back_populates="approvals",
        sa_relationship_kwargs={"foreign_keys": "[ApprovalRequest.task_id]"},
    )

    @property
    def requested_by_name(self) -> Optional[str]:
        return self.requested_by.full_name if self.requested_by is not None else None

    @property
    def approver_name(self) -> Optional[str]:
        return self.approver.full_name if self.approver is not None else None
