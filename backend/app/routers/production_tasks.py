"""The general production task surface (``/production-tasks``).

A richer view over the same ``production_items`` table the legacy
``/production-items`` endpoints use — adding hierarchy, dependencies,
milestones, approvals, validated transitions and an activity log. The legacy
endpoints are untouched for backward compatibility.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, func, select

from app.auth import ADMIN_ONLY, AUTHED, get_current_user
from app.db import get_session
from app.models import (
    ApprovalRequest,
    Manuscript,
    ProductionActivity,
    ProductionActivityType,
    ProductionDependency,
    ProductionItem,
    ProductionItemStatus,
    ProductionMilestone,
    ProductionPriority,
    ProductionTaskType,
    ProductionTrack,
    StoryWorld,
    StudioDivision,
    User,
    Work,
)
from app.schemas.approval_request import ApprovalCreate, ApprovalRead
from app.schemas.production_task import (
    DependencyCreate,
    DependencyRead,
    ProductionActivityRead,
    ProductionTaskCreate,
    ProductionTaskDetail,
    ProductionTaskRead,
    ProductionTaskUpdate,
    StatusTransitionRequest,
)
from app.services import production
from app.utils import (
    Page,
    PageParams,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(prefix="/production-tasks", tags=["production_tasks"])

# Statuses that mean the task is no longer open.
_CLOSED = (
    ProductionItemStatus.DONE,
    ProductionItemStatus.APPROVED,
    ProductionItemStatus.CANCELLED,
)


class TaskSortBy(str, Enum):
    CREATED_AT = "created_at"
    DUE_DATE = "due_date"
    PRIORITY = "priority"
    STATUS = "status"
    TITLE = "title"


_SORT_COLUMNS = {
    TaskSortBy.CREATED_AT: ProductionItem.created_at,
    TaskSortBy.DUE_DATE: ProductionItem.due_date,
    TaskSortBy.PRIORITY: ProductionItem.priority,
    TaskSortBy.STATUS: ProductionItem.status,
    TaskSortBy.TITLE: ProductionItem.title,
}


def _read(item: ProductionItem) -> ProductionTaskRead:
    return ProductionTaskRead.model_validate(item)


def _detail(session: Session, item: ProductionItem) -> ProductionTaskDetail:
    detail = ProductionTaskDetail.model_validate(item)
    unmet = production.unmet_dependencies(session, item.id)
    detail.unmet_dependency_ids = [t.id for t in unmet]
    detail.blocked_by_dependencies = bool(unmet)
    detail.is_blocked = item.status == ProductionItemStatus.BLOCKED or bool(unmet)
    detail.depends_on_ids = list(
        session.exec(
            select(ProductionDependency.depends_on_id).where(
                ProductionDependency.task_id == item.id
            )
        ).all()
    )
    detail.dependent_ids = list(
        session.exec(
            select(ProductionDependency.task_id).where(
                ProductionDependency.depends_on_id == item.id
            )
        ).all()
    )
    detail.subtask_count = session.exec(
        select(func.count())
        .select_from(ProductionItem)
        .where(ProductionItem.parent_id == item.id)
    ).one()
    detail.allowed_transitions = sorted(
        production.ALLOWED_TRANSITIONS.get(item.status, frozenset()),
        key=lambda s: s.value,
    )
    return detail


def _validate_refs(session: Session, payload, *, exclude_task: Optional[str] = None) -> None:
    data = payload.model_dump(exclude_unset=True)
    if data.get("work_id"):
        ensure_exists(session, Work, data["work_id"], name="Work")
    if data.get("manuscript_id"):
        ensure_exists(session, Manuscript, data["manuscript_id"], name="Manuscript")
    if data.get("story_world_id"):
        ensure_exists(session, StoryWorld, data["story_world_id"], name="StoryWorld")
    if data.get("assignee_id"):
        ensure_exists(session, User, data["assignee_id"], name="User")
    if data.get("reviewer_id"):
        ensure_exists(session, User, data["reviewer_id"], name="User")
    if data.get("milestone_id"):
        ensure_exists(
            session, ProductionMilestone, data["milestone_id"], name="ProductionMilestone"
        )
    if data.get("parent_id"):
        if data["parent_id"] == exclude_task:
            raise HTTPException(status_code=400, detail="A task cannot be its own parent.")
        ensure_exists(session, ProductionItem, data["parent_id"], name="ProductionItem")


# --- Collection-level query endpoints (declared before /{task_id}) ----------


@router.get("/my-assignments", response_model=Page[ProductionTaskRead])
def my_assignments(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    user: User = Depends(get_current_user),
    open_only: bool = Query(default=True),
) -> Page[ProductionTaskRead]:
    stmt = select(ProductionItem).where(ProductionItem.assignee_id == user.id)
    if open_only:
        stmt = stmt.where(ProductionItem.status.not_in(_CLOSED))
    stmt = stmt.order_by(ProductionItem.due_date.is_(None), ProductionItem.due_date.asc())
    items, total = paginate(session, stmt, params)
    return Page[ProductionTaskRead](
        items=[_read(i) for i in items], total=total, skip=params.skip, limit=params.limit
    )


@router.get("/overdue", response_model=Page[ProductionTaskRead], dependencies=AUTHED)
def overdue_tasks(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    assignee_id: Optional[str] = Query(default=None),
) -> Page[ProductionTaskRead]:
    today = date.today()
    stmt = select(ProductionItem).where(
        ProductionItem.due_date.is_not(None),
        ProductionItem.due_date < today,
        ProductionItem.status.not_in(_CLOSED),
    )
    if assignee_id is not None:
        stmt = stmt.where(ProductionItem.assignee_id == assignee_id)
    stmt = stmt.order_by(ProductionItem.due_date.asc())
    items, total = paginate(session, stmt, params)
    return Page[ProductionTaskRead](
        items=[_read(i) for i in items], total=total, skip=params.skip, limit=params.limit
    )


@router.get("/blocked", response_model=list[ProductionTaskDetail], dependencies=AUTHED)
def blocked_tasks(
    session: Session = Depends(get_session),
    work_id: Optional[str] = Query(default=None),
) -> list[ProductionTaskDetail]:
    """Tasks that are explicitly BLOCKED or have unmet finish-to-start deps."""
    stmt = select(ProductionItem).where(ProductionItem.status.not_in(_CLOSED))
    if work_id is not None:
        stmt = stmt.where(ProductionItem.work_id == work_id)
    candidates = session.exec(stmt).all()
    out = [_detail(session, t) for t in candidates]
    return [d for d in out if d.is_blocked]


@router.get("/awaiting-approval", response_model=list[ApprovalRead])
def awaiting_approval(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ApprovalRead]:
    """Approval requests assigned to the current user and still pending."""
    from app.models.enums import ApprovalStatus

    stmt = (
        select(ApprovalRequest)
        .where(
            ApprovalRequest.approver_id == user.id,
            ApprovalRequest.status == ApprovalStatus.PENDING,
        )
        .order_by(ApprovalRequest.created_at.asc())
    )
    return [ApprovalRead.model_validate(a) for a in session.exec(stmt).all()]


# --- CRUD -------------------------------------------------------------------


@router.get("", response_model=Page[ProductionTaskRead])
def list_tasks(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    work_id: Optional[str] = Query(default=None),
    manuscript_id: Optional[str] = Query(default=None),
    story_world_id: Optional[str] = Query(default=None),
    milestone_id: Optional[str] = Query(default=None),
    parent_id: Optional[str] = Query(default=None),
    assignee_id: Optional[str] = Query(default=None),
    reviewer_id: Optional[str] = Query(default=None),
    division: Optional[StudioDivision] = Query(default=None),
    track: Optional[ProductionTrack] = Query(default=None),
    task_type: Optional[ProductionTaskType] = Query(default=None),
    priority: Optional[ProductionPriority] = Query(default=None),
    status_: Optional[ProductionItemStatus] = Query(default=None, alias="status"),
    top_level: Optional[bool] = Query(default=None, description="Only tasks with no parent"),
    q: Optional[str] = Query(default=None, description="Search title"),
    sort_by: TaskSortBy = Query(default=TaskSortBy.CREATED_AT),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
) -> Page[ProductionTaskRead]:
    stmt = select(ProductionItem)
    eq = {
        ProductionItem.work_id: work_id,
        ProductionItem.manuscript_id: manuscript_id,
        ProductionItem.story_world_id: story_world_id,
        ProductionItem.milestone_id: milestone_id,
        ProductionItem.parent_id: parent_id,
        ProductionItem.assignee_id: assignee_id,
        ProductionItem.reviewer_id: reviewer_id,
        ProductionItem.division: division,
        ProductionItem.track: track,
        ProductionItem.task_type: task_type,
        ProductionItem.priority: priority,
        ProductionItem.status: status_,
    }
    for column, value in eq.items():
        if value is not None:
            stmt = stmt.where(column == value)
    if top_level:
        stmt = stmt.where(ProductionItem.parent_id.is_(None))
    if q:
        stmt = stmt.where(ProductionItem.title.ilike(f"%{q}%"))

    column = _SORT_COLUMNS[sort_by]
    stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())
    items, total = paginate(session, stmt, params)
    return Page[ProductionTaskRead](
        items=[_read(i) for i in items], total=total, skip=params.skip, limit=params.limit
    )


@router.post(
    "", response_model=ProductionTaskDetail,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def create_task(
    payload: ProductionTaskCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProductionTaskDetail:
    _validate_refs(session, payload)
    item = ProductionItem(**payload.model_dump(), creator_id=user.id)
    session.add(item)
    session.flush()
    production.record_activity(
        session,
        task_id=item.id,
        type=ProductionActivityType.CREATED,
        actor_id=user.id,
        summary=item.title,
    )
    if item.assignee_id:
        production.record_activity(
            session,
            task_id=item.id,
            type=ProductionActivityType.ASSIGNED,
            actor_id=user.id,
            field="assignee_id",
        )
    session.commit()
    session.refresh(item)
    return _detail(session, item)


@router.get("/{task_id}", response_model=ProductionTaskDetail)
def get_task(task_id: str, session: Session = Depends(get_session)) -> ProductionTaskDetail:
    item = get_or_404(session, ProductionItem, task_id, name="ProductionItem")
    return _detail(session, item)


@router.patch("/{task_id}", response_model=ProductionTaskDetail, dependencies=AUTHED)
def update_task(
    task_id: str,
    payload: ProductionTaskUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProductionTaskDetail:
    item = get_or_404(session, ProductionItem, task_id, name="ProductionItem")
    _validate_refs(session, payload, exclude_task=task_id)

    data = payload.model_dump(exclude_unset=True)
    new_status = data.pop("status", None)
    prev_assignee = item.assignee_id

    # Status changes go through the validated transition engine first.
    if new_status is not None and new_status != item.status:
        production.apply_transition(
            session, item, new_status, actor_id=user.id
        )

    for key, value in data.items():
        setattr(item, key, value)

    if "assignee_id" in data and data["assignee_id"] != prev_assignee:
        production.record_activity(
            session,
            task_id=item.id,
            type=ProductionActivityType.REASSIGNED if prev_assignee
            else ProductionActivityType.ASSIGNED,
            actor_id=user.id,
            field="assignee_id",
        )

    session.add(item)
    session.commit()
    session.refresh(item)
    return _detail(session, item)


@router.delete(
    "/{task_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY
)
def delete_task(task_id: str, session: Session = Depends(get_session)):
    item = get_or_404(session, ProductionItem, task_id, name="ProductionItem")
    # Clean up dependency edges referencing this task.
    for dep in session.exec(
        select(ProductionDependency).where(
            (ProductionDependency.task_id == task_id)
            | (ProductionDependency.depends_on_id == task_id)
        )
    ).all():
        session.delete(dep)
    session.delete(item)
    session.commit()


# --- Transitions ------------------------------------------------------------


@router.post(
    "/{task_id}/transition", response_model=ProductionTaskDetail, dependencies=AUTHED
)
def transition_task(
    task_id: str,
    payload: StatusTransitionRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProductionTaskDetail:
    item = get_or_404(session, ProductionItem, task_id, name="ProductionItem")
    production.apply_transition(
        session, item, payload.to_status, actor_id=user.id, note=payload.note
    )
    session.commit()
    session.refresh(item)
    return _detail(session, item)


# --- Subtasks ---------------------------------------------------------------


@router.get("/{task_id}/subtasks", response_model=list[ProductionTaskRead])
def list_subtasks(
    task_id: str, session: Session = Depends(get_session)
) -> list[ProductionTaskRead]:
    get_or_404(session, ProductionItem, task_id, name="ProductionItem")
    stmt = (
        select(ProductionItem)
        .where(ProductionItem.parent_id == task_id)
        .order_by(ProductionItem.created_at.asc())
    )
    return [_read(i) for i in session.exec(stmt).all()]


# --- Dependencies -----------------------------------------------------------


def _dependency_read(session: Session, dep: ProductionDependency) -> DependencyRead:
    read = DependencyRead.model_validate(dep)
    pred = session.get(ProductionItem, dep.depends_on_id)
    if pred is not None:
        read.depends_on_title = pred.title
        read.depends_on_status = pred.status
        read.satisfied = pred.status in production.TERMINAL_DONE
    return read


@router.get("/{task_id}/dependencies", response_model=list[DependencyRead])
def list_dependencies(
    task_id: str, session: Session = Depends(get_session)
) -> list[DependencyRead]:
    get_or_404(session, ProductionItem, task_id, name="ProductionItem")
    stmt = (
        select(ProductionDependency)
        .where(ProductionDependency.task_id == task_id)
        .order_by(ProductionDependency.created_at.asc())
    )
    return [_dependency_read(session, d) for d in session.exec(stmt).all()]


@router.post(
    "/{task_id}/dependencies",
    response_model=DependencyRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def add_dependency(
    task_id: str,
    payload: DependencyCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DependencyRead:
    get_or_404(session, ProductionItem, task_id, name="ProductionItem")
    ensure_exists(session, ProductionItem, payload.depends_on_id, name="ProductionItem")
    if payload.depends_on_id == task_id:
        raise HTTPException(status_code=400, detail="A task cannot depend on itself.")
    if production.would_create_cycle(session, task_id, payload.depends_on_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That dependency would create a cycle.",
        )
    existing = session.exec(
        select(ProductionDependency).where(
            ProductionDependency.task_id == task_id,
            ProductionDependency.depends_on_id == payload.depends_on_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Dependency already exists.")

    dep = ProductionDependency(
        task_id=task_id,
        depends_on_id=payload.depends_on_id,
        type=payload.type,
        note=payload.note,
    )
    session.add(dep)
    production.record_activity(
        session,
        task_id=task_id,
        type=ProductionActivityType.DEPENDENCY_ADDED,
        actor_id=user.id,
        summary=f"depends on {payload.depends_on_id}",
    )
    session.commit()
    session.refresh(dep)
    return _dependency_read(session, dep)


@router.delete(
    "/{task_id}/dependencies/{dependency_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=AUTHED,
)
def remove_dependency(
    task_id: str,
    dependency_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    dep = get_or_404(
        session, ProductionDependency, dependency_id, name="ProductionDependency"
    )
    if dep.task_id != task_id:
        raise HTTPException(status_code=404, detail="Dependency not found on this task")
    session.delete(dep)
    production.record_activity(
        session,
        task_id=task_id,
        type=ProductionActivityType.DEPENDENCY_REMOVED,
        actor_id=user.id,
        summary=f"removed dependency on {dep.depends_on_id}",
    )
    session.commit()


# --- Activity ---------------------------------------------------------------


@router.get("/{task_id}/activity", response_model=list[ProductionActivityRead])
def list_activity(
    task_id: str, session: Session = Depends(get_session)
) -> list[ProductionActivityRead]:
    get_or_404(session, ProductionItem, task_id, name="ProductionItem")
    stmt = (
        select(ProductionActivity)
        .where(ProductionActivity.task_id == task_id)
        .order_by(ProductionActivity.created_at.asc())
    )
    return [ProductionActivityRead.model_validate(a) for a in session.exec(stmt).all()]


# --- Approvals (task-scoped) ------------------------------------------------


@router.get("/{task_id}/approvals", response_model=list[ApprovalRead])
def list_task_approvals(
    task_id: str, session: Session = Depends(get_session)
) -> list[ApprovalRead]:
    get_or_404(session, ProductionItem, task_id, name="ProductionItem")
    stmt = (
        select(ApprovalRequest)
        .where(ApprovalRequest.task_id == task_id)
        .order_by(ApprovalRequest.created_at.desc())
    )
    return [ApprovalRead.model_validate(a) for a in session.exec(stmt).all()]


@router.post(
    "/{task_id}/approvals",
    response_model=ApprovalRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def request_task_approval(
    task_id: str,
    payload: ApprovalCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ApprovalRead:
    item = get_or_404(session, ProductionItem, task_id, name="ProductionItem")
    ensure_exists(session, User, payload.approver_id, name="User")
    approval = ApprovalRequest(
        requested_by_id=user.id,
        approver_id=payload.approver_id,
        task_id=item.id,
        target_type="production_item",
        target_id=item.id,
        title=payload.title or item.title,
        description=payload.description,
    )
    session.add(approval)
    production.record_activity(
        session,
        task_id=item.id,
        type=ProductionActivityType.APPROVAL_REQUESTED,
        actor_id=user.id,
        summary=f"approval requested from {payload.approver_id}",
    )
    session.commit()
    session.refresh(approval)
    return ApprovalRead.model_validate(approval)
