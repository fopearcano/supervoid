"""Schemas for identity linking + security events (Prompt 15)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    IdentityLinkStatus,
    SecurityEventSeverity,
    SecurityEventType,
)


class IdentityLinkCreate(BaseModel):
    supervoid_user_id: str
    librechat_email: str = Field(min_length=1, max_length=255)
    librechat_user_id: Optional[str] = None
    note: Optional[str] = None
    verify: bool = False  # set ACTIVE immediately (admin vouches for it)


class IdentityLinkUpdate(BaseModel):
    librechat_email: Optional[str] = None
    librechat_user_id: Optional[str] = None
    note: Optional[str] = None


class IdentityActionRequest(BaseModel):
    note: Optional[str] = None


class IdentityLinkRead(BaseModel):
    id: str
    supervoid_user_id: str
    user_email: Optional[str] = None        # enriched for the admin list
    user_full_name: Optional[str] = None
    librechat_user_id: Optional[str] = None
    librechat_email: str
    status: IdentityLinkStatus
    linked_at: datetime
    verified_at: Optional[datetime] = None
    disabled_at: Optional[datetime] = None
    linked_by_id: Optional[str] = None
    disabled_by_id: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime


class MyIdentityRead(BaseModel):
    """A member's self-service view of their own Brain identity link."""

    linked: bool
    status: Optional[IdentityLinkStatus] = None
    librechat_email: Optional[str] = None
    linked_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None


class SecurityEventRead(BaseModel):
    id: str
    created_at: datetime
    event_type: SecurityEventType
    severity: SecurityEventSeverity
    source: str
    supervoid_user_id: Optional[str] = None
    librechat_user_id: Optional[str] = None
    email: Optional[str] = None
    reason: Optional[str] = None
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    token_id: Optional[str] = None
    request_id: Optional[str] = None
    detail: dict[str, Any] = {}
