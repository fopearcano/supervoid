"""Ecosystem integration layer for SUPERVOID Publishing.

Declares the seams to sibling systems under SUPERVOID ENTANGLED (the
LOGOSFORGE writing subsystem and the future SUPERVOID Movies division) as
typed, inspectable contracts. Local-first: descriptors only, no live clients.
"""
from __future__ import annotations

from app.integrations.base import (
    Integration,
    IntegrationCapability,
    IntegrationDirection,
    IntegrationStatus,
)
from app.integrations.ecosystem import ECOSYSTEM, Ecosystem, EcosystemMember
from app.integrations.logosforge import LOGOSFORGE
from app.integrations.movies import MOVIES

INTEGRATIONS: tuple[Integration, ...] = (LOGOSFORGE, MOVIES)


def all_integrations() -> list[Integration]:
    """Every declared ecosystem integration."""
    return list(INTEGRATIONS)


def get_integration(key: str) -> Integration | None:
    """Look up a single integration by its key, or ``None``."""
    return next((i for i in INTEGRATIONS if i.key == key), None)


__all__ = [
    "ECOSYSTEM",
    "Ecosystem",
    "EcosystemMember",
    "INTEGRATIONS",
    "Integration",
    "IntegrationCapability",
    "IntegrationDirection",
    "IntegrationStatus",
    "LOGOSFORGE",
    "MOVIES",
    "all_integrations",
    "get_integration",
]
