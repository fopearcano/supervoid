"""Production task workflow: validated state transitions, dependency checks,
blocked-state detection and the append-only activity log.

This is the engine behind ``/production-tasks``. Routers call these helpers; the
rules (which transitions are legal, when a task is blocked, what gets logged)
live here so they are consistent and testable.

Safety invariant — **AI must never auto-approve a deliverable or complete a
task**. Completion (``DONE``) and approval (``APPROVED``) are *human-gated*:
they are only reachable through the authenticated HTTP endpoints, never invoked
by AI service code. ``HUMAN_ONLY_STATUSES`` documents and enforces this.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import (
    DependencyType,
    ProductionActivity,
    ProductionActivityType,
    ProductionDependency,
    ProductionItem,
    ProductionItemStatus,
)

S = ProductionItemStatus

# Statuses a task may move to from each status. Same-status is always allowed
# (a no-op). Terminal states can be reopened to IN_PROGRESS / TODO.
ALLOWED_TRANSITIONS: dict[ProductionItemStatus, frozenset[ProductionItemStatus]] = {
    S.PENDING: frozenset({S.TODO, S.IN_PROGRESS, S.BLOCKED, S.CANCELLED}),
    S.TODO: frozenset({S.IN_PROGRESS, S.BLOCKED, S.CANCELLED}),
    S.IN_PROGRESS: frozenset(
        {S.IN_REVIEW, S.BLOCKED, S.DONE, S.TODO, S.CANCELLED}
    ),
    S.BLOCKED: frozenset({S.IN_PROGRESS, S.TODO, S.CANCELLED}),
    S.IN_REVIEW: frozenset(
        {S.CHANGES_REQUESTED, S.APPROVED, S.IN_PROGRESS, S.BLOCKED, S.CANCELLED}
    ),
    S.CHANGES_REQUESTED: frozenset({S.IN_PROGRESS, S.TODO, S.CANCELLED}),
    S.APPROVED: frozenset({S.DONE, S.IN_PROGRESS, S.CANCELLED}),
    S.DONE: frozenset({S.IN_PROGRESS}),  # reopen
    S.CANCELLED: frozenset({S.TODO, S.IN_PROGRESS}),  # reopen
}

# Reaching these requires a deliberate human action via the API. AI/automation
# code paths must not set them.
HUMAN_ONLY_STATUSES: frozenset[ProductionItemStatus] = frozenset({S.APPROVED, S.DONE})

# Statuses that count as "the task is finished" for dependency satisfaction.
TERMINAL_DONE: frozenset[ProductionItemStatus] = frozenset({S.DONE, S.APPROVED})

# A move into one of these is only allowed once finish-to-start predecessors
# are complete.
REQUIRES_DEPENDENCIES_MET: frozenset[ProductionItemStatus] = frozenset(
    {S.IN_REVIEW, S.APPROVED, S.DONE}
)


def can_transition(current: ProductionItemStatus, target: ProductionItemStatus) -> bool:
    if current == target:
        return True
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def unmet_dependencies(
    session: Session, task_id: str
) -> list[ProductionItem]:
    """Finish-to-start predecessors of ``task_id`` that are not yet complete."""
    deps = session.exec(
        select(ProductionDependency).where(
            ProductionDependency.task_id == task_id,
            ProductionDependency.type == DependencyType.FINISH_TO_START,
        )
    ).all()
    unmet: list[ProductionItem] = []
    for dep in deps:
        pred = session.get(ProductionItem, dep.depends_on_id)
        if pred is not None and pred.status not in TERMINAL_DONE:
            unmet.append(pred)
    return unmet


def is_blocked(session: Session, task: ProductionItem) -> bool:
    """A task is effectively blocked if it is explicitly BLOCKED or has unmet
    finish-to-start dependencies."""
    if task.status == S.BLOCKED:
        return True
    return bool(unmet_dependencies(session, task.id))


def record_activity(
    session: Session,
    *,
    task_id: Optional[str],
    type: ProductionActivityType,
    actor_id: Optional[str] = None,
    field: Optional[str] = None,
    from_status: Optional[ProductionItemStatus] = None,
    to_status: Optional[ProductionItemStatus] = None,
    summary: Optional[str] = None,
    detail: Optional[str] = None,
) -> ProductionActivity:
    """Append an activity record (caller commits)."""
    activity = ProductionActivity(
        task_id=task_id,
        actor_id=actor_id,
        type=type,
        field=field,
        from_status=from_status,
        to_status=to_status,
        summary=summary,
        detail=detail,
    )
    session.add(activity)
    return activity


def apply_transition(
    session: Session,
    task: ProductionItem,
    target: ProductionItemStatus,
    *,
    actor_id: Optional[str] = None,
    note: Optional[str] = None,
) -> ProductionItem:
    """Validate and apply a status change, logging the activity.

    Raises 422 for an illegal transition and 409 when finish-to-start
    dependencies are unmet for a completion/review move. Sets / clears
    ``completed_date`` and records the activity. The caller commits.
    """
    current = task.status
    if current == target:
        return task

    if not can_transition(current, target):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Illegal transition: {current.value} → {target.value}",
        )

    if target in REQUIRES_DEPENDENCIES_MET:
        unmet = unmet_dependencies(session, task.id)
        if unmet:
            titles = ", ".join(t.title or t.id for t in unmet)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Unmet dependencies block this transition: {titles}",
            )

    task.status = target
    if target in TERMINAL_DONE and task.completed_date is None:
        task.completed_date = date.today()
    if target not in TERMINAL_DONE:
        task.completed_date = None
    if target != S.BLOCKED:
        task.blocked_reason = None

    activity_type = ProductionActivityType.STATUS_CHANGED
    if target == S.DONE:
        activity_type = ProductionActivityType.COMPLETED
    elif target == S.BLOCKED:
        activity_type = ProductionActivityType.BLOCKED
    elif current == S.BLOCKED:
        activity_type = ProductionActivityType.UNBLOCKED

    session.add(task)
    record_activity(
        session,
        task_id=task.id,
        type=activity_type,
        actor_id=actor_id,
        field="status",
        from_status=current,
        to_status=target,
        summary=note or f"{current.value} → {target.value}",
    )
    return task


def would_create_cycle(
    session: Session, task_id: str, depends_on_id: str
) -> bool:
    """True if making ``task_id`` depend on ``depends_on_id`` would create a
    cycle (i.e. ``depends_on_id`` already depends, transitively, on ``task_id``)."""
    if task_id == depends_on_id:
        return True
    # Walk the dependency graph starting from depends_on_id; if we reach task_id
    # we'd close a loop.
    seen: set[str] = set()
    frontier = [depends_on_id]
    while frontier:
        current = frontier.pop()
        if current == task_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        preds = session.exec(
            select(ProductionDependency.depends_on_id).where(
                ProductionDependency.task_id == current
            )
        ).all()
        frontier.extend(preds)
    return False
