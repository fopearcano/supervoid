"""Brain Operations aggregator (Prompt 16).

Collects the internal observability surface — vLLM/model health, the gateway
runtime gauge, compiler/outbox lag, sessions, token + latency aggregates, agent
and MCP failures, pending proposals and LibreChat health — and derives coarse
health states. Also renders a Prometheus-compatible exposition.

This is INTERNAL: the router that exposes it is admin-only. GPU / internal
topology is never placed on a public endpoint (and the provider health probe does
not return GPU data anyway — it is reported "when available").
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlmodel import Session, func, select

from app.config import settings
from app.models import (
    AgentActionProposal,
    AgentRun,
    BrainConversation,
    BrainMessage,
    BrainSession,
    ProjectBrainState,
    SecurityEvent,
)
from app.models.base import utcnow
from app.models.enums import (
    AgentRunStatus,
    BrainConversationStatus,
    BrainHealthState,
    BrainMessageRole,
    ProposalStatus,
    SecurityEventSeverity,
)
from app.services import brain
from app.services.ai.providers import get_provider

H = BrainHealthState


def _avg(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 2) if values else None


def _p95(values: list[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return round(ordered[idx], 2)


# --- component collectors --------------------------------------------------
def _vllm_health() -> dict:
    """Provider health (loaded model, reachability, latency). No GPU/topology —
    the probe does not expose it; reported as 'when available'."""
    try:
        provider = get_provider()
        h = provider.health()
        return {
            "provider": h.provider,
            "configured": h.configured,
            "reachable": h.reachable,
            "is_live": provider.name != "dry_run",
            "loaded_model": h.model,
            "context_limit": settings.brain_context_limit,
            "gpu_utilisation": None,  # when available (not exposed by /health)
            "latency_ms": h.latency_ms,
            "detail": h.detail,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "provider": settings.ai_provider, "configured": True, "reachable": False,
            "is_live": settings.ai_provider != "dry_run",
            "loaded_model": None, "context_limit": settings.brain_context_limit,
            "gpu_utilisation": None, "latency_ms": None, "detail": str(exc)[:200],
        }


def _librechat_health() -> dict:
    url = settings.librechat_health_url
    if not url:
        return {"configured": False, "reachable": None, "detail": "no health url configured"}
    try:
        import httpx

        resp = httpx.get(url, timeout=settings.librechat_health_timeout)
        return {"configured": True, "reachable": resp.status_code < 500,
                "status_code": resp.status_code, "detail": None}
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "reachable": False, "detail": str(exc)[:200]}


def _sessions(session: Session) -> dict:
    warmth_rows = session.exec(
        select(BrainSession.warmth, func.count(BrainSession.id)).group_by(BrainSession.warmth)
    ).all()
    by_warmth = {getattr(w, "value", str(w)): int(n) for w, n in warmth_rows}
    distinct_prefixes = int(session.exec(
        select(func.count(func.distinct(BrainSession.last_prefix_hash))).where(
            BrainSession.last_prefix_hash.is_not(None)
        )
    ).one() or 0)
    total = int(session.exec(select(func.count(BrainSession.id))).one() or 0)
    return {"total": total, "by_warmth": by_warmth, "distinct_prefix_hashes": distinct_prefixes}


def _token_and_latency(session: Session) -> dict:
    prompt_total = int(session.exec(
        select(func.coalesce(func.sum(BrainMessage.prompt_tokens), 0))
    ).one() or 0)
    completion_total = int(session.exec(
        select(func.coalesce(func.sum(BrainMessage.completion_tokens), 0))
    ).one() or 0)
    rows = session.exec(
        select(BrainMessage)
        .where(BrainMessage.role == BrainMessageRole.ASSISTANT)
        .order_by(BrainMessage.created_at.desc())
        .limit(settings.brain_ops_latency_window)
    ).all()
    ttfts, latencies = [], []
    for m in rows:
        sm = (m.structured_content or {}).get("session_metrics") or {}
        if sm.get("time_to_first_token_ms") is not None:
            ttfts.append(float(sm["time_to_first_token_ms"]))
        if sm.get("response_latency_ms") is not None:
            latencies.append(float(sm["response_latency_ms"]))
        elif (m.structured_content or {}).get("latency_ms") is not None:
            latencies.append(float(m.structured_content["latency_ms"]))
    return {
        "prompt_tokens_total": prompt_total,
        "completion_tokens_total": completion_total,
        "ttft_ms_avg": _avg(ttfts), "ttft_ms_p95": _p95(ttfts),
        "latency_ms_avg": _avg(latencies), "latency_ms_p95": _p95(latencies),
        "sampled_turns": len(rows),
    }


def _counts(session: Session) -> dict:
    active_conversations = int(session.exec(
        select(func.count(BrainConversation.id)).where(
            BrainConversation.status == BrainConversationStatus.ACTIVE
        )
    ).one() or 0)
    agent_failures = int(session.exec(
        select(func.count(AgentRun.id)).where(AgentRun.status == AgentRunStatus.FAILED)
    ).one() or 0)
    pending_proposals = int(session.exec(
        select(func.count(AgentActionProposal.id)).where(
            AgentActionProposal.status == ProposalStatus.PENDING
        )
    ).one() or 0)
    mcp_failures = int(session.exec(
        select(func.count(SecurityEvent.id)).where(
            SecurityEvent.source == "mcp",
            SecurityEvent.severity.in_([SecurityEventSeverity.WARNING, SecurityEventSeverity.CRITICAL]),
        )
    ).one() or 0)
    recent_cut = utcnow() - timedelta(hours=1)
    mcp_failures_recent = int(session.exec(
        select(func.count(SecurityEvent.id)).where(
            SecurityEvent.source == "mcp",
            SecurityEvent.severity.in_([SecurityEventSeverity.WARNING, SecurityEventSeverity.CRITICAL]),
            SecurityEvent.created_at >= recent_cut,
        )
    ).one() or 0)
    return {
        "active_conversations": active_conversations,
        "agent_failures": agent_failures,
        "pending_proposals": pending_proposals,
        "mcp_failures": mcp_failures,
        "mcp_failures_recent": mcp_failures_recent,
    }


# --- public aggregate ------------------------------------------------------
def ops_status(session: Session) -> dict:
    compiler = brain.compiler_health(session)
    outbox = compiler.get("outbox", {})
    studio = compiler.get("studio") or {}
    projects = compiler.get("projects") or []
    state_versions = {
        "studio": studio.get("version"),
        "projects": [
            {"work_id": p.get("work_id"), "story_world_id": p.get("story_world_id"),
             "version": p.get("version"), "stale": p.get("stale"), "lag": p.get("lag")}
            for p in projects
        ],
    }
    status = {
        "vllm": _vllm_health(),
        "gateway": brain.runtime.snapshot(),
        "compiler": {
            "head_sequence": compiler.get("head_sequence"),
            "compiler_lag": outbox.get("compiler_lag"),
            "unprocessed_events": outbox.get("unprocessed"),
            "failed_events": outbox.get("failed"),
            "studio_stale": outbox.get("studio_stale"),
            "studio_version": outbox.get("studio_version"),
            "stale_projects": outbox.get("stale_projects"),
        },
        "state_versions": state_versions,
        "sessions": _sessions(session),
        "usage": _token_and_latency(session),
        "librechat": _librechat_health(),
    }
    status.update(_counts(session))
    status["health"] = _health(status)
    return status


# --- health states ---------------------------------------------------------
def _health(status: dict) -> dict:
    vllm = status["vllm"]
    gw = status["gateway"]
    comp = status["compiler"]

    if not vllm["is_live"]:
        vllm_state = H.HEALTHY        # dry-run/offline dev provider
    elif vllm["reachable"]:
        vllm_state = H.HEALTHY
    else:
        vllm_state = H.UNAVAILABLE

    if gw["model_requests_disabled"] or gw["draining"]:
        gateway_state = H.MAINTENANCE
    elif gw["queue_depth"] > 0:
        gateway_state = H.DEGRADED
    else:
        gateway_state = H.HEALTHY

    if gw["mcp_disabled"]:
        mcp_state = H.MAINTENANCE
    elif status["mcp_failures_recent"] > 0:
        mcp_state = H.DEGRADED
    else:
        mcp_state = H.HEALTHY

    if comp["failed_events"]:
        compiler_state = H.DEGRADED   # dead-lettered events need attention
    elif comp["stale_projects"] or comp["studio_stale"] or comp["unprocessed_events"]:
        compiler_state = H.STALE
    else:
        compiler_state = H.HEALTHY

    components = {
        "vllm": vllm_state.value, "gateway": gateway_state.value,
        "mcp": mcp_state.value, "compiler": compiler_state.value,
    }
    # Overall precedence: a hard outage first, then operator maintenance, then
    # degradation, then staleness.
    states = [vllm_state, gateway_state, mcp_state, compiler_state]
    for level in (H.UNAVAILABLE, H.MAINTENANCE, H.DEGRADED, H.STALE):
        if level in states:
            overall = level
            break
    else:
        overall = H.HEALTHY
    return {"overall": overall.value, "components": components}


def health_summary(session: Session) -> dict:
    return ops_status(session)["health"]


# --- Prometheus exposition -------------------------------------------------
def _metric(lines: list[str], name: str, value, help_text: str, mtype: str = "gauge") -> None:
    if value is None:
        return
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} {mtype}")
    lines.append(f"{name} {int(value) if isinstance(value, bool) else value}")


def prometheus_text(session: Session) -> str:
    """A minimal Prometheus text-exposition of the numeric Brain metrics.
    Admin-only / internal — never served on a public endpoint."""
    s = ops_status(session)
    gw, comp, usage = s["gateway"], s["compiler"], s["usage"]
    lines: list[str] = []
    _metric(lines, "brain_gateway_active_requests", gw["active_requests"], "Active gateway requests")
    _metric(lines, "brain_gateway_queue_depth", gw["queue_depth"], "Requests waiting for a slot")
    _metric(lines, "brain_gateway_capacity", gw["capacity"], "Per-process concurrency capacity")
    _metric(lines, "brain_gateway_request_total", gw["request_total"], "Gateway requests served", "counter")
    _metric(lines, "brain_gateway_rejected_total", gw["rejected_total"], "Requests rejected (maintenance)", "counter")
    _metric(lines, "brain_model_requests_disabled", gw["model_requests_disabled"], "Model requests disabled flag")
    _metric(lines, "brain_draining", gw["draining"], "Draining flag")
    _metric(lines, "brain_mcp_disabled", gw["mcp_disabled"], "MCP disabled flag")
    _metric(lines, "brain_compiler_lag", comp["compiler_lag"], "Events behind the compiler cursor")
    _metric(lines, "brain_events_unprocessed", comp["unprocessed_events"], "Pending BrainEvents")
    _metric(lines, "brain_events_failed", comp["failed_events"], "Dead-lettered BrainEvents")
    _metric(lines, "brain_stale_projects", comp["stale_projects"], "Stale project states")
    _metric(lines, "brain_studio_state_version", comp["studio_version"], "Studio state version")
    _metric(lines, "brain_active_conversations", s["active_conversations"], "Active conversations")
    _metric(lines, "brain_distinct_prefix_hashes", s["sessions"]["distinct_prefix_hashes"], "Distinct prefix hashes")
    _metric(lines, "brain_prompt_tokens_total", usage["prompt_tokens_total"], "Prompt tokens used", "counter")
    _metric(lines, "brain_completion_tokens_total", usage["completion_tokens_total"], "Completion tokens used", "counter")
    _metric(lines, "brain_ttft_ms_avg", usage["ttft_ms_avg"], "Avg time to first token (ms)")
    _metric(lines, "brain_latency_ms_avg", usage["latency_ms_avg"], "Avg total latency (ms)")
    _metric(lines, "brain_agent_failures_total", s["agent_failures"], "Failed agent runs", "counter")
    _metric(lines, "brain_mcp_failures_total", s["mcp_failures"], "MCP failures", "counter")
    _metric(lines, "brain_pending_proposals", s["pending_proposals"], "Pending action proposals")
    _metric(lines, "brain_vllm_reachable", 1 if s["vllm"]["reachable"] else 0, "vLLM/provider reachable")
    return "\n".join(lines) + "\n"
