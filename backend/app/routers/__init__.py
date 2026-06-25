"""API routers. Each module exposes a `router` attribute mounted in main.py."""

from types import SimpleNamespace

from app.routers import (
    adaptation_dossiers,
    ai,
    attachments,
    auth,
    authors,
    calendar_events,
    contracts,
    dashboard,
    editorial_notes,
    exports,
    graphic_novel_productions,
    health,
    integrations,
    knowledge,
    manuscripts,
    meta,
    production_items,
    production_records,
    public_reader,
    reviews,
    rights,
    search,
    story_series,
    story_worlds,
    workflow,
    workflow_events,
    works,
)

# The knowledge module exposes two routers — the main /knowledge surface
# and a manuscript-scoped one mounted under /manuscripts/{id}/entity-links.
# Both need to be included; wrap the second in a tiny namespace so the
# include loop in main.py can stay uniform.
_manuscript_links = SimpleNamespace(router=knowledge.manuscript_links_router)

ALL_ROUTERS = (
    health,
    meta,
    integrations,
    auth,
    dashboard,
    search,
    story_worlds,
    story_series,
    authors,
    works,
    adaptation_dossiers,
    manuscripts,
    graphic_novel_productions,
    reviews,
    workflow,
    workflow_events,
    contracts,
    rights,
    production_items,
    production_records,
    calendar_events,
    editorial_notes,
    attachments,
    exports,
    ai,
    knowledge,
    _manuscript_links,
)

__all__ = [
    "ALL_ROUTERS",
    "adaptation_dossiers",
    "ai",
    "attachments",
    "auth",
    "authors",
    "calendar_events",
    "contracts",
    "dashboard",
    "editorial_notes",
    "exports",
    "graphic_novel_productions",
    "health",
    "integrations",
    "knowledge",
    "manuscripts",
    "meta",
    "production_items",
    "production_records",
    "public_reader",
    "reviews",
    "rights",
    "search",
    "story_series",
    "story_worlds",
    "workflow",
    "workflow_events",
    "works",
]

# NOTE: ``public_reader`` is intentionally NOT in ALL_ROUTERS. The private API
# routers above are all mounted under the ``/api`` prefix; the public reader is
# mounted separately and unprefixed at ``/public`` in main.py, keeping the
# public/private surfaces cleanly separated at the URL level too.
