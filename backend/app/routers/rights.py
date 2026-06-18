from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED
from app.db import get_session
from app.models import Rights, Work
from app.schemas import RightsCreate, RightsRead, RightsUpdate
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(prefix="/rights", tags=["rights"])


@router.get("", response_model=Page[RightsRead])
def list_rights(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    work_id: Optional[str] = Query(default=None, description="Filter by work id"),
    territory: Optional[str] = Query(
        default=None, description="Filter by territory (exact match)"
    ),
    language: Optional[str] = Query(
        default=None, description="Filter by language (exact match)"
    ),
) -> Page[RightsRead]:
    stmt = select(Rights)
    if work_id is not None:
        stmt = stmt.where(Rights.work_id == work_id)
    if territory is not None:
        stmt = stmt.where(Rights.territory == territory)
    if language is not None:
        stmt = stmt.where(Rights.language == language)
    stmt = stmt.order_by(Rights.created_at.desc())

    items, total = paginate(session, stmt, params)
    return Page[RightsRead](
        items=[RightsRead.model_validate(i) for i in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.get("/{rights_id}", response_model=RightsRead)
def get_rights(rights_id: str, session: Session = Depends(get_session)) -> Rights:
    return get_or_404(session, Rights, rights_id, name="Rights")


@router.post(
    "",
    response_model=RightsRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def create_rights(
    payload: RightsCreate, session: Session = Depends(get_session)
) -> Rights:
    ensure_exists(session, Work, payload.work_id, name="Work")
    rights = Rights(**payload.model_dump())
    session.add(rights)
    session.commit()
    session.refresh(rights)
    return rights


@router.patch("/{rights_id}", response_model=RightsRead, dependencies=AUTHED)
def update_rights(
    rights_id: str,
    payload: RightsUpdate,
    session: Session = Depends(get_session),
) -> Rights:
    rights = get_or_404(session, Rights, rights_id, name="Rights")
    apply_patch(rights, payload)
    session.add(rights)
    session.commit()
    session.refresh(rights)
    return rights


@router.delete(
    "/{rights_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=ADMIN_ONLY,
)
def delete_rights(rights_id: str, session: Session = Depends(get_session)):
    rights = get_or_404(session, Rights, rights_id, name="Rights")
    session.delete(rights)
    session.commit()
