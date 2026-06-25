"""Collaboration: project-scoped access control.

Two layers of tests:

* **Policy unit tests** drive ``app.services.policy`` directly against the
  ``session`` fixture — the precise truth table for global role + membership +
  ownership + scope.
* **API tests** exercise the user-management and collaboration endpoints and,
  crucially, prove a collaborator on one project cannot reach into another.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.security import create_access_token
from app.models import (
    Author,
    MembershipStatus,
    PermissionScope,
    ProjectMembership,
    ProjectRole,
    StoryWorld,
    User,
    UserRole,
    Work,
)
from app.services import policy

PS = PermissionScope


# --- helpers (unit level) --------------------------------------------------


def _user(session: Session, email: str, role: UserRole = UserRole.EDITOR) -> User:
    from app.auth.security import hash_password

    user = User(
        email=email,
        full_name=email.split("@")[0],
        role=role,
        hashed_password=hash_password("password"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _work(session: Session, **over) -> Work:
    author = Author(full_name="Maker")
    session.add(author)
    session.commit()
    session.refresh(author)
    work = Work(title="W", author_id=author.id, **over)
    session.add(work)
    session.commit()
    session.refresh(work)
    return work


def _world(session: Session, **over) -> StoryWorld:
    world = StoryWorld(name="World", slug=over.pop("slug", "world"), **over)
    session.add(world)
    session.commit()
    session.refresh(world)
    return world


def _member(
    session: Session,
    user: User,
    role: ProjectRole,
    *,
    work_id: str | None = None,
    story_world_id: str | None = None,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> ProjectMembership:
    m = ProjectMembership(
        user_id=user.id,
        work_id=work_id,
        story_world_id=story_world_id,
        role=role,
        status=status,
    )
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


# --- policy unit tests -----------------------------------------------------


def test_admin_global_role_is_superuser(session: Session) -> None:
    admin = _user(session, "admin2@x.test", UserRole.ADMIN)
    work = _work(session)
    # No membership at all, yet every scope is permitted.
    for scope in PermissionScope:
        assert policy.can(session, admin, scope, work_id=work.id)


def test_no_membership_means_no_access(session: Session) -> None:
    user = _user(session, "nobody@x.test")
    work = _work(session)
    assert not policy.can(session, user, PS.VIEW_PROJECT, work_id=work.id)
    assert policy.effective_role(session, user, work_id=work.id) is None


def test_viewer_can_only_view(session: Session) -> None:
    user = _user(session, "viewer@x.test")
    work = _work(session)
    _member(session, user, ProjectRole.VIEWER, work_id=work.id)
    assert policy.can(session, user, PS.VIEW_PROJECT, work_id=work.id)
    assert not policy.can(session, user, PS.EDIT_NARRATIVE, work_id=work.id)
    assert not policy.can(session, user, PS.MANAGE_COLLABORATORS, work_id=work.id)


def test_editor_can_edit_narrative_not_manage(session: Session) -> None:
    user = _user(session, "editor2@x.test")
    work = _work(session)
    _member(session, user, ProjectRole.EDITOR, work_id=work.id)
    assert policy.can(session, user, PS.EDIT_NARRATIVE, work_id=work.id)
    assert policy.can(session, user, PS.REVIEW, work_id=work.id)
    assert not policy.can(session, user, PS.MANAGE_COLLABORATORS, work_id=work.id)
    assert not policy.can(session, user, PS.PUBLISH, work_id=work.id)


def test_owner_has_every_scope(session: Session) -> None:
    user = _user(session, "owner@x.test")
    work = _work(session)
    _member(session, user, ProjectRole.OWNER, work_id=work.id)
    for scope in PermissionScope:
        assert policy.can(session, user, scope, work_id=work.id)


def test_world_membership_cascades_to_work(session: Session) -> None:
    world = _world(session)
    work = _work(session, story_world_id=world.id)
    user = _user(session, "director@x.test")
    _member(session, user, ProjectRole.DIRECTOR, story_world_id=world.id)
    # The work has no direct membership; access is inherited from the world.
    assert policy.can(session, user, PS.MANAGE_PRODUCTION, work_id=work.id)
    assert policy.can(session, user, PS.MANAGE_COLLABORATORS, work_id=work.id)
    assert policy.effective_role(session, user, work_id=work.id) == ProjectRole.DIRECTOR


def test_inactive_memberships_grant_nothing(session: Session) -> None:
    work = _work(session)
    for status in (
        MembershipStatus.INVITED,
        MembershipStatus.SUSPENDED,
        MembershipStatus.DECLINED,
        MembershipStatus.REVOKED,
    ):
        user = _user(session, f"{status.value}@x.test")
        _member(session, user, ProjectRole.OWNER, work_id=work.id, status=status)
        assert not policy.can(session, user, PS.VIEW_PROJECT, work_id=work.id)


def test_strongest_role_wins(session: Session) -> None:
    world = _world(session)
    work = _work(session, story_world_id=world.id)
    user = _user(session, "multi@x.test")
    _member(session, user, ProjectRole.VIEWER, work_id=work.id)
    _member(session, user, ProjectRole.DIRECTOR, story_world_id=world.id)
    assert policy.effective_role(session, user, work_id=work.id) == ProjectRole.DIRECTOR


# --- API helpers -----------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(user: dict) -> str:
    token, _ = create_access_token(subject=user["id"], role=user["role"])
    return token


def _mk_user(client: TestClient, email: str, role: str = "editor") -> dict:
    r = client.post(
        "/api/users",
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "password": "password123",
            "role": role,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _author_id(client: TestClient, name: str = "Maker") -> str:
    r = client.post("/api/authors", json={"full_name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _work_api(client: TestClient, **over) -> dict:
    payload = {"title": "W", "author_id": _author_id(client)}
    payload.update(over)
    r = client.post("/api/works", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _world_api(client: TestClient, **over) -> dict:
    payload = {"name": "World"}
    payload.update(over)
    r = client.post("/api/story-worlds", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# --- user management API ---------------------------------------------------


def test_user_management_is_admin_only(editor_client: TestClient) -> None:
    assert editor_client.get("/api/users").status_code == 403
    assert (
        editor_client.post(
            "/api/users",
            json={"email": "x@x.test", "full_name": "X", "password": "password123"},
        ).status_code
        == 403
    )


def test_user_crud_and_uniqueness(client: TestClient) -> None:
    user = _mk_user(client, "newbie@x.test")
    assert client.get(f"/api/users/{user['id']}").status_code == 200
    # Duplicate email -> 409.
    assert (
        client.post(
            "/api/users",
            json={
                "email": "newbie@x.test",
                "full_name": "Dup",
                "password": "password123",
            },
        ).status_code
        == 409
    )
    patched = client.patch(f"/api/users/{user['id']}", json={"role": "marketing"})
    assert patched.status_code == 200 and patched.json()["role"] == "marketing"

    assert client.post(f"/api/users/{user['id']}/deactivate").json()["is_active"] is False
    assert client.post(f"/api/users/{user['id']}/activate").json()["is_active"] is True


def test_cannot_deactivate_self(client: TestClient, admin_user) -> None:
    assert client.post(f"/api/users/{admin_user.id}/deactivate").status_code == 400


def test_password_rotation_self_admin_and_forbidden(client: TestClient) -> None:
    user = _mk_user(client, "rot@x.test")
    token = _token(user)
    # Self may rotate.
    assert (
        client.post(
            f"/api/users/{user['id']}/rotate-password",
            json={"new_password": "brandnew123"},
            headers=_auth(token),
        ).status_code
        == 200
    )
    # Admin may rotate anyone.
    assert (
        client.post(
            f"/api/users/{user['id']}/rotate-password",
            json={"new_password": "anotherone123"},
        ).status_code
        == 200
    )
    # A different non-admin may not.
    other = _mk_user(client, "other@x.test")
    assert (
        client.post(
            f"/api/users/{user['id']}/rotate-password",
            json={"new_password": "nope12345678"},
            headers=_auth(_token(other)),
        ).status_code
        == 403
    )


# --- invitations & membership lifecycle API --------------------------------


def test_invite_lists_and_resolves_user(client: TestClient) -> None:
    work = _work_api(client)
    invitee = _mk_user(client, "inv@x.test")
    r = client.post(
        f"/api/works/{work['id']}/members",
        json={"user_id": invitee["id"], "role": "editor"},
    )
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["status"] == "invited"
    assert m["role"] == "editor"
    assert m["user_email"] == "inv@x.test"

    # Duplicate live membership -> 409.
    assert (
        client.post(
            f"/api/works/{work['id']}/members",
            json={"user_id": invitee["id"], "role": "viewer"},
        ).status_code
        == 409
    )

    members = client.get(f"/api/works/{work['id']}/members").json()
    assert [mm["id"] for mm in members] == [m["id"]]


def test_accept_and_decline_restricted_to_invitee(client: TestClient) -> None:
    work = _work_api(client)
    user = _mk_user(client, "acc@x.test")
    token = _token(user)
    other = _mk_user(client, "stranger@x.test")

    m = client.post(
        f"/api/works/{work['id']}/members",
        json={"user_id": user["id"], "role": "viewer"},
    ).json()

    # A stranger cannot accept someone else's invitation.
    assert (
        client.post(
            f"/api/memberships/{m['id']}/accept", headers=_auth(_token(other))
        ).status_code
        == 403
    )
    accepted = client.post(f"/api/memberships/{m['id']}/accept", headers=_auth(token))
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "active"
    assert accepted.json()["accepted_at"] is not None
    # Re-accepting is rejected (no longer pending).
    assert (
        client.post(f"/api/memberships/{m['id']}/accept", headers=_auth(token)).status_code
        == 400
    )


def test_decline_invitation(client: TestClient) -> None:
    work = _work_api(client)
    user = _mk_user(client, "dec@x.test")
    token = _token(user)
    m = client.post(
        f"/api/works/{work['id']}/members",
        json={"user_id": user["id"], "role": "viewer"},
    ).json()
    declined = client.post(f"/api/memberships/{m['id']}/decline", headers=_auth(token))
    assert declined.status_code == 200 and declined.json()["status"] == "declined"


def test_membership_lifecycle_writes_audit(client: TestClient) -> None:
    work = _work_api(client)
    user = _mk_user(client, "life@x.test")
    token = _token(user)
    m = client.post(
        f"/api/works/{work['id']}/members",
        json={"user_id": user["id"], "role": "viewer"},
    ).json()

    assert client.patch(
        f"/api/memberships/{m['id']}", json={"role": "editor"}
    ).json()["role"] == "editor"
    client.post(f"/api/memberships/{m['id']}/accept", headers=_auth(token))
    assert (
        client.post(f"/api/memberships/{m['id']}/suspend").json()["status"] == "suspended"
    )
    assert (
        client.post(f"/api/memberships/{m['id']}/reactivate").json()["status"] == "active"
    )
    assert client.delete(f"/api/memberships/{m['id']}").status_code == 204

    audits = client.get(f"/api/memberships/{m['id']}/audits").json()
    actions = [a["action"] for a in audits]
    assert len(actions) == 6
    assert set(actions) == {
        "invited",
        "role_changed",
        "accepted",
        "suspended",
        "reactivated",
        "revoked",
    }
    assert actions[0] == "invited"


def test_world_membership_grants_work_access_via_api(client: TestClient) -> None:
    world = _world_api(client)
    work = _work_api(client, story_world_id=world["id"])
    user = _mk_user(client, "casc@x.test")
    token = _token(user)
    m = client.post(
        f"/api/story-worlds/{world['id']}/members",
        json={"user_id": user["id"], "role": "director"},
    ).json()
    client.post(f"/api/memberships/{m['id']}/accept", headers=_auth(token))

    # Director (world-level) inherits manage-collaborators on the work.
    assert client.get(f"/api/works/{work['id']}/members", headers=_auth(token)).status_code == 200
    invitee = _mk_user(client, "z@x.test")
    assert (
        client.post(
            f"/api/works/{work['id']}/members",
            json={"user_id": invitee["id"], "role": "viewer"},
            headers=_auth(token),
        ).status_code
        == 201
    )


def test_collaborator_cannot_reach_other_project(client: TestClient) -> None:
    work_a = _work_api(client, title="A")
    work_b = _work_api(client, title="B")
    boss = _mk_user(client, "boss@x.test")
    token = _token(boss)

    # Make boss OWNER of A and have them accept.
    ma = client.post(
        f"/api/works/{work_a['id']}/members",
        json={"user_id": boss["id"], "role": "owner"},
    ).json()
    client.post(f"/api/memberships/{ma['id']}/accept", headers=_auth(token))

    invitee = _mk_user(client, "newhand@x.test")
    # Boss can manage A.
    assert (
        client.post(
            f"/api/works/{work_a['id']}/members",
            json={"user_id": invitee["id"], "role": "viewer"},
            headers=_auth(token),
        ).status_code
        == 201
    )
    # Boss has no membership on B: cannot view or manage it.
    assert client.get(f"/api/works/{work_b['id']}/members", headers=_auth(token)).status_code == 403
    assert (
        client.post(
            f"/api/works/{work_b['id']}/members",
            json={"user_id": invitee["id"], "role": "viewer"},
            headers=_auth(token),
        ).status_code
        == 403
    )


def test_viewer_cannot_manage_collaborators_via_api(client: TestClient) -> None:
    work = _work_api(client)
    user = _mk_user(client, "justview@x.test")
    token = _token(user)
    m = client.post(
        f"/api/works/{work['id']}/members",
        json={"user_id": user["id"], "role": "viewer"},
    ).json()
    client.post(f"/api/memberships/{m['id']}/accept", headers=_auth(token))

    # A viewer can list members but cannot invite.
    assert client.get(f"/api/works/{work['id']}/members", headers=_auth(token)).status_code == 200
    invitee = _mk_user(client, "wannabe@x.test")
    assert (
        client.post(
            f"/api/works/{work['id']}/members",
            json={"user_id": invitee["id"], "role": "viewer"},
            headers=_auth(token),
        ).status_code
        == 403
    )


def test_my_projects(client: TestClient) -> None:
    work = _work_api(client)
    world = _world_api(client)
    user = _mk_user(client, "mp@x.test")
    token = _token(user)
    mw = client.post(
        f"/api/works/{work['id']}/members",
        json={"user_id": user["id"], "role": "writer"},
    ).json()
    client.post(
        f"/api/story-worlds/{world['id']}/members",
        json={"user_id": user["id"], "role": "director"},
    )

    # Both live memberships (one invited, one invited) show up by default.
    projects = client.get("/api/me/projects", headers=_auth(token)).json()
    assert len(projects) == 2

    client.post(f"/api/memberships/{mw['id']}/accept", headers=_auth(token))
    projects = client.get("/api/me/projects", headers=_auth(token)).json()
    work_proj = [p for p in projects if p["work_id"] == work["id"]][0]
    assert work_proj["role"] == "writer"
    assert work_proj["status"] == "active"
    assert work_proj["work_title"] == work["title"]
    assert "edit_narrative" in work_proj["scopes"]


def test_roles_catalog(client: TestClient) -> None:
    catalog = client.get("/api/collaboration/roles").json()
    by_role = {c["role"]: c["scopes"] for c in catalog}
    assert by_role["viewer"] == ["view_project"]
    assert "manage_collaborators" in by_role["owner"]
    assert "publish" in by_role["owner"]


def test_collaboration_requires_auth(anon_client: TestClient) -> None:
    assert anon_client.get("/api/me/projects").status_code == 401
    assert anon_client.get("/api/works/anything/members").status_code == 401
    assert anon_client.get("/api/users").status_code == 401
