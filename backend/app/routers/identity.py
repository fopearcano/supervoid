"""Identity linking + security events API (Prompt 15).

* Admin linking workflow: ``/identity-links`` (list / create / verify / disable /
  edit), admin-only.
* Member self-service: ``/identity-links/me`` — a member sees their own Brain
  identity link status (read-only).
* Security events: ``/security-events`` (admin) — failed mappings, revoked-token
  use, disabled members, project-denied tool calls, suspicious repeated failures,
  and the token/identity audit trail.

This is the simpler, robust identity bridge — not a custom OAuth/OIDC provider
(see docs/IDENTITY.md).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.auth import ADMIN_ONLY
from app.auth.dependencies import get_current_user
from app.db import get_session
from app.models import LibreChatIdentityLink, User
from app.models.enums import (
    IdentityLinkStatus,
    SecurityEventSeverity,
    SecurityEventType,
)
from app.schemas.identity import (
    IdentityActionRequest,
    IdentityLinkCreate,
    IdentityLinkRead,
    IdentityLinkUpdate,
    MyIdentityRead,
    SecurityEventRead,
)
from app.services import identity as identity_svc
from app.services import security_events as sec

router = APIRouter(tags=["identity"])


def _read(session: Session, link: LibreChatIdentityLink) -> IdentityLinkRead:
    user = session.get(User, link.supervoid_user_id)
    return IdentityLinkRead(
        id=link.id, supervoid_user_id=link.supervoid_user_id,
        user_email=(user.email if user else None),
        user_full_name=(user.full_name if user else None),
        librechat_user_id=link.librechat_user_id, librechat_email=link.librechat_email,
        status=link.status, linked_at=link.linked_at, verified_at=link.verified_at,
        disabled_at=link.disabled_at, linked_by_id=link.linked_by_id,
        disabled_by_id=link.disabled_by_id, note=link.note, created_at=link.created_at,
    )


# === admin linking workflow ================================================
@router.get("/identity-links", response_model=list[IdentityLinkRead], dependencies=ADMIN_ONLY)
def list_identity_links(
    session: Session = Depends(get_session),
    link_status: Optional[IdentityLinkStatus] = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
) -> list[IdentityLinkRead]:
    rows = identity_svc.list_links(session, status=link_status, limit=limit, offset=skip)
    return [_read(session, r) for r in rows]


@router.post("/identity-links", response_model=IdentityLinkRead, status_code=201, dependencies=ADMIN_ONLY)
def create_identity_link(
    body: IdentityLinkCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> IdentityLinkRead:
    try:
        link = identity_svc.link_user(
            session, supervoid_user_id=body.supervoid_user_id,
            librechat_email=body.librechat_email, librechat_user_id=body.librechat_user_id,
            linked_by_id=user.id, note=body.note, verify=body.verify,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    session.commit()
    session.refresh(link)
    return _read(session, link)


# NOTE: the fixed ``/me`` path must precede ``/{link_id}``.
@router.get("/identity-links/me", response_model=MyIdentityRead)
def my_identity_link(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MyIdentityRead:
    """A member's own Brain identity link status (self-service)."""
    link = identity_svc.get_link_for_user(session, user.id)
    if link is None:
        return MyIdentityRead(linked=False)
    return MyIdentityRead(
        linked=True, status=link.status, librechat_email=link.librechat_email,
        linked_at=link.linked_at, verified_at=link.verified_at,
    )


def _load_link(session: Session, link_id: str) -> LibreChatIdentityLink:
    link = identity_svc.get_link(session, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Identity link not found")
    return link


@router.get("/identity-links/{link_id}", response_model=IdentityLinkRead, dependencies=ADMIN_ONLY)
def get_identity_link(
    link_id: str, session: Session = Depends(get_session)
) -> IdentityLinkRead:
    return _read(session, _load_link(session, link_id))


@router.patch("/identity-links/{link_id}", response_model=IdentityLinkRead, dependencies=ADMIN_ONLY)
def update_identity_link(
    link_id: str,
    body: IdentityLinkUpdate,
    session: Session = Depends(get_session),
) -> IdentityLinkRead:
    link = _load_link(session, link_id)
    if body.librechat_email is not None:
        link.librechat_email = body.librechat_email.strip().lower()
    if body.librechat_user_id is not None:
        link.librechat_user_id = body.librechat_user_id
    if body.note is not None:
        link.note = body.note
    session.add(link)
    session.commit()
    session.refresh(link)
    return _read(session, link)


@router.post("/identity-links/{link_id}/verify", response_model=IdentityLinkRead, dependencies=ADMIN_ONLY)
def verify_identity_link(
    link_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> IdentityLinkRead:
    link = identity_svc.verify_link(session, _load_link(session, link_id), actor_id=user.id)
    session.commit()
    session.refresh(link)
    return _read(session, link)


@router.post("/identity-links/{link_id}/disable", response_model=IdentityLinkRead, dependencies=ADMIN_ONLY)
def disable_identity_link(
    link_id: str,
    body: IdentityActionRequest = IdentityActionRequest(),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> IdentityLinkRead:
    link = identity_svc.disable_link(
        session, _load_link(session, link_id), actor_id=user.id, note=body.note
    )
    session.commit()
    session.refresh(link)
    return _read(session, link)


# === security events (admin) ===============================================
@router.get("/security-events", response_model=list[SecurityEventRead], dependencies=ADMIN_ONLY)
def list_security_events(
    session: Session = Depends(get_session),
    event_type: Optional[SecurityEventType] = Query(default=None),
    severity: Optional[SecurityEventSeverity] = Query(default=None),
    source: Optional[str] = Query(default=None),
    email: Optional[str] = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[SecurityEventRead]:
    rows = sec.list_security_events(
        session, event_type=event_type, severity=severity, source=source,
        email=email, limit=limit, offset=skip,
    )
    return [SecurityEventRead.model_validate(r, from_attributes=True) for r in rows]
