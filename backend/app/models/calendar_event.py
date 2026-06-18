from datetime import date as date_type
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import CalendarEventStatus, CalendarEventType

if TYPE_CHECKING:
    from app.models.work import Work


class PublishingCalendarEvent(BaseEntity, table=True):
    """A dated entry on the publishing calendar.

    Usually tied to a Work (a release, cover reveal, preorder window…) but
    ``work_id`` is optional so house-wide events (fairs, catalogue deadlines)
    can also be scheduled.
    """

    __tablename__ = "calendar_events"

    work_id: Optional[str] = Field(default=None, foreign_key="works.id", index=True)

    title: str = Field(max_length=300)
    event_type: CalendarEventType = Field(
        default=CalendarEventType.OTHER, index=True
    )
    date: date_type = Field(index=True)
    description: Optional[str] = Field(default=None)
    status: CalendarEventStatus = Field(
        default=CalendarEventStatus.PLANNED, index=True
    )

    work: Optional["Work"] = Relationship(back_populates="calendar_events")
