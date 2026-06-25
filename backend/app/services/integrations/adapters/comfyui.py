"""ComfyUI adapter — local image/video generation backend.

Capabilities: queue a workflow, read queue/history status, attach a generated
output to an Asset (creating a version + AI provenance), and import a workflow's
metadata as a provenance record. Full dry-run support throughout. No assumption
is made that ComfyUI is running: queueing is recorded unless network access is
enabled, and status reads degrade gracefully to an "offline" result.
"""
from __future__ import annotations

from app.models.enums import (
    IntegrationAdapterKind,
    IntegrationDirectionKind,
    IntegrationHealthStatus,
    ProvenanceKind,
)
from app.services.integrations import effects, transport
from app.services.integrations.base import (
    AdapterContext,
    AdapterOperation,
    HealthReport,
    IntegrationAdapter,
    recorded_result,
)


class ComfyUIAdapter(IntegrationAdapter):
    key = "comfyui"
    kind = IntegrationAdapterKind.COMFYUI
    name = "ComfyUI"
    description = (
        "Local ComfyUI generation backend: queue workflows, read status/history, "
        "attach generated outputs to assets and import workflow provenance. "
        "Local-first: never assumes ComfyUI is running."
    )
    required_config = ("base_url",)
    credential_names = ()  # ComfyUI is typically local and unauthenticated
    operations = (
        AdapterOperation(
            key="queue_workflow",
            name="Queue workflow",
            summary="Submit a ComfyUI workflow graph for generation.",
            direction=IntegrationDirectionKind.OUTBOUND,
            external=True,
            touches_network=True,
            risk="medium",
        ),
        AdapterOperation(
            key="query_status",
            name="Query status",
            summary="Read the status of a queued prompt.",
            direction=IntegrationDirectionKind.INBOUND,
            touches_network=True,
        ),
        AdapterOperation(
            key="query_history",
            name="Query history",
            summary="Read recent generation history.",
            direction=IntegrationDirectionKind.INBOUND,
            touches_network=True,
        ),
        AdapterOperation(
            key="attach_output_to_asset",
            name="Attach output to asset",
            summary="Create an asset version from a generated output, with AI provenance.",
            direction=IntegrationDirectionKind.INBOUND,
            mutating=True,
            risk="medium",
        ),
        AdapterOperation(
            key="import_workflow_metadata",
            name="Import workflow metadata",
            summary="Record an AI provenance entry from a ComfyUI workflow.",
            direction=IntegrationDirectionKind.INBOUND,
            mutating=True,
        ),
    )

    # --- health / status ---------------------------------------------------

    def health_check(self, ctx: AdapterContext) -> HealthReport:
        report = self.base_health(ctx)
        if report.status != IntegrationHealthStatus.UNKNOWN or not ctx.allow_network:
            return report
        # Network allowed and configured: probe liveness without failing hard.
        base_url = ctx.config.get("base_url")
        try:
            transport.get_json(f"{base_url.rstrip('/')}/system_stats")
            report.status = IntegrationHealthStatus.HEALTHY
            report.detail = "ComfyUI responded to /system_stats."
            report.checked_live = True
        except Exception:  # noqa: BLE001 - liveness probe must never raise
            report.status = IntegrationHealthStatus.UNREACHABLE
            report.detail = "Configured but ComfyUI did not respond."
            report.checked_live = True
        return report

    def status(self, ctx: AdapterContext) -> dict:
        return {
            "adapter": self.key,
            "base_url": ctx.config.get("base_url"),
            "queue": "unknown (not polled)",
        }

    # --- operations --------------------------------------------------------

    def dry_run(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        if op.key == "queue_workflow":
            return {
                "operation": op.key,
                "would_queue": self._queue_request(ctx),
                "note": "Dry-run: workflow not submitted.",
            }
        if op.key in ("query_status", "query_history"):
            return {"operation": op.key, "would_read": self._read_request(op, ctx)}
        if op.key == "attach_output_to_asset":
            return {
                "operation": op.key,
                "would_create": self._attach_preview(ctx),
                "note": "Dry-run: no asset version created.",
            }
        if op.key == "import_workflow_metadata":
            return {
                "operation": op.key,
                "would_record": self._provenance_from_payload(ctx),
                "note": "Dry-run: no provenance recorded.",
            }
        return {"operation": op.key, "note": "Dry-run."}

    def outbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        # Only queue_workflow is outbound.
        request = self._queue_request(ctx)
        base_url = ctx.config.get("base_url")
        if not base_url:
            raise ValueError("No base_url configured for ComfyUI.")
        if not ctx.allow_network:
            result = recorded_result(
                request,
                "Network disabled (local-first): workflow recorded, not queued.",
            )
            result["prompt_id"] = f"recorded-{ctx.payload.get('client_id', 'local')}"
            return result
        return transport.post_json(
            f"{base_url.rstrip('/')}/prompt", request["body"]
        )

    def inbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        if op.key == "query_status":
            return self._query(op, ctx)
        if op.key == "query_history":
            return self._query(op, ctx)
        if op.key == "attach_output_to_asset":
            return self._attach_output(ctx)
        if op.key == "import_workflow_metadata":
            return self._import_metadata(ctx)
        raise ValueError(f"Unsupported ComfyUI operation '{op.key}'.")

    # --- helpers -----------------------------------------------------------

    def _queue_request(self, ctx: AdapterContext) -> dict:
        return {
            "method": "POST",
            "url": f"{(ctx.config.get('base_url') or '').rstrip('/')}/prompt",
            "body": {
                "prompt": ctx.payload.get("workflow", {}),
                "client_id": ctx.payload.get("client_id", "supervoid"),
            },
        }

    def _read_request(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        base = (ctx.config.get("base_url") or "").rstrip("/")
        if op.key == "query_status":
            prompt_id = ctx.payload.get("prompt_id", "")
            return {"method": "GET", "url": f"{base}/history/{prompt_id}"}
        return {"method": "GET", "url": f"{base}/history"}

    def _query(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        if not ctx.allow_network:
            return {
                "operation": op.key,
                "reachable": False,
                "items": [],
                "note": "ComfyUI not polled (local-first); assume offline.",
            }
        request = self._read_request(op, ctx)
        result = transport.get_json(request["url"])
        result["operation"] = op.key
        return result

    def _attach_preview(self, ctx: AdapterContext) -> dict:
        output = ctx.payload.get("output", {})
        return {
            "asset_id": ctx.payload.get("asset_id"),
            "new_asset": ctx.payload.get("new_asset"),
            "storage_key": self._storage_key(ctx),
            "mime_type": output.get("mime_type", "image/png"),
            "provenance": self._provenance_from_payload(ctx),
        }

    def _storage_key(self, ctx: AdapterContext) -> str:
        output = ctx.payload.get("output", {})
        ref = output.get("filename") or output.get("url") or ctx.payload.get(
            "prompt_id", "output"
        )
        return f"placeholder:comfyui/{ref}"

    def _provenance_from_payload(self, ctx: AdapterContext) -> dict:
        prov = dict(ctx.payload.get("provenance", {}))
        prov.setdefault("kind", ProvenanceKind.AI_GENERATED.value)
        prov.setdefault("provider", "comfyui")
        if "workflow_id" in ctx.payload:
            prov.setdefault("generating_workflow", str(ctx.payload["workflow_id"]))
        return prov

    def _attach_output(self, ctx: AdapterContext) -> dict:
        output = ctx.payload.get("output", {})
        return effects.attach_asset_version(
            ctx.session,
            asset_id=ctx.payload.get("asset_id"),
            new_asset=ctx.payload.get("new_asset"),
            owner_id=ctx.user.id if ctx.user else None,
            storage_key=self._storage_key(ctx),
            mime_type=output.get("mime_type", "image/png"),
            technical_metadata={"comfyui_output": output},
            provenance=self._provenance_from_payload(ctx),
            default_provenance_kind=ProvenanceKind.AI_GENERATED,
        )

    def _import_metadata(self, ctx: AdapterContext) -> dict:
        asset_version_id = ctx.payload.get("asset_version_id")
        if not asset_version_id:
            raise ValueError("asset_version_id is required to import provenance.")
        data = self._provenance_from_payload(ctx)
        if "workflow" in ctx.payload:
            data.setdefault("settings", {})
            data["settings"] = {**data["settings"], "workflow": ctx.payload["workflow"]}
        return effects.record_provenance(
            ctx.session,
            asset_version_id=asset_version_id,
            data=data,
            owner_id=ctx.user.id if ctx.user else None,
            default_kind=ProvenanceKind.AI_GENERATED,
        )
