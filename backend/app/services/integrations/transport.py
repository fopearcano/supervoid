"""Thin HTTP transport for adapters, used only when network access is enabled.

By default the hub is local-first and outbound network effects are *recorded*
rather than dispatched (see the adapters). When ``integrations_allow_network``
is set, adapters call these helpers to perform the real request. Responses are
returned in a uniform, redaction-friendly shape; failures raise so the service
layer records the run as FAILED.
"""
from __future__ import annotations

from typing import Optional

from app.config import settings


def _client():
    import httpx  # imported lazily so the dependency is only needed live

    return httpx.Client(timeout=settings.integrations_request_timeout)


def post_json(url: str, body: dict, *, headers: Optional[dict] = None) -> dict:
    with _client() as client:
        response = client.post(url, json=body, headers=headers or {})
        return _shape(response)


def get_json(url: str, *, headers: Optional[dict] = None, params: Optional[dict] = None) -> dict:
    with _client() as client:
        response = client.get(url, headers=headers or {}, params=params or {})
        return _shape(response)


def _shape(response) -> dict:
    content_type = response.headers.get("content-type", "")
    try:
        payload = response.json() if "application/json" in content_type else response.text
    except ValueError:
        payload = response.text
    return {
        "mode": "dispatched",
        "dispatched": True,
        "status_code": response.status_code,
        "ok": response.is_success,
        "response": payload,
    }
