from typing import Optional

from sqlmodel import Field

from app.models.base import BaseEntity
from app.models.enums import MembershipAuditAction, MembershipStatus, ProjectRole


class MembershipAudit(BaseEntity, table=True):
    """An append-only audit record of a project-membership change.

    Deliberately decoupled (plain id columns, no foreign keys or relationships)
    so the log is durable even if a membership is later revoked/removed. The
    scope (work/world), actor, subject, role and status transition are captured
    inline.
    """

    __tablename__ = "membership_audits"

    membership_id: Optional[str] = Field(default=None, index=True)
    actor_id: Optional[str] = Field(default=None, index=True)
    subject_user_id: str = Field(index=True)
    work_id: Optional[str] = Field(default=None, index=True)
    story_world_id: Optional[str] = Field(default=None, index=True)

    action: MembershipAuditAction = Field(index=True)
    role: Optional[ProjectRole] = Field(default=None)
    from_status: Optional[MembershipStatus] = Field(default=None)
    to_status: Optional[MembershipStatus] = Field(default=None)
    note: Optional[str] = Field(default=None)
