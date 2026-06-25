from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import MembershipStatus, PermissionScope, ProjectRole
from app.schemas._common import TimestampedRead


class ProjectMembershipCreate(BaseModel):
    """Invite a user to a project. The project scope (work or story world) is
    taken from the request path, so the body only carries the invitee, the role
    to grant, and an optional note."""

    user_id: str
    role: ProjectRole = ProjectRole.VIEWER
    notes: Optional[str] = None


class ProjectMembershipRoleUpdate(BaseModel):
    role: ProjectRole


class ProjectMembershipRead(TimestampedRead):
    user_id: str
    work_id: Optional[str]
    story_world_id: Optional[str]
    role: ProjectRole
    status: MembershipStatus
    invited_at: datetime
    accepted_at: Optional[datetime]
    created_by_id: Optional[str]
    notes: Optional[str]
    # Convenience fields, resolved from the related user.
    user_name: Optional[str] = None
    user_email: Optional[str] = None


class MyProjectRead(BaseModel):
    """One entry in the caller's "my projects" list: the membership plus the
    resolved project label and the concrete permission scopes it grants."""

    membership_id: str
    role: ProjectRole
    status: MembershipStatus
    work_id: Optional[str] = None
    work_title: Optional[str] = None
    story_world_id: Optional[str] = None
    story_world_name: Optional[str] = None
    scopes: list[PermissionScope] = Field(default_factory=list)
