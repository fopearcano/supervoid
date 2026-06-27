"""Observability & operational controls (Prompt 16).

Proves: the internal Ops aggregate + health states; Prometheus exposition;
admin-only / never-public surfaces; the operator controls actually take effect
(disable model requests → gateway 503; disable MCP → rejected; drain; mark project
cold; admin token revoke; replay); and log redaction.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.security import generate_brain_token, hash_brain_token
from app.models import (
    Author,
    BrainAccessToken,
    BrainSession,
    ProjectBrainState,
    SecurityEvent,
    User,
    UserRole,
    Work,
)
from app.models.enums import BrainSessionWarmth, SecurityEventType
from app.services.brain import ops, runtime
from app.services.mcp.auth import sign_user_context

TOKEN = "test-mcp-service-token"


@pytest.fixture(autouse=True)
def _reset_runtime(monkeypatch):
    """Runtime flags are process-global — reset around every test so flag state
    never bleeds into other suites."""
    runtime.reset()
    monkeypatch.setattr("app.config.settings.mcp_service_token", TOKEN)
    monkeypatch.setattr("app.config.settings.mcp_enabled", True)
    yield
    runtime.reset()


def _user(session: Session, email: str, role: UserRole = UserRole.EDITOR, *, active: bool = True) -> User:
    from app.auth.security import hash_password

    u = User(email=email, full_name=email.split("@")[0], role=role,
             hashed_password=hash_password("pw"), is_active=active)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _brain_token(session: Session, user: User) -> str:
    secret = generate_brain_token()
    session.add(BrainAccessToken(
        user_id=user.id, name="t", token_hash=hash_brain_token(secret),
        token_prefix=secret[:12],
    ))
    session.commit()
    return secret


# === aggregate + health ====================================================
def test_ops_status_shape_and_healthy(session: Session) -> None:
    s = ops.ops_status(session)
    for key in ("vllm", "gateway", "compiler", "sessions", "usage", "health",
                "active_conversations", "agent_failures", "mcp_failures",
                "pending_proposals", "librechat", "state_versions"):
        assert key in s, key
    assert s["vllm"]["gpu_utilisation"] is None  # not exposed by /health
    assert s["vllm"]["context_limit"] == 8192
    assert s["health"]["overall"] == "healthy"


def test_health_stale_when_project_stale(session: Session) -> None:
    session.add(ProjectBrainState(work_id="w-stale", stale=True, version=1))
    session.commit()
    h = ops.health_summary(session)
    assert h["components"]["compiler"] == "stale"
    assert h["overall"] == "stale"


def test_health_maintenance_when_draining(session: Session) -> None:
    runtime.set_drain(draining=True)
    h = ops.health_summary(session)
    assert h["components"]["gateway"] == "maintenance"
    assert h["overall"] == "maintenance"


def test_prometheus_text(session: Session) -> None:
    text = ops.prometheus_text(session)
    assert "brain_gateway_active_requests" in text
    assert "brain_compiler_lag" in text
    assert "# TYPE brain_prompt_tokens_total counter" in text


# === admin-only / never public =============================================
def test_ops_endpoints_admin_only(client: TestClient, editor_client: TestClient, anon_client: TestClient) -> None:
    assert client.get("/api/brain/ops/status").status_code == 200
    assert client.get("/api/brain/ops/metrics").status_code == 200
    assert editor_client.get("/api/brain/ops/status").status_code == 403
    assert editor_client.get("/api/brain/ops/metrics").status_code == 403
    assert anon_client.get("/api/brain/ops/status").status_code == 401


def test_metrics_is_prometheus_text(client: TestClient) -> None:
    r = client.get("/api/brain/ops/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "brain_gateway_active_requests" in r.text


# === controls take effect ==================================================
def test_disable_model_requests_blocks_gateway(client: TestClient, session: Session) -> None:
    user = _user(session, "gw@s.test")
    secret = _brain_token(session, user)
    body = {"model": "supervoid-brain", "messages": [{"role": "user", "content": "hi"}]}
    auth = {"Authorization": f"Bearer {secret}"}
    # works before disabling
    assert client.post("/brain/v1/chat/completions", json=body, headers=auth).status_code == 200
    # disable → 503 maintenance
    client.post("/api/brain/ops/controls/model-requests", json={"enabled": False})
    r = client.post("/brain/v1/chat/completions", json=body, headers=auth)
    assert r.status_code == 503
    # re-enable → works again
    client.post("/api/brain/ops/controls/model-requests", json={"enabled": True})
    assert client.post("/brain/v1/chat/completions", json=body, headers=auth).status_code == 200


def test_drain_blocks_new_requests(client: TestClient, session: Session) -> None:
    user = _user(session, "drain@s.test")
    secret = _brain_token(session, user)
    body = {"model": "supervoid-brain", "messages": [{"role": "user", "content": "hi"}]}
    auth = {"Authorization": f"Bearer {secret}"}
    client.post("/api/brain/ops/controls/drain", json={"draining": True})
    assert client.post("/brain/v1/chat/completions", json=body, headers=auth).status_code == 503


def test_disable_mcp_blocks_mcp(anon_client: TestClient, client: TestClient, session: Session) -> None:
    from app.services import identity as identity_svc

    u = _user(session, "mcp@s.test")
    identity_svc.link_user(session, supervoid_user_id=u.id, librechat_email=u.email, verify=True)
    session.commit()
    sig = sign_user_context(TOKEN, user_id="lc-1", email=u.email, role="USER", request_id="r1")
    headers = {
        "X-SUPERVOID-Service-Token": TOKEN, "X-SUPERVOID-User-Id": "lc-1",
        "X-SUPERVOID-User-Email": u.email, "X-SUPERVOID-User-Role": "USER",
        "X-SUPERVOID-Request-Id": "r1", "X-SUPERVOID-User-Sig": sig,
    }
    list_rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert anon_client.post("/mcp", json=list_rpc, headers=headers).status_code == 200
    client.post("/api/brain/ops/controls/mcp", json={"enabled": False})
    assert anon_client.post("/mcp", json=list_rpc, headers=headers).status_code == 401


def test_mark_project_cold(client: TestClient, session: Session) -> None:
    a = Author(full_name="A"); session.add(a); session.commit(); session.refresh(a)
    w = Work(title="W", author_id=a.id); session.add(w); session.commit(); session.refresh(w)
    from app.models import BrainConversation

    conv = BrainConversation(owner_user_id="u1", work_id=w.id)
    session.add(conv); session.commit(); session.refresh(conv)
    session.add(BrainSession(conversation_id=conv.id, work_id=w.id, warmth=BrainSessionWarmth.HOT))
    session.commit()
    r = client.post(f"/api/brain/ops/projects/{w.id}/cold")
    assert r.status_code == 200 and r.json()["marked"] == 1
    sess = session.exec(select(BrainSession).where(BrainSession.work_id == w.id)).first()
    assert sess.warmth == BrainSessionWarmth.COLD


def test_admin_revoke_any_token(client: TestClient, session: Session) -> None:
    user = _user(session, "rev@s.test")
    session.add(BrainAccessToken(user_id=user.id, name="t", token_hash="h" * 64, token_prefix="p"))
    session.commit()
    tok = session.exec(select(BrainAccessToken)).first()
    r = client.post(f"/api/brain/ops/tokens/{tok.id}/revoke")
    assert r.status_code == 200 and r.json()["revoked_at"] is not None
    session.refresh(tok)
    assert tok.revoked_at is not None
    assert session.exec(
        select(SecurityEvent).where(SecurityEvent.event_type == SecurityEventType.TOKEN_REVOKED)
    ).first() is not None


def test_replay_events_control(client: TestClient) -> None:
    r = client.post("/api/brain/ops/events/replay", json={})
    assert r.status_code == 200 and "requeued" in r.json()


# === redaction =============================================================
def test_log_redaction() -> None:
    from app.utils.logging import redact_log

    out = redact_log({
        "authorization": "Bearer abc", "password": "hunter2", "api_key": "sk-x",
        "prompt": "private prompt text", "contract": "secret clause",
        "model": "supervoid-brain", "latency_ms": 12,
    })
    assert out["authorization"] == "[redacted]"
    assert out["password"] == "[redacted]"
    assert out["api_key"] == "[redacted]"
    assert out["prompt"] == "[redacted]"
    assert out["contract"] == "[redacted]"
    assert out["model"] == "supervoid-brain" and out["latency_ms"] == 12
