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
    status=IntegrationStatus.AVAILABLE,
    summary=(
        "Bridge between the LOGOSFORGE writing/narrative subsystem and "
        "SUPERVOID Publishing, implemented as a local-first, package-based hub "
        "adapter (adapter key 'logosforge') — NOT a live LOGOSFORGE API. The "
        "inbound seam works today: ingest an exported draft bundle as a "
        "manuscript and seed the knowledge graph through the integration hub's "
        "approval boundary. Outbound editorial notes are recorded for return, "
        "not dispatched."
    ),
    capabilities=[
        IntegrationCapability(
            key="import_manuscript",
            summary=(
                "Import a completed LOGOSFORGE draft *bundle* as a SUPERVOID "
                "manuscript (local-first; via the hub adapter)."
            ),
            direction=IntegrationDirection.INBOUND,
        ),
        IntegrationCapability(
            key="sync_knowledge_graph",
            summary=(
                "Seed the editorial knowledge graph from LOGOSFORGE story "
                "entities and relationships in the bundle (local-first)."
            ),
            direction=IntegrationDirection.INBOUND,
        ),
        IntegrationCapability(
            key="return_editorial_notes",
            summary=(
                "Record editorial notes to return to the author in LOGOSFORGE "
                "(recorded only — not dispatched; no live LOGOSFORGE API)."
            ),
            direction=IntegrationDirection.OUTBOUND,
        ),
    ],
)
