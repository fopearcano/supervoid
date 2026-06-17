"""Integration contract for the future SUPERVOID Movies division.

SUPERVOID Movies is a planned sibling division under SUPERVOID ENTANGLED that
will reuse this architecture for film production. This descriptor defines the
publishing -> film boundary so an adaptation can later be opened from a
published title without redesigning the domain.
"""
from __future__ import annotations

from app.integrations.base import (
    Integration,
    IntegrationCapability,
    IntegrationDirection,
    IntegrationStatus,
)

MOVIES = Integration(
    key="supervoid_movies",
    name="SUPERVOID Movies",
    system="SUPERVOID Movies",
    relationship=(
        "Future sibling division under SUPERVOID ENTANGLED — film and screen "
        "production, intended to reuse and extend the SUPERVOID Publishing "
        "architecture."
    ),
    status=IntegrationStatus.PLANNED,
    summary=(
        "Film-adaptation bridge. Promotes a published title into a SUPERVOID "
        "Movies adaptation dossier, carrying rights, contracts, and the "
        "knowledge graph across the publishing -> film boundary."
    ),
    capabilities=[
        IntegrationCapability(
            key="promote_to_adaptation",
            summary="Open a film-adaptation dossier from a published title.",
            direction=IntegrationDirection.OUTBOUND,
        ),
        IntegrationCapability(
            key="share_rights",
            summary="Share rights and contract terms with the film production system.",
            direction=IntegrationDirection.BIDIRECTIONAL,
        ),
        IntegrationCapability(
            key="share_knowledge_graph",
            summary="Expose characters, places, and themes for screen adaptation.",
            direction=IntegrationDirection.OUTBOUND,
        ),
    ],
)
