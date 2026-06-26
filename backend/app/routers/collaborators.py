"""Project-scoped collaboration: memberships, invitations and audit.

All authorization flows through ``app.services.policy`` — routers never hand-roll
permission checks. Listing collaborators requires ``VIEW_PROJECT``; changing them
requires ``MANAGE_COLLABORATORS``; accepting / declining an invitation is
restricted to the invited user.

Mounted without an extra prefix so the project routes read naturally
(``/works/{work_id}/members``, ``/story-worlds/{world_id}/members``) alongside
the membership-centric routes (``/memberships/...``) and ``/me/projects``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.auth import get_current_user
from app.db import get_session
from app.models import (
    MembershipAudit,
    MembershipStatus,
    PermissionScope,
    ProjectMembership,
    StoryWorld,
    User,
    Work,
)
from app.models.base import utcnow
from app.models.enums import MembershipAuditAction
from app.schemas.membership_audit import MembershipAuditRead, ScopeCatalogEntry
from app.schemas.project_membership import (
    MyProjectRead,
    ProjectMembershipCreate,
    ProjectMembershipRead,
    ProjectMembershipRoleUpdate,
)
from app.services import brain, policy
from app.utils import ensure_exists, get_or_404

router = APIRouter(tags=["collaboration"])

# A membership is "live" (currently grants or could grant access) when it is
# pending or active; declined/revoked rows are kept only for history.
_LIVE_STATUSES = (MembershipStatus.INVITED, MembershipStatus.ACTIVE,
                  MembershipStatus.SUSPENDED)


def _read(m: ProjectMembership) -> ProjectMembershipRead:
    return ProjectMembershipRead.model_validate(m)


def _invite(
    session: Session,
    actor: User,
    payload: ProjectMembershipCreate,
    *,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
) -> ProjectMembership:
    ensure_exists(session, User, payload.user_id, name="User")

    # Reject a duplicate live membership for the same user on the same project.
    clash = session.exec(
        select(ProjectMembership).where(
            ProjectMembership.user_id == payload.user_id,
            ProjectMembership.work_id == work_id,
            ProjectMembership.story_world_id == story_world_id,
            ProjectMembership.status.in_(_LIVE_STATUSES),
        )
    ).first()
    if clash is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has a membership on this project",
        )

    membership = ProjectMembership(
        user_id=payload.user_id,
        work_id=work_id,
        story_world_id=story_world_id,
        role=payload.role,
        status=MembershipStatus.INVITED,
        invited_at=utcnow(),
        created_by_id=actor.id,
        notes=payload.notes,
    )
    session.add(membership)
    session.flush()
    policy.record_audit(
        session,
        action=MembershipAuditAction.INVITED,
        subject_user_id=membership.user_id,
        actor_id=actor.id,
        membership=membership,
        role=membership.role,
        to_status=MembershipStatus.INVITED,
        note=payload.notes,
    )
    brain.emit(
        session, event_type=brain.BrainEventType.COLLABORATOR_INVITED,
        aggregate_type="collaborator", aggregate_id=membership.id,
        work_id=membership.work_id, story_world_id=membership.story_world_id,
        actor_id=actor.id, changes={"role": membership.role.value},
    )
    session.commit()
    session.refresh(membership)
    return membership


def _list_members(
    session: Session, *, work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
) -> list[ProjectMembershipRead]:
    stmt = select(ProjectMembership)
    if work_id is not None:
        stmt = stmt.where(ProjectMembership.work_id == work_id)
    if story_world_id is not None:
        stmt = stmt.where(ProjectMembership.story_world_id == story_world_id)
    stmt = stmt.order_by(ProjectMembership.created_at.asc())
    return [_read(m) for m in session.exec(stmt).all()]


# --- Work-scoped collaborators --------------------------------------------


@router.get("/works/{work_id}/members", response_model=list[ProjectMembershipRead])
def list_work_members(
    work_id: str,
    session: Session = Depends(get_session),
    _: User = Depends(policy.require_scope(PermissionScope.VIEW_PROJECT)),
) -> list[ProjectMembershipRead]:
    get_or_404(session, Work, work_id, name="Work")
    return _list_members(session, work_id=work_id)


@router.post(
    "/works/{work_id}/members",
    response_model=ProjectMembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def invite_work_member(
    work_id: str,
    payload: ProjectMembershipCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(policy.require_scope(PermissionScope.MANAGE_COLLABORATORS)),
) -> ProjectMembershipRead:
    get_or_404(session, Work, work_id, name="Work")
    return _read(_invite(session, actor, payload, work_id=work_id))


# --- Story-world-scoped collaborators -------------------------------------


@router.get(
    "/story-worlds/{world_id}/members",
    response_model=list[ProjectMembershipRead],
)
def list_world_members(
    world_id: str,
    session: Session = Depends(get_session),
    _: User = Depends(policy.require_scope(PermissionScope.VIEW_PROJECT)),
) -> list[ProjectMembershipRead]:
    get_or_404(session, StoryWorld, world_id, name="StoryWorld")
    return _list_members(session, story_world_id=world_id)


@router.post(
    "/story-worlds/{world_id}/members",
    response_model=ProjectMembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def invite_world_member(
    world_id: str,
    payload: ProjectMembershipCreate,
    session: Session = Depends(get_session),
    actor: User = Depends(policy.require_scope(PermissionScope.MANAGE_COLLABORATORS)),
) -> ProjectMembershipRead:
    get_or_404(session, StoryWorld, world_id, name="StoryWorld")
    return _read(_invite(session, actor, payload, story_world_id=world_id))


# --- Membership lifecycle (by membership id) ------------------------------


def _manageable(
    membership_id: str, session: Session, actor: User
) -> ProjectMembership:
    """Load a membership and require MANAGE_COLLABORATORS on its project."""
    m = get_or_404(session, ProjectMembership, membership_id, name="ProjectMembership")
    policy.ensure_can(
        session,
        actor,
        PermissionScope.MANAGE_COLLABORATORS,
        work_id=m.work_id,
        story_world_id=m.story_world_id,
    )
    return m


@router.patch(
    "/memberships/{membership_id}", response_model=ProjectMembershipRead
)
def change_membership_role(
    membership_id: str,
    payload: ProjectMembershipRoleUpdate,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> ProjectMembershipRead:
    m = _manageable(membership_id, session, actor)
    if m.status in (MembershipStatus.REVOKED, MembershipStatus.DECLINED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change the role of an inactive membership",
        )
    if payload.role != m.role:
        old = m.role
        m.role = payload.role
        session.add(m)
        policy.record_audit(
            session,
            action=MembershipAuditAction.ROLE_CHANGED,
            subject_user_id=m.user_id,
            actor_id=actor.id,
            membership=m,
            role=payload.role,
            note=f"{old.value} -> {payload.role.value}",
        )
        brain.emit(
            session, event_type=brain.BrainEventType.COLLABORATOR_ROLE_CHANGED,
            aggregate_type="collaborator", aggregate_id=m.id,
            work_id=m.work_id, story_world_id=m.story_world_id,
            actor_id=actor.id,
            changes={"from_role": old.value, "to_role": payload.role.value},
        )
        session.commit()
        session.refresh(m)
    return _read(m)


@router.post(
    "/memberships/{membership_id}/suspend",
    response_model=ProjectMembershipRead,
)
def suspend_membership(
    membership_id: str,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> ProjectMembershipRead:
    m = _manageable(membership_id, session, actor)
    if m.status != MembershipStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only an active membership can be suspended",
        )
    m.status = MembershipStatus.SUSPENDED
    session.add(m)
    policy.record_audit(
        session,
        action=MembershipAuditAction.SUSPENDED,
        subject_user_id=m.user_id,
        actor_id=actor.id,
        membership=m,
        from_status=MembershipStatus.ACTIVE,
        to_status=MembershipStatus.SUSPENDED,
    )
    brain.emit(
        session, event_type=brain.BrainEventType.COLLABORATOR_SUSPENDED,
        aggregate_type="collaborator", aggregate_id=m.id,
        work_id=m.work_id, story_world_id=m.story_world_id, actor_id=actor.id,
    )
    session.commit()
    session.refresh(m)
    return _read(m)


@router.post(
    "/memberships/{membership_id}/reactivate",
    response_model=ProjectMembershipRead,
)
def reactivate_membership(
    membership_id: str,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> ProjectMembershipRead:
    m = _manageable(membership_id, session, actor)
    if m.status != MembershipStatus.SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a suspended membership can be reactivated",
        )
    m.status = MembershipStatus.ACTIVE
    session.add(m)
    policy.record_audit(
        session,
        action=MembershipAuditAction.REACTIVATED,
        subject_user_id=m.user_id,
        actor_id=actor.id,
        membership=m,
        from_status=MembershipStatus.SUSPENDED,
        to_status=MembershipStatus.ACTIVE,
    )
    brain.emit(
        session, event_type=brain.BrainEventType.COLLABORATOR_REACTIVATED,
        aggregate_type="collaborator", aggregate_id=m.id,
        work_id=m.work_id, story_world_id=m.story_world_id, actor_id=actor.id,
    )
    session.commit()
    session.refresh(m)
    return _read(m)


@router.delete(
    "/memberships/{membership_id}", status_code=status.HTTP_204_NO_CONTENT
)
def revoke_membership(
    membership_id: str,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
):
    m = _manageable(membership_id, session, actor)
    if m.status == MembershipStatus.REVOKED:
        return
    previous = m.status
    m.status = MembershipStatus.REVOKED
    session.add(m)
    policy.record_audit(
        session,
        action=MembershipAuditAction.REVOKED,
        subject_user_id=m.user_id,
        actor_id=actor.id,
        membership=m,
        from_status=previous,
        to_status=MembershipStatus.REVOKED,
    )
    brain.emit(
        session, event_type=brain.BrainEventType.COLLABORATOR_REVOKED,
        aggregate_type="collaborator", aggregate_id=m.id,
        work_id=m.work_id, story_world_id=m.story_world_id, actor_id=actor.id,
    )
    session.commit()


@router.post(
    "/memberships/{membership_id}/accept",
    response_model=ProjectMembershipRead,
)
def accept_invitation(
    membership_id: str,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> ProjectMembershipRead:
    m = get_or_404(session, ProjectMembership, membership_id, name="ProjectMembership")
    if m.user_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the invited user can accept this invitation",
        )
    if m.status != MembershipStatus.INVITED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation is not pending",
        )
    m.status = MembershipStatus.ACTIVE
    m.accepted_at = utcnow()
    session.add(m)
    policy.record_audit(
        session,
        action=MembershipAuditAction.ACCEPTED,
        subject_user_id=m.user_id,
        actor_id=actor.id,
        membership=m,
        from_status=MembershipStatus.INVITED,
        to_status=MembershipStatus.ACTIVE,
    )
    session.commit()
    session.refresh(m)
    return _read(m)


@router.post(
    "/memberships/{membership_id}/decline",
    response_model=ProjectMembershipRead,
)
def decline_invitation(
    membership_id: str,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> ProjectMembershipRead:
    m = get_or_404(session, ProjectMembership, membership_id, name="ProjectMembership")
    if m.user_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the invited user can decline this invitation",
        )
    if m.status != MembershipStatus.INVITED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation is not pending",
        )
    m.status = MembershipStatus.DECLINED
    session.add(m)
    policy.record_audit(
        session,
        action=MembershipAuditAction.DECLINED,
        subject_user_id=m.user_id,
        actor_id=actor.id,
        membership=m,
        from_status=MembershipStatus.INVITED,
        to_status=MembershipStatus.DECLINED,
    )
    session.commit()
    session.refresh(m)
    return _read(m)


@router.get(
    "/memberships/{membership_id}/audits",
    response_model=list[MembershipAuditRead],
)
def membership_audits(
    membership_id: str,
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
) -> list[MembershipAuditRead]:
    _manageable(membership_id, session, actor)
    stmt = (
        select(MembershipAudit)
        .where(MembershipAudit.membership_id == membership_id)
        .order_by(MembershipAudit.created_at.asc())
    )
    return [MembershipAuditRead.model_validate(a) for a in session.exec(stmt).all()]


# --- The caller's own projects --------------------------------------------


@router.get("/me/projects", response_model=list[MyProjectRead])
def my_projects(
    session: Session = Depends(get_session),
    actor: User = Depends(get_current_user),
    include_inactive: bool = Query(default=False),
) -> list[MyProjectRead]:
    statuses = None if include_inactive else list(_LIVE_STATUSES)
    memberships = policy.my_memberships(session, actor, statuses=statuses)

    out: list[MyProjectRead] = []
    for m in memberships:
        work_title = None
        world_name = None
        if m.work_id:
            work = session.get(Work, m.work_id)
            work_title = work.title if work is not None else None
        if m.story_world_id:
            world = session.get(StoryWorld, m.story_world_id)
            world_name = world.name if world is not None else None
        out.append(
            MyProjectRead(
                membership_id=m.id,
                role=m.role,
                status=m.status,
                work_id=m.work_id,
                work_title=work_title,
                story_world_id=m.story_world_id,
                story_world_name=world_name,
                scopes=sorted(policy.role_scopes(m.role), key=lambda s: s.value),
            )
        )
    return out


@router.get("/collaboration/roles", response_model=list[ScopeCatalogEntry])
def collaboration_roles(
    _: User = Depends(get_current_user),
) -> list[ScopeCatalogEntry]:
    """The project-role → permission-scope matrix (for the private UI)."""
    return [
        ScopeCatalogEntry(role=role, scopes=scopes)
        for role, scopes in policy.roles_catalog()
    ]
