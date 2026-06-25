"""Generic outbound webhook adapter (n8n and any webhook receiver).

Sends a structured JSON event to a configured webhook URL. The dispatch is an
external side effect, so it is gated behind approval and — local-first by
default — *recorded* rather than sent unless network access is enabled. The
optional bearer token is referenced from the environment and never persisted.
"""
from __future__ import annotations

from app.models.enums import IntegrationAdapterKind, IntegrationDirectionKind
from app.services.integrations.base import (
    AdapterContext,
    AdapterOperation,
    HealthReport,
    IntegrationAdapter,
    recorded_result,
)
from app.services.integrations import transport


class N8nWebhookAdapter(IntegrationAdapter):
    key = "n8n_webhook"
    kind = IntegrationAdapterKind.WEBHOOK
    name = "n8n webhook"
    description = (
        "Generic outbound webhook to an n8n workflow (or any webhook receiver). "
        "Sends structured JSON events; the bearer token is referenced from the "
        "environment, never stored."
    )
    required_config = ("webhook_url",)
    credential_names = ("auth_token",)
    operations = (
        AdapterOperation(
            key="send_event",
            name="Send event",
            summary="POST a JSON event to the configured webhook.",
            direction=IntegrationDirectionKind.OUTBOUND,
            external=True,
            touches_network=True,
            risk="high",
        ),
    )

    def _build_request(self, ctx: AdapterContext) -> dict:
        """The request that would be sent. The auth token is referenced by name
        only — its value never appears in the persisted request."""
        headers = {"Content-Type": "application/json"}
        if ctx.has_secret("auth_token"):
            headers["Authorization"] = "Bearer <auth_token from environment>"
        return {
            "method": "POST",
            "url": ctx.config.get("webhook_url"),
            "headers": headers,
            "body": {
                "event_type": ctx.payload.get("event_type", "supervoid.event"),
                "data": ctx.payload.get("data", {}),
            },
        }

    def health_check(self, ctx: AdapterContext) -> HealthReport:
        return self.base_health(ctx)

    def status(self, ctx: AdapterContext) -> dict:
        return {
            "adapter": self.key,
            "configured": bool(ctx.config.get("webhook_url")),
            "auth_token_present": ctx.has_secret("auth_token"),
        }

    def dry_run(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        return {
            "operation": op.key,
            "would_send": self._build_request(ctx),
            "note": "Dry-run: nothing was dispatched.",
        }

    def inbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        raise ValueError("The webhook adapter is outbound only.")

    def outbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        request = self._build_request(ctx)
        url = ctx.config.get("webhook_url")
        if not url:
            raise ValueError("No webhook_url configured.")
        if not ctx.allow_network:
            return recorded_result(
                request,
                "Network disabled (local-first): event recorded, not dispatched.",
            )
        headers = {"Content-Type": "application/json"}
        token = ctx.secret("auth_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        result = transport.post_json(url, request["body"], headers=headers)
        # Never echo the auth header back into the persisted result.
        result["request"] = request
        return result
