"""Typed descriptors for SUPERVOID ENTANGLED ecosystem integrations.

These are *contracts*, not clients. SUPERVOID Publishing is local-first and
ships no live calls to sibling systems; this module declares the integration
points (what would cross the boundary, and in which direction) so the seams
are explicit in code and inspectable over the API. Concrete adapters can be
added later behind these shapes without disturbing the rest of the system.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class IntegrationStatus(str, Enum):
    """Lifecycle of an ecosystem integration."""

    AVAILABLE = "available"  # wired and usable today
    PLANNED = "planned"  # contract defined, implementation pending
    DISABLED = "disabled"  # present but switched off


class IntegrationDirection(str, Enum):
    """Which way data flows relative to SUPERVOID Publishing."""

    INBOUND = "inbound"  # data flows into SUPERVOID Publishing
    OUTBOUND = "outbound"  # data flows out to the sibling system
    BIDIRECTIONAL = "bidirectional"


class IntegrationCapability(BaseModel):
    """A single thing an integration can do once implemented."""

    key: str
    summary: str
    direction: IntegrationDirection


class Integration(BaseModel):
    """A bridge between SUPERVOID Publishing and another ecosystem system."""

    key: str
    name: str
    system: str
    relationship: str
    status: IntegrationStatus
    summary: str
    capabilities: list[IntegrationCapability]
