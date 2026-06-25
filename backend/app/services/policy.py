"""Authorization policy for project-scoped collaboration.

The single source of truth for "can this user perform this operation on this
project?". It combines, in order:

1. the global ``UserRole`` (an ``ADMIN`` is a studio-wide super-user — this is
   how existing admin behaviour stays valid);
2. project **membership** (an active ``ProjectMembership`` on the Work, or on the
   Work's StoryWorld, which cascades down);
3. **ownership** (the ``OWNER`` project role grants every scope);
4. the requested **operation** (a ``PermissionScope``).

Routers must not hand-roll permission checks — they use ``require_scope`` (a
FastAPI dependency that reads the project id from the path) or ``ensure_can``
(for checks where the scope comes from a loaded record).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import or_
from sqlmodel import Session, select

from app.auth.dependencies import get_current_user
from app.db import get_session
from app.models import (
    MembershipAudit,
    MembershipStatus,
    PermissionScope,
    ProjectMembership,
    ProjectRole,
    User,
    UserRole,
    Work,
)
from app.models.enums import MembershipAuditAction

_PS = PermissionScope

# What each project role is allowed to do. OWNER gets everything.
ROLE_SCOPES: dict[ProjectRole, frozenset[PermissionScope]] = {
    ProjectRole.OWNER: frozenset(PermissionScope),
    ProjectRole.DIRECTOR: frozenset(
        {
            _PS.VIEW_PROJECT,
            _PS.EDIT_NARRATIVE,
            _PS.EDIT_VISUAL_ASSETS,
            _PS.MANAGE_PRODUCTION,
            _PS.UPLOAD_ASSETS,
            _PS.REVIEW,
            _PS.APPROVE,
            _PS.MANAGE_COLLABORATORS,
            _PS.PUBLISH,
        }
    ),
    ProjectRole.EDITOR: frozenset(
        {_PS.VIEW_PROJECT, _PS.EDIT_NARRATIVE, _PS.UPLOAD_ASSETS, _PS.REVIEW, _PS.APPROVE}
    ),
    ProjectRole.WRITER: frozenset(
        {_PS.VIEW_PROJECT, _PS.EDIT_NARRATIVE, _PS.UPLOAD_ASSETS}
    ),
    ProjectRole.ARTIST: frozenset(
        {_PS.VIEW_PROJECT, _PS.EDIT_VISUAL_ASSETS, _PS.UPLOAD_ASSETS}
    ),
    ProjectRole.LETTERER: frozenset(
        {_PS.VIEW_PROJECT, _PS.EDIT_VISUAL_ASSETS, _PS.UPLOAD_ASSETS}
    ),
    ProjectRole.COLOURIST: frozenset(
        {_PS.VIEW_PROJECT, _PS.EDIT_VISUAL_ASSETS, _PS.UPLOAD_ASSETS}
    ),
    ProjectRole.ANIMATOR: frozenset(
        {_PS.VIEW_PROJECT, _PS.EDIT_VISUAL_ASSETS, _PS.UPLOAD_ASSETS}
    ),
    ProjectRole.SOUND_DESIGNER: frozenset(
        {_PS.VIEW_PROJECT, _PS.EDIT_VISUAL_ASSETS, _PS.UPLOAD_ASSETS}
    ),
    ProjectRole.TECHNICIAN: frozenset(
        {_PS.VIEW_PROJECT, _PS.UPLOAD_ASSETS, _PS.MANAGE_PRODUCTION}
    ),
    ProjectRole.PRODUCTION_MANAGER: frozenset(
        {_PS.VIEW_PROJECT, _PS.MANAGE_PRODUCTION, _PS.UPLOAD_ASSETS, _PS.APPROVE}
    ),
    ProjectRole.MARKETING: frozenset({_PS.VIEW_PROJECT, _PS.MANAGE_MARKETING}),
    ProjectRole.REVIEWER: frozenset({_PS.VIEW_PROJECT, _PS.REVIEW}),
    ProjectRole.VIEWER: frozenset({_PS.VIEW_PROJECT}),
}

# Seniority order (used to pick the strongest role when several memberships
# apply, e.g. a world-level and a work-level membership for the same user).
_RANK_ORDER = [
    ProjectRole.OWNER,
    ProjectRole.DIRECTOR,
    ProjectRole.PRODUCTION_MANAGER,
    ProjectRole.EDITOR,
    ProjectRole.WRITER,
    ProjectRole.ARTIST,
    ProjectRole.LETTERER,
    ProjectRole.COLOURIST,
    ProjectRole.ANIMATOR,
    ProjectRole.SOUND_DESIGNER,
    ProjectRole.TECHNICIAN,
    ProjectRole.MARKETING,
    ProjectRole.REVIEWER,
    ProjectRole.VIEWER,
]
ROLE_RANK: dict[ProjectRole, int] = {
    role: len(_RANK_ORDER) - i for i, role in enumerate(_RANK_ORDER)
}


def role_scopes(role: ProjectRole) -> frozenset[PermissionScope]:
    return ROLE_SCOPES.get(role, frozenset())


def roles_catalog() -> list[tuple[ProjectRole, list[PermissionScope]]]:
    """The full project-role → permission-scope matrix, ordered by seniority.

    Exposed to the private UI so it can show what each role can do without
    re-encoding the rules client-side.
    """
    return [
        (role, sorted(role_scopes(role), key=lambda s: s.value))
        for role in _RANK_ORDER
    ]


def effective_role(
    session: Session,
    user: User,
    *,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
) -> Optional[ProjectRole]:
    """The strongest ACTIVE project role the user holds for this scope.

    A Work inherits its StoryWorld's memberships (world membership cascades to
    the works in that world). Returns ``None`` if the user has no active
    membership applying to the scope.
    """
    world_ids: set[str] = set()
    if story_world_id:
        world_ids.add(story_world_id)
    if work_id:
        work = session.get(Work, work_id)
        if work is not None and work.story_world_id:
            world_ids.add(work.story_world_id)

    conds = []
    if work_id:
        conds.append(ProjectMembership.work_id == work_id)
    if world_ids:
        conds.append(ProjectMembership.story_world_id.in_(world_ids))
    if not conds:
        return None

    stmt = select(ProjectMembership).where(
        ProjectMembership.user_id == user.id,
        ProjectMembership.status == MembershipStatus.ACTIVE,
        or_(*conds),
    )
    roles = [m.role for m in session.exec(stmt).all()]
    if not roles:
        return None
    return max(roles, key=lambda r: ROLE_RANK[r])


def can(
    session: Session,
    user: User,
    scope: PermissionScope,
    *,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
) -> bool:
    """Combine global role + membership + ownership + operation into a verdict."""
    if user.role == UserRole.ADMIN:
        return True
    role = effective_role(
        session, user, work_id=work_id, story_world_id=story_world_id
    )
    return role is not None and scope in role_scopes(role)


def ensure_can(
    session: Session,
    user: User,
    scope: PermissionScope,
    *,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
) -> None:
    """Raise 403 unless ``can`` allows the operation."""
    if not can(session, user, scope, work_id=work_id, story_world_id=story_world_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not permitted for this project",
        )


def require_scope(scope: PermissionScope):
    """FastAPI dependency factory: authorise ``scope`` using the project id taken
    from the request path (``work_id`` and/or ``world_id``/``story_world_id``)."""

    def dependency(
        request: Request,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> User:
        work_id = request.path_params.get("work_id")
        story_world_id = request.path_params.get("world_id") or request.path_params.get(
            "story_world_id"
        )
        ensure_can(
            session, user, scope, work_id=work_id, story_world_id=story_world_id
        )
        return user

    return dependency


def my_memberships(
    session: Session,
    user: User,
    *,
    statuses: Optional[list[MembershipStatus]] = None,
) -> list[ProjectMembership]:
    stmt = select(ProjectMembership).where(ProjectMembership.user_id == user.id)
    if statuses:
        stmt = stmt.where(ProjectMembership.status.in_(statuses))
    stmt = stmt.order_by(ProjectMembership.created_at.desc())
    return list(session.exec(stmt).all())


def record_audit(
    session: Session,
    *,
    action: MembershipAuditAction,
    subject_user_id: str,
    actor_id: Optional[str] = None,
    membership: Optional[ProjectMembership] = None,
    role: Optional[ProjectRole] = None,
    from_status: Optional[MembershipStatus] = None,
    to_status: Optional[MembershipStatus] = None,
    note: Optional[str] = None,
) -> MembershipAudit:
    """Append a membership-audit record (caller commits)."""
    audit = MembershipAudit(
        membership_id=membership.id if membership is not None else None,
        actor_id=actor_id,
        subject_user_id=subject_user_id,
        work_id=membership.work_id if membership is not None else None,
        story_world_id=membership.story_world_id if membership is not None else None,
        action=action,
        role=role if role is not None else (membership.role if membership else None),
        from_status=from_status,
        to_status=to_status,
        note=note,
    )
    session.add(audit)
    return audit
