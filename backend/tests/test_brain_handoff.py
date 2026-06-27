"""Context-aware Brain hand-off (Prompt 12): signed short-lived tokens, project
binding, permission enforcement, single-use consume, and the status panel.

Proves the security invariants: the redirect carries ONLY an opaque token (no
project content), the token is permission-gated, single-use, and expires; and an
unauthorised member cannot hand off a project they cannot view.
"""
from __future__ import annotations

import base64

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import BrainHandoff
from app.models.base import utcnow


def _author(client: TestClient) -> str:
    return client.post("/api/authors", json={"full_name": "Maker"}).json()["id"]


def _work(client: TestClient, **over) -> dict:
    payload = {"title": "W", "author_id": _author(client)}
    payload.update(over)
    r = client.post("/api/works", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _token_of(handoff_url: str) -> str:
    return handoff_url.split("token=", 1)[1]


# --- create -----------------------------------------------------------------
def test_handoff_creates_signed_binding(client: TestClient, session: Session) -> None:
    work = _work(client, title="SECRET_TITLE_XYZ", synopsis="confidential pitch")
    r = client.post("/api/brain/handoff",
                    json={"entity_type": "work", "entity_id": work["id"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["handoff_url"].startswith("/brain-handoff?token=")
    assert body["work_id"] == work["id"]
    assert body["conversation_id"]
    # a hand-off row + a bound conversation exist
    ho = session.exec(select(BrainHandoff)).first()
    assert ho is not None and ho.work_id == work["id"]


def test_token_carries_no_sensitive_data(client: TestClient) -> None:
    work = _work(client, title="SECRET_TITLE_XYZ", synopsis="confidential pitch")
    url = client.post("/api/brain/handoff",
                      json={"entity_type": "work", "entity_id": work["id"]}).json()["handoff_url"]
    token = _token_of(url)
    # nothing sensitive in the URL itself
    assert "SECRET_TITLE_XYZ" not in url and "confidential" not in url
    # and the decoded token is only <id>:<exp>:<sig>
    raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
    assert raw.count(":") == 2
    assert "SECRET_TITLE_XYZ" not in raw and "confidential" not in raw


def test_handoff_permission_enforced(client: TestClient, editor_client: TestClient) -> None:
    work = _work(client)  # owned by admin's context
    # a global editor with no project membership cannot hand off this project
    r = editor_client.post("/api/brain/handoff",
                           json={"entity_type": "work", "entity_id": work["id"]})
    assert r.status_code == 403


def test_handoff_unsupported_entity(client: TestClient) -> None:
    r = client.post("/api/brain/handoff",
                    json={"entity_type": "spaceship", "entity_id": "x"})
    assert r.status_code == 400


def test_handoff_entity_not_found(client: TestClient) -> None:
    r = client.post("/api/brain/handoff",
                    json={"entity_type": "work", "entity_id": "does-not-exist"})
    assert r.status_code == 404


# --- landing (consume) ------------------------------------------------------
def test_landing_consumes_once_and_redirects(client: TestClient) -> None:
    work = _work(client)
    url = client.post("/api/brain/handoff",
                      json={"entity_type": "work", "entity_id": work["id"]}).json()["handoff_url"]
    # first use: 303 -> LibreChat
    r = client.get(url, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/brain/"
    # second use: single-use -> safe error redirect
    r2 = client.get(url, follow_redirects=False)
    assert r2.status_code == 303
    assert "brain_handoff=error" in r2.headers["location"]


def test_landing_rejects_garbage_token(client: TestClient) -> None:
    r = client.get("/brain-handoff?token=not-a-real-token", follow_redirects=False)
    assert r.status_code == 303
    assert "brain_handoff=error" in r.headers["location"]


def test_landing_rejects_expired(client: TestClient, session: Session) -> None:
    from datetime import timedelta

    work = _work(client)
    url = client.post("/api/brain/handoff",
                      json={"entity_type": "work", "entity_id": work["id"]}).json()["handoff_url"]
    ho = session.exec(select(BrainHandoff)).first()
    ho.expires_at = utcnow().replace(tzinfo=None) - timedelta(minutes=5)
    session.add(ho)
    session.commit()
    r = client.get(url, follow_redirects=False)
    assert r.status_code == 303
    assert "brain_handoff=error" in r.headers["location"]


# --- status -----------------------------------------------------------------
def test_status_panel(client: TestClient) -> None:
    work = _work(client)
    client.post("/api/brain/handoff", json={"entity_type": "work", "entity_id": work["id"]})
    r = client.get("/api/brain/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active_project"]["work_id"] == work["id"]
    assert "state_version" in body
    assert body["model"]["provider"]  # model status present
    assert "compiler" in body and "head_sequence" in body["compiler"]
    assert isinstance(body["pending_proposals"], int)
    assert body["brain_url"] == "/brain/"
