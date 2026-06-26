"""Durable persistence for the SUPERVOID Brain.

This is the **storage layer only** — no state is compiled here (the compiler is
a later phase). It defines:

* the current compiled state for the studio and per Work/StoryWorld
  (``StudioBrainState`` / ``ProjectBrainState`` — mutable "current" rows),
* the immutable revision history (``BrainStateRevision``),
* the append-only domain-event log (``BrainEvent``),
* conversations / messages / prompt-prefix checkpoints
  (``BrainConversation`` / ``BrainMessage`` / ``BrainCheckpoint``),
* durable memory and decisions (``BrainMemoryItem`` / ``DecisionRecord``).

Invariants (enforced by the service layer, not by free CRUD): revisions and
events are never edited or deleted; state "current" rows are upserted in place
while every version is snapshotted as a revision. No field stores a model
secret, API key or credential.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import (
    BrainCheckpointStatus,
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


class StudioBrainState(BaseEntity, table=True):
    """The single current compiled state for the whole studio.

    Updated in place as new versions compile; each version is snapshotted into
    ``BrainStateRevision``. ``singleton_key`` keeps exactly one row.
    """

    __tablename__ = "studio_brain_states"

    singleton_key: str = Field(default="studio", max_length=20, unique=True)
    version: int = Field(default=0, index=True)
    status: BrainStateStatus = Field(default=BrainStateStatus.PENDING, index=True)
    compiled_at: Optional[datetime] = Field(default=None)
    source_event_cursor: int = Field(default=0, index=True)

    structured_state: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    compact_summary: Optional[str] = Field(default=None)
    checksum: Optional[str] = Field(default=None, max_length=128, index=True)
    compiler_version: Optional[str] = Field(default=None, max_length=60)
    # Version of the model-assisted (LLM-generated) fields, tracked separately
    # from the deterministic ``compiler_version``.
    assist_version: Optional[str] = Field(default=None, max_length=60)

    stale: bool = Field(default=True, index=True)


class ProjectBrainState(BaseEntity, table=True):
    """The current compiled state for one Work or one StoryWorld.

    Exactly one row per Work and one per StoryWorld (nullable unique columns;
    a row sets one of the two scope ids).
    """

    __tablename__ = "project_brain_states"

    work_id: Optional[str] = Field(
        default=None, foreign_key="works.id", unique=True, index=True
    )
    story_world_id: Optional[str] = Field(
        default=None, foreign_key="story_worlds.id", unique=True, index=True
    )

    version: int = Field(default=0, index=True)
    status: BrainStateStatus = Field(default=BrainStateStatus.PENDING, index=True)
    compiled_at: Optional[datetime] = Field(default=None)
    source_event_cursor: int = Field(default=0, index=True)

    structured_state: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    compact_summary: Optional[str] = Field(default=None)
    canon_digest: Optional[str] = Field(default=None)
    production_digest: Optional[str] = Field(default=None)
    open_questions: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    priorities: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    recent_changes: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    checksum: Optional[str] = Field(default=None, max_length=128, index=True)
    stale: bool = Field(default=True, index=True)


class BrainStateRevision(BaseEntity, table=True):
    """Immutable snapshot of one compiled state version.

    Polymorphic over the two state families: ``state_type`` + ``state_id``
    identify the owning ``StudioBrainState`` / ``ProjectBrainState`` (stored as a
    plain id, not an FK, because the target table varies). Never edited.
    """

    __tablename__ = "brain_state_revisions"

    __table_args__ = (
        Index("ix_brain_state_revisions_state", "state_type", "state_id"),
    )

    state_type: BrainStateType = Field(index=True)
    state_id: str = Field(max_length=36, index=True)
    version: int = Field(index=True)
    previous_version: Optional[int] = Field(default=None)

    deterministic_payload: dict = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    # Optional model-generated summary; may need approval (below) when it can
    # affect canon.
    llm_summary: Optional[str] = Field(default=None)

    source_event_from: Optional[int] = Field(default=None)
    source_event_to: Optional[int] = Field(default=None, index=True)
    compiler_version: Optional[str] = Field(default=None, max_length=60)
    generated_at: datetime = Field(index=True)

    approval_status: BrainRevisionApproval = Field(
        default=BrainRevisionApproval.NOT_REQUIRED, index=True
    )
    approved_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    approved_at: Optional[datetime] = Field(default=None)


class BrainEvent(BaseEntity, table=True):
    """An append-only domain event the Brain compiler consumes.

    ``sequence`` is a monotonic, unique global ordering assigned by the service
    on append. Events are never edited; ``processed_at`` / ``attempts`` /
    ``error`` / ``status`` are advanced only by the (future) processor.
    """

    __tablename__ = "brain_events"

    __table_args__ = (
        # The processor's "next unprocessed event" scan.
        Index("ix_brain_events_status_sequence", "status", "sequence"),
        Index("ix_brain_events_aggregate", "aggregate_type", "aggregate_id"),
    )

    sequence: int = Field(index=True, unique=True)
    event_type: str = Field(max_length=120, index=True)
    aggregate_type: str = Field(max_length=80, index=True)
    aggregate_id: str = Field(max_length=64, index=True)

    work_id: Optional[str] = Field(default=None, foreign_key="works.id", index=True)
    story_world_id: Optional[str] = Field(
        default=None, foreign_key="story_worlds.id", index=True
    )
    actor_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)
    correlation_id: Optional[str] = Field(default=None, max_length=80, index=True)

    payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    occurred_at: datetime = Field(index=True)

    status: BrainEventStatus = Field(default=BrainEventStatus.PENDING, index=True)
    processed_at: Optional[datetime] = Field(default=None)
    attempts: int = Field(default=0, ge=0)
    error: Optional[str] = Field(default=None)


class BrainConversation(BaseEntity, table=True):
    """A persistent Brain conversation owned by a member, optionally project-scoped."""

    __tablename__ = "brain_conversations"

    owner_user_id: str = Field(foreign_key="users.id", index=True)
    work_id: Optional[str] = Field(default=None, foreign_key="works.id", index=True)
    story_world_id: Optional[str] = Field(
        default=None, foreign_key="story_worlds.id", index=True
    )
    librechat_conversation_id: Optional[str] = Field(
        default=None, max_length=120, index=True
    )

    title: Optional[str] = Field(default=None, max_length=300)
    active_profile: Optional[str] = Field(default=None, max_length=80)
    status: BrainConversationStatus = Field(
        default=BrainConversationStatus.ACTIVE, index=True
    )
    last_state_version: Optional[int] = Field(default=None)

    messages: list["BrainMessage"] = Relationship(
        back_populates="conversation",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class BrainMessage(BaseEntity, table=True):
    """One turn in a Brain conversation. Append-only within a conversation."""

    __tablename__ = "brain_messages"

    __table_args__ = (
        Index("ix_brain_messages_conversation_created", "conversation_id", "created_at"),
    )

    conversation_id: str = Field(foreign_key="brain_conversations.id", index=True)
    role: BrainMessageRole = Field(index=True)
    content: Optional[str] = Field(default=None)
    structured_content: dict = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )

    model: Optional[str] = Field(default=None, max_length=160)
    provider: Optional[str] = Field(default=None, max_length=80)
    prompt_tokens: Optional[int] = Field(default=None, ge=0)
    completion_tokens: Optional[int] = Field(default=None, ge=0)
    request_id: Optional[str] = Field(default=None, max_length=80, index=True)
    state_version: Optional[int] = Field(default=None)

    retrieval_ids: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    tool_call_ids: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))

    conversation: "BrainConversation" = Relationship(back_populates="messages")


class BrainCheckpoint(BaseEntity, table=True):
    """A prompt-prefix cache checkpoint for a conversation (gateway warm/cold)."""

    __tablename__ = "brain_checkpoints"

    conversation_id: str = Field(foreign_key="brain_conversations.id", index=True)
    model: Optional[str] = Field(default=None, max_length=160)
    prompt_template_version: Optional[int] = Field(default=None)
    studio_state_version: Optional[int] = Field(default=None)
    project_state_version: Optional[int] = Field(default=None)
    last_message_id: Optional[str] = Field(
        default=None, foreign_key="brain_messages.id", index=True
    )
    context_checksum: Optional[str] = Field(default=None, max_length=128)
    prefix_hash: Optional[str] = Field(default=None, max_length=128, index=True)
    status: BrainCheckpointStatus = Field(
        default=BrainCheckpointStatus.COLD, index=True
    )
    last_used_at: Optional[datetime] = Field(default=None, index=True)


class BrainMemoryItem(BaseEntity, table=True):
    """A durable, scoped piece of memory (fact, preference, decision, …)."""

    __tablename__ = "brain_memory_items"

    scope: BrainScope = Field(index=True)
    work_id: Optional[str] = Field(default=None, foreign_key="works.id", index=True)
    story_world_id: Optional[str] = Field(
        default=None, foreign_key="story_worlds.id", index=True
    )
    member_user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    conversation_id: Optional[str] = Field(
        default=None, foreign_key="brain_conversations.id", index=True
    )

    kind: BrainMemoryKind = Field(index=True)
    content: str = Field(default="")
    structured_data: dict = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    confidence: Optional[float] = Field(default=None, ge=0, le=1)

    source_message_id: Optional[str] = Field(
        default=None, foreign_key="brain_messages.id", index=True
    )
    source_event_id: Optional[str] = Field(
        default=None, foreign_key="brain_events.id", index=True
    )

    verification: BrainMemoryVerification = Field(
        default=BrainMemoryVerification.UNVERIFIED, index=True
    )
    supersedes_id: Optional[str] = Field(
        default=None, foreign_key="brain_memory_items.id", index=True
    )
    expires_at: Optional[datetime] = Field(default=None, index=True)

    created_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    approved_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )


class DecisionRecord(BaseEntity, table=True):
    """A recorded studio/project decision with an approval lifecycle."""

    __tablename__ = "decision_records"

    __table_args__ = (
        Index("ix_decision_records_scope_status", "scope", "status"),
    )

    scope: BrainScope = Field(index=True)
    work_id: Optional[str] = Field(default=None, foreign_key="works.id", index=True)
    story_world_id: Optional[str] = Field(
        default=None, foreign_key="story_worlds.id", index=True
    )

    subject: str = Field(default="", max_length=300)
    decision: str = Field(default="")
    rationale: Optional[str] = Field(default=None)
    alternatives: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    affected_entities: list = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )

    status: DecisionStatus = Field(default=DecisionStatus.PROPOSED, index=True)
    source_conversation_id: Optional[str] = Field(
        default=None, foreign_key="brain_conversations.id", index=True
    )
    proposer_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    approver_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    effective_date: Optional[datetime] = Field(default=None)
    superseded_by_id: Optional[str] = Field(
        default=None, foreign_key="decision_records.id", index=True
    )
