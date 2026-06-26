"""Persistence-layer tests for the SUPERVOID Brain.

Exercise the service invariants directly against the in-memory DB: append-only
events with a monotonic sequence, immutable revision history, current-state
upsert, conversation/message append, memory supersede/verify, decision
lifecycle, checkpoint upsert. No state is compiled here.
"""
from __future__ import annotations

import pytest
from sqlmodel import Session, func, select

from app.models import (
    BrainConversation,
    BrainEvent,
    BrainStateRevision,
    StudioBrainState,
)
from app.models.enums import (
    BrainEventStatus,
    BrainMemoryKind,
    BrainMemoryVerification,
    BrainMessageRole,
    BrainScope,
    BrainStateType,
    DecisionStatus,
)
from app.services import brain


def _make_work(session: Session, *, title: str = "Brain Work") -> str:
    """A real Work (FK constraints are enforced on the test engine too)."""
    from app.models import Author, Work

    author = Author(full_name="A. Author")
    session.add(author)
    session.commit()
    session.refresh(author)
    work = Work(title=title, author_id=author.id)
    session.add(work)
    session.commit()
    session.refresh(work)
    return work.id


# --- events: append-only + monotonic sequence ------------------------------
def test_append_event_assigns_monotonic_sequence(session: Session) -> None:
    e1 = brain.append_event(session, event_type="work.updated", aggregate_type="work", aggregate_id="w1")
    e2 = brain.append_event(session, event_type="work.updated", aggregate_type="work", aggregate_id="w1")
    e3 = brain.append_event(session, event_type="manuscript.updated", aggregate_type="manuscript", aggregate_id="m1")
    session.commit()
    assert [e1.sequence, e2.sequence, e3.sequence] == [1, 2, 3]
    assert all(e.status == BrainEventStatus.PENDING for e in (e1, e2, e3))
    listed = brain.list_events(session)
    assert [e.sequence for e in listed] == [1, 2, 3]
    # sequence is unique
    with pytest.raises(Exception):
        session.add(BrainEvent(sequence=1, event_type="x", aggregate_type="y", aggregate_id="z", occurred_at=e1.occurred_at))
        session.commit()
    session.rollback()


def test_event_processing_transitions(session: Session) -> None:
    e = brain.append_event(session, event_type="x", aggregate_type="work", aggregate_id="w")
    session.commit()
    brain.mark_event_processed(session, e)
    session.commit()
    assert e.status == BrainEventStatus.PROCESSED and e.processed_at is not None and e.attempts == 1
    brain.mark_event_failed(session, e, "boom")
    session.commit()
    assert e.status == BrainEventStatus.FAILED and e.error == "boom" and e.attempts == 2


# --- studio state: singleton upsert + immutable revisions ------------------
def test_studio_state_upserts_and_snapshots_revisions(session: Session) -> None:
    s1 = brain.set_studio_state(session, structured_state={"n": 1}, source_event_cursor=5)
    session.commit()
    assert s1.version == 1 and s1.stale is False
    s2 = brain.set_studio_state(session, structured_state={"n": 2}, source_event_cursor=9)
    session.commit()
    assert s2.version == 2
    # exactly one current studio row (singleton)
    count = session.exec(select(func.count()).select_from(StudioBrainState)).one()
    assert count == 1
    # both versions are preserved as immutable revisions
    revs = brain.list_revisions(session, state_type=BrainStateType.STUDIO)
    assert [r.version for r in revs] == [2, 1]
    assert revs[0].previous_version == 1
    assert revs[1].deterministic_payload == {"n": 1}


def test_project_state_per_scope_and_validation(session: Session) -> None:
    wa = _make_work(session, title="A")
    wb = _make_work(session, title="B")
    a = brain.set_project_state(session, work_id=wa, structured_state={"k": "a"})
    b = brain.set_project_state(session, work_id=wb, structured_state={"k": "b"})
    session.commit()
    assert a.version == 1 and b.version == 1
    a2 = brain.set_project_state(session, work_id=wa, structured_state={"k": "a2"})
    session.commit()
    assert a2.version == 2 and a2.id == a.id  # same current row, bumped
    assert brain.get_project_state(session, work_id=wa).version == 2
    revs = brain.list_revisions(session, state_type=BrainStateType.PROJECT, state_id=a.id)
    assert [r.version for r in revs] == [2, 1]
    # exactly one of work_id / story_world_id is required
    with pytest.raises(ValueError):
        brain.set_project_state(session, structured_state={})
    with pytest.raises(ValueError):
        brain.set_project_state(session, work_id="x", story_world_id="y", structured_state={})


# --- conversations + messages ----------------------------------------------
def test_conversation_and_message_append(session: Session, editor_user) -> None:
    conv = brain.create_conversation(session, owner_user_id=editor_user.id, title="Chat")
    session.commit()
    brain.append_message(session, conv, role=BrainMessageRole.USER, content="hello")
    brain.append_message(
        session, conv, role=BrainMessageRole.ASSISTANT, content="hi", state_version=3,
        request_id="rid-1", provider="vllm", model="supervoid-brain",
    )
    session.commit()
    msgs = brain.list_messages(session, conv.id)
    assert [m.role for m in msgs] == [BrainMessageRole.USER, BrainMessageRole.ASSISTANT]
    session.refresh(conv)
    assert conv.last_state_version == 3


# --- memory: supersede + verify --------------------------------------------
def test_memory_supersede_and_verify(session: Session, admin_user) -> None:
    a = brain.create_memory(
        session, scope=BrainScope.STUDIO, kind=BrainMemoryKind.FACT,
        content="old fact", created_by_id=admin_user.id,
    )
    session.commit()
    b = brain.create_memory(
        session, scope=BrainScope.STUDIO, kind=BrainMemoryKind.FACT,
        content="new fact", created_by_id=admin_user.id, supersedes_id=a.id,
    )
    session.commit()
    session.refresh(a)
    assert a.verification == BrainMemoryVerification.SUPERSEDED
    assert b.supersedes_id == a.id

    brain.verify_memory(session, b, verification=BrainMemoryVerification.VERIFIED, approver_id=admin_user.id)
    session.commit()
    assert b.verification == BrainMemoryVerification.VERIFIED and b.approved_by_id == admin_user.id


# --- decisions: lifecycle ---------------------------------------------------
def test_decision_lifecycle(session: Session, admin_user) -> None:
    d = brain.create_decision(
        session, scope=BrainScope.STUDIO, subject="Tone", decision="Lean dry",
        proposer_id=admin_user.id, alternatives=["wry", "earnest"],
    )
    session.commit()
    assert d.status == DecisionStatus.PROPOSED
    brain.decide_decision(session, d, approve=True, approver_id=admin_user.id)
    session.commit()
    assert d.status == DecisionStatus.APPROVED and d.approver_id == admin_user.id

    d2 = brain.create_decision(session, scope=BrainScope.STUDIO, subject="X", decision="Y", proposer_id=admin_user.id)
    session.commit()
    brain.decide_decision(session, d2, approve=False, approver_id=admin_user.id)
    session.commit()
    assert d2.status == DecisionStatus.REJECTED


# --- checkpoint upsert ------------------------------------------------------
def test_checkpoint_upsert(session: Session, editor_user) -> None:
    conv = brain.create_conversation(session, owner_user_id=editor_user.id)
    session.commit()
    cp1 = brain.upsert_checkpoint(session, conversation_id=conv.id, prefix_hash="abc", status="warm")
    session.commit()
    cp2 = brain.upsert_checkpoint(session, conversation_id=conv.id, prefix_hash="abc", model="supervoid-brain")
    session.commit()
    assert cp1.id == cp2.id  # same checkpoint updated, not duplicated
    assert cp2.model == "supervoid-brain"


# --- no secret/credential fields anywhere ----------------------------------
def test_no_secret_fields_on_brain_models() -> None:
    from app.models import brain as brain_models

    # Secret-like names (not "token", which legitimately appears in token COUNT
    # fields like prompt_tokens / completion_tokens).
    banned = ("api_key", "apikey", "secret", "password", "credential", "private_key", "access_token", "refresh_token")
    models = [
        brain_models.StudioBrainState, brain_models.ProjectBrainState,
        brain_models.BrainStateRevision, brain_models.BrainEvent,
        brain_models.BrainConversation, brain_models.BrainMessage,
        brain_models.BrainCheckpoint, brain_models.BrainMemoryItem,
        brain_models.DecisionRecord,
    ]
    for model in models:
        for field_name in model.model_fields:
            assert not any(b in field_name.lower() for b in banned), (model.__name__, field_name)
