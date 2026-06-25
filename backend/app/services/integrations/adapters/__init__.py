"""Code-registered integration adapters.

Importing this package builds the adapter registry. Each adapter implements the
:class:`~app.services.integrations.base.IntegrationAdapter` interface and is
local-first: external network effects are recorded unless network access is
explicitly enabled, and all mutating/external operations pass through the
service-layer approval boundary.
"""
from __future__ import annotations

from app.services.integrations.adapters.comfyui import ComfyUIAdapter
from app.services.integrations.adapters.file_exchange import (
    DESKTOP_APP_PROFILES,
    FileExchangeAdapter,
)
from app.services.integrations.adapters.github import GitHubProjectAdapter
from app.services.integrations.adapters.n8n import N8nWebhookAdapter
from app.services.integrations.base import IntegrationAdapter

_ADAPTERS: dict[str, IntegrationAdapter] = {}


def _register(adapter: IntegrationAdapter) -> IntegrationAdapter:
    _ADAPTERS[adapter.key] = adapter
    return adapter


_register(N8nWebhookAdapter())
_register(ComfyUIAdapter())
_register(GitHubProjectAdapter())
for _profile in DESKTOP_APP_PROFILES:
    _register(FileExchangeAdapter(_profile))


def get_adapter(key: str | None) -> IntegrationAdapter | None:
    if not key:
        return None
    return _ADAPTERS.get(key)


def list_adapters() -> list[IntegrationAdapter]:
    return list(_ADAPTERS.values())


__all__ = [
    "ComfyUIAdapter",
    "DESKTOP_APP_PROFILES",
    "FileExchangeAdapter",
    "GitHubProjectAdapter",
    "N8nWebhookAdapter",
    "get_adapter",
    "list_adapters",
]
