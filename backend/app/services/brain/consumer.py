"""The Brain event consumer (outbox processor).

Reads ``BrainEvent`` rows (the outbox) in sequence order and, for each, marks
the affected compiled state(s) **stale** — i.e. schedules a project-scoped
recompilation. It does **not** compile state (that is a later phase).

Properties:

* **cursor** — derived high-water mark = max processed sequence;
* **idempotency** — only PENDING events are selected; re-marking stale is a
  no-op, so re-running is harmless;
* **retries** — a failing event is retried up to ``brain_event_max_attempts``;
* **dead-letter** — after that it moves to FAILED with the error;
* **replay** — FAILED events can be re-queued to PENDING;
* **reconciliation** — a full scan re-flags any scope whose state is behind the
  latest event (detects changes a crashed/skipped run missed).

Each event is processed inside a SAVEPOINT so a single failure rolls back only
that event's effects, never the rest of the batch.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.config import settings
from app.models import (
    BrainEvent,
    ProjectBrainState,
    StudioBrainState,
)
from app.models.base import utcnow
from app.models.enums import BrainEventStatus, BrainStateStatus
from app.services.brain import get_project_state, get_studio_state


# --- stale scheduling (no compilation) -------------------------------------
def _mark_studio_stale(session: Session) -> None:
    state = get_studio_state(session)
    if state is None:
        state = StudioBrainState(
            singleton_key="studio", status=BrainStateStatus.STALE,
            stale=True, version=0,
        )
    else:
        state.stale = True
        if state.status == BrainStateStatus.READY:
            state.status = BrainStateStatus.STALE
    session.add(state)
    session.flush()


def _mark_project_stale(
    session: Session, *, work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
) -> None:
    if not (work_id or story_world_id):
        return
    state = get_project_state(session, work_id=work_id, story_world_id=story_world_id)
    if state is None:
        state = ProjectBrainState(
            work_id=work_id, story_world_id=story_world_id,
            status=BrainStateStatus.STALE, stale=True, version=0,
        )
    else:
        state.stale = True
        if state.status == BrainStateStatus.READY:
            state.status = BrainStateStatus.STALE
    session.add(state)
    session.flush()


def _schedule_recompile(session: Session, event: BrainEvent) -> None:
    """Flag the scopes an event touches as needing recompilation."""
    _mark_studio_stale(session)
    work_id = event.work_id
    story_world_id = event.story_world_id
    # Fall back to the aggregate itself when it *is* a work / story world.
    if not work_id and event.aggregate_type == "work":
        work_id = event.aggregate_id
    if not story_world_id and event.aggregate_type == "story_world":
        story_world_id = event.aggregate_id
    if work_id:
        _mark_project_stale(session, work_id=work_id)
    if story_world_id:
        _mark_project_stale(session, story_world_id=story_world_id)


def _schedule_index(session: Session, event: BrainEvent) -> None:
    """Best-effort cold-index refresh for an indexable aggregate (Prompt 14).

    Isolated in its own SAVEPOINT so an extraction/embedding failure never blocks
    the recompile scheduling that shares this event. Imported lazily to avoid an
    import cycle."""
    if not settings.retrieval_enabled:
        return
    from app.services.brain.retrieval.extractors import EVENT_SOURCE_MAP

    source_type = EVENT_SOURCE_MAP.get(event.aggregate_type)
    if source_type is None:
        return
    sp = session.begin_nested()
    try:
        from app.services.brain.retrieval import indexer

        indexer.reindex_source(session, source_type, event.aggregate_id)
        sp.commit()
    except Exception:  # noqa: BLE001 - indexing is best-effort, never fatal
        sp.rollback()


def _handle_event(session: Session, event: BrainEvent) -> None:
    """Dispatch one event. Most events schedule a recompile; the memory-analysis
    job (a completed conversation turn) runs the analyzer instead — a chat turn
    must never invalidate compiled domain state. The analyzer is imported lazily
    to avoid an import cycle (it depends on this package)."""
    if event.event_type == "conversation.turn_completed":
        from app.services.brain import memory as memory_svc

        memory_svc.analyze_turn(session, event)
        return
    _schedule_recompile(session, event)
    _schedule_index(session, event)


# --- the consumer ----------------------------------------------------------
def process_pending(
    session: Session, *, batch: Optional[int] = None,
    max_attempts: Optional[int] = None,
) -> dict:
    """Process one batch of PENDING events. Returns a small summary dict.

    Commits at the end. Safe to call repeatedly (idempotent)."""
    batch = batch or settings.brain_worker_batch
    max_attempts = max_attempts or settings.brain_event_max_attempts

    events = list(
        session.exec(
            select(BrainEvent)
            .where(BrainEvent.status == BrainEventStatus.PENDING)
            .order_by(BrainEvent.sequence)
            .limit(batch)
        ).all()
    )
    processed = failed = 0
    for event in events:
        savepoint = session.begin_nested()
        try:
            _handle_event(session, event)
            savepoint.commit()
        except Exception as exc:  # noqa: BLE001 — record + isolate, never crash the batch
            savepoint.rollback()
            event.attempts = (event.attempts or 0) + 1
            event.error = str(exc)[:500]
            if event.attempts >= max_attempts:
                event.status = BrainEventStatus.FAILED
                failed += 1
            session.add(event)
            session.flush()
            continue
        # success path (outside the savepoint)
        event.status = BrainEventStatus.PROCESSED
        event.processed_at = utcnow()
        event.attempts = (event.attempts or 0) + 1
        event.error = None
        session.add(event)
        session.flush()
        processed += 1

    session.commit()
    return {"selected": len(events), "processed": processed, "failed": failed}


def drain(
    session: Session, *, max_batches: int = 1000,
    batch: Optional[int] = None, max_attempts: Optional[int] = None,
) -> dict:
    """Process pending events until the backlog is drained (deterministic
    one-shot). Stops when a pass makes no progress."""
    total_processed = total_failed = passes = 0
    for _ in range(max_batches):
        result = process_pending(session, batch=batch, max_attempts=max_attempts)
        passes += 1
        total_processed += result["processed"]
        total_failed += result["failed"]
        # No progress (nothing processed and nothing newly failed) -> done.
        if result["processed"] == 0 and result["failed"] == 0:
            break
    return {"passes": passes, "processed": total_processed, "failed": total_failed}


def replay_failed(
    session: Session, *, event_ids: Optional[list[str]] = None,
) -> int:
    """Manual replay: move FAILED events back to PENDING (attempts reset)."""
    stmt = select(BrainEvent).where(BrainEvent.status == BrainEventStatus.FAILED)
    if event_ids:
        stmt = stmt.where(BrainEvent.id.in_(event_ids))
    requeued = 0
    for event in session.exec(stmt).all():
        event.status = BrainEventStatus.PENDING
        event.attempts = 0
        event.error = None
        session.add(event)
        requeued += 1
    session.commit()
    return requeued


def reconcile(session: Session) -> dict:
    """Detect and fix missed changes.

    Re-queues dead-letters, then re-flags any scope whose compiled state is
    behind the latest event affecting it (independent of the incremental
    consumer, so it catches anything a crash or skip missed)."""
    requeued = replay_failed(session)

    head = int(session.exec(select(func.max(BrainEvent.sequence))).one() or 0)
    marked: list[str] = []

    studio = get_studio_state(session)
    studio_cursor = studio.source_event_cursor if studio else 0
    if head > studio_cursor and not (studio and studio.stale):
        _mark_studio_stale(session)
        marked.append("studio")

    # per work
    rows = session.exec(
        select(BrainEvent.work_id, func.max(BrainEvent.sequence))
        .where(BrainEvent.work_id.is_not(None))
        .group_by(BrainEvent.work_id)
    ).all()
    for work_id, max_seq in rows:
        state = get_project_state(session, work_id=work_id)
        cursor = state.source_event_cursor if state else 0
        if int(max_seq or 0) > cursor and not (state and state.stale):
            _mark_project_stale(session, work_id=work_id)
            marked.append(f"work:{work_id}")

    # per story world
    rows = session.exec(
        select(BrainEvent.story_world_id, func.max(BrainEvent.sequence))
        .where(BrainEvent.story_world_id.is_not(None))
        .group_by(BrainEvent.story_world_id)
    ).all()
    for world_id, max_seq in rows:
        state = get_project_state(session, story_world_id=world_id)
        cursor = state.source_event_cursor if state else 0
        if int(max_seq or 0) > cursor and not (state and state.stale):
            _mark_project_stale(session, story_world_id=world_id)
            marked.append(f"story_world:{world_id}")

    session.commit()
    return {"requeued": requeued, "marked": marked, "marked_count": len(marked)}


# --- monitoring ------------------------------------------------------------
def outbox_status(session: Session) -> dict:
    """Snapshot for monitoring: unprocessed, failed, cursor, compiler lag."""
    head = int(session.exec(select(func.max(BrainEvent.sequence))).one() or 0)
    cursor = int(
        session.exec(
            select(func.max(BrainEvent.sequence)).where(
                BrainEvent.status == BrainEventStatus.PROCESSED
            )
        ).one()
        or 0
    )
    pending = int(
        session.exec(
            select(func.count(BrainEvent.id)).where(
                BrainEvent.status == BrainEventStatus.PENDING
            )
        ).one()
        or 0
    )
    failed = int(
        session.exec(
            select(func.count(BrainEvent.id)).where(
                BrainEvent.status == BrainEventStatus.FAILED
            )
        ).one()
        or 0
    )
    stale_projects = int(
        session.exec(
            select(func.count(ProjectBrainState.id)).where(
                ProjectBrainState.stale.is_(True)
            )
        ).one()
        or 0
    )
    studio = get_studio_state(session)
    return {
        "head_sequence": head,
        "cursor": cursor,
        "unprocessed": pending,
        "failed": failed,
        "compiler_lag": head - cursor,
        "studio_stale": (studio.stale if studio else None),
        "studio_version": (studio.version if studio else None),
        "stale_projects": stale_projects,
    }
