from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED
from app.db import get_session
from app.models import AdaptationDossier, Author, StorySeries, StoryWorld, Work
from app.models.enums import CanonState, Medium, StudioDivision, WorkStatus, WorkType
from app.schemas import WorkCreate, WorkRead, WorkUpdate
from app.schemas.adaptation_dossier import AdaptationDossierRead, WorkTransmediaOverview
from app.schemas.story_series import StorySeriesRead
from app.schemas.story_world import StoryWorldRead
from app.services import brain
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


def _validate_links(session: Session, payload: WorkCreate | WorkUpdate) -> None:
    """Ensure any referenced author/world/series/source-work actually exist."""
    if getattr(payload, "author_id", None) is not None:
        ensure_exists(session, Author, payload.author_id, name="Author")
    if payload.story_world_id is not None:
        ensure_exists(session, StoryWorld, payload.story_world_id, name="StoryWorld")
    if payload.story_series_id is not None:
        ensure_exists(session, StorySeries, payload.story_series_id, name="StorySeries")
    if payload.source_work_id is not None:
        ensure_exists(session, Work, payload.source_work_id, name="Work")


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
    story_world_id: Optional[str] = Query(default=None, description="Filter by story world"),
    story_series_id: Optional[str] = Query(default=None, description="Filter by series"),
    primary_division: Optional[StudioDivision] = Query(default=None),
    primary_medium: Optional[Medium] = Query(default=None),
    canon_status: Optional[CanonState] = Query(default=None),
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
    if story_world_id is not None:
        stmt = stmt.where(Work.story_world_id == story_world_id)
    if story_series_id is not None:
        stmt = stmt.where(Work.story_series_id == story_series_id)
    if primary_division is not None:
        stmt = stmt.where(Work.primary_division == primary_division)
    if primary_medium is not None:
        stmt = stmt.where(Work.primary_medium == primary_medium)
    if canon_status is not None:
        stmt = stmt.where(Work.canon_status == canon_status)

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


@router.get(
    "/{work_id}/transmedia",
    response_model=WorkTransmediaOverview,
    summary="A Work's IP placement and adaptation web",
)
def work_transmedia(
    work_id: str, session: Session = Depends(get_session)
) -> WorkTransmediaOverview:
    work = get_or_404(session, Work, work_id, name="Work")
    world = (
        session.get(StoryWorld, work.story_world_id) if work.story_world_id else None
    )
    series = (
        session.get(StorySeries, work.story_series_id)
        if work.story_series_id
        else None
    )
    source = session.get(Work, work.source_work_id) if work.source_work_id else None
    derived = session.exec(select(Work).where(Work.source_work_id == work_id)).all()
    dossiers = session.exec(
        select(AdaptationDossier).where(AdaptationDossier.source_work_id == work_id)
    ).all()
    return WorkTransmediaOverview(
        work=WorkRead.model_validate(work),
        story_world=StoryWorldRead.model_validate(world) if world else None,
        story_series=StorySeriesRead.model_validate(series) if series else None,
        source_work=WorkRead.model_validate(source) if source else None,
        derived_works=[WorkRead.model_validate(w) for w in derived],
        adaptation_dossiers=[AdaptationDossierRead.model_validate(d) for d in dossiers],
    )


@router.post(
    "",
    response_model=WorkRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def create_work(payload: WorkCreate, session: Session = Depends(get_session)) -> Work:
    _validate_links(session, payload)
    work = Work(**payload.model_dump())
    session.add(work)
    brain.emit(
        session, event_type=brain.BrainEventType.WORK_CREATED,
        aggregate_type="work", aggregate_id=work.id,
        work_id=work.id, story_world_id=work.story_world_id,
    )
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
    _validate_links(session, payload)
    apply_patch(work, payload)
    session.add(work)
    brain.emit(
        session, event_type=brain.BrainEventType.WORK_UPDATED,
        aggregate_type="work", aggregate_id=work.id,
        work_id=work.id, story_world_id=work.story_world_id,
        changes=payload.model_dump(exclude_unset=True),
    )
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
    # work_id scope omitted on delete (the work row is going away — FK-safe);
    # the surviving story world still goes stale.
    story_world_id = work.story_world_id
    session.delete(work)
    brain.emit(
        session, event_type=brain.BrainEventType.WORK_DELETED,
        aggregate_type="work", aggregate_id=work_id,
        work_id=None, story_world_id=story_world_id,
    )
    session.commit()
