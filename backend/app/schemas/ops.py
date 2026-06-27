"""Request schemas for Brain Operations controls (Prompt 16)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ToggleRequest(BaseModel):
    enabled: bool


class DrainRequest(BaseModel):
    draining: bool


class MaintenanceRequest(BaseModel):
    note: Optional[str] = None


class ReplayRequest(BaseModel):
    event_ids: Optional[list[str]] = None
