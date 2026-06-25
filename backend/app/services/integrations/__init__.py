"""The operational, local-first integration hub.

Code-registered adapters (n8n webhook, ComfyUI, GitHub project, desktop
file-exchange) implement a common :class:`IntegrationAdapter` interface; the
service layer persists every run and enforces an approval boundary that all
external mutations must pass through. Secure by construction: secrets live in
the environment (referenced by name), never in the database or API responses.
"""
from app.services.integrations.adapters import get_adapter, list_adapters
from app.services.integrations.base import (
    AdapterContext,
    AdapterOperation,
    HealthReport,
    IntegrationAdapter,
    recorded_result,
)
from app.services.integrations.service import (
    adapter_health,
    approve_run,
    config_status,
    execute_run,
    reject_run,
    request_operation,
)

__all__ = [
    "AdapterContext",
    "AdapterOperation",
    "HealthReport",
    "IntegrationAdapter",
    "adapter_health",
    "approve_run",
    "config_status",
    "execute_run",
    "get_adapter",
    "list_adapters",
    "recorded_result",
    "reject_run",
    "request_operation",
]
