"""Identity linking & member administration (Prompt 15).

Proves the operational identity bridge: admin link workflow + member self-service,
MCP mapping that rejects unlinked / disabled identities, and the security-event
trail (failed mapping, revoked-token use, disabled member, project-denied tool
call, suspicious repeated failures) plus the token audit trail.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.security import generate_brain_token, hash_brain_token
from app.models import (
    Author,
    BrainAccessToken,
    LibreChatIdentityLink,
    SecurityEvent,
    User,
    UserRole,
    Work,
)
from app.models.base import utcnow
from app.models.enums import (
    IdentityLinkStatus,
    MembershipStatus,
    ProjectRole,
    SecurityEventType,
)
from app.services import identity as identity_svc
from app.services.mcp.auth import sign_user_context

TOKEN = "test-mcp-service-token"


@pytest.fixture(autouse=True)
def _mcp_cfg(monkeypatch):
    monkeypatch.setattr("app.config.settings.mcp_service_token", TOKEN)
    monkeypatch.setattr("app.config.settings.mcp_enabled", True)


# --- helpers ---------------------------------------------------------------
def _user(session: Session, email: str, role: UserRole = UserRole.EDITOR, *, active: bool = True) -> User:
    from app.auth.security import hash_password

    u = User(email=email, full_name=email.split("@")[0], role=role,
             hashed_password=hash_password("pw"), is_active=active)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _link(session: Session, user: User, *, status: IdentityLinkStatus = IdentityLinkStatus.ACTIVE,
          email: str | None = None) -> LibreChatIdentityLink:
    link = identity_svc.link_user(
        session, supervoid_user_id=user.id, librechat_email=(email or user.email),
        verify=(status == IdentityLinkStatus.ACTIVE),
    )
    if status not in (IdentityLinkStatus.ACTIVE, IdentityLinkStatus.PENDING):
        link.status = status
    session.add(link)
    session.commit()
    return link


def _headers(email, *, user_id="lc-1", sign_email=None, role="USER", request_id="req-1"):
    sig = sign_user_context(TOKEN, user_id=user_id, email=(sign_email or email),
                            role=role, request_id=request_id)
    return {
        "X-SUPERVOID-Service-Token": TOKEN, "X-SUPERVOID-User-Id": user_id,
        "X-SUPERVOID-User-Email": email, "X-SUPERVOID-User-Role": role,
        "X-SUPERVOID-Request-Id": request_id, "X-SUPERVOID-User-Sig": sig,
    }


def _tools_list(client: TestClient, headers):
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=headers)


def _events(session: Session, event_type: SecurityEventType) -> list[SecurityEvent]:
    return list(session.exec(
        select(SecurityEvent).where(SecurityEvent.event_type == event_type)
    ).all())


def _work(session: Session) -> Work:
    a = Author(full_name="A")
    session.add(a)
    session.commit()
    session.refresh(a)
    w = Work(title="W", author_id=a.id)
    session.add(w)
    session.commit()
    session.refresh(w)
    return w


# === admin link workflow + member self-service =============================
def test_admin_links_member_and_member_sees_status(
    client: TestClient, editor_client: TestClient, session: Session, editor_user
) -> None:
    r = client.post("/api/identity-links", json={
        "supervoid_user_id": editor_user.id, "librechat_email": "ed@librechat.test",
        "verify": True,
    })
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "active" and r.json()["user_email"] == editor_user.email
    # admin sees it in the list
    assert any(l["supervoid_user_id"] == editor_user.id for l in client.get("/api/identity-links").json())
    # the member sees their own link via self-service
    me = editor_client.get("/api/identity-links/me").json()
    assert me["linked"] is True and me["status"] == "active"


def test_non_admin_cannot_manage_links(editor_client: TestClient, admin_user) -> None:
    assert editor_client.get("/api/identity-links").status_code == 403
    assert editor_client.post("/api/identity-links", json={
        "supervoid_user_id": admin_user.id, "librechat_email": "x@y.z"
    }).status_code == 403
    assert editor_client.get("/api/security-events").status_code == 403


def test_unlinked_member_self_service(client: TestClient, admin_user) -> None:
    # the admin themselves is not linked
    assert client.get("/api/identity-links/me").json()["linked"] is False


# === MCP mapping: rejects unlinked / disabled =============================
def test_mcp_rejects_unlinked_user(anon_client: TestClient, session: Session) -> None:
    _user(session, "nolink@s.test")  # exists, but no identity link
    r = _tools_list(anon_client, _headers("nolink@s.test"))
    assert r.status_code == 401
    assert _events(session, SecurityEventType.UNLINKED_USER)


def test_mcp_rejects_disabled_member(anon_client: TestClient, session: Session) -> None:
    u = _user(session, "disabled@s.test", active=False)
    _link(session, u)  # active link, but the SUPERVOID user is deactivated
    r = _tools_list(anon_client, _headers("disabled@s.test"))
    assert r.status_code == 401
    assert _events(session, SecurityEventType.DISABLED_MEMBER)


def test_mcp_mapping_failed_unknown_email(anon_client: TestClient, session: Session) -> None:
    r = _tools_list(anon_client, _headers("ghost@s.test"))
    assert r.status_code == 401
    assert _events(session, SecurityEventType.MAPPING_FAILED)


def test_mcp_invalid_signature(anon_client: TestClient, session: Session) -> None:
    u = _user(session, "real@s.test")
    _link(session, u)
    # sign a different email than the one sent → signature mismatch
    r = _tools_list(anon_client, _headers("real@s.test", sign_email="other@s.test"))
    assert r.status_code == 401
    assert _events(session, SecurityEventType.INVALID_SIGNATURE)


def test_mcp_disabled_link_rejected(anon_client: TestClient, session: Session) -> None:
    u = _user(session, "dlink@s.test")
    _link(session, u, status=IdentityLinkStatus.DISABLED)
    r = _tools_list(anon_client, _headers("dlink@s.test"))
    assert r.status_code == 401  # no ACTIVE link → unlinked
    assert _events(session, SecurityEventType.UNLINKED_USER)


def test_active_link_authenticates(anon_client: TestClient, session: Session) -> None:
    u = _user(session, "ok@s.test")
    _link(session, u)
    r = _tools_list(anon_client, _headers("ok@s.test"))
    assert r.status_code == 200 and "result" in r.json()


# === gateway token-use security events ====================================
def _brain_token(session: Session, user: User, *, revoked=False, expired=False) -> str:
    secret = generate_brain_token()
    tok = BrainAccessToken(
        user_id=user.id, name="t", token_hash=hash_brain_token(secret),
        token_prefix=secret[:12],
        revoked_at=(utcnow() if revoked else None),
        expires_at=(utcnow().replace(year=2000) if expired else None),
    )
    session.add(tok)
    session.commit()
    return secret


def test_revoked_token_use_records_event(anon_client: TestClient, session: Session) -> None:
    u = _user(session, "tok@s.test")
    secret = _brain_token(session, u, revoked=True)
    r = anon_client.get("/brain/v1/models", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 401
    assert _events(session, SecurityEventType.REVOKED_TOKEN_USE)


def test_expired_token_use_records_event(anon_client: TestClient, session: Session) -> None:
    u = _user(session, "tok2@s.test")
    secret = _brain_token(session, u, expired=True)
    r = anon_client.get("/brain/v1/models", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 401
    assert _events(session, SecurityEventType.EXPIRED_TOKEN_USE)


# === project-denied tool call =============================================
def test_project_denied_tool_records_event(anon_client: TestClient, session: Session) -> None:
    u = _user(session, "ed3@s.test", UserRole.EDITOR)
    _link(session, u)
    work = _work(session)  # the editor is NOT a member
    r = anon_client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "get_project_state", "arguments": {"work_id": work.id}},
    }, headers=_headers("ed3@s.test"))
    assert r.status_code == 200
    assert r.json()["result"]["isError"] is True
    denied = _events(session, SecurityEventType.PROJECT_DENIED)
    assert denied and denied[0].work_id == work.id


# === suspicious repeated failures =========================================
def test_repeated_failures_flagged(anon_client: TestClient, session: Session, monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.security_repeated_failure_threshold", 3)
    for _ in range(3):
        _tools_list(anon_client, _headers("burst@s.test"))  # unknown email → MAPPING_FAILED ×3
    assert _events(session, SecurityEventType.REPEATED_FAILURES)


# === token audit trail =====================================================
def test_token_lifecycle_audit(client: TestClient, session: Session) -> None:
    created = client.post("/api/brain-tokens", json={"name": "CI"}).json()
    tid = created["token"]["id"]
    client.post(f"/api/brain-tokens/{tid}/rotate")
    client.delete(f"/api/brain-tokens/{tid}")
    assert _events(session, SecurityEventType.TOKEN_CREATED)
    assert _events(session, SecurityEventType.TOKEN_ROTATED)
    assert _events(session, SecurityEventType.TOKEN_REVOKED)


# === disable blocks MCP (verify/disable lifecycle) ========================
def test_disable_link_blocks_mcp(anon_client: TestClient, session: Session) -> None:
    u = _user(session, "cycle@s.test")
    link = _link(session, u)
    assert _tools_list(anon_client, _headers("cycle@s.test")).status_code == 200
    identity_svc.disable_link(session, link, actor_id="admin")
    session.commit()
    assert _tools_list(anon_client, _headers("cycle@s.test")).status_code == 401
