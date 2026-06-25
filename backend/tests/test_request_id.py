"""Request-id middleware behaviour."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def test_request_id_header_minted_when_absent(anon_client: TestClient) -> None:
    r = anon_client.get("/api/health")
    rid = r.headers.get("X-Request-ID")
    assert rid is not None
    assert UUID_RE.match(rid)


def test_request_id_passthrough_when_supplied(anon_client: TestClient) -> None:
    r = anon_client.get(
        "/api/health", headers={"X-Request-ID": "external-correlation-1"}
    )
    assert r.headers["X-Request-ID"] == "external-correlation-1"


def test_request_id_present_on_404(anon_client: TestClient) -> None:
    r = anon_client.get("/api/manuscripts/no-such-id")
    assert r.status_code == 404
    assert "X-Request-ID" in r.headers


def test_request_id_present_on_422(anon_client: TestClient) -> None:
    r = anon_client.get("/api/authors?limit=0")
    assert r.status_code == 422
    assert "X-Request-ID" in r.headers


def test_error_envelope_on_404(anon_client: TestClient) -> None:
    """Every HTTPException body carries the same {detail, request_id} envelope,
    and the body's request_id matches the response header."""
    r = anon_client.get("/api/manuscripts/no-such-id")
    assert r.status_code == 404
    body = r.json()
    assert body["detail"] == "Manuscript not found"
    assert body["request_id"] == r.headers["X-Request-ID"]


def test_error_envelope_on_422(anon_client: TestClient) -> None:
    """Validation failures keep a string ``detail`` plus structured ``errors``
    and the shared request_id."""
    r = anon_client.get("/api/authors?limit=0")
    assert r.status_code == 422
    body = r.json()
    assert isinstance(body["detail"], str)
    assert isinstance(body["errors"], list) and body["errors"]
    assert body["request_id"] == r.headers["X-Request-ID"]


def test_error_envelope_preserves_auth_header(anon_client: TestClient) -> None:
    """A 401 still advertises the auth scheme and carries the envelope."""
    r = anon_client.get("/api/agents")
    assert r.status_code == 401
    assert "www-authenticate" in {k.lower() for k in r.headers}
    assert r.json()["request_id"] == r.headers["X-Request-ID"]
