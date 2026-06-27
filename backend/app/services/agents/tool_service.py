"""The governed internal tool service for model-driven agent runs (Prompt 9).

ONLY read-only tools execute here, and only after a permission check. Their
results are redacted and bounded before being fed back to the model. Mutation /
external tools never reach this service — the runner converts those intentions
into human-approved proposals instead.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from app.models.enums import AgentToolKind, PermissionScope
from app.services import policy
from app.services.agents.tools import Tool


class ToolExecutionError(RuntimeError):
    """A read-only tool could not be executed (bad target, etc.)."""


class ToolPermissionError(RuntimeError):
    """The user lacks a permission the tool declares."""


def _ensure_permissions(
    session: Session, user, tool: Tool, *, work_id: Optional[str], story_world_id: Optional[str]
) -> None:
    for perm in tool.required_permissions:
        try:
            scope = PermissionScope(perm)
        except ValueError:
            continue
        if not policy.can(session, user, scope, work_id=work_id, story_world_id=story_world_id):
            raise ToolPermissionError(
                f"Tool '{tool.key}' requires permission '{perm}'."
            )


def _read_entity(session: Session, call, *, work_id, story_world_id) -> dict:
    from app.services.agents.runner import build_snapshot, redact

    target_type = call.target_type
    target_id = call.target_id
    if not target_type or not target_id:
        raise ToolExecutionError("read_entity requires a target_type and target_id.")
    snap = build_snapshot(session, target_type, target_id)  # raises 404 if missing
    return redact(snap)


def _search_knowledge(session: Session, call, *, work_id, story_world_id) -> dict:
    from app.models import KnowledgeEntity
    from app.services.agents.runner import redact
    from app.services.brain import state_builders as sb

    work_ids: list[str] = []
    if work_id:
        work_ids = [work_id]
    elif story_world_id:
        from app.models import Work

        work_ids = list(
            session.exec(select(Work.id).where(Work.story_world_id == story_world_id)).all()
        )
    if not work_ids:
        return {"entities": []}
    entity_ids = sb._entity_ids_for_works(session, work_ids)
    if not entity_ids:
        return {"entities": []}
    rows = session.exec(
        select(KnowledgeEntity)
        .where(KnowledgeEntity.id.in_(entity_ids))
        .order_by(KnowledgeEntity.name)
        .limit(20)  # bounded
    ).all()
    return redact({
        "entities": [
            {"kind": e.kind.value, "name": e.name,
             "description": (e.description or "")[:280]}
            for e in rows
        ]
    })


_READ_EXECUTORS = {
    "read_entity": _read_entity,
    "search_knowledge": _search_knowledge,
}


def execute_read_only(
    session: Session,
    tool: Tool,
    call,
    *,
    user,
    work_id: Optional[str],
    story_world_id: Optional[str],
) -> dict:
    """Execute a read-only tool under governance. Raises if the tool is not
    read-only, the user lacks permission, or the read fails."""
    if tool.kind != AgentToolKind.READ_ONLY:
        raise ToolExecutionError(f"Tool '{tool.key}' is not read-only.")
    _ensure_permissions(session, user, tool, work_id=work_id, story_world_id=story_world_id)
    executor = _READ_EXECUTORS.get(tool.key)
    if executor is None:
        # A read-only tool with no executor returns an explicit, bounded stub
        # rather than failing the whole run.
        return {"note": f"No internal executor for read-only tool '{tool.key}'."}
    return executor(session, call, work_id=work_id, story_world_id=story_world_id)
