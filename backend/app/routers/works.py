from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED
from app.db import get_session
from app.models import Author, Work
from app.models.enums import WorkStatus, WorkType
from app.schemas import WorkCreate, WorkRead, WorkUpdate
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(prefix="/works", tags=["works"])


class WorkSortBy(str, Enum):
    TITLE = "title"
    WORK_TYPE = "work_type"
    STATUS = "status"
    GENRE = "genre"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


_WORK_SORT_COLUMNS = {
    WorkSortBy.TITLE: Work.title,
    WorkSortBy.WORK_TYPE: Work.work_type,
    WorkSortBy.STATUS: Work.status,
    WorkSortBy.GENRE: Work.genre,
    WorkSortBy.CREATED_AT: Work.created_at,
    WorkSortBy.UPDATED_AT: Work.updated_at,
}


@router.get("", response_model=Page[WorkRead])
def list_works(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    work_type: Optional[WorkType] = Query(
        default=None, description="Filter by work type (book, graphic_novel, …)"
    ),
    status_: Optional[WorkStatus] = Query(
        default=None, alias="status", description="Filter by work status"
    ),
    genre: Optional[str] = Query(
        default=None, description="Filter by genre (exact match)"
    ),
    author_id: Optional[str] = Query(default=None, description="Filter by author id"),
    sort_by: WorkSortBy = Query(
        default=WorkSortBy.CREATED_AT, description="Field to order results by"
    ),
    sort_dir: Literal["asc", "desc"] = Query(
        default="desc", description="Sort direction"
    ),
) -> Page[WorkRead]:
    stmt = select(Work)
    if work_type is not None:
        stmt = stmt.where(Work.work_type == work_type)
    if status_ is not None:
        stmt = stmt.where(Work.status == status_)
    if genre is not None:
        stmt = stmt.where(Work.genre == genre)
    if author_id is not None:
        stmt = stmt.where(Work.author_id == author_id)

    column = _WORK_SORT_COLUMNS[sort_by]
    stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())

    items, total = paginate(session, stmt, params)
    return Page[WorkRead](
        items=[WorkRead.model_validate(i) for i in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.get("/{work_id}", response_model=WorkRead)
def get_work(work_id: str, session: Session = Depends(get_session)) -> Work:
    return get_or_404(session, Work, work_id, name="Work")


@router.post(
    "",
    response_model=WorkRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def create_work(payload: WorkCreate, session: Session = Depends(get_session)) -> Work:
    ensure_exists(session, Author, payload.author_id, name="Author")
    work = Work(**payload.model_dump())
    session.add(work)
    session.commit()
    session.refresh(work)
    return work


@router.patch("/{work_id}", response_model=WorkRead, dependencies=AUTHED)
def update_work(
    work_id: str,
    payload: WorkUpdate,
    session: Session = Depends(get_session),
) -> Work:
    work = get_or_404(session, Work, work_id, name="Work")
    if payload.author_id is not None:
        ensure_exists(session, Author, payload.author_id, name="Author")
    apply_patch(work, payload)
    session.add(work)
    session.commit()
    session.refresh(work)
    return work


@router.delete(
    "/{work_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=ADMIN_ONLY,
)
def delete_work(work_id: str, session: Session = Depends(get_session)):
    work = get_or_404(session, Work, work_id, name="Work")
    session.delete(work)
    session.commit()
