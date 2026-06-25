"""The supervised agent runner.

Builds a redacted input snapshot, runs the agent through the (dry-run by
default) provider, persists findings immediately, turns any mutations into
PENDING proposals, and never auto-executes. Approved proposals are executed
through the tool executors; retries create new runs (history is append-only).
"""
from __future__ import annotations

import re
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session

from app.models import (
    AgentActionProposal,
    AgentFinding,
    AgentMutability,
    AgentRiskLevel,
    AgentRun,
    AgentRunStatus,
    AgentToolKind,
    ProposalStatus,
    User,
    Work,
)
from app.models.base import utcnow
from app.services.agents.definitions import AgentContext, AgentDefinition
from app.services.agents.tools import get_tool
from app.services.ai.providers import ChatMessage, get_provider

# Keys whose values must never be persisted in snapshots / payloads / results.
_SECRET_RE = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|authorization|bearer|credential)",
    re.IGNORECASE,
)
_REDACTED = "[redacted]"


def redact(value):
    """Recursively strip secret-like keys from a structure."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out[k] = _REDACTED if _SECRET_RE.search(str(k)) else redact(v)
        return out
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


# --- snapshots -------------------------------------------------------------


def _manuscript_snapshot(session: Session, target_id: str) -> Optional[dict]:
    from app.models import Manuscript

    m = session.get(Manuscript, target_id)
    if m is None:
        return None
    return {
        "id": m.id, "title": m.title, "subtitle": m.subtitle,
        "synopsis": m.synopsis, "genre": m.genre, "word_count": m.word_count,
        "work_type": m.work_type.value, "status": m.status.value,
    }


def _work_snapshot(session: Session, target_id: str) -> Optional[dict]:
    w = session.get(Work, target_id)
    if w is None:
        return None
    return {
        "id": w.id, "title": w.title, "subtitle": w.subtitle,
        "synopsis": w.synopsis, "internal_pitch": w.internal_pitch,
        "genre": w.genre, "status": w.status.value, "word_count": w.word_count,
    }


_SNAPSHOTS = {"manuscript": _manuscript_snapshot, "work": _work_snapshot}


def build_snapshot(
    session: Session, target_type: Optional[str], target_id: Optional[str]
) -> dict:
    if not target_type or not target_id:
        return {}
    builder = _SNAPSHOTS.get(target_type)
    if builder is None:
        return {"target_type": target_type, "target_id": target_id}
    snap = builder(session, target_id)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"{target_type} not found")
    return redact(snap)


# --- running ---------------------------------------------------------------


def run_agent(
    session: Session,
    *,
    definition: AgentDefinition,
    user: User,
    target_type: Optional[str],
    target_id: Optional[str],
    retry_of_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> AgentRun:
    """Execute an agent and persist its run, findings and proposals. Caller
    commits. Validation failures raise before any run is created.

    ``correlation_id`` ties the run to the originating HTTP request (the API
    layer passes ``request.state.request_id``); it falls back to a fresh id when
    invoked outside a request (seeds, scripts)."""
    if not definition.enabled:
        raise HTTPException(status_code=409, detail="Agent is disabled.")
    if target_type and target_type not in definition.supported_entity_types:
        raise HTTPException(
            status_code=400,
            detail=f"Agent '{definition.key}' does not support '{target_type}'.",
        )
    snapshot = build_snapshot(session, target_type, target_id)

    provider = get_provider()
    completion = provider.chat(
        [
            ChatMessage("system", f"AGENT:{definition.key}\n{definition.description}"),
            ChatMessage("user", str(redact(snapshot))),
        ],
        model=definition.default_model,
    )

    run = AgentRun(
        agent_key=definition.key,
        requested_by_id=user.id,
        target_type=target_type,
        target_id=target_id,
        provider=completion.provider,
        model=completion.model,
        input_snapshot=snapshot,
        status=AgentRunStatus.RUNNING,
        started_at=utcnow(),
        correlation_id=correlation_id or uuid4().hex,
        retry_of_id=retry_of_id,
    )
    session.add(run)
    session.flush()

    try:
        ctx = AgentContext(
            target_type=target_type, target_id=target_id, snapshot=snapshot,
            completion={"provider": completion.provider, "model": completion.model},
        )
        output = definition.handler(ctx)

        # Invariant: a read-only agent must never produce proposals.
        if definition.mutability == AgentMutability.READ_ONLY and output.proposals:
            raise RuntimeError("Read-only agent attempted to emit a proposal.")

        for f in output.findings:
            session.add(AgentFinding(
                run_id=run.id, agent_key=definition.key, severity=f.severity,
                category=f.category, target_type=f.target_type or target_type,
                target_id=f.target_id or target_id, message=f.message,
                evidence=redact(f.evidence or {}), confidence=f.confidence,
            ))

        for p in output.proposals:
            tool = get_tool(p.tool_key)
            if tool is None:
                raise RuntimeError(f"Unknown tool '{p.tool_key}'.")
            if tool.kind == AgentToolKind.READ_ONLY:
                raise RuntimeError(f"Tool '{p.tool_key}' is read-only; cannot propose.")
            action_type = "external" if tool.kind == AgentToolKind.EXTERNAL else "mutation"
            session.add(AgentActionProposal(
                run_id=run.id, agent_key=definition.key, tool_key=tool.key,
                action_type=action_type,
                target_type=p.target_type or target_type,
                target_id=p.target_id or target_id,
                payload=redact(p.payload or {}), reason=p.reason,
                risk_level=p.risk_level or tool.risk_level,
                requires_approval=True,  # every proposal is human-gated
                status=ProposalStatus.PENDING,
            ))

        if completion.usage:
            run.prompt_tokens = completion.usage.get("prompt_tokens")
            run.completion_tokens = completion.usage.get("completion_tokens")
            run.total_tokens = completion.usage.get("total_tokens")
        run.result = redact(output.result or {})
        run.status = AgentRunStatus.SUCCEEDED
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - record any handler failure on the run
        run.status = AgentRunStatus.FAILED
        run.error = str(exc)
    finally:
        run.completed_at = utcnow()
        session.add(run)
    return run


def retry_run(
    session: Session,
    original: AgentRun,
    *,
    definition: AgentDefinition,
    user: User,
    correlation_id: Optional[str] = None,
) -> AgentRun:
    """Create a NEW run for the same agent/target — never overwrite history."""
    return run_agent(
        session, definition=definition, user=user,
        target_type=original.target_type, target_id=original.target_id,
        retry_of_id=original.id, correlation_id=correlation_id,
    )


# --- proposal execution ----------------------------------------------------


def _exec_update_work_metadata(session: Session, proposal: AgentActionProposal) -> dict:
    if not proposal.target_id:
        raise RuntimeError("No target work for metadata update.")
    work = session.get(Work, proposal.target_id)
    if work is None:
        raise RuntimeError("Work not found.")
    allowed = {"internal_pitch", "synopsis", "target_audience", "genre", "subtitle"}
    changes = (proposal.payload or {}).get("changes", {})
    applied: dict = {}
    for key, val in changes.items():
        if key in allowed:
            setattr(work, key, val)
            applied[key] = val
    session.add(work)
    return {"updated_fields": applied}


# Concrete executors for internal mutation tools. Destructive / publishing /
# rights / external tools intentionally record the action rather than perform
# it: even after approval the framework does not fire those side effects (no
# real external calls, no secrets) — they remain a deliberate manual step.
_EXECUTORS = {"update_work_metadata": _exec_update_work_metadata}


def execute_proposal(
    session: Session, proposal: AgentActionProposal, *, user: User
) -> AgentActionProposal:
    if proposal.status != ProposalStatus.APPROVED:
        raise HTTPException(
            status_code=409,
            detail="Only an approved proposal can be executed.",
        )
    tool = get_tool(proposal.tool_key)
    try:
        executor = _EXECUTORS.get(proposal.tool_key)
        if executor is not None:
            result = executor(session, proposal)
        elif tool is not None and tool.kind == AgentToolKind.EXTERNAL:
            result = {
                "mode": "recorded",
                "note": "External action recorded — not dispatched (dry-run, no secrets).",
            }
        else:
            result = {
                "mode": "recorded",
                "note": (
                    "High-risk action recorded — perform the underlying operation "
                    "manually through its dedicated, audited endpoint."
                ),
            }
        proposal.execution_result = redact(result)
        proposal.status = ProposalStatus.EXECUTED
    except Exception as exc:  # noqa: BLE001 - record execution failure
        proposal.status = ProposalStatus.FAILED
        proposal.error = str(exc)
    session.add(proposal)
    return proposal


def risk_is_always_gated(risk: AgentRiskLevel) -> bool:
    return risk in (AgentRiskLevel.HIGH, AgentRiskLevel.CRITICAL)
