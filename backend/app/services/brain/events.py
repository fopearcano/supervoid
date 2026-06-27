"""The single entry point for emitting Brain domain events (the outbox).

Mutation services call :func:`emit` inside their own database transaction, so
the event row is committed atomically with the change it describes (the outbox
*is* a table in the same database — no second datastore, no triggers). Payloads
carry identifiers and a changed-field *summary*, never a complete,
secret-bearing record.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional, Union

from sqlmodel import Session

from app.models import BrainEvent
from app.services.brain import append_event
from app.utils.logging import get_request_id


# Stable, dotted event-type names. Add new ones here; never rename an existing
# one (consumers and history depend on stability).
class BrainEventType:
    # Work
    WORK_CREATED = "work.created"
    WORK_UPDATED = "work.updated"
    WORK_DELETED = "work.deleted"
    # Story world / series
    STORY_WORLD_CREATED = "story_world.created"
    STORY_WORLD_UPDATED = "story_world.updated"
    STORY_WORLD_DELETED = "story_world.deleted"
    STORY_SERIES_CREATED = "story_series.created"
    STORY_SERIES_UPDATED = "story_series.updated"
    STORY_SERIES_DELETED = "story_series.deleted"
    # Manuscript
    MANUSCRIPT_CREATED = "manuscript.created"
    MANUSCRIPT_UPDATED = "manuscript.updated"
    MANUSCRIPT_DELETED = "manuscript.deleted"
    MANUSCRIPT_TRANSITIONED = "manuscript.transitioned"
    # Knowledge graph
    KNOWLEDGE_ENTITY_CREATED = "knowledge_entity.created"
    KNOWLEDGE_ENTITY_UPDATED = "knowledge_entity.updated"
    KNOWLEDGE_ENTITY_DELETED = "knowledge_entity.deleted"
    KNOWLEDGE_RELATIONSHIP_CREATED = "knowledge_relationship.created"
    KNOWLEDGE_RELATIONSHIP_UPDATED = "knowledge_relationship.updated"
    KNOWLEDGE_RELATIONSHIP_DELETED = "knowledge_relationship.deleted"
    # Production tasks + approvals
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_DELETED = "task.deleted"
    TASK_TRANSITIONED = "task.transitioned"
    TASK_COMPLETED = "task.completed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_DECIDED = "approval.decided"
    # Assets / versions / provenance / licences
    ASSET_CREATED = "asset.created"
    ASSET_UPDATED = "asset.updated"
    ASSET_DELETED = "asset.deleted"
    ASSET_VERSION_CREATED = "asset.version_created"
    ASSET_VERSION_PROMOTED = "asset.version_promoted"
    PROVENANCE_RECORDED = "provenance.recorded"
    LICENCE_CREATED = "licence.created"
    LICENCE_UPDATED = "licence.updated"
    LICENCE_DELETED = "licence.deleted"
    # Graphic-novel pages + panels
    PAGE_UPDATED = "page.updated"
    PAGE_APPROVED = "page.approved"
    PANEL_UPDATED = "panel.updated"
    PANEL_APPROVED = "panel.approved"
    # Screen
    SCREEN_PROJECT_CREATED = "screen_project.created"
    SCREEN_PROJECT_UPDATED = "screen_project.updated"
    SCENE_CREATED = "scene.created"
    SCENE_UPDATED = "scene.updated"
    SHOT_CREATED = "shot.created"
    SHOT_UPDATED = "shot.updated"
    SHOT_APPROVED = "shot.approved"
    # Rights / contracts
    RIGHTS_UPDATED = "rights.updated"
    CONTRACT_CREATED = "contract.created"
    CONTRACT_UPDATED = "contract.updated"
    # Adaptations
    ADAPTATION_CREATED = "adaptation.created"
    ADAPTATION_UPDATED = "adaptation.updated"
    # Collaborators
    COLLABORATOR_INVITED = "collaborator.invited"
    COLLABORATOR_ROLE_CHANGED = "collaborator.role_changed"
    COLLABORATOR_SUSPENDED = "collaborator.suspended"
    COLLABORATOR_REACTIVATED = "collaborator.reactivated"
    COLLABORATOR_REVOKED = "collaborator.revoked"
    # Publishing / public curation
    PUBLICATION_APPROVED = "publication.approved"
    PUBLICATION_PUBLISHED = "publication.published"
    PUBLICATION_UNPUBLISHED = "publication.unpublished"
    PUBLICATION_PAGE_HANDED_OFF = "publication.page_handed_off"
    # Agent findings + proposals
    AGENT_FINDING_CREATED = "agent.finding_created"
    AGENT_PROPOSAL_APPROVED = "agent.proposal_approved"
    AGENT_PROPOSAL_EXECUTED = "agent.proposal_executed"
    # Brain decisions
    DECISION_APPROVED = "decision.approved"
    DECISION_REJECTED = "decision.rejected"
    DECISION_SUPERSEDED = "decision.superseded"
    # Conversation memory & decision extraction (Prompt 13).
    # ``CONVERSATION_TURN_COMPLETED`` is the memory-analysis job: the consumer
    # routes it to the analyzer instead of scheduling a recompile (a chat turn
    # never invalidates compiled domain state). The ``memory.*`` events DO
    # invalidate compiled state, so a newly verified/retired project- or
    # studio-scoped memory surfaces on the next compile.
    CONVERSATION_TURN_COMPLETED = "conversation.turn_completed"
    MEMORY_VERIFIED = "memory.verified"
    MEMORY_SUPERSEDED = "memory.superseded"
    MEMORY_EXPIRED = "memory.expired"


_SECRET_RE = re.compile(
    r"(api[_-]?key|secret|token|password|authorization|bearer|credential|private[_-]?key)",
    re.IGNORECASE,
)
_MAX_VALUE = 200

ChangeSpec = Union[dict, Iterable[str], None]


def _summarize_changes(changes: ChangeSpec) -> dict:
    """Reduce a change spec to a small, secret-free summary.

    Accepts a dict of changed fields (values summarised, secret-like keys
    redacted), or an iterable of changed field names. Never stores large or
    structured values verbatim.
    """
    if changes is None:
        return {}
    if isinstance(changes, dict):
        out: dict[str, Any] = {}
        for key, value in changes.items():
            if _SECRET_RE.search(str(key)):
                out[str(key)] = "[redacted]"
                continue
            if value is None or isinstance(value, (str, int, float, bool)):
                text = str(value)
                out[str(key)] = text if len(text) <= _MAX_VALUE else text[:_MAX_VALUE] + "…"
            else:
                out[str(key)] = f"<{type(value).__name__}>"
        return out
    # an iterable of field names
    return {"fields": [str(field) for field in changes]}


def work_scope(session: Session, work_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return ``(work_id, story_world_id)`` for a work id, guarded so a missing
    work or a lazy-load error never breaks the caller's mutation."""
    if not work_id:
        return (None, None)
    try:
        from app.models import Work

        work = session.get(Work, work_id)
        return (work_id, getattr(work, "story_world_id", None) if work else None)
    except Exception:
        return (work_id, None)


def emit(
    session: Session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    changes: ChangeSpec = None,
    summary: Optional[str] = None,
) -> BrainEvent:
    """Append a domain event in the caller's transaction (the outbox write).

    Identifiers + a changed-field summary only — never a full, secret-bearing
    record. ``correlation_id`` defaults to the current request id.
    """
    payload: dict[str, Any] = {
        "aggregate_id": aggregate_id,
        "changes": _summarize_changes(changes),
    }
    if work_id:
        payload["work_id"] = work_id
    if story_world_id:
        payload["story_world_id"] = story_world_id
    if summary:
        payload["summary"] = str(summary)[:300]

    return append_event(
        session,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        work_id=work_id,
        story_world_id=story_world_id,
        actor_id=actor_id,
        correlation_id=correlation_id or get_request_id(),
    )
