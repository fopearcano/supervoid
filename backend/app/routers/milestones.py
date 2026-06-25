from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, func, select

from app.auth import ADMIN_ONLY, AUTHED
from app.db import get_session
from app.models import ProductionItem, ProductionMilestone, StoryWorld, Work
from app.models.enums import MilestoneStatus, StudioDivision
from app.schemas.production_milestone import (
    MilestoneCreate,
    MilestoneRead,
    MilestoneUpdate,
)
from app.schemas.production_task import ProductionTaskRead
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(prefix="/milestones", tags=["milestones"])


def _read(session: Session, milestone: ProductionMilestone) -> MilestoneRead:
    read = MilestoneRead.model_validate(milestone)
    read.task_count = session.exec(
        select(func.count())
        .select_from(ProductionItem)
        .where(ProductionItem.milestone_id == milestone.id)
    ).one()
    return read


@router.get("", response_model=Page[MilestoneRead])
def list_milestones(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    work_id: Optional[str] = Query(default=None),
    story_world_id: Optional[str] = Query(default=None),
    division: Optional[StudioDivision] = Query(default=None),
    status_: Optional[MilestoneStatus] = Query(default=None, alias="status"),
) -> Page[MilestoneRead]:
    stmt = select(ProductionMilestone)
    if work_id is not None:
        stmt = stmt.where(ProductionMilestone.work_id == work_id)
    if story_world_id is not None:
        stmt = stmt.where(ProductionMilestone.story_world_id == story_world_id)
    if division is not None:
        stmt = stmt.where(ProductionMilestone.division == division)
    if status_ is not None:
        stmt = stmt.where(ProductionMilestone.status == status_)
    stmt = stmt.order_by(
        ProductionMilestone.sequence_order.asc(), ProductionMilestone.created_at.asc()
    )
    items, total = paginate(session, stmt, params)
    return Page[MilestoneRead](
        items=[_read(session, m) for m in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.get("/{milestone_id}", response_model=MilestoneRead)
def get_milestone(
    milestone_id: str, session: Session = Depends(get_session)
) -> MilestoneRead:
    milestone = get_or_404(
        session, ProductionMilestone, milestone_id, name="ProductionMilestone"
    )
    return _read(session, milestone)


@router.post(
    "", response_model=MilestoneRead,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def create_milestone(
    payload: MilestoneCreate, session: Session = Depends(get_session)
) -> MilestoneRead:
    if payload.work_id is not None:
        ensure_exists(session, Work, payload.work_id, name="Work")
    if payload.story_world_id is not None:
        ensure_exists(session, StoryWorld, payload.story_world_id, name="StoryWorld")
    milestone = ProductionMilestone(**payload.model_dump())
    session.add(milestone)
    session.commit()
    session.refresh(milestone)
    return _read(session, milestone)


@router.patch("/{milestone_id}", response_model=MilestoneRead, dependencies=AUTHED)
def update_milestone(
    milestone_id: str,
    payload: MilestoneUpdate,
    session: Session = Depends(get_session),
) -> MilestoneRead:
    milestone = get_or_404(
        session, ProductionMilestone, milestone_id, name="ProductionMilestone"
    )
    apply_patch(milestone, payload)
    session.add(milestone)
    session.commit()
    session.refresh(milestone)
    return _read(session, milestone)


@router.delete(
    "/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY
)
def delete_milestone(milestone_id: str, session: Session = Depends(get_session)):
    milestone = get_or_404(
        session, ProductionMilestone, milestone_id, name="ProductionMilestone"
    )
    # Detach tasks from the milestone rather than deleting them.
    for task in session.exec(
        select(ProductionItem).where(ProductionItem.milestone_id == milestone_id)
    ).all():
        task.milestone_id = None
        session.add(task)
    session.delete(milestone)
    session.commit()


@router.get("/{milestone_id}/tasks", response_model=list[ProductionTaskRead])
def milestone_tasks(
    milestone_id: str, session: Session = Depends(get_session)
) -> list[ProductionTaskRead]:
    get_or_404(session, ProductionMilestone, milestone_id, name="ProductionMilestone")
    stmt = (
        select(ProductionItem)
        .where(ProductionItem.milestone_id == milestone_id)
        .order_by(ProductionItem.due_date.is_(None), ProductionItem.due_date.asc())
    )
    return [ProductionTaskRead.model_validate(t) for t in session.exec(stmt).all()]
