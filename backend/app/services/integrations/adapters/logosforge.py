"""LOGOSFORGE bundle-exchange adapter (local-first, package-based).

LOGOSFORGE is a *sibling* writing subsystem under SUPERVOID ENTANGLED — not part
of SUPERVOID Publishing and not reachable over a live API here. This adapter is
therefore **package-based**, exactly like the desktop file-exchange adapters: it
ingests a *bundle* (a structured dict a LOGOSFORGE export produced) and turns it
into a SUPERVOID ``Manuscript`` and/or seeds the editorial knowledge graph.

It implements the inbound seam declared by the static ``logosforge`` descriptor
(``import_manuscript`` / ``sync_knowledge_graph``). The outbound
``return_editorial_notes`` capability is **recorded only** — nothing is
dispatched to an external system. This is an adapter-only / package-import
integration, NOT a fully operational remote integration.
"""
from __future__ import annotations

from app.models.enums import (
    IntegrationAdapterKind,
    IntegrationDirectionKind,
    IntegrationHealthStatus,
)
from app.services.integrations import effects
from app.services.integrations.base import (
    AdapterContext,
    AdapterOperation,
    HealthReport,
    IntegrationAdapter,
    recorded_result,
)

BUNDLE_SCHEMA = "supervoid.logosforge_bundle/1"


def _bundle(ctx: AdapterContext) -> dict:
    """The operation payload IS the bundle; allow an explicit ``bundle`` key too."""
    payload = ctx.payload or {}
    bundle = payload.get("bundle")
    return bundle if isinstance(bundle, dict) else payload


class LogosforgeAdapter(IntegrationAdapter):
    key = "logosforge"
    kind = IntegrationAdapterKind.LOGOSFORGE
    name = "LOGOSFORGE bundle exchange"
    description = (
        "Local-first, package-based bridge to the LOGOSFORGE writing subsystem. "
        "Ingests an exported draft bundle as a manuscript and seeds the knowledge "
        "graph; editorial notes are recorded for return, not dispatched. No live "
        "LOGOSFORGE API is contacted."
    )
    required_config = ()
    credential_names = ()
    operations = (
        AdapterOperation(
            key="import_manuscript",
            name="Import manuscript bundle",
            summary="Ingest a completed LOGOSFORGE draft bundle as a manuscript.",
            direction=IntegrationDirectionKind.INBOUND,
            mutating=True,
            risk="medium",
        ),
        AdapterOperation(
            key="sync_knowledge_graph",
            name="Sync knowledge graph",
            summary="Seed the editorial knowledge graph from LOGOSFORGE entities.",
            direction=IntegrationDirectionKind.INBOUND,
            mutating=True,
            risk="low",
        ),
        AdapterOperation(
            key="return_editorial_notes",
            name="Return editorial notes",
            summary="Record editorial notes to return to the author in LOGOSFORGE.",
            direction=IntegrationDirectionKind.OUTBOUND,
            external=True,
            touches_network=True,
            risk="medium",
        ),
    )

    # --- health / status ---------------------------------------------------

    def health_check(self, ctx: AdapterContext) -> HealthReport:
        if not ctx.point.enabled:
            return HealthReport(
                IntegrationHealthStatus.DISABLED,
                "Integration point is disabled.",
                configured=True,
            )
        return HealthReport(
            IntegrationHealthStatus.HEALTHY,
            "Local bundle exchange ready (no external connection required).",
            configured=True,
        )

    def status(self, ctx: AdapterContext) -> dict:
        return {
            "adapter": self.key,
            "mode": "package",
            "bundle_schema": BUNDLE_SCHEMA,
            "inbound": ["import_manuscript", "sync_knowledge_graph"],
            "outbound": ["return_editorial_notes (recorded only)"],
        }

    # --- operations --------------------------------------------------------

    def dry_run(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        bundle = _bundle(ctx)
        if op.key == "import_manuscript":
            ms = bundle.get("manuscript") or {}
            author = bundle.get("author") or {}
            return {
                "operation": op.key,
                "would_create": {
                    "manuscript_title": ms.get("title"),
                    "author": author.get("full_name") or author.get("id"),
                    "work_id": bundle.get("work_id"),
                },
                "note": "Dry-run: nothing ingested.",
            }
        if op.key == "sync_knowledge_graph":
            kg = bundle.get("knowledge") or bundle
            return {
                "operation": op.key,
                "would_create": {
                    "entities": len(kg.get("entities") or []),
                    "relationships": len(kg.get("relationships") or []),
                },
                "note": "Dry-run: nothing ingested.",
            }
        if op.key == "return_editorial_notes":
            return {
                "operation": op.key,
                "would_return": {"notes": len((ctx.payload or {}).get("notes") or [])},
                "note": "Dry-run: nothing dispatched.",
            }
        return {"operation": op.key, "note": "Dry-run."}

    def inbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        bundle = _bundle(ctx)
        if op.key == "import_manuscript":
            result = effects.import_manuscript_bundle(
                ctx.session,
                bundle=bundle,
                owner_id=ctx.user.id if ctx.user else None,
            )
            result["operation"] = "import_manuscript"
            return result
        if op.key == "sync_knowledge_graph":
            kg = bundle.get("knowledge") or bundle
            result = effects.seed_knowledge_graph(
                ctx.session,
                entities=kg.get("entities") or [],
                relationships=kg.get("relationships") or [],
            )
            result["operation"] = "sync_knowledge_graph"
            return result
        raise ValueError(f"Unsupported LOGOSFORGE inbound operation '{op.key}'.")

    def outbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        if op.key == "return_editorial_notes":
            request = {
                "target_manuscript": (ctx.payload or {}).get("manuscript_id"),
                "note_count": len((ctx.payload or {}).get("notes") or []),
            }
            # Local-first: nothing is sent to LOGOSFORGE. The notes are recorded
            # on the run so they can be exported and returned by hand.
            return recorded_result(
                request,
                "Editorial notes recorded for return to LOGOSFORGE — not dispatched "
                "(no live LOGOSFORGE API; local-first).",
            )
        raise ValueError(f"Unsupported LOGOSFORGE outbound operation '{op.key}'.")
