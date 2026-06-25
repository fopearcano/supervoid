"""Integration descriptor for the SUPERVOID Pictures (Movies) division.

SUPERVOID Pictures is now an **operational internal adapter** — a screen-
production bounded context living inside this repository (``/api/screen``),
entered via ``AdaptationDossier`` (ScreenProject → Unit → Sequence → Scene →
Shot). It is kept extractable into a separate service later, but runs here
today; this descriptor reflects that it is wired and usable, not merely planned.
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
    name="SUPERVOID Pictures",
    system="SUPERVOID Pictures",
    relationship=(
        "Screen-production division under SUPERVOID ENTANGLED — now an "
        "operational bounded context inside SUPERVOID Publishing, kept "
        "extractable into its own service later."
    ),
    status=IntegrationStatus.AVAILABLE,
    summary=(
        "Operational film/screen adapter at /api/screen. Promotes a Work or "
        "graphic novel into an adaptation dossier, builds a ScreenProject of "
        "scenes and shots, reuses graphic-novel panels as storyboards, carries "
        "knowledge entities / rights / provenance, and exports an adaptation "
        "package as JSON or Markdown."
    ),
    capabilities=[
        IntegrationCapability(
            key="promote_to_adaptation",
            summary="Promote a Work / graphic novel into a Pictures adaptation dossier.",
            direction=IntegrationDirection.OUTBOUND,
        ),
        IntegrationCapability(
            key="create_screen_project",
            summary="Create a ScreenProject (scenes & shots) from an approved dossier.",
            direction=IntegrationDirection.OUTBOUND,
        ),
        IntegrationCapability(
            key="reuse_storyboard_panels",
            summary="Map graphic-novel pages/panels onto shots as storyboard references.",
            direction=IntegrationDirection.INBOUND,
        ),
        IntegrationCapability(
            key="share_rights",
            summary="Carry rights and contract terms into the screen production.",
            direction=IntegrationDirection.BIDIRECTIONAL,
        ),
        IntegrationCapability(
            key="share_knowledge_graph",
            summary="Carry characters, places and themes into scenes and shots.",
            direction=IntegrationDirection.OUTBOUND,
        ),
        IntegrationCapability(
            key="export_adaptation_package",
            summary="Export the adaptation package (shot list & breakdown) as JSON/Markdown.",
            direction=IntegrationDirection.OUTBOUND,
        ),
    ],
)
