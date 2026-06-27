"""SUPERVOID ↔ LibreChat identity linking (Prompt 15).

Admin-managed links bridge a SUPERVOID user to a LibreChat identity. The MCP
server resolves an incoming LibreChat identity to a SUPERVOID user THROUGH an
ACTIVE link — there is no implicit provisioning, so unlinked identities are
rejected. One link per SUPERVOID user (re-linking upserts).

This is the simpler, robust first version of the bridge — not a custom OAuth/OIDC
provider. Every lifecycle change emits an audit security event.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from app.models import LibreChatIdentityLink, User
from app.models.base import utcnow
from app.models.enums import IdentityLinkStatus, SecurityEventType
from app.services import security_events


def get_link_for_user(session: Session, supervoid_user_id: str) -> Optional[LibreChatIdentityLink]:
    return session.exec(
        select(LibreChatIdentityLink).where(
            LibreChatIdentityLink.supervoid_user_id == supervoid_user_id
        )
    ).first()


def get_link(session: Session, link_id: str) -> Optional[LibreChatIdentityLink]:
    return session.get(LibreChatIdentityLink, link_id)


def list_links(
    session: Session, *, status: Optional[IdentityLinkStatus] = None,
    limit: int = 200, offset: int = 0,
) -> list[LibreChatIdentityLink]:
    stmt = select(LibreChatIdentityLink)
    if status is not None:
        stmt = stmt.where(LibreChatIdentityLink.status == status)
    stmt = stmt.order_by(LibreChatIdentityLink.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())


def resolve_active_link(
    session: Session, *, supervoid_user_id: str,
    email: Optional[str] = None, librechat_user_id: Optional[str] = None,
) -> Optional[LibreChatIdentityLink]:
    """The ACTIVE link for a user, but only if the incoming LibreChat identity
    matches it. Returns None for no link / not active / identity mismatch."""
    link = get_link_for_user(session, supervoid_user_id)
    if link is None or link.status != IdentityLinkStatus.ACTIVE:
        return None
    if email and link.librechat_email and link.librechat_email.lower() != email.lower():
        return None
    if librechat_user_id and link.librechat_user_id and link.librechat_user_id != librechat_user_id:
        return None
    return link


def link_user(
    session: Session, *, supervoid_user_id: str, librechat_email: str,
    librechat_user_id: Optional[str] = None, linked_by_id: Optional[str] = None,
    note: Optional[str] = None, verify: bool = False,
) -> LibreChatIdentityLink:
    """Create or update the link for a SUPERVOID user (one per user). Re-linking
    a previously disabled/revoked identity moves it back to PENDING (or ACTIVE
    when ``verify`` is set). Adds + flushes; caller commits."""
    user = session.get(User, supervoid_user_id)
    if user is None:
        raise ValueError("SUPERVOID user not found")
    now = utcnow()
    link = get_link_for_user(session, supervoid_user_id)
    if link is None:
        link = LibreChatIdentityLink(supervoid_user_id=supervoid_user_id)
    link.librechat_email = (librechat_email or "").strip().lower()
    if librechat_user_id is not None:
        link.librechat_user_id = librechat_user_id
    link.linked_at = now
    link.linked_by_id = linked_by_id
    if note is not None:
        link.note = note
    link.disabled_at = None
    link.disabled_by_id = None
    if verify:
        link.status = IdentityLinkStatus.ACTIVE
        link.verified_at = now
    else:
        link.status = IdentityLinkStatus.PENDING
        link.verified_at = None
    session.add(link)
    session.flush()
    security_events.record_security_event(
        session, event_type=SecurityEventType.IDENTITY_LINKED, source="api",
        supervoid_user_id=supervoid_user_id, librechat_user_id=link.librechat_user_id,
        email=link.librechat_email, reason=("verified" if verify else "pending"),
        detail={"linked_by": linked_by_id, "link_id": link.id},
    )
    return link


def verify_link(
    session: Session, link: LibreChatIdentityLink, *, actor_id: Optional[str] = None
) -> LibreChatIdentityLink:
    """Mark a link verified + ACTIVE (the only state the MCP server accepts)."""
    link.status = IdentityLinkStatus.ACTIVE
    link.verified_at = utcnow()
    link.disabled_at = None
    link.disabled_by_id = None
    session.add(link)
    session.flush()
    security_events.record_security_event(
        session, event_type=SecurityEventType.IDENTITY_VERIFIED, source="api",
        supervoid_user_id=link.supervoid_user_id, librechat_user_id=link.librechat_user_id,
        email=link.librechat_email, detail={"actor": actor_id, "link_id": link.id},
    )
    return link


def disable_link(
    session: Session, link: LibreChatIdentityLink, *, actor_id: Optional[str] = None,
    note: Optional[str] = None,
) -> LibreChatIdentityLink:
    """Disable a link — the LibreChat identity can no longer authenticate MCP."""
    link.status = IdentityLinkStatus.DISABLED
    link.disabled_at = utcnow()
    link.disabled_by_id = actor_id
    if note is not None:
        link.note = note
    session.add(link)
    session.flush()
    security_events.record_security_event(
        session, event_type=SecurityEventType.IDENTITY_DISABLED, source="api",
        supervoid_user_id=link.supervoid_user_id, librechat_user_id=link.librechat_user_id,
        email=link.librechat_email, detail={"actor": actor_id, "link_id": link.id},
    )
    return link
