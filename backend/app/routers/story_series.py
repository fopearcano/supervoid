from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED
from app.db import get_session
from app.models import StorySeries, StoryWorld
from app.models.enums import StorySeriesStatus
from app.schemas.story_series import (
    StorySeriesCreate,
    StorySeriesRead,
    StorySeriesUpdate,
)
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(prefix="/story-series", tags=["story_series"])


@router.get("", response_model=Page[StorySeriesRead])
def list_story_series(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    story_world_id: Optional[str] = Query(default=None),
    status_: Optional[StorySeriesStatus] = Query(default=None, alias="status"),
    sort_dir: Literal["asc", "desc"] = Query(
        default="asc", description="Sort by sequence order"
    ),
) -> Page[StorySeriesRead]:
    stmt = select(StorySeries)
    if story_world_id is not None:
        stmt = stmt.where(StorySeries.story_world_id == story_world_id)
    if status_ is not None:
        stmt = stmt.where(StorySeries.status == status_)
    column = StorySeries.sequence_order
    stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())

    items, total = paginate(session, stmt, params)
    return Page[StorySeriesRead](
        items=[StorySeriesRead.model_validate(i) for i in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.get("/{series_id}", response_model=StorySeriesRead)
def get_story_series(series_id: str, session: Session = Depends(get_session)) -> StorySeries:
    return get_or_404(session, StorySeries, series_id, name="StorySeries")


@router.post("", response_model=StorySeriesRead, status_code=status.HTTP_201_CREATED, dependencies=AUTHED)
def create_story_series(
    payload: StorySeriesCreate, session: Session = Depends(get_session)
) -> StorySeries:
    ensure_exists(session, StoryWorld, payload.story_world_id, name="StoryWorld")
    series = StorySeries(**payload.model_dump())
    session.add(series)
    session.commit()
    session.refresh(series)
    return series


@router.patch("/{series_id}", response_model=StorySeriesRead, dependencies=AUTHED)
def update_story_series(
    series_id: str,
    payload: StorySeriesUpdate,
    session: Session = Depends(get_session),
) -> StorySeries:
    series = get_or_404(session, StorySeries, series_id, name="StorySeries")
    if payload.story_world_id is not None:
        ensure_exists(session, StoryWorld, payload.story_world_id, name="StoryWorld")
    apply_patch(series, payload)
    session.add(series)
    session.commit()
    session.refresh(series)
    return series


@router.delete("/{series_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY)
def delete_story_series(series_id: str, session: Session = Depends(get_session)):
    series = get_or_404(session, StorySeries, series_id, name="StorySeries")
    session.delete(series)
    session.commit()
