"""Permission + CRUD tests for the Brain API (``/api/brain``).

Verifies user/project permissions apply: conversation owner isolation, scope
gating for memory and decisions, admin-only events/revisions, and that events
are append-only (no create endpoint).
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session


def _second_user_token(session: Session, *, email: str = "mallory@supervoid.test"):
    from app.auth.security import create_access_token, hash_password
    from app.models import User, UserRole

    user = User(
        email=email, full_name="Mallory", role=UserRole.EDITOR,
        hashed_password=hash_password("password"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    token, _ = create_access_token(subject=user.id, role=user.role.value)
    return user, token


def _grant_membership(session: Session, *, user_id: str, work_id: str, role=None):
    from app.models import MembershipStatus, ProjectMembership, ProjectRole

    membership = ProjectMembership(
        user_id=user_id, work_id=work_id,
        role=role or ProjectRole.EDITOR, status=MembershipStatus.ACTIVE,
    )
    session.add(membership)
    session.commit()


def _make_work(session: Session, *, title: str = "Brain Work") -> str:
    """A real Work — FK constraints are enforced on the test engine."""
    from app.models import Author, Work

    author = Author(full_name="A. Author")
    session.add(author)
    session.commit()
    session.refresh(author)
    work = Work(title=title, author_id=author.id)
    session.add(work)
    session.commit()
    session.refresh(work)
    return work.id


# --- auth ------------------------------------------------------------------
def test_brain_requires_auth(anon_client: TestClient) -> None:
    assert anon_client.get("/api/brain/conversations").status_code == 401


# --- conversation owner isolation ------------------------------------------
def test_conversation_owner_isolation(
    editor_client: TestClient, anon_client: TestClient, session: Session
) -> None:
    created = editor_client.post(
        "/api/brain/conversations", json={"title": "Editor's chat"}
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]

    _mallory, token = _second_user_token(session)
    anon_client.headers["Authorization"] = f"Bearer {token}"

    # A different, non-admin user cannot read, message, or list it.
    assert anon_client.get(f"/api/brain/conversations/{cid}").status_code == 403
    assert anon_client.post(
        f"/api/brain/conversations/{cid}/messages",
        json={"role": "user", "content": "hi"},
    ).status_code == 403
    assert anon_client.get("/api/brain/conversations").json() == []

    # The owner can.
    assert editor_client.get(f"/api/brain/conversations/{cid}").status_code == 200
    listed = editor_client.get("/api/brain/conversations").json()
    assert [c["id"] for c in listed] == [cid]


def test_message_append_and_list(editor_client: TestClient) -> None:
    cid = editor_client.post("/api/brain/conversations", json={}).json()["id"]
    r = editor_client.post(
        f"/api/brain/conversations/{cid}/messages",
        json={"role": "user", "content": "first"},
    )
    assert r.status_code == 201, r.text
    editor_client.post(
        f"/api/brain/conversations/{cid}/messages",
        json={"role": "assistant", "content": "second", "provider": "vllm"},
    )
    msgs = editor_client.get(f"/api/brain/conversations/{cid}/messages").json()
    assert [m["content"] for m in msgs] == ["first", "second"]


# --- events + revisions are admin-only, append-only ------------------------
def test_events_and_revisions_admin_only(
    client: TestClient, editor_client: TestClient
) -> None:
    assert editor_client.get("/api/brain/events").status_code == 403
    assert editor_client.get("/api/brain/revisions").status_code == 403
    assert client.get("/api/brain/events").status_code == 200
    assert client.get("/api/brain/revisions").status_code == 200
    # Append-only: there is no create endpoint for events.
    assert client.post("/api/brain/events", json={}).status_code == 405


# --- studio state read is available to any authed user ---------------------
def test_studio_state_read_empty(editor_client: TestClient) -> None:
    r = editor_client.get("/api/brain/state/studio")
    assert r.status_code == 200
    assert r.json() is None  # nothing compiled yet


# --- memory: studio is admin-only to write, readable by all authed ---------
def test_studio_memory_admin_only_write(
    client: TestClient, editor_client: TestClient
) -> None:
    body = {"scope": "studio", "kind": "fact", "content": "The studio favours serifs."}
    assert editor_client.post("/api/brain/memory", json=body).status_code == 403
    assert client.post("/api/brain/memory", json=body).status_code == 201
    # any authenticated user may read studio memory
    r = editor_client.get("/api/brain/memory", params={"scope": "studio"})
    assert r.status_code == 200 and len(r.json()) == 1


# --- memory: project write gated by membership -----------------------------
def test_project_memory_requires_membership(
    client: TestClient, editor_client: TestClient, session: Session, editor_user
) -> None:
    work_id = _make_work(session, title="Memory Work")
    body = {"scope": "project", "kind": "fact", "content": "Cover is teal.", "work_id": work_id}

    # No membership -> forbidden; admin bypass -> allowed.
    assert editor_client.post("/api/brain/memory", json=body).status_code == 403
    assert client.post("/api/brain/memory", json=body).status_code == 201

    # Grant the editor an active membership -> now allowed (EDITOR has EDIT_NARRATIVE).
    _grant_membership(session, user_id=editor_user.id, work_id=work_id)
    assert editor_client.post("/api/brain/memory", json=body).status_code == 201
    # ...and may read the project's memory.
    r = editor_client.get(
        "/api/brain/memory", params={"scope": "project", "work_id": work_id}
    )
    assert r.status_code == 200 and len(r.json()) >= 2


# --- memory: member scope is private ---------------------------------------
def test_member_memory_is_private(
    editor_client: TestClient, anon_client: TestClient, session: Session
) -> None:
    body = {"scope": "member", "kind": "preference", "content": "Prefers dark UI."}
    assert editor_client.post("/api/brain/memory", json=body).status_code == 201

    _mallory, token = _second_user_token(session)
    anon_client.headers["Authorization"] = f"Bearer {token}"
    # Each member only sees their own member-scoped memory.
    assert len(editor_client.get("/api/brain/memory", params={"scope": "member"}).json()) == 1
    assert anon_client.get("/api/brain/memory", params={"scope": "member"}).json() == []

    # Writing member memory for someone else is forbidden.
    other = {"scope": "member", "kind": "preference", "content": "x", "member_user_id": "someone-else"}
    assert editor_client.post("/api/brain/memory", json=other).status_code == 403


# --- decisions: studio approval is admin-only ------------------------------
def test_decision_studio_approval_admin_only(
    client: TestClient, editor_client: TestClient
) -> None:
    created = editor_client.post(
        "/api/brain/decisions",
        json={"scope": "studio", "subject": "House style", "decision": "EB Garamond"},
    )
    assert created.status_code == 201, created.text
    did = created.json()["id"]
    assert created.json()["status"] == "proposed"

    # Proposer (non-admin) cannot approve a studio decision.
    assert editor_client.post(f"/api/brain/decisions/{did}/approve").status_code == 403
    approved = client.post(f"/api/brain/decisions/{did}/approve")
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    # Re-approving a non-proposed decision conflicts.
    assert client.post(f"/api/brain/decisions/{did}/approve").status_code == 409


# --- decisions: project propose/approve gated by membership ----------------
def test_decision_project_requires_membership(
    editor_client: TestClient, session: Session, editor_user
) -> None:
    work_id = _make_work(session, title="Decision Work")
    body = {"scope": "project", "subject": "Panel count", "decision": "6 per page", "work_id": work_id}

    # No membership -> cannot even propose (needs VIEW_PROJECT).
    assert editor_client.post("/api/brain/decisions", json=body).status_code == 403

    _grant_membership(session, user_id=editor_user.id, work_id=work_id)
    created = editor_client.post("/api/brain/decisions", json=body)
    assert created.status_code == 201, created.text
    did = created.json()["id"]
    # EDITOR has APPROVE on the project, so the member may approve.
    assert editor_client.post(f"/api/brain/decisions/{did}/approve").status_code == 200
