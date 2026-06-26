"""Schemas for Brain access tokens (gateway bearer tokens)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProjectRestriction(BaseModel):
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None


class BrainTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    project_restrictions: list[ProjectRestriction] = []
    # Optional lifetime in days; omit for a non-expiring token.
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=3650)


class BrainTokenMeta(BaseModel):
    """Public metadata for a token — NEVER includes the secret."""

    id: str
    name: str
    token_prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    project_restrictions: list = []


class BrainTokenSecret(BaseModel):
    """Returned exactly once at creation/rotation — the only time the plaintext
    secret is ever exposed."""

    token: BrainTokenMeta
    secret: str
