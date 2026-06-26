"""Tests for Brain access-token management (private UI, JWT-authenticated).

Covers the lifecycle a user drives from the authenticated Studio UI: create
(secret shown exactly once), list (never leaks the secret), rotate (new secret,
hash changes, old secret dies), revoke (immediate, irreversible), and strict
per-user isolation — one user can never see or mutate another's tokens.
"""
from __future__ import annotations

from sqlmodel import Session, select

from app.auth.security import hash_brain_token
from app.models import BrainAccessToken


def _create(client, **body) -> dict:
    body.setdefault("name", "LibreChat")
    r = client.post("/api/brain-tokens", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# --- create -----------------------------------------------------------------
def test_create_returns_secret_once(client, session):
    payload = _create(client, name="My Laptop")
    assert payload["secret"].startswith("sk-brain-")
    meta = payload["token"]
    assert meta["name"] == "My Laptop"
    # The prefix is a non-secret display aid; the full secret is never the prefix.
    assert meta["token_prefix"] == payload["secret"][:12]
    assert "secret" not in meta
    # Only the hash is persisted — the plaintext is unrecoverable.
    row = session.get(BrainAccessToken, meta["id"])
    assert row is not None
    assert row.token_hash == hash_brain_token(payload["secret"])
    assert row.token_hash != payload["secret"]


def test_create_rejects_blank_name(client):
    r = client.post("/api/brain-tokens", json={"name": ""})
    assert r.status_code == 422


def test_create_with_expiry_and_restrictions(client, session):
    payload = _create(
        client,
        name="Scoped",
        expires_in_days=30,
        project_restrictions=[{"work_id": "w-1"}, {"story_world_id": "sw-9"}],
    )
    meta = payload["token"]
    assert meta["expires_at"] is not None
    assert {"work_id": "w-1", "story_world_id": None} in meta["project_restrictions"]
    row = session.get(BrainAccessToken, meta["id"])
    assert row.expires_at is not None
    assert len(row.project_restrictions) == 2


# --- list -------------------------------------------------------------------
def test_list_never_leaks_secret(client):
    _create(client, name="one")
    _create(client, name="two")
    r = client.get("/api/brain-tokens")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    for row in rows:
        assert "secret" not in row
        assert set(row) >= {"id", "name", "token_prefix", "created_at"}
    # Newest first.
    assert rows[0]["name"] == "two"


# --- rotate -----------------------------------------------------------------
def test_rotate_changes_secret_and_hash(client, session):
    created = _create(client, name="rotate-me")
    tid = created["token"]["id"]
    old_secret = created["secret"]
    old_hash = session.get(BrainAccessToken, tid).token_hash

    r = client.post(f"/api/brain-tokens/{tid}/rotate")
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["secret"] != old_secret
    assert new["token"]["id"] == tid  # same record, new secret

    session.expire_all()
    row = session.get(BrainAccessToken, tid)
    assert row.token_hash != old_hash
    assert row.token_hash == hash_brain_token(new["secret"])
    # The old secret no longer resolves to any token.
    assert (
        session.exec(
            select(BrainAccessToken).where(
                BrainAccessToken.token_hash == hash_brain_token(old_secret)
            )
        ).first()
        is None
    )
    # Rotation resets last-used so usage tracking restarts cleanly.
    assert row.last_used_at is None


def test_cannot_rotate_revoked_token(client):
    tid = _create(client, name="doomed")["token"]["id"]
    assert client.delete(f"/api/brain-tokens/{tid}").status_code == 204
    r = client.post(f"/api/brain-tokens/{tid}/rotate")
    assert r.status_code == 400


# --- revoke -----------------------------------------------------------------
def test_revoke_is_immediate_and_idempotent(client, session):
    tid = _create(client, name="kill")["token"]["id"]
    assert client.delete(f"/api/brain-tokens/{tid}").status_code == 204
    session.expire_all()
    assert session.get(BrainAccessToken, tid).revoked_at is not None
    # A second revoke is a harmless no-op (already revoked).
    assert client.delete(f"/api/brain-tokens/{tid}").status_code == 204
    # The revoked token surfaces in the list with its revoked timestamp.
    listed = {t["id"]: t for t in client.get("/api/brain-tokens").json()}
    assert listed[tid]["revoked_at"] is not None


# --- isolation --------------------------------------------------------------
def test_tokens_are_per_user_isolated(client, editor_client):
    """A token created by one user is invisible and immutable to another."""
    tid = _create(client, name="admin-only")["token"]["id"]

    # The editor's list does not include the admin's token.
    editor_rows = editor_client.get("/api/brain-tokens").json()
    assert all(t["id"] != tid for t in editor_rows)

    # The editor cannot rotate or revoke it — it simply does not exist for them.
    assert editor_client.post(f"/api/brain-tokens/{tid}/rotate").status_code == 404
    assert editor_client.delete(f"/api/brain-tokens/{tid}").status_code == 404


def test_requires_authentication(anon_client):
    assert anon_client.get("/api/brain-tokens").status_code == 401
    assert anon_client.post("/api/brain-tokens", json={"name": "x"}).status_code == 401
