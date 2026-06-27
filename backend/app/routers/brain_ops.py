"""Brain Operations API (Prompt 16) — INTERNAL, admin-only.

Observability (vLLM/model/gateway/compiler/sessions/usage/agents/MCP/proposals/
LibreChat health), Prometheus exposition, and operational controls (disable model
requests, drain, rebuild project state, replay failed events, mark project cold,
prewarm project, revoke a Brain token, disable MCP).

Everything here is gated to admins — GPU / internal topology is never exposed on a
public endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlmodel import Session

from app.auth import ADMIN_ONLY
from app.auth.dependencies import get_current_user
from app.db import get_session
from app.models import BrainAccessToken, User
from app.models.base import utcnow
from app.models.enums import SecurityEventType
from app.schemas.ops import DrainRequest, MaintenanceRequest, ReplayRequest, ToggleRequest
from app.services import brain
from app.services import security_events as sec
from app.utils.logging import log_event

router = APIRouter(prefix="/brain/ops", tags=["brain-ops"], dependencies=ADMIN_ONLY)


def _audit(control: str, value, actor: User) -> None:
    log_event("ops.control", control=control, value=value, actor=actor.id)


# === observability =========================================================
@router.get("/status")
def ops_status(session: Session = Depends(get_session)) -> dict:
    """The full internal operations snapshot + derived health states."""
    return brain.ops.ops_status(session)


@router.get("/health")
def ops_health(session: Session = Depends(get_session)) -> dict:
    """Coarse health states (overall + per component)."""
    return brain.ops.health_summary(session)


@router.get("/metrics", response_class=PlainTextResponse)
def ops_metrics(session: Session = Depends(get_session)) -> str:
    """Prometheus-compatible exposition (admin-only; NOT a public endpoint)."""
    return brain.ops.prometheus_text(session)


# === operational controls ==================================================
@router.post("/controls/model-requests")
def control_model_requests(
    body: ToggleRequest, user: User = Depends(get_current_user),
) -> dict:
    """Disable / re-enable NEW model requests (in-flight requests are unaffected)."""
    brain.runtime.set_model_requests(enabled=body.enabled)
    _audit("model_requests", body.enabled, user)
    return brain.runtime.snapshot()


@router.post("/controls/drain")
def control_drain(body: DrainRequest, user: User = Depends(get_current_user)) -> dict:
    """Drain: reject new model requests while in-flight ones finish."""
    brain.runtime.set_drain(draining=body.draining)
    _audit("drain", body.draining, user)
    return brain.runtime.snapshot()


@router.post("/controls/mcp")
def control_mcp(body: ToggleRequest, user: User = Depends(get_current_user)) -> dict:
    """Disable / re-enable the MCP integration at runtime."""
    brain.runtime.set_mcp(enabled=body.enabled)
    _audit("mcp", body.enabled, user)
    return brain.runtime.snapshot()


@router.post("/controls/maintenance")
def control_maintenance(
    body: MaintenanceRequest, user: User = Depends(get_current_user),
) -> dict:
    """Set / clear a maintenance note (shown in the Ops view)."""
    brain.runtime.set_maintenance(body.note)
    _audit("maintenance", bool(body.note), user)
    return brain.runtime.snapshot()


# === state operations ======================================================
@router.post("/projects/{work_id}/rebuild")
def rebuild_project(
    work_id: str, full: bool = Query(default=False),
    session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> dict:
    """Rebuild a Work's compiled state (incremental, or a full rebuild)."""
    try:
        result = brain.compile_project(session, work_id=work_id, full=full)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _audit("rebuild_project", work_id, user)
    return result


@router.post("/projects/{work_id}/cold")
def mark_project_cold(
    work_id: str, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Mark a Work's sessions COLD (prefix cache treated as evicted)."""
    result = brain.session.mark_project_cold(session, work_id=work_id)
    _audit("mark_cold", work_id, user)
    return result


@router.post("/projects/{work_id}/prewarm")
def prewarm_project(
    work_id: str, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Best-effort prewarm of active project prefixes (no-op under dry-run)."""
    from app.services.ai.providers import get_provider

    result = brain.session.prewarm_active(session, provider=get_provider())
    _audit("prewarm", work_id, user)
    return result


@router.post("/events/replay")
def replay_events(
    body: ReplayRequest = ReplayRequest(), session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Re-queue dead-lettered BrainEvents (all, or a given set)."""
    requeued = brain.replay_failed(session, event_ids=body.event_ids)
    _audit("replay_events", requeued, user)
    return {"requeued": requeued}


@router.post("/tokens/{token_id}/revoke")
def revoke_token(
    token_id: str, session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Admin revoke of ANY Brain access token (immediate)."""
    token = session.get(BrainAccessToken, token_id)
    if token is None:
        raise HTTPException(status_code=404, detail="Token not found")
    if token.revoked_at is None:
        token.revoked_at = utcnow()
        session.add(token)
        sec.record_security_event(
            session, event_type=SecurityEventType.TOKEN_REVOKED, source="api",
            supervoid_user_id=token.user_id, token_id=token.id,
            reason="admin revoke", detail={"actor": user.id},
        )
        session.commit()
    _audit("revoke_token", token_id, user)
    return {"id": token.id, "revoked_at": token.revoked_at}
