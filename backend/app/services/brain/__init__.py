"""Persistence service for the SUPERVOID Brain.

This is the durable storage API — it does **not** compile state (that is a later
phase). It exists so the invariants live in one place rather than in free CRUD:

* ``BrainEvent`` is append-only; ``append_event`` assigns the next monotonic
  ``sequence``; only ``mark_event_*`` advance processing fields.
* ``BrainStateRevision`` is immutable; ``record_revision`` only ever inserts.
* ``Studio/ProjectBrainState`` are the single "current" rows, upserted in place
  while every version is snapshotted as a revision.

Functions add (and flush where an id/sequence is needed) but do not commit —
the caller (router or test) owns the transaction, matching ``policy.record_audit``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, func, select

from app.models import (
    BrainCheckpoint,
    BrainConversation,
    BrainEvent,
    BrainMemoryItem,
    BrainMessage,
    BrainStateRevision,
    DecisionRecord,
    ProjectBrainState,
    StudioBrainState,
)
from app.models.base import utcnow
from app.models.enums import (
    BrainConversationStatus,
    BrainEventStatus,
    BrainMemoryKind,
    BrainMemoryVerification,
    BrainMessageRole,
    BrainRevisionApproval,
    BrainScope,
    BrainStateStatus,
    BrainStateType,
    DecisionStatus,
)


# === events (append-only) ==================================================
def next_sequence(session: Session) -> int:
    current = session.exec(select(func.max(BrainEvent.sequence))).one()
    return int(current or 0) + 1


def append_event(
    session: Session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: Optional[dict] = None,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
) -> BrainEvent:
    """Append a domain event with the next monotonic sequence number."""
    event = BrainEvent(
        sequence=next_sequence(session),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload or {},
        work_id=work_id,
        story_world_id=story_world_id,
        actor_id=actor_id,
        correlation_id=correlation_id,
        occurred_at=occurred_at or utcnow(),
        status=BrainEventStatus.PENDING,
    )
    session.add(event)
    session.flush()  # assign id; make the new sequence visible to next_sequence
    return event


def mark_event_processed(session: Session, event: BrainEvent) -> BrainEvent:
    event.status = BrainEventStatus.PROCESSED
    event.processed_at = utcnow()
    event.attempts += 1
    event.error = None
    session.add(event)
    session.flush()
    return event


def mark_event_failed(session: Session, event: BrainEvent, error: str) -> BrainEvent:
    event.status = BrainEventStatus.FAILED
    event.attempts += 1
    event.error = error
    session.add(event)
    session.flush()
    return event


def list_events(
    session: Session,
    *,
    status: Optional[BrainEventStatus] = None,
    aggregate_type: Optional[str] = None,
    aggregate_id: Optional[str] = None,
    after_sequence: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[BrainEvent]:
    stmt = select(BrainEvent)
    if status is not None:
        stmt = stmt.where(BrainEvent.status == status)
    if aggregate_type is not None:
        stmt = stmt.where(BrainEvent.aggregate_type == aggregate_type)
    if aggregate_id is not None:
        stmt = stmt.where(BrainEvent.aggregate_id == aggregate_id)
    if after_sequence is not None:
        stmt = stmt.where(BrainEvent.sequence > after_sequence)
    stmt = stmt.order_by(BrainEvent.sequence).offset(offset).limit(limit)
    return list(session.exec(stmt).all())


# === revisions (immutable) =================================================
def record_revision(
    session: Session,
    *,
    state_type: BrainStateType,
    state_id: str,
    version: int,
    previous_version: Optional[int] = None,
    deterministic_payload: Optional[dict] = None,
    llm_summary: Optional[str] = None,
    source_event_from: Optional[int] = None,
    source_event_to: Optional[int] = None,
    compiler_version: Optional[str] = None,
    approval_status: BrainRevisionApproval = BrainRevisionApproval.NOT_REQUIRED,
    generated_at: Optional[datetime] = None,
) -> BrainStateRevision:
    revision = BrainStateRevision(
        state_type=state_type,
        state_id=state_id,
        version=version,
        previous_version=previous_version,
        deterministic_payload=deterministic_payload or {},
        llm_summary=llm_summary,
        source_event_from=source_event_from,
        source_event_to=source_event_to,
        compiler_version=compiler_version,
        approval_status=approval_status,
        generated_at=generated_at or utcnow(),
    )
    session.add(revision)
    session.flush()
    return revision


def list_revisions(
    session: Session,
    *,
    state_type: Optional[BrainStateType] = None,
    state_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[BrainStateRevision]:
    stmt = select(BrainStateRevision)
    if state_type is not None:
        stmt = stmt.where(BrainStateRevision.state_type == state_type)
    if state_id is not None:
        stmt = stmt.where(BrainStateRevision.state_id == state_id)
    stmt = stmt.order_by(BrainStateRevision.version.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())


# === current compiled state (upsert + snapshot) ============================
def get_studio_state(session: Session) -> Optional[StudioBrainState]:
    return session.exec(
        select(StudioBrainState).where(StudioBrainState.singleton_key == "studio")
    ).first()


def set_studio_state(
    session: Session,
    *,
    structured_state: dict,
    version: Optional[int] = None,
    status: BrainStateStatus = BrainStateStatus.READY,
    compact_summary: Optional[str] = None,
    checksum: Optional[str] = None,
    compiler_version: Optional[str] = None,
    assist_version: Optional[str] = None,
    source_event_cursor: int = 0,
    stale: bool = False,
    snapshot: bool = True,
    llm_summary: Optional[str] = None,
) -> StudioBrainState:
    """Upsert the single studio state row and snapshot the version."""
    state = get_studio_state(session)
    previous_version: Optional[int] = None
    if state is None:
        new_version = version if version is not None else 1
        state = StudioBrainState(singleton_key="studio")
    else:
        previous_version = state.version
        new_version = version if version is not None else state.version + 1

    state.version = new_version
    state.status = status
    state.structured_state = structured_state
    state.compact_summary = compact_summary
    state.checksum = checksum
    state.compiler_version = compiler_version
    state.assist_version = assist_version
    state.source_event_cursor = source_event_cursor
    state.stale = stale
    state.compiled_at = utcnow()
    session.add(state)
    session.flush()

    if snapshot:
        record_revision(
            session,
            state_type=BrainStateType.STUDIO,
            state_id=state.id,
            version=new_version,
            previous_version=previous_version,
            deterministic_payload=structured_state,
            llm_summary=llm_summary,
            source_event_to=source_event_cursor,
            compiler_version=compiler_version,
        )
    return state


def get_project_state(
    session: Session,
    *,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
) -> Optional[ProjectBrainState]:
    stmt = select(ProjectBrainState)
    if work_id is not None:
        stmt = stmt.where(ProjectBrainState.work_id == work_id)
    elif story_world_id is not None:
        stmt = stmt.where(ProjectBrainState.story_world_id == story_world_id)
    else:
        return None
    return session.exec(stmt).first()


def set_project_state(
    session: Session,
    *,
    structured_state: dict,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    version: Optional[int] = None,
    status: BrainStateStatus = BrainStateStatus.READY,
    compact_summary: Optional[str] = None,
    canon_digest: Optional[str] = None,
    production_digest: Optional[str] = None,
    open_questions: Optional[list] = None,
    priorities: Optional[list] = None,
    recent_changes: Optional[list] = None,
    checksum: Optional[str] = None,
    source_event_cursor: int = 0,
    stale: bool = False,
    snapshot: bool = True,
    llm_summary: Optional[str] = None,
) -> ProjectBrainState:
    if bool(work_id) == bool(story_world_id):
        raise ValueError(
            "set_project_state requires exactly one of work_id / story_world_id."
        )
    state = get_project_state(session, work_id=work_id, story_world_id=story_world_id)
    previous_version: Optional[int] = None
    if state is None:
        new_version = version if version is not None else 1
        state = ProjectBrainState(work_id=work_id, story_world_id=story_world_id)
    else:
        previous_version = state.version
        new_version = version if version is not None else state.version + 1

    state.version = new_version
    state.status = status
    state.structured_state = structured_state
    state.compact_summary = compact_summary
    state.canon_digest = canon_digest
    state.production_digest = production_digest
    state.open_questions = open_questions or []
    state.priorities = priorities or []
    state.recent_changes = recent_changes or []
    state.checksum = checksum
    state.source_event_cursor = source_event_cursor
    state.stale = stale
    state.compiled_at = utcnow()
    session.add(state)
    session.flush()

    if snapshot:
        record_revision(
            session,
            state_type=BrainStateType.PROJECT,
            state_id=state.id,
            version=new_version,
            previous_version=previous_version,
            deterministic_payload=structured_state,
            llm_summary=llm_summary,
            source_event_to=source_event_cursor,
            compiler_version=None,
        )
    return state


# === conversations + messages =============================================
def create_conversation(
    session: Session,
    *,
    owner_user_id: str,
    title: Optional[str] = None,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    active_profile: Optional[str] = None,
    librechat_conversation_id: Optional[str] = None,
) -> BrainConversation:
    conv = BrainConversation(
        owner_user_id=owner_user_id,
        title=title,
        work_id=work_id,
        story_world_id=story_world_id,
        active_profile=active_profile,
        librechat_conversation_id=librechat_conversation_id,
        status=BrainConversationStatus.ACTIVE,
    )
    session.add(conv)
    session.flush()
    return conv


def get_conversation(session: Session, conversation_id: str) -> Optional[BrainConversation]:
    return session.get(BrainConversation, conversation_id)


def list_conversations(
    session: Session,
    *,
    owner_user_id: str,
    status: Optional[BrainConversationStatus] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[BrainConversation]:
    stmt = select(BrainConversation).where(
        BrainConversation.owner_user_id == owner_user_id
    )
    if status is not None:
        stmt = stmt.where(BrainConversation.status == status)
    stmt = stmt.order_by(BrainConversation.updated_at.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())


def append_message(
    session: Session,
    conversation: BrainConversation,
    *,
    role: BrainMessageRole,
    content: Optional[str] = None,
    structured_content: Optional[dict] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    request_id: Optional[str] = None,
    state_version: Optional[int] = None,
    retrieval_ids: Optional[list] = None,
    tool_call_ids: Optional[list] = None,
) -> BrainMessage:
    message = BrainMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        structured_content=structured_content or {},
        model=model,
        provider=provider,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        request_id=request_id,
        state_version=state_version,
        retrieval_ids=retrieval_ids or [],
        tool_call_ids=tool_call_ids or [],
    )
    session.add(message)
    # Bump the conversation's updated_at so listings order by recency.
    conversation.updated_at = utcnow()
    if state_version is not None:
        conversation.last_state_version = state_version
    session.add(conversation)
    session.flush()
    return message


def list_messages(
    session: Session,
    conversation_id: str,
    *,
    limit: int = 200,
    offset: int = 0,
) -> list[BrainMessage]:
    stmt = (
        select(BrainMessage)
        .where(BrainMessage.conversation_id == conversation_id)
        .order_by(BrainMessage.created_at)
        .offset(offset)
        .limit(limit)
    )
    return list(session.exec(stmt).all())


# === checkpoints (gateway prompt-prefix cache) =============================
def upsert_checkpoint(
    session: Session,
    *,
    conversation_id: str,
    prefix_hash: Optional[str] = None,
    **fields,
) -> BrainCheckpoint:
    checkpoint: Optional[BrainCheckpoint] = None
    if prefix_hash is not None:
        checkpoint = session.exec(
            select(BrainCheckpoint).where(
                BrainCheckpoint.conversation_id == conversation_id,
                BrainCheckpoint.prefix_hash == prefix_hash,
            )
        ).first()
    if checkpoint is None:
        checkpoint = BrainCheckpoint(
            conversation_id=conversation_id, prefix_hash=prefix_hash
        )
    for key, value in fields.items():
        setattr(checkpoint, key, value)
    checkpoint.last_used_at = utcnow()
    session.add(checkpoint)
    session.flush()
    return checkpoint


# === memory ================================================================
def create_memory(
    session: Session,
    *,
    scope: BrainScope,
    kind: BrainMemoryKind,
    content: str,
    created_by_id: Optional[str] = None,
    structured_data: Optional[dict] = None,
    confidence: Optional[float] = None,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    member_user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    source_message_id: Optional[str] = None,
    source_event_id: Optional[str] = None,
    supersedes_id: Optional[str] = None,
    expires_at: Optional[datetime] = None,
) -> BrainMemoryItem:
    item = BrainMemoryItem(
        scope=scope,
        kind=kind,
        content=content,
        structured_data=structured_data or {},
        confidence=confidence,
        work_id=work_id,
        story_world_id=story_world_id,
        member_user_id=member_user_id,
        conversation_id=conversation_id,
        source_message_id=source_message_id,
        source_event_id=source_event_id,
        supersedes_id=supersedes_id,
        expires_at=expires_at,
        created_by_id=created_by_id,
    )
    session.add(item)
    # Superseding marks the prior item retired (a controlled transition).
    if supersedes_id is not None:
        prior = session.get(BrainMemoryItem, supersedes_id)
        if prior is not None:
            prior.verification = BrainMemoryVerification.SUPERSEDED
            session.add(prior)
    session.flush()
    return item


def get_memory(session: Session, item_id: str) -> Optional[BrainMemoryItem]:
    return session.get(BrainMemoryItem, item_id)


def list_memory(
    session: Session,
    *,
    scope: Optional[BrainScope] = None,
    kind: Optional[BrainMemoryKind] = None,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    member_user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    verification: Optional[BrainMemoryVerification] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[BrainMemoryItem]:
    stmt = select(BrainMemoryItem)
    if scope is not None:
        stmt = stmt.where(BrainMemoryItem.scope == scope)
    if kind is not None:
        stmt = stmt.where(BrainMemoryItem.kind == kind)
    if work_id is not None:
        stmt = stmt.where(BrainMemoryItem.work_id == work_id)
    if story_world_id is not None:
        stmt = stmt.where(BrainMemoryItem.story_world_id == story_world_id)
    if member_user_id is not None:
        stmt = stmt.where(BrainMemoryItem.member_user_id == member_user_id)
    if conversation_id is not None:
        stmt = stmt.where(BrainMemoryItem.conversation_id == conversation_id)
    if verification is not None:
        stmt = stmt.where(BrainMemoryItem.verification == verification)
    stmt = stmt.order_by(BrainMemoryItem.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())


def verify_memory(
    session: Session,
    item: BrainMemoryItem,
    *,
    verification: BrainMemoryVerification,
    approver_id: Optional[str] = None,
) -> BrainMemoryItem:
    item.verification = verification
    if verification in (
        BrainMemoryVerification.VERIFIED,
        BrainMemoryVerification.REJECTED,
    ):
        item.approved_by_id = approver_id
    session.add(item)
    session.flush()
    return item


# === decisions =============================================================
def create_decision(
    session: Session,
    *,
    scope: BrainScope,
    subject: str,
    decision: str,
    proposer_id: Optional[str] = None,
    rationale: Optional[str] = None,
    alternatives: Optional[list] = None,
    affected_entities: Optional[list] = None,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    source_conversation_id: Optional[str] = None,
    effective_date: Optional[datetime] = None,
) -> DecisionRecord:
    record = DecisionRecord(
        scope=scope,
        subject=subject,
        decision=decision,
        rationale=rationale,
        alternatives=alternatives or [],
        affected_entities=affected_entities or [],
        work_id=work_id,
        story_world_id=story_world_id,
        source_conversation_id=source_conversation_id,
        effective_date=effective_date,
        proposer_id=proposer_id,
        status=DecisionStatus.PROPOSED,
    )
    session.add(record)
    session.flush()
    return record


def get_decision(session: Session, decision_id: str) -> Optional[DecisionRecord]:
    return session.get(DecisionRecord, decision_id)


def list_decisions(
    session: Session,
    *,
    scope: Optional[BrainScope] = None,
    status: Optional[DecisionStatus] = None,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[DecisionRecord]:
    stmt = select(DecisionRecord)
    if scope is not None:
        stmt = stmt.where(DecisionRecord.scope == scope)
    if status is not None:
        stmt = stmt.where(DecisionRecord.status == status)
    if work_id is not None:
        stmt = stmt.where(DecisionRecord.work_id == work_id)
    if story_world_id is not None:
        stmt = stmt.where(DecisionRecord.story_world_id == story_world_id)
    stmt = stmt.order_by(DecisionRecord.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())


def decide_decision(
    session: Session,
    record: DecisionRecord,
    *,
    approve: bool,
    approver_id: Optional[str] = None,
    effective_date: Optional[datetime] = None,
) -> DecisionRecord:
    """Move a PROPOSED decision to APPROVED or REJECTED (idempotency guarded by
    the caller, which checks the current status first)."""
    record.status = DecisionStatus.APPROVED if approve else DecisionStatus.REJECTED
    record.approver_id = approver_id
    if approve and effective_date is not None:
        record.effective_date = effective_date
    session.add(record)
    session.flush()
    return record


# --- outbox: emitter + consumer (imported last to avoid an import cycle) ----
# These submodules import the functions defined above; importing them here, at
# the bottom, keeps the package's public surface in one place.
from app.services.brain.events import BrainEventType, emit, work_scope  # noqa: E402
from app.services.brain.consumer import (  # noqa: E402
    drain,
    outbox_status,
    process_pending,
    reconcile,
    replay_failed,
)
from app.services.brain.compiler import (  # noqa: E402
    checksum,
    compile_project,
    compile_stale,
    compile_studio,
    compiler_health,
    head_sequence,
    revision_delta,
    stale_states,
)
