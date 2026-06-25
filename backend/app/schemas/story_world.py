from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import StoryWorldStatus
from app.schemas._common import TimestampedRead


class StoryWorldCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    # Optional — the router derives a slug from the name when omitted.
    slug: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = None
    canon_summary: Optional[str] = None
    status: StoryWorldStatus = StoryWorldStatus.DEVELOPING
    visual_identity_notes: Optional[str] = None
    default_language: str = Field(default="en", max_length=10)
    owner_id: Optional[str] = None
    parent_id: Optional[str] = None


class StoryWorldUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=300)
    slug: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = None
    canon_summary: Optional[str] = None
    status: Optional[StoryWorldStatus] = None
    visual_identity_notes: Optional[str] = None
    default_language: Optional[str] = Field(default=None, max_length=10)
    owner_id: Optional[str] = None
    parent_id: Optional[str] = None


class StoryWorldRead(TimestampedRead):
    name: str
    slug: str
    description: Optional[str]
    canon_summary: Optional[str]
    status: StoryWorldStatus
    visual_identity_notes: Optional[str]
    default_language: str
    owner_id: Optional[str]
    parent_id: Optional[str]
