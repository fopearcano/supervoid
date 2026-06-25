"""File-exchange adapters for desktop applications.

These adapters do NOT pretend to remotely control desktop apps (none of which
expose a general remote API). Instead they generate and ingest *structured
export/import packages*: an ``export_package`` writes a manifest describing what
to open/produce in the app, and an ``import_package`` ingests a manifest the app
produced, creating assets and provenance. A profile per app captures its native
formats and package conventions.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import (
    IntegrationAdapterKind,
    IntegrationDirectionKind,
    IntegrationHealthStatus,
    ProvenanceKind,
)
from app.services.integrations import effects
from app.services.integrations.base import (
    AdapterContext,
    AdapterOperation,
    HealthReport,
    IntegrationAdapter,
)

PACKAGE_SCHEMA = "supervoid.file_exchange/1"


@dataclass(frozen=True)
class DesktopAppProfile:
    key: str
    app_name: str
    discipline: str
    package_ext: str
    native_formats: tuple[str, ...]


# One profile per desktop application the studio exchanges files with.
DESKTOP_APP_PROFILES: tuple[DesktopAppProfile, ...] = (
    DesktopAppProfile(
        "affinity", "Affinity (Publisher / Designer / Photo)", "layout/illustration",
        ".afpackage", ("afpub", "afdesign", "afphoto", "pdf", "psd", "tiff"),
    ),
    DesktopAppProfile(
        "indesign", "Adobe InDesign", "layout",
        ".idml.package", ("indd", "idml", "pdf", "epub"),
    ),
    DesktopAppProfile(
        "clip_studio", "Clip Studio Paint", "comics/illustration",
        ".clip.package", ("clip", "psd", "png", "tiff"),
    ),
    DesktopAppProfile(
        "davinci_resolve", "DaVinci Resolve", "editing/color",
        ".drp.package", ("drp", "xml", "edl", "aaf", "fcpxml"),
    ),
    DesktopAppProfile(
        "blender", "Blender", "3d/animation",
        ".blend.package", ("blend", "usd", "abc", "fbx", "gltf"),
    ),
    DesktopAppProfile(
        "cinema4d", "Maxon Cinema 4D", "3d/motion",
        ".c4d.package", ("c4d", "usd", "abc", "fbx"),
    ),
    DesktopAppProfile(
        "houdini", "SideFX Houdini", "3d/vfx",
        ".hip.package", ("hip", "usd", "abc", "bgeo"),
    ),
)


class FileExchangeAdapter(IntegrationAdapter):
    kind = IntegrationAdapterKind.FILE_EXCHANGE
    required_config = ()
    credential_names = ()

    def __init__(self, profile: DesktopAppProfile) -> None:
        self.profile = profile
        self.key = f"file_exchange.{profile.key}"
        self.name = f"{profile.app_name} file exchange"
        self.description = (
            f"Structured export/import packages for {profile.app_name} "
            f"({profile.discipline}). Generates a manifest to open in the app and "
            "ingests deliverables back as assets — no remote control."
        )
        self.operations = (
            AdapterOperation(
                key="export_package",
                name="Export package",
                summary=f"Generate a structured package for {profile.app_name}.",
                direction=IntegrationDirectionKind.INTERNAL,
                mutating=True,
            ),
            AdapterOperation(
                key="import_package",
                name="Import package",
                summary=f"Ingest a deliverable package from {profile.app_name}.",
                direction=IntegrationDirectionKind.INBOUND,
                mutating=True,
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
            "Local file-exchange ready (no external connection required).",
            configured=True,
        )

    def status(self, ctx: AdapterContext) -> dict:
        return {
            "adapter": self.key,
            "app": self.profile.app_name,
            "package_format": self.profile.package_ext,
            "native_formats": list(self.profile.native_formats),
        }

    # --- operations --------------------------------------------------------

    def dry_run(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        if op.key == "export_package":
            return {
                "operation": op.key,
                "manifest": self._export_manifest(ctx, correlation_id="dry-run"),
                "note": "Dry-run: package not written.",
            }
        if op.key == "import_package":
            return {
                "operation": op.key,
                "would_create": self._import_preview(ctx),
                "note": "Dry-run: nothing ingested.",
            }
        return {"operation": op.key, "note": "Dry-run."}

    def outbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        # export_package is INTERNAL; execute() routes it through inbound().
        return self.inbound(op, ctx)

    def inbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        if op.key == "export_package":
            return self._export(ctx)
        if op.key == "import_package":
            return self._import(ctx)
        raise ValueError(f"Unsupported file-exchange operation '{op.key}'.")

    # --- helpers -----------------------------------------------------------

    def _export_manifest(self, ctx: AdapterContext, *, correlation_id: str) -> dict:
        payload = ctx.payload
        return {
            "schema": PACKAGE_SCHEMA,
            "direction": "export",
            "app": self.profile.key,
            "app_name": self.profile.app_name,
            "package_format": self.profile.package_ext,
            "native_formats": list(self.profile.native_formats),
            "correlation_id": correlation_id,
            "title": payload.get("title", f"{self.profile.app_name} package"),
            "source": {
                "work_id": payload.get("work_id"),
                "story_world_id": payload.get("story_world_id"),
            },
            "items": payload.get("items", []),
            "notes": payload.get("notes"),
            "instructions": (
                f"Open the referenced material in {self.profile.app_name}, work, then "
                "produce a deliverable package and ingest it with import_package."
            ),
        }

    def _export(self, ctx: AdapterContext) -> dict:
        correlation_id = ctx.payload.get("correlation_id", "export")
        manifest = self._export_manifest(ctx, correlation_id=correlation_id)
        written = effects.write_exchange_package(
            app_key=self.profile.key,
            manifest=manifest,
            correlation_id=correlation_id,
        )
        return {
            "operation": "export_package",
            "app": self.profile.key,
            "item_count": len(manifest["items"]),
            **written,
        }

    def _import_preview(self, ctx: AdapterContext) -> dict:
        deliverable = ctx.payload.get("deliverable", {})
        return {
            "new_asset": ctx.payload.get("new_asset")
            or {
                "title": deliverable.get("title", f"{self.profile.app_name} deliverable"),
                "asset_type": deliverable.get("asset_type", "document"),
                "work_id": ctx.payload.get("work_id"),
            },
            "asset_id": ctx.payload.get("asset_id"),
            "storage_key": self._storage_key(deliverable),
            "provenance": self._provenance(deliverable),
        }

    def _storage_key(self, deliverable: dict) -> str:
        ref = deliverable.get("path") or deliverable.get("filename") or self.profile.key
        return f"placeholder:{self.profile.key}/{ref}"

    def _provenance(self, deliverable: dict) -> dict:
        prov = dict(deliverable.get("provenance", {}))
        prov.setdefault("kind", ProvenanceKind.MIXED.value)
        prov.setdefault("provider", self.profile.app_name)
        prov.setdefault("human_modifications", f"Authored in {self.profile.app_name}.")
        return prov

    def _import(self, ctx: AdapterContext) -> dict:
        deliverable = ctx.payload.get("deliverable", {})
        new_asset = ctx.payload.get("new_asset") or {
            "title": deliverable.get("title", f"{self.profile.app_name} deliverable"),
            "asset_type": deliverable.get("asset_type", "document"),
            "work_id": ctx.payload.get("work_id"),
            "story_world_id": ctx.payload.get("story_world_id"),
        }
        result = effects.attach_asset_version(
            ctx.session,
            asset_id=ctx.payload.get("asset_id"),
            new_asset=new_asset,
            owner_id=ctx.user.id if ctx.user else None,
            storage_key=self._storage_key(deliverable),
            mime_type=deliverable.get("mime_type", "application/octet-stream"),
            technical_metadata={"file_exchange": {"app": self.profile.key, "deliverable": deliverable}},
            provenance=self._provenance(deliverable),
            default_provenance_kind=ProvenanceKind.MIXED,
        )
        result["operation"] = "import_package"
        result["app"] = self.profile.key
        return result
