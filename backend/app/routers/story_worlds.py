from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED
from app.db import get_session
from app.models import Author, StoryWorld
from app.models.enums import StoryWorldStatus
from app.schemas.story_world import StoryWorldCreate, StoryWorldRead, StoryWorldUpdate
from app.services import brain
from app.services.knowledge import slugify
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(prefix="/story-worlds", tags=["story_worlds"])


class StoryWorldSortBy(str, Enum):
    NAME = "name"
    STATUS = "status"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


_SORT_COLUMNS = {
    StoryWorldSortBy.NAME: StoryWorld.name,
    StoryWorldSortBy.STATUS: StoryWorld.status,
    StoryWorldSortBy.CREATED_AT: StoryWorld.created_at,
    StoryWorldSortBy.UPDATED_AT: StoryWorld.updated_at,
}


def _unique_slug(session: Session, base: str, *, exclude_id: Optional[str] = None) -> str:
    base = slugify(base)
    candidate, i = base, 2
    while True:
        clash = session.exec(
            select(StoryWorld).where(StoryWorld.slug == candidate)
        ).first()
        if clash is None or clash.id == exclude_id:
            return candidate
        candidate, i = f"{base}-{i}", i + 1


@router.get("", response_model=Page[StoryWorldRead])
def list_story_worlds(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    status_: Optional[StoryWorldStatus] = Query(default=None, alias="status"),
    parent_id: Optional[str] = Query(default=None),
    owner_id: Optional[str] = Query(default=None),
    sort_by: StoryWorldSortBy = Query(default=StoryWorldSortBy.NAME),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
) -> Page[StoryWorldRead]:
    stmt = select(StoryWorld)
    if status_ is not None:
        stmt = stmt.where(StoryWorld.status == status_)
    if parent_id is not None:
        stmt = stmt.where(StoryWorld.parent_id == parent_id)
    if owner_id is not None:
        stmt = stmt.where(StoryWorld.owner_id == owner_id)

    column = _SORT_COLUMNS[sort_by]
    stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())

    items, total = paginate(session, stmt, params)
    return Page[StoryWorldRead](
        items=[StoryWorldRead.model_validate(i) for i in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.get("/{world_id}", response_model=StoryWorldRead)
def get_story_world(world_id: str, session: Session = Depends(get_session)) -> StoryWorld:
    return get_or_404(session, StoryWorld, world_id, name="StoryWorld")


@router.post("", response_model=StoryWorldRead, status_code=status.HTTP_201_CREATED, dependencies=AUTHED)
def create_story_world(
    payload: StoryWorldCreate, session: Session = Depends(get_session)
) -> StoryWorld:
    if payload.owner_id is not None:
        ensure_exists(session, Author, payload.owner_id, name="Author")
    if payload.parent_id is not None:
        ensure_exists(session, StoryWorld, payload.parent_id, name="StoryWorld")
    data = payload.model_dump()
    data["slug"] = _unique_slug(session, payload.slug or payload.name)
    world = StoryWorld(**data)
    session.add(world)
    brain.emit(
        session, event_type=brain.BrainEventType.STORY_WORLD_CREATED,
        aggregate_type="story_world", aggregate_id=world.id,
        story_world_id=world.id,
    )
    session.commit()
    session.refresh(world)
    return world


@router.patch("/{world_id}", response_model=StoryWorldRead, dependencies=AUTHED)
def update_story_world(
    world_id: str,
    payload: StoryWorldUpdate,
    session: Session = Depends(get_session),
) -> StoryWorld:
    world = get_or_404(session, StoryWorld, world_id, name="StoryWorld")
    if payload.owner_id is not None:
        ensure_exists(session, Author, payload.owner_id, name="Author")
    if payload.parent_id is not None:
        if payload.parent_id == world_id:
            raise HTTPException(status_code=400, detail="A world cannot be its own parent.")
        ensure_exists(session, StoryWorld, payload.parent_id, name="StoryWorld")
    if payload.slug is not None:
        payload.slug = _unique_slug(session, payload.slug, exclude_id=world_id)
    apply_patch(world, payload)
    session.add(world)
    brain.emit(
        session, event_type=brain.BrainEventType.STORY_WORLD_UPDATED,
        aggregate_type="story_world", aggregate_id=world.id,
        story_world_id=world.id,
        changes=payload.model_dump(exclude_unset=True),
    )
    session.commit()
    session.refresh(world)
    return world


@router.delete("/{world_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY)
def delete_story_world(world_id: str, session: Session = Depends(get_session)):
    world = get_or_404(session, StoryWorld, world_id, name="StoryWorld")
    session.delete(world)
    # The world row is going away — scope omitted (FK-safe); studio goes stale.
    brain.emit(
        session, event_type=brain.BrainEventType.STORY_WORLD_DELETED,
        aggregate_type="story_world", aggregate_id=world_id,
    )
    session.commit()
