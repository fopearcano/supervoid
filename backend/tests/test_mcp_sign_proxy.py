"""The MCP signing shim (deploy/brain/sign-proxy) must produce EXACTLY what the
SUPERVOID backend verifies in app/services/mcp/auth.py.

The dangerous failure mode is a signature mismatch — the shim signing a slightly
different canonical string than the backend recomputes, which would silently
break every tool call. These tests pin the contract:

  * compute_signature == backend sign_user_context (over the NORMALISED email);
  * the email-normalisation edge (mixed case + whitespace) still verifies;
  * build_forward_headers strips any client-supplied service token / signature
    and injects the shim's own, normalises the email, and drops hop-by-hop;
  * headers the shim emits are accepted end-to-end by the real authenticate().
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import httpx
import pytest
from sqlmodel import Session
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from app.models import User, UserRole
from app.services.mcp.auth import (
    H_EMAIL,
    H_REQUEST_ID,
    H_ROLE,
    H_SERVICE,
    H_SIG,
    H_USER_ID,
    MCPAuthError,
    authenticate,
    sign_user_context,
)

TOKEN = "test-mcp-service-token"


def _load_shim():
    path = Path(__file__).resolve().parents[2] / "deploy" / "brain" / "sign-proxy" / "sign_proxy.py"
    assert path.exists(), f"shim not found at {path}"
    spec = importlib.util.spec_from_file_location("supervoid_sign_proxy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shim = _load_shim()


@pytest.fixture(autouse=True)
def _configure_mcp(monkeypatch):
    monkeypatch.setattr("app.config.settings.mcp_service_token", TOKEN)
    monkeypatch.setattr("app.config.settings.mcp_enabled", True)
    # The shim reads the OS environment (it is a standalone process), not settings.
    monkeypatch.setenv("MCP_SERVICE_TOKEN", TOKEN)


def _upstream_app(captured, response_factory):
    """A real ASGI app standing in for the SUPERVOID /mcp backend. Captures the
    request the shim forwarded and returns the factory's response."""

    async def endpoint(request):
        captured["headers"] = Headers(dict(request.headers))
        captured["body"] = await request.body()
        return response_factory()

    return Starlette(
        routes=[Route("/mcp", endpoint, methods=["GET", "POST", "DELETE"])]
    )


async def _drive(response_factory, *, method="POST", headers=None, content=b"{}"):
    """Drive the shim ASGI app in-process, forwarding to a real ASGI upstream.

    Exercises the actual proxy() path — header injection + true streaming on both
    hops — not just the pure helpers. Returns (client_response, captured); on the
    fail-closed path the upstream is never hit so captured stays empty.
    """
    captured = {}
    upstream = _upstream_app(captured, response_factory)
    # The shim addresses an absolute URL; ASGITransport routes by path (/mcp) and
    # ignores the host, so the default upstream URL is fine here.
    shim.app.state.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=upstream))
    try:
        transport = httpx.ASGITransport(app=shim.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://shim") as c:
            r = await c.request(method, "/mcp", headers=headers or {}, content=content)
        return r, captured
    finally:
        await shim.app.state.client.aclose()


def _linked_user(session: Session, email: str, role: UserRole = UserRole.ADMIN) -> User:
    from app.auth.security import hash_password
    from app.services import identity as identity_svc

    u = User(email=email, full_name=email.split("@")[0], role=role,
             hashed_password=hash_password("pw"))
    session.add(u)
    session.commit()
    session.refresh(u)
    identity_svc.link_user(session, supervoid_user_id=u.id, librechat_email=email, verify=True)
    session.commit()
    return u


# --- signing parity ---------------------------------------------------------

def test_canonical_and_signature_match_backend():
    kwargs = dict(user_id="lc-1", email="alice@studio.test", role="USER", request_id="req-1")
    assert shim.canonical_user_context(**kwargs) == "lc-1\nalice@studio.test\nUSER\nreq-1"
    # Backend signs the (already-normalised) email; shim normalises internally.
    assert shim.compute_signature(TOKEN, **kwargs) == sign_user_context(TOKEN, **kwargs)


def test_signature_matches_after_email_normalisation():
    """A mixed-case / padded email must still verify: the backend lower-strips it
    before recomputing the expected signature, so the shim must sign the same."""
    raw = "  Alice@Studio.TEST  "
    norm = "alice@studio.test"
    shim_sig = shim.compute_signature(
        TOKEN, user_id="lc-1", email=raw, role="USER", request_id="req-1"
    )
    backend_expected = sign_user_context(
        TOKEN, user_id="lc-1", email=norm, role="USER", request_id="req-1"
    )
    assert shim_sig == backend_expected


def test_different_token_yields_different_signature():
    a = shim.compute_signature("token-a", user_id="u", email="e@x.t", role="USER", request_id="r")
    b = shim.compute_signature("token-b", user_id="u", email="e@x.t", role="USER", request_id="r")
    assert a != b


# --- header construction ----------------------------------------------------

def test_build_forward_headers_strips_client_supplied_and_injects():
    incoming = Headers(
        {
            # An attacker-controlled client tries to smuggle its own credential.
            "X-SUPERVOID-Service-Token": "attacker-token",
            "X-SUPERVOID-User-Sig": "deadbeef",
            "X-SUPERVOID-User-Id": "lc-9",
            "X-SUPERVOID-User-Email": "Bob@Studio.TEST",
            "X-SUPERVOID-User-Role": "ADMIN",
            "X-SUPERVOID-Request-Id": "req-9",
            "Content-Type": "application/json",
            "Mcp-Session-Id": "sess-123",
            "Host": "sign-proxy:8092",
        }
    )
    fwd = shim.build_forward_headers(incoming, TOKEN)

    # The shim's own credential + a correct signature replace anything supplied.
    assert fwd["X-SUPERVOID-Service-Token"] == TOKEN
    assert fwd["X-SUPERVOID-User-Sig"] == sign_user_context(
        TOKEN, user_id="lc-9", email="bob@studio.test", role="ADMIN", request_id="req-9"
    )
    assert fwd["X-SUPERVOID-User-Sig"] != "deadbeef"
    # Email is normalised in the forwarded header too.
    assert fwd["X-SUPERVOID-User-Email"] == "bob@studio.test"
    # Innocuous headers pass through; hop-by-hop are dropped.
    assert fwd.get("content-type") == "application/json"
    assert fwd.get("mcp-session-id") == "sess-123"
    assert "host" not in {k.lower() for k in fwd}


def test_response_headers_drop_hop_by_hop():
    upstream = Headers(
        {
            "Content-Type": "text/event-stream",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
            "Mcp-Session-Id": "sess-xyz",
        }
    )
    out = shim.build_response_headers(upstream)
    assert out.get("content-type") == "text/event-stream"
    assert out.get("mcp-session-id") == "sess-xyz"
    assert "transfer-encoding" not in {k.lower() for k in out}
    assert "connection" not in {k.lower() for k in out}


# --- end-to-end against the real authenticator ------------------------------

def test_shim_headers_accepted_by_backend_authenticate(session: Session):
    """Headers the shim emits for a mixed-case email are accepted, and resolve to
    the linked SUPERVOID user."""
    user = _linked_user(session, "carla@studio.test", role=UserRole.ADMIN)

    raw_email = "Carla@Studio.TEST"  # what LibreChat might send
    fwd = shim.build_forward_headers(
        Headers(
            {
                "X-SUPERVOID-User-Id": "lc-carla",
                "X-SUPERVOID-User-Email": raw_email,
                "X-SUPERVOID-User-Role": "USER",
                "X-SUPERVOID-Request-Id": "req-carla",
            }
        ),
        TOKEN,
    )

    # Over the wire the backend reads a case-insensitive header mapping; mirror
    # that (the shim emits canonical-case keys, HTTP makes lookups case-insensitive).
    principal = authenticate(session, Headers(fwd))
    assert principal.user.id == user.id
    assert principal.email == "carla@studio.test"


def test_backend_rejects_when_shim_uses_wrong_token(session: Session):
    _linked_user(session, "dora@studio.test")
    fwd = shim.build_forward_headers(
        Headers(
            {
                "X-SUPERVOID-User-Id": "lc-dora",
                "X-SUPERVOID-User-Email": "dora@studio.test",
                "X-SUPERVOID-User-Role": "USER",
                "X-SUPERVOID-Request-Id": "req-dora",
            }
        ),
        "the-wrong-service-token",
    )
    with pytest.raises(MCPAuthError):
        authenticate(session, Headers(fwd))


# --- live proxy path (in-process, mocked upstream) --------------------------

def test_proxy_injects_credential_and_forwards_body():
    body = b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
    r, captured = asyncio.run(
        _drive(
            lambda: JSONResponse({"ok": True}),
            headers={
                "X-SUPERVOID-User-Id": "lc-1",
                "X-SUPERVOID-User-Email": "Eve@Studio.TEST",
                "X-SUPERVOID-User-Role": "USER",
                "X-SUPERVOID-Request-Id": "req-1",
                # client-supplied credential/sig must be discarded by the shim
                "X-SUPERVOID-Service-Token": "attacker",
                "X-SUPERVOID-User-Sig": "bad",
                "Content-Type": "application/json",
            },
            content=body,
        )
    )

    assert r.status_code == 200
    h = captured["headers"]
    assert h["x-supervoid-service-token"] == TOKEN
    assert h["x-supervoid-user-email"] == "eve@studio.test"
    assert h["x-supervoid-user-sig"] == sign_user_context(
        TOKEN, user_id="lc-1", email="eve@studio.test", role="USER", request_id="req-1"
    )
    # body is forwarded verbatim
    assert captured["body"] == body


def test_proxy_streams_sse_response():
    async def _sse():
        yield b"event: message\n"
        yield b'data: {"chunk":1}\n\n'

    r, _ = asyncio.run(
        _drive(
            lambda: StreamingResponse(_sse(), media_type="text/event-stream"),
            headers={
                "X-SUPERVOID-User-Id": "lc-2",
                "X-SUPERVOID-User-Email": "sse@studio.test",
                "X-SUPERVOID-User-Role": "USER",
                "X-SUPERVOID-Request-Id": "req-2",
            },
        )
    )
    assert r.headers["content-type"].startswith("text/event-stream")
    assert b'data: {"chunk":1}' in r.content


def test_proxy_fails_closed_without_service_token(monkeypatch):
    monkeypatch.delenv("MCP_SERVICE_TOKEN", raising=False)

    def _never():  # pragma: no cover - upstream must not be reached
        raise AssertionError("upstream must not be called without a service token")

    r, captured = asyncio.run(_drive(_never, headers={"X-SUPERVOID-User-Email": "x@y.z"}))
    assert r.status_code == 503
    assert captured == {}  # never forwarded
    assert r.json()["error"]["code"] == -32001
