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
    ProjectBrainStateRead,
    StudioBrainStateRead,
)
from app.services import brain
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
