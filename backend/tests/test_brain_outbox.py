"""Tests for the Brain domain-event outbox (emit + consume + reconcile).

The four headline guarantees from the spec are proven here:
  * a mutation and its event commit together,
  * a rollback removes both,
  * duplicate consumption is harmless,
  * only the affected project is marked stale.
Plus retries/dead-letter/replay, reconciliation, monitoring and secret-safety.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

from app.models import BrainEvent, ProjectBrainState, Work
from app.models.enums import BrainEventStatus
from app.services import brain
from app.services.brain import consumer
from app.services.brain.events import BrainEventType as ET


def _make_work(session: Session, *, title: str = "Outbox Work") -> Work:
    from app.models import Author

    author = Author(full_name="A. Author")
    session.add(author)
    session.commit()
    session.refresh(author)
    work = Work(title=title, author_id=author.id)
    session.add(work)
    session.commit()
    session.refresh(work)
    return work


def _event_count(session: Session) -> int:
    return int(session.exec(select(func.count(BrainEvent.id))).one() or 0)


# --- 1. mutation + event commit together -----------------------------------
def test_mutation_and_event_commit_together(session: Session, engine: Engine) -> None:
    work = _make_work(session)
    # one transaction: change the work AND emit its event
    work.title = "Renamed"
    session.add(work)
    brain.emit(
        session, event_type=ET.WORK_UPDATED, aggregate_type="work",
        aggregate_id=work.id, work_id=work.id, changes={"title": "Renamed"},
    )
    session.commit()

    # a fresh connection sees BOTH the change and the event
    with Session(engine) as other:
        assert other.get(Work, work.id).title == "Renamed"
        ev = other.exec(
            select(BrainEvent).where(BrainEvent.aggregate_id == work.id)
        ).first()
        assert ev is not None
        assert ev.event_type == ET.WORK_UPDATED
        assert ev.work_id == work.id
        assert ev.payload["changes"] == {"title": "Renamed"}


# --- 2. rollback removes both ----------------------------------------------
def test_rollback_removes_both(session: Session, engine: Engine) -> None:
    work = _make_work(session, title="Original")
    before = _event_count(session)

    work.title = "WillRollback"
    session.add(work)
    brain.emit(
        session, event_type=ET.WORK_UPDATED, aggregate_type="work",
        aggregate_id=work.id, work_id=work.id, changes={"title": "WillRollback"},
    )
    session.rollback()

    with Session(engine) as other:
        assert other.get(Work, work.id).title == "Original"   # change undone
        assert _event_count(other) == before                   # event undone


# --- 3. duplicate consumption is harmless ----------------------------------
def test_duplicate_consumption_is_harmless(session: Session) -> None:
    work = _make_work(session)
    brain.set_project_state(session, work_id=work.id, structured_state={}, stale=False)
    session.commit()
    brain.emit(session, event_type=ET.WORK_UPDATED, aggregate_type="work",
               aggregate_id=work.id, work_id=work.id)
    session.commit()

    first = consumer.process_pending(session)
    assert first["processed"] == 1
    assert brain.get_project_state(session, work_id=work.id).stale is True

    # consuming again does nothing and does not error
    second = consumer.process_pending(session)
    assert second["processed"] == 0
    assert brain.get_project_state(session, work_id=work.id).stale is True


# --- 4. only the affected project is marked stale --------------------------
def test_only_affected_project_marked_stale(session: Session) -> None:
    a = _make_work(session, title="A")
    b = _make_work(session, title="B")
    brain.set_project_state(session, work_id=a.id, structured_state={}, stale=False)
    brain.set_project_state(session, work_id=b.id, structured_state={}, stale=False)
    session.commit()

    brain.emit(session, event_type=ET.WORK_UPDATED, aggregate_type="work",
               aggregate_id=a.id, work_id=a.id)
    session.commit()
    consumer.process_pending(session)

    assert brain.get_project_state(session, work_id=a.id).stale is True
    assert brain.get_project_state(session, work_id=b.id).stale is False
    # studio is always affected
    assert brain.get_studio_state(session).stale is True


# --- retries -> dead-letter -> replay --------------------------------------
def test_retries_dead_letter_and_replay(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = _make_work(session)
    brain.emit(session, event_type=ET.WORK_UPDATED, aggregate_type="work",
               aggregate_id=work.id, work_id=work.id)
    session.commit()

    def _boom(*_a, **_k):
        raise RuntimeError("handler exploded")

    monkeypatch.setattr(consumer, "_schedule_recompile", _boom)

    consumer.process_pending(session, max_attempts=2)
    ev = session.exec(select(BrainEvent)).first()
    assert ev.status == BrainEventStatus.PENDING and ev.attempts == 1  # retryable

    consumer.process_pending(session, max_attempts=2)
    session.refresh(ev)
    assert ev.status == BrainEventStatus.FAILED and ev.attempts == 2   # dead-letter

    # manual replay puts it back to PENDING
    assert brain.replay_failed(session) == 1
    session.refresh(ev)
    assert ev.status == BrainEventStatus.PENDING and ev.attempts == 0


# --- reconciliation detects missed changes ---------------------------------
def test_reconcile_detects_missed_changes(session: Session) -> None:
    work = _make_work(session)
    # a fresh, non-stale state, but an event exists for it that was never consumed
    brain.set_project_state(session, work_id=work.id, structured_state={}, stale=False)
    brain.emit(session, event_type=ET.WORK_UPDATED, aggregate_type="work",
               aggregate_id=work.id, work_id=work.id)
    session.commit()

    result = brain.reconcile(session)
    assert f"work:{work.id}" in result["marked"]
    assert brain.get_project_state(session, work_id=work.id).stale is True


# --- monitoring ------------------------------------------------------------
def test_outbox_status_monitoring(session: Session) -> None:
    work = _make_work(session)
    brain.emit(session, event_type=ET.WORK_UPDATED, aggregate_type="work",
               aggregate_id=work.id, work_id=work.id)
    brain.emit(session, event_type=ET.WORK_UPDATED, aggregate_type="work",
               aggregate_id=work.id, work_id=work.id)
    session.commit()

    pre = brain.outbox_status(session)
    assert pre["unprocessed"] == 2 and pre["cursor"] == 0 and pre["compiler_lag"] == pre["head_sequence"]

    consumer.process_pending(session)
    post = brain.outbox_status(session)
    assert post["unprocessed"] == 0
    assert post["cursor"] == post["head_sequence"]
    assert post["compiler_lag"] == 0
    assert post["stale_projects"] >= 0


# --- end-to-end: real API mutations emit events in the same transaction ----
def test_api_mutations_emit_domain_events(
    client: TestClient, engine: Engine
) -> None:
    """Driving the actual HTTP routes (not the emitter directly) proves the
    domain mutations are wired to the outbox — create/update/delete each land a
    work.* event, and delete succeeds (the Brain holds no FK on the work)."""
    author_id = client.post(
        "/api/authors", json={"full_name": "E. Mitter"}
    ).json()["id"]

    created = client.post(
        "/api/works", json={"title": "Emitted", "author_id": author_id}
    )
    assert created.status_code == 201
    work_id = created.json()["id"]

    assert (
        client.patch(f"/api/works/{work_id}", json={"title": "Re-titled"}).status_code
        == 200
    )
    # The Brain referencing this work must NOT block its deletion.
    assert client.delete(f"/api/works/{work_id}").status_code == 204

    with Session(engine) as s:
        kinds = [
            e.event_type
            for e in s.exec(
                select(BrainEvent)
                .where(BrainEvent.aggregate_id == work_id)
                .order_by(BrainEvent.sequence)
            ).all()
        ]
        assert kinds == [ET.WORK_CREATED, ET.WORK_UPDATED, ET.WORK_DELETED]
        # No secret-bearing full record — only a changed-field summary.
        upd = s.exec(
            select(BrainEvent).where(BrainEvent.event_type == ET.WORK_UPDATED)
        ).first()
        assert upd.payload["changes"] == {"title": "Re-titled"}


# --- payload carries no secrets --------------------------------------------
def test_event_payload_redacts_secrets(session: Session) -> None:
    work = _make_work(session)
    brain.emit(
        session, event_type=ET.WORK_UPDATED, aggregate_type="work",
        aggregate_id=work.id, work_id=work.id,
        changes={"title": "ok", "api_key": "sk-secret", "auth_token": "t"},
    )
    session.commit()
    ev = session.exec(select(BrainEvent)).first()
    changes = ev.payload["changes"]
    assert changes["title"] == "ok"
    assert changes["api_key"] == "[redacted]"
    assert "sk-secret" not in str(ev.payload)
