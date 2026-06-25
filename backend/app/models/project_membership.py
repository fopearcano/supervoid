from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity, utcnow
from app.models.enums import MembershipStatus, ProjectRole

if TYPE_CHECKING:
    from app.models.story_world import StoryWorld
    from app.models.user import User
    from app.models.work import Work


class ProjectMembership(BaseEntity, table=True):
    """A user's collaboration membership on a project — a Work and/or a
    StoryWorld. Sits alongside the global ``UserRole``; it never replaces it.

    A membership scoped to a StoryWorld cascades to the Works inside that world
    (resolved by the policy service), so world owners need not be re-added to
    every Work.
    """

    __tablename__ = "project_memberships"

    user_id: str = Field(foreign_key="users.id", index=True)
    work_id: Optional[str] = Field(default=None, foreign_key="works.id", index=True)
    story_world_id: Optional[str] = Field(
        default=None, foreign_key="story_worlds.id", index=True
    )

    role: ProjectRole = Field(default=ProjectRole.VIEWER, index=True)
    status: MembershipStatus = Field(default=MembershipStatus.INVITED, index=True)

    invited_at: datetime = Field(default_factory=utcnow, nullable=False)
    accepted_at: Optional[datetime] = Field(default=None)

    created_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    notes: Optional[str] = Field(default=None)

    user: "User" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ProjectMembership.user_id]"},
    )
    created_by: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ProjectMembership.created_by_id]"},
    )
    work: Optional["Work"] = Relationship()
    story_world: Optional["StoryWorld"] = Relationship()

    @property
    def user_name(self) -> Optional[str]:
        return self.user.full_name if self.user is not None else None

    @property
    def user_email(self) -> Optional[str]:
        return self.user.email if self.user is not None else None
