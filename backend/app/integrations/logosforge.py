"""Integration contract for the LOGOSFORGE writing subsystem.

LOGOSFORGE is a *separate* writing app / narrative engine, a sibling subsystem
under SUPERVOID ENTANGLED — not part of SUPERVOID Publishing. This descriptor
defines the seam where a finished LOGOSFORGE draft would cross into the
publishing pipeline, so the relationship is explicit and ready to implement.
"""
from __future__ import annotations

from app.integrations.base import (
    Integration,
    IntegrationCapability,
    IntegrationDirection,
    IntegrationStatus,
)

LOGOSFORGE = Integration(
    key="logosforge",
    name="LOGOSFORGE",
    system="LOGOSFORGE",
    relationship=(
        "Sibling subsystem under SUPERVOID ENTANGLED — the writing app and "
        "narrative engine where stories are drafted before they enter the "
        "SUPERVOID Publishing pipeline."
    ),
    status=IntegrationStatus.PLANNED,
    summary=(
        "Bridge between the LOGOSFORGE writing/narrative subsystem and "
        "SUPERVOID Publishing. Carries a finished draft from authoring into "
        "editorial production without re-keying, and lets narrative structure "
        "(characters, places, themes) seed the editorial knowledge graph."
    ),
    capabilities=[
        IntegrationCapability(
            key="import_manuscript",
            summary="Import a completed LOGOSFORGE draft as a SUPERVOID manuscript.",
            direction=IntegrationDirection.INBOUND,
        ),
        IntegrationCapability(
            key="sync_knowledge_graph",
            summary=(
                "Seed the editorial knowledge graph from LOGOSFORGE story "
                "entities and relationships."
            ),
            direction=IntegrationDirection.INBOUND,
        ),
        IntegrationCapability(
            key="return_editorial_notes",
            summary="Return editorial notes and revisions to the author in LOGOSFORGE.",
            direction=IntegrationDirection.OUTBOUND,
        ),
    ],
)
