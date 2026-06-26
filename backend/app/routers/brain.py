"""SUPERVOID Brain — persistence API (private, ``/api/brain``).

Exposes CRUD only where appropriate, with user/project permissions applied via
the policy service:

* conversations + messages — strictly owner-scoped;
* memory + decisions — scoped (studio = admin; project = policy scopes;
  member/conversation = self/owner);
* compiled state — read-only;
* events + state revisions — append-only / immutable, so read-only (admin), with
  no create/update/delete endpoints.

No endpoint compiles state (that is a later phase).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.auth import ADMIN_ONLY
from app.auth.dependencies import get_current_user
from app.db import get_session
from app.models import (
    BrainConversation,
    BrainEvent,
    BrainMemoryItem,
    BrainStateRevision,
    DecisionRecord,
    PermissionScope,
    StudioBrainState,
    User,
    UserRole,
)
from app.models.enums import (
    BrainConversationStatus,
    BrainEventStatus,
    BrainMemoryKind,
    BrainMemoryVerification,
    BrainScope,
    BrainStateType,
    DecisionStatus,
)
from app.schemas.brain import (
    BrainConversationCreate,
    BrainConversationRead,
    BrainConversationUpdate,
    BrainEventRead,
    BrainMemoryItemCreate,
    BrainMemoryItemRead,
    BrainMemoryItemUpdate,
    BrainMemoryVerify,
    BrainMessageCreate,
    BrainMessageRead,
    BrainStateRevisionRead,
    DecisionDecision,
    DecisionRecordCreate,
    DecisionRecordRead,
    OutboxReplayRequest,
    OutboxStatusRead,
    ProjectBrainStateRead,
    RebuildRequest,
    RebuildResult,
    StudioBrainStateRead,
)
from app.schemas.instruction import (
    AssembleRequest,
    ConstitutionRead,
    ConstitutionVersionCreate,
    GlossaryRead,
    GlossaryVersionCreate,
    PolicyRead,
    PolicyVersionCreate,
    ProfileRead,
    ProfileVersionCreate,
    TemplateRead,
    TemplateVersionCreate,
    VersionRef,
)
from app.services import brain
from app.services.brain import instruction as instruction_svc
from app.services.policy import ensure_can

router = APIRouter(prefix="/brain", tags=["brain"])

_PS = PermissionScope


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _forbid(detail: str = "Not permitted") -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# === conversations + messages =============================================
def _owned_conversation(
    session: Session, conversation_id: str, user: User
) -> BrainConversation:
    conv = brain.get_conversation(session, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.owner_user_id != user.id and not _is_admin(user):
        _forbid("Not your conversation")
    return conv


@router.post("/conversations", response_model=BrainConversationRead, status_code=201)
def create_conversation(
    body: BrainConversationCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BrainConversationRead:
    conv = brain.create_conversation(
        session,
        owner_user_id=user.id,
        title=body.title,
        work_id=body.work_id,
        story_world_id=body.story_world_id,
        active_profile=body.active_profile,
        librechat_conversation_id=body.librechat_conversation_id,
    )
    session.commit()
    session.refresh(conv)
    return BrainConversationRead.model_validate(conv)


@router.get("/conversations", response_model=list[BrainConversationRead])
def list_conversations(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    conv_status: Optional[BrainConversationStatus] = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[BrainConversationRead]:
    rows = brain.list_conversations(
        session, owner_user_id=user.id, status=conv_status, limit=limit, offset=skip
    )
    return [BrainConversationRead.model_validate(c) for c in rows]


@router.get("/conversations/{conversation_id}", response_model=BrainConversationRead)
def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BrainConversationRead:
    conv = _owned_conversation(session, conversation_id, user)
    return BrainConversationRead.model_validate(conv)


@router.patch("/conversations/{conversation_id}", response_model=BrainConversationRead)
def update_conversation(
    conversation_id: str,
    body: BrainConversationUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BrainConversationRead:
    conv = _owned_conversation(session, conversation_id, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(conv, field, value)
    session.add(conv)
    session.commit()
    session.refresh(conv)
    return BrainConversationRead.model_validate(conv)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    conv = _owned_conversation(session, conversation_id, user)
    session.delete(conv)
    session.commit()


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=BrainMessageRead,
    status_code=201,
)
def append_message(
    conversation_id: str,
    body: BrainMessageCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BrainMessageRead:
    conv = _owned_conversation(session, conversation_id, user)
    msg = brain.append_message(
        session,
        conv,
        role=body.role,
        content=body.content,
        structured_content=body.structured_content,
        model=body.model,
        provider=body.provider,
        prompt_tokens=body.prompt_tokens,
        completion_tokens=body.completion_tokens,
        request_id=body.request_id,
        state_version=body.state_version,
        retrieval_ids=body.retrieval_ids,
        tool_call_ids=body.tool_call_ids,
    )
    session.commit()
    session.refresh(msg)
    return BrainMessageRead.model_validate(msg)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[BrainMessageRead],
)
def list_messages(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
) -> list[BrainMessageRead]:
    _owned_conversation(session, conversation_id, user)
    rows = brain.list_messages(session, conversation_id, limit=limit, offset=skip)
    return [BrainMessageRead.model_validate(m) for m in rows]


# === memory ================================================================
def _check_memory_access(
    session: Session,
    user: User,
    *,
    scope: BrainScope,
    work_id: Optional[str],
    story_world_id: Optional[str],
    member_user_id: Optional[str],
    conversation_id: Optional[str],
    write: bool,
) -> None:
    """Apply scope-appropriate permissions for a memory operation."""
    if _is_admin(user):
        return
    if scope == BrainScope.STUDIO:
        if write:
            _forbid("Studio memory is admin-only to write")
        return  # any authenticated user may read studio memory
    if scope == BrainScope.PROJECT:
        if not (work_id or story_world_id):
            raise HTTPException(status_code=400, detail="Project memory needs a work_id or story_world_id")
        needed = _PS.EDIT_NARRATIVE if write else _PS.VIEW_PROJECT
        ensure_can(session, user, needed, work_id=work_id, story_world_id=story_world_id)
        return
    if scope == BrainScope.MEMBER:
        if member_user_id != user.id:
            _forbid("Member memory is private to that member")
        return
    if scope == BrainScope.CONVERSATION:
        conv = brain.get_conversation(session, conversation_id) if conversation_id else None
        if conv is None:
            raise HTTPException(status_code=400, detail="Conversation memory needs a valid conversation_id")
        if conv.owner_user_id != user.id:
            _forbid("Not your conversation")
        return


@router.post("/memory", response_model=BrainMemoryItemRead, status_code=201)
def create_memory(
    body: BrainMemoryItemCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BrainMemoryItemRead:
    member_user_id = body.member_user_id
    if body.scope == BrainScope.MEMBER and member_user_id is None:
        member_user_id = user.id
    _check_memory_access(
        session, user, scope=body.scope, work_id=body.work_id,
        story_world_id=body.story_world_id, member_user_id=member_user_id,
        conversation_id=body.conversation_id, write=True,
    )
    item = brain.create_memory(
        session,
        scope=body.scope,
        kind=body.kind,
        content=body.content,
        created_by_id=user.id,
        structured_data=body.structured_data,
        confidence=body.confidence,
        work_id=body.work_id,
        story_world_id=body.story_world_id,
        member_user_id=member_user_id,
        conversation_id=body.conversation_id,
        source_message_id=body.source_message_id,
        source_event_id=body.source_event_id,
        supersedes_id=body.supersedes_id,
        expires_at=body.expires_at,
    )
    session.commit()
    session.refresh(item)
    return BrainMemoryItemRead.model_validate(item)


@router.get("/memory", response_model=list[BrainMemoryItemRead])
def list_memory(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    scope: Optional[BrainScope] = Query(default=None),
    kind: Optional[BrainMemoryKind] = Query(default=None),
    work_id: Optional[str] = Query(default=None),
    story_world_id: Optional[str] = Query(default=None),
    verification: Optional[BrainMemoryVerification] = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
) -> list[BrainMemoryItemRead]:
    # Project reads are gated; studio/member/conversation are filtered to what
    # the caller may see.
    if scope == BrainScope.PROJECT and not _is_admin(user):
        if not (work_id or story_world_id):
            raise HTTPException(status_code=400, detail="Project memory listing needs work_id or story_world_id")
        ensure_can(session, user, _PS.VIEW_PROJECT, work_id=work_id, story_world_id=story_world_id)
    member_filter = None
    if scope == BrainScope.MEMBER and not _is_admin(user):
        member_filter = user.id
    rows = brain.list_memory(
        session, scope=scope, kind=kind, work_id=work_id,
        story_world_id=story_world_id, member_user_id=member_filter,
        verification=verification, limit=limit, offset=skip,
    )
    return [BrainMemoryItemRead.model_validate(m) for m in rows]


def _load_memory(session: Session, item_id: str) -> BrainMemoryItem:
    item = brain.get_memory(session, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return item


@router.get("/memory/{item_id}", response_model=BrainMemoryItemRead)
def get_memory(
    item_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BrainMemoryItemRead:
    item = _load_memory(session, item_id)
    _check_memory_access(
        session, user, scope=item.scope, work_id=item.work_id,
        story_world_id=item.story_world_id, member_user_id=item.member_user_id,
        conversation_id=item.conversation_id, write=False,
    )
    return BrainMemoryItemRead.model_validate(item)


@router.patch("/memory/{item_id}", response_model=BrainMemoryItemRead)
def update_memory(
    item_id: str,
    body: BrainMemoryItemUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BrainMemoryItemRead:
    item = _load_memory(session, item_id)
    _check_memory_access(
        session, user, scope=item.scope, work_id=item.work_id,
        story_world_id=item.story_world_id, member_user_id=item.member_user_id,
        conversation_id=item.conversation_id, write=True,
    )
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    session.add(item)
    session.commit()
    session.refresh(item)
    return BrainMemoryItemRead.model_validate(item)


@router.post("/memory/{item_id}/verify", response_model=BrainMemoryItemRead)
def verify_memory(
    item_id: str,
    body: BrainMemoryVerify,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BrainMemoryItemRead:
    item = _load_memory(session, item_id)
    # Verifying is an approval-grade action: admin (studio) or APPROVE (project).
    if not _is_admin(user):
        if item.scope == BrainScope.PROJECT:
            ensure_can(session, user, _PS.APPROVE, work_id=item.work_id, story_world_id=item.story_world_id)
        else:
            _forbid("Verification is admin-only for this scope")
    item = brain.verify_memory(session, item, verification=body.verification, approver_id=user.id)
    session.commit()
    session.refresh(item)
    return BrainMemoryItemRead.model_validate(item)


@router.delete("/memory/{item_id}", status_code=204)
def delete_memory(
    item_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    item = _load_memory(session, item_id)
    if not (_is_admin(user) or item.created_by_id == user.id):
        _check_memory_access(
            session, user, scope=item.scope, work_id=item.work_id,
            story_world_id=item.story_world_id, member_user_id=item.member_user_id,
            conversation_id=item.conversation_id, write=True,
        )
    session.delete(item)
    session.commit()


# === decisions =============================================================
def _check_decision_write(
    session: Session, user: User, *, scope: BrainScope,
    work_id: Optional[str], story_world_id: Optional[str], approve: bool,
) -> None:
    if _is_admin(user):
        return
    if scope == BrainScope.PROJECT:
        if not (work_id or story_world_id):
            raise HTTPException(status_code=400, detail="Project decision needs a work_id or story_world_id")
        needed = _PS.APPROVE if approve else _PS.VIEW_PROJECT
        ensure_can(session, user, needed, work_id=work_id, story_world_id=story_world_id)
        return
    # studio / member / conversation scope
    if approve:
        _forbid("Approving this decision is admin-only")
    # proposing a non-project decision only needs authentication


@router.post("/decisions", response_model=DecisionRecordRead, status_code=201)
def propose_decision(
    body: DecisionRecordCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> DecisionRecordRead:
    _check_decision_write(
        session, user, scope=body.scope, work_id=body.work_id,
        story_world_id=body.story_world_id, approve=False,
    )
    record = brain.create_decision(
        session,
        scope=body.scope,
        subject=body.subject,
        decision=body.decision,
        proposer_id=user.id,
        rationale=body.rationale,
        alternatives=body.alternatives,
        affected_entities=body.affected_entities,
        work_id=body.work_id,
        story_world_id=body.story_world_id,
        source_conversation_id=body.source_conversation_id,
        effective_date=body.effective_date,
    )
    session.commit()
    session.refresh(record)
    return DecisionRecordRead.model_validate(record)


@router.get("/decisions", response_model=list[DecisionRecordRead])
def list_decisions(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    scope: Optional[BrainScope] = Query(default=None),
    decision_status: Optional[DecisionStatus] = Query(default=None),
    work_id: Optional[str] = Query(default=None),
    story_world_id: Optional[str] = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
) -> list[DecisionRecordRead]:
    if scope == BrainScope.PROJECT and not _is_admin(user):
        if not (work_id or story_world_id):
            raise HTTPException(status_code=400, detail="Project decision listing needs work_id or story_world_id")
        ensure_can(session, user, _PS.VIEW_PROJECT, work_id=work_id, story_world_id=story_world_id)
    rows = brain.list_decisions(
        session, scope=scope, status=decision_status, work_id=work_id,
        story_world_id=story_world_id, limit=limit, offset=skip,
    )
    return [DecisionRecordRead.model_validate(d) for d in rows]


def _load_decision(session: Session, decision_id: str) -> DecisionRecord:
    record = brain.get_decision(session, decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return record


@router.get("/decisions/{decision_id}", response_model=DecisionRecordRead)
def get_decision(
    decision_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> DecisionRecordRead:
    record = _load_decision(session, decision_id)
    if record.scope == BrainScope.PROJECT and not _is_admin(user):
        ensure_can(session, user, _PS.VIEW_PROJECT, work_id=record.work_id, story_world_id=record.story_world_id)
    return DecisionRecordRead.model_validate(record)


def _decide(decision_id: str, *, approve: bool, body: DecisionDecision, user: User, session: Session) -> DecisionRecordRead:
    record = _load_decision(session, decision_id)
    if record.status != DecisionStatus.PROPOSED:
        raise HTTPException(status_code=409, detail=f"Decision is {record.status.value}, not proposed")
    _check_decision_write(
        session, user, scope=record.scope, work_id=record.work_id,
        story_world_id=record.story_world_id, approve=True,
    )
    record = brain.decide_decision(
        session, record, approve=approve, approver_id=user.id,
        effective_date=body.effective_date,
    )
    if approve:
        brain.emit(
            session, event_type=brain.BrainEventType.DECISION_APPROVED,
            aggregate_type="decision", aggregate_id=record.id,
            work_id=record.work_id, story_world_id=record.story_world_id,
            actor_id=user.id, changes={"subject": record.subject},
        )
    session.commit()
    session.refresh(record)
    return DecisionRecordRead.model_validate(record)


@router.post("/decisions/{decision_id}/approve", response_model=DecisionRecordRead)
def approve_decision(
    decision_id: str,
    body: DecisionDecision = DecisionDecision(),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> DecisionRecordRead:
    return _decide(decision_id, approve=True, body=body, user=user, session=session)


@router.post("/decisions/{decision_id}/reject", response_model=DecisionRecordRead)
def reject_decision(
    decision_id: str,
    body: DecisionDecision = DecisionDecision(),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> DecisionRecordRead:
    return _decide(decision_id, approve=False, body=body, user=user, session=session)


# === compiled state (read-only) ===========================================
@router.get("/state/studio", response_model=Optional[StudioBrainStateRead])
def get_studio_state(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Optional[StudioBrainStateRead]:
    state = brain.get_studio_state(session)
    return StudioBrainStateRead.model_validate(state) if state else None


@router.get("/works/{work_id}/state", response_model=Optional[ProjectBrainStateRead])
def get_work_state(
    work_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Optional[ProjectBrainStateRead]:
    if not _is_admin(user):
        ensure_can(session, user, _PS.VIEW_PROJECT, work_id=work_id)
    state = brain.get_project_state(session, work_id=work_id)
    return ProjectBrainStateRead.model_validate(state) if state else None


@router.get("/story-worlds/{world_id}/state", response_model=Optional[ProjectBrainStateRead])
def get_world_state(
    world_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Optional[ProjectBrainStateRead]:
    if not _is_admin(user):
        ensure_can(session, user, _PS.VIEW_PROJECT, story_world_id=world_id)
    state = brain.get_project_state(session, story_world_id=world_id)
    return ProjectBrainStateRead.model_validate(state) if state else None


# === revisions + events (immutable / append-only → read-only, admin) =======
@router.get("/revisions", response_model=list[BrainStateRevisionRead], dependencies=ADMIN_ONLY)
def list_revisions(
    session: Session = Depends(get_session),
    state_type: Optional[BrainStateType] = Query(default=None),
    state_id: Optional[str] = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[BrainStateRevisionRead]:
    rows = brain.list_revisions(
        session, state_type=state_type, state_id=state_id, limit=limit, offset=skip
    )
    return [BrainStateRevisionRead.model_validate(r) for r in rows]


@router.get("/events", response_model=list[BrainEventRead], dependencies=ADMIN_ONLY)
def list_events(
    session: Session = Depends(get_session),
    event_status: Optional[BrainEventStatus] = Query(default=None),
    aggregate_type: Optional[str] = Query(default=None),
    aggregate_id: Optional[str] = Query(default=None),
    after_sequence: Optional[int] = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[BrainEventRead]:
    rows = brain.list_events(
        session, status=event_status, aggregate_type=aggregate_type,
        aggregate_id=aggregate_id, after_sequence=after_sequence,
        limit=limit, offset=skip,
    )
    return [BrainEventRead.model_validate(e) for e in rows]


# === outbox monitoring + operations (admin-only) ===========================
@router.get("/outbox", response_model=OutboxStatusRead, dependencies=ADMIN_ONLY)
def outbox_status(session: Session = Depends(get_session)) -> OutboxStatusRead:
    """Unprocessed + failed counts, current cursor, and compiler lag."""
    return OutboxStatusRead(**brain.outbox_status(session))


@router.get("/outbox/failed", response_model=list[BrainEventRead], dependencies=ADMIN_ONLY)
def outbox_failed(
    session: Session = Depends(get_session),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[BrainEventRead]:
    rows = brain.list_events(
        session, status=BrainEventStatus.FAILED, limit=limit, offset=skip
    )
    return [BrainEventRead.model_validate(e) for e in rows]


@router.post("/outbox/replay", dependencies=ADMIN_ONLY)
def outbox_replay(
    body: OutboxReplayRequest = OutboxReplayRequest(),
    session: Session = Depends(get_session),
) -> dict:
    """Manual replay: re-queue dead-lettered events (all, or a given set)."""
    requeued = brain.replay_failed(session, event_ids=body.event_ids)
    return {"requeued": requeued}


@router.post("/outbox/process", dependencies=ADMIN_ONLY)
def outbox_process(session: Session = Depends(get_session)) -> dict:
    """One-shot: drain the current backlog (also available as a CLI)."""
    return brain.drain(session)


@router.post("/outbox/reconcile", dependencies=ADMIN_ONLY)
def outbox_reconcile(session: Session = Depends(get_session)) -> dict:
    """Detect and re-flag any scope whose state is behind the latest event."""
    return brain.reconcile(session)


# === state compiler (admin-only) ===========================================
@router.get("/health", dependencies=ADMIN_ONLY)
def compiler_health(session: Session = Depends(get_session)) -> dict:
    """Compiler health: head sequence, outbox status, and per-state version /
    staleness / cursor lag for the studio and every project state."""
    return brain.compiler_health(session)


@router.get("/stale", dependencies=ADMIN_ONLY)
def stale_states(session: Session = Depends(get_session)) -> dict:
    """States needing (re)compilation — flagged stale or whose cursor trails the
    latest in-scope event. Read-only (mirrors reconcile's comparison)."""
    return brain.stale_states(session)


@router.get("/revisions/{revision_a_id}/delta/{revision_b_id}", dependencies=ADMIN_ONLY)
def revision_delta(
    revision_a_id: str,
    revision_b_id: str,
    session: Session = Depends(get_session),
) -> dict:
    """Deterministic section-level diff (added / removed / changed) between two
    immutable revisions."""
    try:
        return brain.revision_delta(
            session, revision_a_id=revision_a_id, revision_b_id=revision_b_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/state/studio/rebuild", response_model=RebuildResult, dependencies=ADMIN_ONLY)
def rebuild_studio_state(
    body: RebuildRequest = RebuildRequest(),
    session: Session = Depends(get_session),
) -> RebuildResult:
    """Compile the studio state (incremental, or a full rebuild when ``full``)."""
    return RebuildResult(**brain.compile_studio(session, full=body.full))


@router.post("/works/{work_id}/state/rebuild", response_model=RebuildResult, dependencies=ADMIN_ONLY)
def rebuild_work_state(
    work_id: str,
    body: RebuildRequest = RebuildRequest(),
    session: Session = Depends(get_session),
) -> RebuildResult:
    try:
        return RebuildResult(
            **brain.compile_project(session, work_id=work_id, full=body.full)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/story-worlds/{world_id}/state/rebuild", response_model=RebuildResult, dependencies=ADMIN_ONLY)
def rebuild_world_state(
    world_id: str,
    body: RebuildRequest = RebuildRequest(),
    session: Session = Depends(get_session),
) -> RebuildResult:
    try:
        return RebuildResult(
            **brain.compile_project(session, story_world_id=world_id, full=body.full)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# === stable instruction layer (Studio Constitution, profiles, …) ===========
def _constitution_read(parent, v) -> ConstitutionRead:
    return ConstitutionRead(
        key=parent.key, name=parent.name, description=parent.description,
        current_version=parent.current_version, body=v.body if v else "",
    )


def _profile_read(parent, v) -> ProfileRead:
    return ProfileRead(
        key=parent.key, name=parent.name, description=parent.description,
        current_version=parent.current_version,
        purpose=v.purpose if v else "",
        permitted_domains=v.permitted_domains if v else [],
        required_project_scope=v.required_project_scope if v else True,
        available_tools=v.available_tools if v else [],
        tone=v.tone if v else "", response_format=v.response_format if v else "prose",
        approval_policy=v.approval_policy if v else "default",
        default_temperature=v.default_temperature if v else 0.3,
        output_limit=v.output_limit if v else 1500,
        model_preference=v.model_preference if v else None,
        required_scopes=v.required_scopes if v else [],
    )


def _version_refs(rows) -> list[VersionRef]:
    return [VersionRef(version=r.version, notes=r.notes, created_by_id=r.created_by_id) for r in rows]


@router.get("/constitution", response_model=ConstitutionRead)
def get_constitution(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> ConstitutionRead:
    parent, v = instruction_svc.get_active(session, "constitution", "studio-constitution")
    if parent is None:
        raise HTTPException(status_code=404, detail="Constitution not seeded")
    return _constitution_read(parent, v)


@router.get("/constitution/versions", response_model=list[VersionRef], dependencies=ADMIN_ONLY)
def list_constitution_versions(session: Session = Depends(get_session)) -> list[VersionRef]:
    return _version_refs(instruction_svc.list_versions(session, "constitution", "studio-constitution"))


@router.post("/constitution/versions", response_model=ConstitutionRead, dependencies=ADMIN_ONLY)
def add_constitution_version(
    body: ConstitutionVersionCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConstitutionRead:
    try:
        instruction_svc.add_version(
            session, "constitution", "studio-constitution",
            fields={"body": body.body, "notes": body.notes}, created_by_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    session.commit()
    parent, v = instruction_svc.get_active(session, "constitution", "studio-constitution")
    return _constitution_read(parent, v)


@router.get("/profiles", response_model=list[ProfileRead])
def list_profiles(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> list[ProfileRead]:
    return [_profile_read(p, v) for p, v in instruction_svc.list_profiles(session)]


@router.get("/profiles/{key}", response_model=ProfileRead)
def get_profile(
    key: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> ProfileRead:
    parent, v = instruction_svc.get_active(session, "profile", key)
    if parent is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _profile_read(parent, v)


@router.get("/profiles/{key}/versions", response_model=list[VersionRef], dependencies=ADMIN_ONLY)
def list_profile_versions(key: str, session: Session = Depends(get_session)) -> list[VersionRef]:
    return _version_refs(instruction_svc.list_versions(session, "profile", key))


@router.post("/profiles/{key}/versions", response_model=ProfileRead, dependencies=ADMIN_ONLY)
def add_profile_version(
    key: str,
    body: ProfileVersionCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProfileRead:
    fields = body.model_dump()
    notes = fields.pop("notes", None)
    fields["notes"] = notes
    try:
        instruction_svc.add_version(session, "profile", key, fields=fields, created_by_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    session.commit()
    parent, v = instruction_svc.get_active(session, "profile", key)
    return _profile_read(parent, v)


@router.get("/context-templates/{key}", response_model=TemplateRead)
def get_context_template(
    key: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> TemplateRead:
    parent, v = instruction_svc.get_active(session, "template", key)
    if parent is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplateRead(
        key=parent.key, name=parent.name, current_version=parent.current_version,
        segment_key=v.segment_key if v else "", body=v.body if v else "",
    )


@router.post("/context-templates/{key}/versions", response_model=TemplateRead, dependencies=ADMIN_ONLY)
def add_template_version(
    key: str,
    body: TemplateVersionCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TemplateRead:
    try:
        instruction_svc.add_version(
            session, "template", key,
            fields={"segment_key": body.segment_key, "body": body.body, "notes": body.notes},
            created_by_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    session.commit()
    parent, v = instruction_svc.get_active(session, "template", key)
    return TemplateRead(
        key=parent.key, name=parent.name, current_version=parent.current_version,
        segment_key=v.segment_key, body=v.body,
    )


@router.get("/policies/{key}", response_model=PolicyRead)
def get_policy(
    key: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> PolicyRead:
    parent, v = instruction_svc.get_active(session, "policy", key)
    if parent is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    return PolicyRead(
        key=parent.key, name=parent.name, current_version=parent.current_version,
        mode=v.mode, required_scope_to_act=v.required_scope_to_act,
        blocked_tools=v.blocked_tools,
    )


@router.post("/policies/{key}/versions", response_model=PolicyRead, dependencies=ADMIN_ONLY)
def add_policy_version(
    key: str,
    body: PolicyVersionCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PolicyRead:
    try:
        instruction_svc.add_version(
            session, "policy", key,
            fields={
                "mode": body.mode, "required_scope_to_act": body.required_scope_to_act,
                "blocked_tools": body.blocked_tools, "rules": body.rules, "notes": body.notes,
            },
            created_by_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    session.commit()
    parent, v = instruction_svc.get_active(session, "policy", key)
    return PolicyRead(
        key=parent.key, name=parent.name, current_version=parent.current_version,
        mode=v.mode, required_scope_to_act=v.required_scope_to_act, blocked_tools=v.blocked_tools,
    )


@router.get("/glossary", response_model=GlossaryRead)
def get_glossary(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> GlossaryRead:
    parent, v = instruction_svc.get_active(session, "glossary", "studio-glossary")
    if parent is None:
        raise HTTPException(status_code=404, detail="Glossary not seeded")
    return GlossaryRead(
        key=parent.key, name=parent.name, current_version=parent.current_version,
        entries=v.entries if v else [], body=v.body if v else "",
    )


@router.post("/glossary/versions", response_model=GlossaryRead, dependencies=ADMIN_ONLY)
def add_glossary_version(
    body: GlossaryVersionCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> GlossaryRead:
    entries = sorted(body.entries, key=lambda e: e.get("term", "") if isinstance(e, dict) else str(e))
    rendered = "\n".join(
        f"{e.get('term', '')}: {e.get('definition', '')}" for e in entries if isinstance(e, dict)
    )
    try:
        instruction_svc.add_version(
            session, "glossary", "studio-glossary",
            fields={"entries": entries, "body": rendered, "notes": body.notes},
            created_by_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    session.commit()
    parent, v = instruction_svc.get_active(session, "glossary", "studio-glossary")
    return GlossaryRead(
        key=parent.key, name=parent.name, current_version=parent.current_version,
        entries=v.entries, body=v.body,
    )


# === context assembly ======================================================
@router.post("/conversations/{conversation_id}/assemble")
def assemble_context(
    conversation_id: str,
    body: AssembleRequest = AssembleRequest(),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Assemble the ordered, permission-filtered context for a conversation and
    persist its prefix-cache checkpoint. Scoped conversations require
    VIEW_PROJECT (admins bypass)."""
    conv = brain.get_conversation(session, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.owner_user_id != user.id and not _is_admin(user):
        raise HTTPException(status_code=403, detail="Not your conversation")
    if (conv.work_id or conv.story_world_id) and not _is_admin(user):
        ensure_can(
            session, user, _PS.VIEW_PROJECT,
            work_id=conv.work_id, story_world_id=conv.story_world_id,
        )
    ctx = brain.assemble(
        session, conv, user=user, model=body.model,
        include_evidence=body.include_evidence, question=body.question,
    )
    session.commit()
    return {
        "messages": ctx.messages,
        "model": ctx.model,
        "temperature": ctx.temperature,
        "max_tokens": ctx.max_tokens,
        "tools": ctx.tools,
        "prefix_hash": ctx.prefix_hash,
        "context_checksum": ctx.context_checksum,
        "versions": ctx.versions,
        "resolved_scopes": ctx.resolved_scopes,
    }


@router.get("/conversations/{conversation_id}/debug/context", dependencies=ADMIN_ONLY)
def debug_context(
    conversation_id: str,
    include_evidence: bool = Query(default=False),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Admin debug view: per-segment sizes + REDACTED content, prefix hash and
    state versions — computed for the calling admin, and read-only (it never
    writes a checkpoint). Never reads or echoes any API key / Authorization header."""
    conv = brain.get_conversation(session, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return brain.debug_context(
        session, conv, user=user, include_evidence=include_evidence
    )
