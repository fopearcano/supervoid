"""Context-aware hand-off from a SUPERVOID entity into the Brain (LibreChat).

Resolves the entity's project scope, ensures a bound :class:`BrainConversation`,
and mints a SIGNED, short-lived, single-use token. The landing endpoint consumes
the token and redirects to LibreChat. No sensitive project content is ever placed
in the URL — only the opaque token, which references a ``BrainHandoff`` row.

Deep-linking into a *specific* LibreChat conversation is NOT done — that would
require forking upstream LibreChat. Instead we open the normal Brain UI and make
the selected context available via the MCP ``select_active_project`` /
``list_my_projects`` tools (the most recent hand-off is the suggested active
project). See docs/LIBRECHAT_INTEGRATION.md → "Private navigation & hand-off".
"""
from __future__ import annotations

import base64
import hmac
from datetime import timedelta
from hashlib import sha256
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import settings
from app.models import BrainHandoff, PermissionScope, User
from app.models.base import utcnow
from app.models.brain import BrainConversation
from app.models.enums import BrainConversationStatus
from app.services import brain, policy


# --- entity -> project scope resolver --------------------------------------
def _work_scope(session: Session, work_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not work_id:
        return (None, None)
    from app.models import Work

    w = session.get(Work, work_id)
    return (work_id, w.story_world_id if w else None)


def _scope_work(session, entity_id):
    from app.models import Work

    w = session.get(Work, entity_id)
    return None if w is None else (w.id, w.story_world_id, w.title)


def _scope_story_world(session, entity_id):
    from app.models import StoryWorld

    sw = session.get(StoryWorld, entity_id)
    return None if sw is None else (None, sw.id, sw.name)


def _scope_manuscript(session, entity_id):
    from app.models import Manuscript

    m = session.get(Manuscript, entity_id)
    if m is None:
        return None
    w, sw = _work_scope(session, m.work_id)
    return (w, sw, m.title)


def _scope_asset(session, entity_id):
    from app.models import Asset

    a = session.get(Asset, entity_id)
    return None if a is None else (a.work_id, a.story_world_id, a.title)


def _scope_production_task(session, entity_id):
    from app.models import Manuscript, ProductionItem

    t = session.get(ProductionItem, entity_id)
    if t is None:
        return None
    work_id, sw = t.work_id, t.story_world_id
    if not work_id and t.manuscript_id:
        m = session.get(Manuscript, t.manuscript_id)
        work_id = m.work_id if m else None
    if work_id:
        work_id, sw = _work_scope(session, work_id)
    return (work_id, sw, t.title or "Production task")


def _scope_rights(session, entity_id):
    from app.models import Rights

    r = session.get(Rights, entity_id)
    if r is None:
        return None
    w, sw = _work_scope(session, r.work_id)
    return (w, sw, f"Rights · {r.territory or 'World'}")


def _scope_gn_page(session, entity_id):
    from app.models import (
        GraphicNovelChapter, GraphicNovelPage, GraphicNovelProduction, GraphicNovelVolume,
    )

    page = session.get(GraphicNovelPage, entity_id)
    if page is None:
        return None
    ch = session.get(GraphicNovelChapter, page.chapter_id)
    vol = session.get(GraphicNovelVolume, ch.volume_id) if ch else None
    prod = session.get(GraphicNovelProduction, vol.production_id) if vol else None
    if prod is None:
        return None
    w, sw = _work_scope(session, prod.work_id)
    return (w, sw, f"GN page {getattr(page, 'page_number', '')}".strip())


def _scope_gn_panel(session, entity_id):
    from app.models import GraphicNovelPanel

    panel = session.get(GraphicNovelPanel, entity_id)
    if panel is None:
        return None
    scoped = _scope_gn_page(session, panel.page_id)
    if scoped is None:
        return None
    return (scoped[0], scoped[1], "GN panel")


def _scope_screen_project(session, entity_id):
    from app.models import ScreenProject

    sp = session.get(ScreenProject, entity_id)
    if sp is None:
        return None
    w, sw = _work_scope(session, sp.source_work_id)
    return (w, sw, getattr(sp, "title", None) or "Screen project")


def _scope_scene(session, entity_id):
    from app.models import Scene, ScreenSequence

    sc = session.get(Scene, entity_id)
    if sc is None:
        return None
    seq = session.get(ScreenSequence, sc.sequence_id)
    if seq is None:
        return None
    scoped = _scope_screen_project(session, seq.screen_project_id)
    return None if scoped is None else (scoped[0], scoped[1], "Scene")


def _scope_shot(session, entity_id):
    from app.models import Shot

    shot = session.get(Shot, entity_id)
    if shot is None:
        return None
    scoped = _scope_scene(session, shot.scene_id)
    return None if scoped is None else (scoped[0], scoped[1], "Shot")


_RESOLVERS = {
    "work": _scope_work,
    "story_world": _scope_story_world,
    "manuscript": _scope_manuscript,
    "asset": _scope_asset,
    "production_task": _scope_production_task,
    "production_item": _scope_production_task,
    "rights": _scope_rights,
    "gn_page": _scope_gn_page,
    "gn_panel": _scope_gn_panel,
    "screen_project": _scope_screen_project,
    "scene": _scope_scene,
    "shot": _scope_shot,
}


def resolve_scope(session: Session, entity_type: str, entity_id: str):
    resolver = _RESOLVERS.get(entity_type)
    if resolver is None:
        raise HTTPException(status_code=400, detail=f"Unsupported entity type '{entity_type}'.")
    scoped = resolver(session, entity_id)
    if scoped is None:
        raise HTTPException(status_code=404, detail=f"{entity_type} not found.")
    work_id, story_world_id, label = scoped
    if not work_id and not story_world_id:
        raise HTTPException(status_code=400, detail="Entity is not linked to a project.")
    return work_id, story_world_id, label


# --- signed, short-lived token ---------------------------------------------
def _sign(handoff_id: str, exp_ts: int) -> str:
    payload = f"{handoff_id}:{exp_ts}"
    sig = hmac.new(settings.secret_key.encode(), payload.encode(), sha256).hexdigest()[:32]
    raw = f"{payload}:{sig}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _verify(token: str) -> tuple[str, int]:
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + pad).decode()
        handoff_id, exp_str, sig = raw.rsplit(":", 2)
        exp_ts = int(exp_str)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Malformed hand-off token.") from exc
    expected = hmac.new(
        settings.secret_key.encode(), f"{handoff_id}:{exp_ts}".encode(), sha256
    ).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=400, detail="Invalid hand-off token.")
    return handoff_id, exp_ts


# --- conversation binding ---------------------------------------------------
def _resolve_conversation(
    session: Session, user: User, *, work_id, story_world_id, profile: str
) -> BrainConversation:
    stmt = select(BrainConversation).where(
        BrainConversation.owner_user_id == user.id,
        BrainConversation.status == BrainConversationStatus.ACTIVE,
    )
    if work_id:
        stmt = stmt.where(BrainConversation.work_id == work_id)
    else:
        stmt = stmt.where(BrainConversation.story_world_id == story_world_id)
    conv = session.exec(stmt.order_by(BrainConversation.updated_at.desc())).first()
    if conv is not None:
        return conv
    return brain.create_conversation(
        session, owner_user_id=user.id, work_id=work_id, story_world_id=story_world_id,
        active_profile=profile,
    )


def create_handoff(
    session: Session, user: User, *, entity_type: str, entity_id: str,
    profile: Optional[str] = None,
) -> tuple[BrainHandoff, str]:
    """Resolve scope + permission, bind a conversation, mint a signed token.
    Caller commits. Returns ``(handoff, token)``."""
    work_id, story_world_id, label = resolve_scope(session, entity_type, entity_id)
    # NEVER guess access to an unauthorised project.
    policy.ensure_can(
        session, user, PermissionScope.VIEW_PROJECT,
        work_id=work_id, story_world_id=story_world_id,
    )
    prof = (profile or "studio-director").replace("_", "-")
    conv = _resolve_conversation(
        session, user, work_id=work_id, story_world_id=story_world_id, profile=prof
    )
    expires_at = utcnow() + timedelta(seconds=settings.brain_handoff_ttl_seconds)
    handoff = BrainHandoff(
        user_id=user.id, conversation_id=conv.id, entity_type=entity_type,
        entity_id=entity_id, label=label, work_id=work_id, story_world_id=story_world_id,
        profile=prof, expires_at=expires_at,
    )
    session.add(handoff)
    session.flush()
    token = _sign(handoff.id, int(expires_at.timestamp()))
    return handoff, token


def consume_handoff(session: Session, token: str) -> BrainHandoff:
    """Validate + single-use-consume a hand-off token. Caller commits."""
    handoff_id, _exp = _verify(token)
    handoff = session.get(BrainHandoff, handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="Hand-off not found.")
    now = utcnow()
    exp = handoff.expires_at
    if exp.tzinfo is None:
        from datetime import timezone

        exp = exp.replace(tzinfo=timezone.utc)
    if handoff.consumed_at is not None:
        raise HTTPException(status_code=409, detail="Hand-off already used.")
    if exp < now:
        raise HTTPException(status_code=410, detail="Hand-off expired.")
    handoff.consumed_at = now
    session.add(handoff)
    session.flush()
    return handoff


# --- status panel -----------------------------------------------------------
def brain_status(session: Session, user: User) -> dict:
    """Current active project, state version, model + compiler status, and the
    count of pending proposals the user may act on."""
    from app.models import AgentActionProposal, ProposalStatus
    from app.services.brain import compiler

    # Most recent hand-off is the suggested "active project".
    recent = session.exec(
        select(BrainHandoff)
        .where(BrainHandoff.user_id == user.id)
        .order_by(BrainHandoff.created_at.desc())
    ).first()
    active = None
    state_version = None
    if recent is not None and (recent.work_id or recent.story_world_id):
        active = {"entity_type": recent.entity_type, "label": recent.label,
                  "work_id": recent.work_id, "story_world_id": recent.story_world_id}
        ps = brain.get_project_state(
            session, work_id=recent.work_id, story_world_id=recent.story_world_id
        )
        state_version = ps.version if ps else None
    if state_version is None:
        ss = brain.get_studio_state(session)
        state_version = ss.version if ss else None

    health = compiler.compiler_health(session)
    studio = health.get("studio") or {}
    projects = health.get("projects") or []
    stale_projects = sum(1 for p in projects if p.get("stale"))

    # Pending proposals the user can act on.
    is_admin = user.role.value == "admin"
    if is_admin:
        pending = session.exec(
            select(AgentActionProposal).where(AgentActionProposal.status == ProposalStatus.PENDING)
        ).all()
        pending_count = len(pending)
    else:
        member_work_ids = {
            m.work_id for m in policy.my_memberships(session, user) if m.work_id
        }
        rows = session.exec(
            select(AgentActionProposal).where(AgentActionProposal.status == ProposalStatus.PENDING)
        ).all()
        pending_count = sum(
            1 for p in rows
            if (p.target_type == "work" and p.target_id in member_work_ids)
        )

    return {
        "active_project": active,
        "state_version": state_version,
        "model": {"provider": settings.ai_provider, "model": settings.ai_model,
                  "gateway_model": settings.brain_gateway_model},
        "compiler": {
            "head_sequence": health.get("head_sequence"),
            "studio_stale": studio.get("stale"),
            "studio_version": studio.get("version"),
            "stale_projects": stale_projects,
        },
        "pending_proposals": pending_count,
        "brain_url": settings.librechat_public_url,
    }
