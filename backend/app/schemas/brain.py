from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

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
from app.schemas._common import ORMModel, TimestampedRead


# --- compiled state (read-only) -------------------------------------------
class StudioBrainStateRead(TimestampedRead):
    version: int
    status: BrainStateStatus
    compiled_at: Optional[datetime] = None
    source_event_cursor: int
    structured_state: dict[str, Any] = {}
    compact_summary: Optional[str] = None
    checksum: Optional[str] = None
    compiler_version: Optional[str] = None
    assist_version: Optional[str] = None
    stale: bool


class ProjectBrainStateRead(TimestampedRead):
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    version: int
    status: BrainStateStatus
    compiled_at: Optional[datetime] = None
    source_event_cursor: int
    structured_state: dict[str, Any] = {}
    compact_summary: Optional[str] = None
    canon_digest: Optional[str] = None
    production_digest: Optional[str] = None
    open_questions: list[Any] = []
    priorities: list[Any] = []
    recent_changes: list[Any] = []
    checksum: Optional[str] = None
    stale: bool


class BrainStateRevisionRead(TimestampedRead):
    state_type: BrainStateType
    state_id: str
    version: int
    previous_version: Optional[int] = None
    deterministic_payload: dict[str, Any] = {}
    llm_summary: Optional[str] = None
    source_event_from: Optional[int] = None
    source_event_to: Optional[int] = None
    compiler_version: Optional[str] = None
    generated_at: datetime
    approval_status: BrainRevisionApproval
    approved_by_id: Optional[str] = None
    approved_at: Optional[datetime] = None


# --- events (append-only; read-only surface) ------------------------------
class OutboxStatusRead(BaseModel):
    """Monitoring snapshot of the event outbox."""

    head_sequence: int
    cursor: int            # high-water mark = max processed sequence
    unprocessed: int       # PENDING events awaiting the consumer
    failed: int            # dead-lettered events
    compiler_lag: int      # head_sequence - cursor
    studio_stale: Optional[bool] = None
    studio_version: Optional[int] = None
    stale_projects: int


class OutboxReplayRequest(BaseModel):
    event_ids: Optional[list[str]] = None  # None = replay all dead-letters


# --- state compiler (Prompt 5) ---------------------------------------------
class RebuildRequest(BaseModel):
    """Trigger a (re)compile. ``full`` forces a full deterministic rebuild for
    validation / disaster recovery; otherwise the compile is incremental."""

    full: bool = False


class RebuildResult(BaseModel):
    scope: str
    version: int
    checksum: Optional[str] = None
    changed: bool
    from_seq: int
    to_seq: int
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None


class BrainEventRead(TimestampedRead):
    sequence: int
    event_type: str
    aggregate_type: str
    aggregate_id: str
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    actor_id: Optional[str] = None
    correlation_id: Optional[str] = None
    payload: dict[str, Any] = {}
    occurred_at: datetime
    status: BrainEventStatus
    processed_at: Optional[datetime] = None
    attempts: int
    error: Optional[str] = None


# --- conversations ---------------------------------------------------------
class BrainConversationCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300)
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    active_profile: Optional[str] = Field(default=None, max_length=80)
    librechat_conversation_id: Optional[str] = Field(default=None, max_length=120)


class BrainConversationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300)
    status: Optional[BrainConversationStatus] = None
    active_profile: Optional[str] = Field(default=None, max_length=80)
    last_state_version: Optional[int] = None
    librechat_conversation_id: Optional[str] = Field(default=None, max_length=120)


class BrainConversationRead(TimestampedRead):
    owner_user_id: str
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    librechat_conversation_id: Optional[str] = None
    title: Optional[str] = None
    active_profile: Optional[str] = None
    status: BrainConversationStatus
    last_state_version: Optional[int] = None


# --- messages (append-only within a conversation) -------------------------
class BrainMessageCreate(BaseModel):
    role: BrainMessageRole
    content: Optional[str] = None
    structured_content: dict[str, Any] = {}
    model: Optional[str] = Field(default=None, max_length=160)
    provider: Optional[str] = Field(default=None, max_length=80)
    prompt_tokens: Optional[int] = Field(default=None, ge=0)
    completion_tokens: Optional[int] = Field(default=None, ge=0)
    request_id: Optional[str] = Field(default=None, max_length=80)
    state_version: Optional[int] = None
    retrieval_ids: list[Any] = []
    tool_call_ids: list[Any] = []


class BrainMessageRead(TimestampedRead):
    conversation_id: str
    role: BrainMessageRole
    content: Optional[str] = None
    structured_content: dict[str, Any] = {}
    model: Optional[str] = None
    provider: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    request_id: Optional[str] = None
    state_version: Optional[int] = None
    retrieval_ids: list[Any] = []
    tool_call_ids: list[Any] = []


# --- memory ----------------------------------------------------------------
class BrainMemoryItemCreate(BaseModel):
    scope: BrainScope
    kind: BrainMemoryKind
    content: str
    structured_data: dict[str, Any] = {}
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    member_user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    source_message_id: Optional[str] = None
    source_event_id: Optional[str] = None
    supersedes_id: Optional[str] = None
    expires_at: Optional[datetime] = None


class BrainMemoryItemUpdate(BaseModel):
    content: Optional[str] = None
    structured_data: Optional[dict[str, Any]] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    expires_at: Optional[datetime] = None


class BrainMemoryVerify(BaseModel):
    verification: BrainMemoryVerification


class BrainMemoryItemRead(TimestampedRead):
    scope: BrainScope
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    member_user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    kind: BrainMemoryKind
    content: str
    structured_data: dict[str, Any] = {}
    confidence: Optional[float] = None
    source_message_id: Optional[str] = None
    source_event_id: Optional[str] = None
    verification: BrainMemoryVerification
    supersedes_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_by_id: Optional[str] = None
    approved_by_id: Optional[str] = None


# --- decisions -------------------------------------------------------------
class DecisionRecordCreate(BaseModel):
    scope: BrainScope
    subject: str = Field(max_length=300)
    decision: str
    rationale: Optional[str] = None
    alternatives: list[Any] = []
    affected_entities: list[Any] = []
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    source_conversation_id: Optional[str] = None
    effective_date: Optional[datetime] = None


class DecisionDecision(BaseModel):
    """Approve or reject a proposed decision."""

    note: Optional[str] = None
    effective_date: Optional[datetime] = None


class DecisionRecordRead(TimestampedRead):
    scope: BrainScope
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    subject: str
    decision: str
    rationale: Optional[str] = None
    alternatives: list[Any] = []
    affected_entities: list[Any] = []
    status: DecisionStatus
    source_conversation_id: Optional[str] = None
    proposer_id: Optional[str] = None
    approver_id: Optional[str] = None
    effective_date: Optional[datetime] = None
    superseded_by_id: Optional[str] = None
