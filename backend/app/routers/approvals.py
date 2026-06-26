"""Human approval gates for deliverables and production tasks.

Safety: a decision is recorded only by the assigned human ``approver`` (or an
admin). The system never auto-approves, and approving a task does **not**
auto-complete it — completion remains a separate, deliberate human transition.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.auth import AUTHED, get_current_user
from app.db import get_session
from app.models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    ProductionActivityType,
    ProductionItem,
    User,
    UserRole,
)
from app.models.base import utcnow
from app.schemas.approval_request import (
    ApprovalCreate,
    ApprovalDecisionRequest,
    ApprovalRead,
)
from app.services import brain, production
from app.utils import Page, PageParams, ensure_exists, get_or_404, page_params, paginate

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _approval_scope(
    session: Session, approval: ApprovalRequest
) -> tuple[Optional[str], Optional[str]]:
    """Resolve ``(work_id, story_world_id)`` from the approval's task, if any."""
    if approval.task_id is None:
        return (None, None)
    item = session.get(ProductionItem, approval.task_id)
    if item is None:
        return (None, None)
    return (item.work_id, item.story_world_id)

_DECISION_STATUS = {
    ApprovalDecision.APPROVED: ApprovalStatus.APPROVED,
    ApprovalDecision.REJECTED: ApprovalStatus.REJECTED,
    ApprovalDecision.CHANGES_REQUESTED: ApprovalStatus.CHANGES_REQUESTED,
}


@router.get("", response_model=Page[ApprovalRead])
def list_approvals(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    approver_id: Optional[str] = Query(default=None),
    requested_by_id: Optional[str] = Query(default=None),
    task_id: Optional[str] = Query(default=None),
    target_type: Optional[str] = Query(default=None),
    status_: Optional[ApprovalStatus] = Query(default=None, alias="status"),
) -> Page[ApprovalRead]:
    stmt = select(ApprovalRequest)
    if approver_id is not None:
        stmt = stmt.where(ApprovalRequest.approver_id == approver_id)
    if requested_by_id is not None:
        stmt = stmt.where(ApprovalRequest.requested_by_id == requested_by_id)
    if task_id is not None:
        stmt = stmt.where(ApprovalRequest.task_id == task_id)
    if target_type is not None:
        stmt = stmt.where(ApprovalRequest.target_type == target_type)
    if status_ is not None:
        stmt = stmt.where(ApprovalRequest.status == status_)
    stmt = stmt.order_by(ApprovalRequest.created_at.desc())
    items, total = paginate(session, stmt, params)
    return Page[ApprovalRead](
        items=[ApprovalRead.model_validate(a) for a in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.get("/{approval_id}", response_model=ApprovalRead)
def get_approval(
    approval_id: str, session: Session = Depends(get_session)
) -> ApprovalRequest:
    return get_or_404(session, ApprovalRequest, approval_id, name="ApprovalRequest")


@router.post(
    "", response_model=ApprovalRead,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def create_approval(
    payload: ApprovalCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ApprovalRead:
    ensure_exists(session, User, payload.approver_id, name="User")
    if payload.task_id is not None:
        ensure_exists(session, ProductionItem, payload.task_id, name="ProductionItem")
    approval = ApprovalRequest(
        requested_by_id=user.id,
        approver_id=payload.approver_id,
        task_id=payload.task_id,
        target_type=payload.target_type
        or ("production_item" if payload.task_id else None),
        target_id=payload.target_id or payload.task_id,
        title=payload.title,
        description=payload.description,
    )
    session.add(approval)
    if payload.task_id is not None:
        production.record_activity(
            session,
            task_id=payload.task_id,
            type=ProductionActivityType.APPROVAL_REQUESTED,
            actor_id=user.id,
            summary=f"approval requested from {payload.approver_id}",
        )
    work_id, story_world_id = _approval_scope(session, approval)
    brain.emit(
        session, event_type=brain.BrainEventType.APPROVAL_REQUESTED,
        aggregate_type="approval", aggregate_id=approval.id,
        work_id=work_id, story_world_id=story_world_id, actor_id=user.id,
        changes={"target_type": approval.target_type, "target_id": approval.target_id},
    )
    session.commit()
    session.refresh(approval)
    return ApprovalRead.model_validate(approval)


@router.post("/{approval_id}/decide", response_model=ApprovalRead, dependencies=AUTHED)
def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ApprovalRead:
    """Record a human decision. Only the assigned approver (or an admin) may
    decide; the request must still be pending. Approving does NOT complete the
    underlying task — that stays a separate human action."""
    approval = get_or_404(session, ApprovalRequest, approval_id, name="ApprovalRequest")

    is_approver = approval.approver_id is not None and approval.approver_id == user.id
    if not is_approver and user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned approver (or an admin) can decide this request",
        )
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This approval has already been decided",
        )

    approval.decision = payload.decision
    approval.status = _DECISION_STATUS[payload.decision]
    approval.comments = payload.comments
    approval.decided_at = utcnow()
    session.add(approval)

    if approval.task_id is not None:
        production.record_activity(
            session,
            task_id=approval.task_id,
            type=ProductionActivityType.APPROVAL_DECIDED,
            actor_id=user.id,
            summary=f"approval {payload.decision.value}",
            detail=payload.comments,
        )
    work_id, story_world_id = _approval_scope(session, approval)
    brain.emit(
        session, event_type=brain.BrainEventType.APPROVAL_DECIDED,
        aggregate_type="approval", aggregate_id=approval.id,
        work_id=work_id, story_world_id=story_world_id, actor_id=user.id,
        changes={"decision": payload.decision.value, "status": approval.status.value},
    )
    session.commit()
    session.refresh(approval)
    return ApprovalRead.model_validate(approval)


@router.post("/{approval_id}/cancel", response_model=ApprovalRead, dependencies=AUTHED)
def cancel_approval(
    approval_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ApprovalRead:
    approval = get_or_404(session, ApprovalRequest, approval_id, name="ApprovalRequest")
    is_requester = (
        approval.requested_by_id is not None and approval.requested_by_id == user.id
    )
    if not is_requester and user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the requester (or an admin) can cancel this request",
        )
    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a pending approval can be cancelled",
        )
    approval.status = ApprovalStatus.CANCELLED
    session.add(approval)
    session.commit()
    session.refresh(approval)
    return ApprovalRead.model_validate(approval)
