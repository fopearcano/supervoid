from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import RightStatus
from app.schemas._common import TimestampedRead


class RightsCreate(BaseModel):
    work_id: str
    territory: str = Field(default="World", max_length=100)
    language: str = Field(default="all", max_length=40)
    print_rights: RightStatus = RightStatus.AVAILABLE
    ebook_rights: RightStatus = RightStatus.AVAILABLE
    audiobook_rights: RightStatus = RightStatus.AVAILABLE
    film_rights: RightStatus = RightStatus.AVAILABLE
    adaptation_rights: RightStatus = RightStatus.AVAILABLE
    merchandising_rights: RightStatus = RightStatus.AVAILABLE
    holder: Optional[str] = Field(default=None, max_length=200)
    expiration_date: Optional[date] = None
    notes: Optional[str] = None


class RightsUpdate(BaseModel):
    territory: Optional[str] = Field(default=None, max_length=100)
    language: Optional[str] = Field(default=None, max_length=40)
    print_rights: Optional[RightStatus] = None
    ebook_rights: Optional[RightStatus] = None
    audiobook_rights: Optional[RightStatus] = None
    film_rights: Optional[RightStatus] = None
    adaptation_rights: Optional[RightStatus] = None
    merchandising_rights: Optional[RightStatus] = None
    holder: Optional[str] = Field(default=None, max_length=200)
    expiration_date: Optional[date] = None
    notes: Optional[str] = None


class RightsRead(TimestampedRead):
    work_id: str
    territory: str
    language: str
    print_rights: RightStatus
    ebook_rights: RightStatus
    audiobook_rights: RightStatus
    film_rights: RightStatus
    adaptation_rights: RightStatus
    merchandising_rights: RightStatus
    holder: Optional[str]
    expiration_date: Optional[date]
    notes: Optional[str]
