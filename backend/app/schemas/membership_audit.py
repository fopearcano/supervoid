from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.models.enums import (
    MembershipAuditAction,
    MembershipStatus,
    PermissionScope,
    ProjectRole,
)
from app.schemas._common import TimestampedRead


class MembershipAuditRead(TimestampedRead):
    membership_id: Optional[str]
    actor_id: Optional[str]
    subject_user_id: str
    work_id: Optional[str]
    story_world_id: Optional[str]
    action: MembershipAuditAction
    role: Optional[ProjectRole]
    from_status: Optional[MembershipStatus]
    to_status: Optional[MembershipStatus]
    note: Optional[str]


class ScopeCatalogEntry(BaseModel):
    """A project role and the permission scopes it grants — used to expose the
    policy matrix to the private UI so it can render capabilities without
    duplicating the rules."""

    role: ProjectRole
    scopes: list[PermissionScope]
