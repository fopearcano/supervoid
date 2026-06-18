from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED
from app.db import get_session
from app.models import PublishingCalendarEvent, Work
from app.models.enums import CalendarEventStatus, CalendarEventType
from app.schemas import (
    PublishingCalendarEventCreate,
    PublishingCalendarEventRead,
    PublishingCalendarEventUpdate,
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

router = APIRouter(prefix="/calendar-events", tags=["calendar_events"])


@router.get("", response_model=Page[PublishingCalendarEventRead])
def list_calendar_events(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    work_id: Optional[str] = Query(default=None, description="Filter by work id"),
    event_type: Optional[CalendarEventType] = Query(default=None),
    status_: Optional[CalendarEventStatus] = Query(default=None, alias="status"),
    date_from: Optional[date] = Query(
        default=None, description="Only events on/after this date"
    ),
    date_to: Optional[date] = Query(
        default=None, description="Only events on/before this date"
    ),
    sort_dir: Literal["asc", "desc"] = Query(
        default="asc", description="Sort by event date"
    ),
) -> Page[PublishingCalendarEventRead]:
    stmt = select(PublishingCalendarEvent)
    if work_id is not None:
        stmt = stmt.where(PublishingCalendarEvent.work_id == work_id)
    if event_type is not None:
        stmt = stmt.where(PublishingCalendarEvent.event_type == event_type)
    if status_ is not None:
        stmt = stmt.where(PublishingCalendarEvent.status == status_)
    if date_from is not None:
        stmt = stmt.where(PublishingCalendarEvent.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(PublishingCalendarEvent.date <= date_to)

    column = PublishingCalendarEvent.date
    stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())

    items, total = paginate(session, stmt, params)
    return Page[PublishingCalendarEventRead](
        items=[PublishingCalendarEventRead.model_validate(i) for i in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.get("/{event_id}", response_model=PublishingCalendarEventRead)
def get_calendar_event(
    event_id: str, session: Session = Depends(get_session)
) -> PublishingCalendarEvent:
    return get_or_404(
        session, PublishingCalendarEvent, event_id, name="PublishingCalendarEvent"
    )


@router.post(
    "",
    response_model=PublishingCalendarEventRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
)
def create_calendar_event(
    payload: PublishingCalendarEventCreate, session: Session = Depends(get_session)
) -> PublishingCalendarEvent:
    if payload.work_id is not None:
        ensure_exists(session, Work, payload.work_id, name="Work")
    event = PublishingCalendarEvent(**payload.model_dump())
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.patch(
    "/{event_id}",
    response_model=PublishingCalendarEventRead,
    dependencies=AUTHED,
)
def update_calendar_event(
    event_id: str,
    payload: PublishingCalendarEventUpdate,
    session: Session = Depends(get_session),
) -> PublishingCalendarEvent:
    event = get_or_404(
        session, PublishingCalendarEvent, event_id, name="PublishingCalendarEvent"
    )
    if payload.work_id is not None:
        ensure_exists(session, Work, payload.work_id, name="Work")
    apply_patch(event, payload)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=ADMIN_ONLY,
)
def delete_calendar_event(
    event_id: str, session: Session = Depends(get_session)
):
    event = get_or_404(
        session, PublishingCalendarEvent, event_id, name="PublishingCalendarEvent"
    )
    session.delete(event)
    session.commit()
