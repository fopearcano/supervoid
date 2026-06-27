"""SUPERVOID MCP signing shim.

LibreChat's MCP client cannot hold the shared service credential or compute the
HMAC over the user-context, so this tiny trusted hop sits between LibreChat and
the SUPERVOID ``/mcp`` server on the PRIVATE network and does it for every
request:

  LibreChat ──(user-context headers)──▶ sign-proxy ──(+ service token + HMAC)──▶ /mcp

It mirrors ``app/services/mcp/auth.py`` EXACTLY:
  * the canonical string is ``"\\n".join([user_id, email, role, request_id])``;
  * the email is normalised (``strip().lower()``) BEFORE signing, because the
    SUPERVOID backend normalises the incoming email before it recomputes the
    expected signature — sign over the raw header and a mixed-case address would
    be rejected;
  * the HMAC is SHA-256 keyed by the service token.

Security posture:
  * it INJECTS the service token + signature and STRIPS any client-supplied
    ``X-SUPERVOID-Service-Token`` / ``-User-Sig`` so a caller can never smuggle
    its own;
  * it holds the secret in env only and never logs it;
  * it is a transparent streaming proxy (Streamable HTTP / SSE safe) — it does
    not parse or buffer the JSON-RPC body.

Run:  uvicorn sign_proxy:app --host 0.0.0.0 --port 8092
Env:  MCP_SERVICE_TOKEN (required; must match the SUPERVOID backend)
      MCP_UPSTREAM_URL (e.g. http://supervoid-backend:8000/mcp) OR
      SUPERVOID_BACKEND_HOST + SUPERVOID_BACKEND_PORT (default :8000 → /mcp)
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
from typing import Dict, Mapping

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

# --- canonical signing (must match app/services/mcp/auth.py) ----------------

# Lower-cased; HTTP header lookups are case-insensitive anyway.
H_SERVICE = "x-supervoid-service-token"
H_USER_ID = "x-supervoid-user-id"
H_EMAIL = "x-supervoid-user-email"
H_ROLE = "x-supervoid-user-role"
H_REQUEST_ID = "x-supervoid-request-id"
H_SIG = "x-supervoid-user-sig"

# Headers the shim OWNS (re-derived every request) — never trust the client's.
_OWNED = {H_SERVICE, H_USER_ID, H_EMAIL, H_ROLE, H_REQUEST_ID, H_SIG}

# Hop-by-hop / connection headers that must not be forwarded verbatim.
_HOP_BY_HOP = {
    "host", "content-length", "connection", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade",
}


def normalize_email(email: str | None) -> str:
    """Match the backend: ``(value or "").strip().lower()``."""
    return (email or "").strip().lower()


def canonical_user_context(*, user_id: str, email: str, role: str, request_id: str) -> str:
    """The exact string both sides HMAC. Order + separators are fixed."""
    return "\n".join([user_id or "", email or "", role or "", request_id or ""])


def compute_signature(token: str, *, user_id: str, email: str, role: str, request_id: str) -> str:
    """HMAC-SHA256 over the canonical context, keyed by the service token.

    The email is normalised here so callers may pass the raw header value.
    """
    msg = canonical_user_context(
        user_id=user_id, email=normalize_email(email), role=role, request_id=request_id
    )
    return hmac.new(token.encode(), msg.encode(), hashlib.sha256).hexdigest()


def build_forward_headers(incoming: Mapping[str, str], token: str) -> Dict[str, str]:
    """Construct the header set to forward upstream.

    Passes through everything the client sent EXCEPT the headers we own and the
    hop-by-hop set, then injects the normalised user-context, the service token
    and a fresh signature. Pure + side-effect free so it can be unit tested.
    """
    user_id = incoming.get(H_USER_ID, "") or ""
    email = normalize_email(incoming.get(H_EMAIL, ""))
    role = incoming.get(H_ROLE, "") or ""
    request_id = incoming.get(H_REQUEST_ID, "") or ""

    fwd: Dict[str, str] = {
        k: v
        for k, v in incoming.items()
        if k.lower() not in _OWNED and k.lower() not in _HOP_BY_HOP
    }
    fwd["X-SUPERVOID-Service-Token"] = token
    fwd["X-SUPERVOID-User-Id"] = user_id
    fwd["X-SUPERVOID-User-Email"] = email
    fwd["X-SUPERVOID-User-Role"] = role
    fwd["X-SUPERVOID-Request-Id"] = request_id
    fwd["X-SUPERVOID-User-Sig"] = compute_signature(
        token, user_id=user_id, email=email, role=role, request_id=request_id
    )
    return fwd


def build_response_headers(upstream: Mapping[str, str]) -> Dict[str, str]:
    """Forward upstream response headers minus hop-by-hop ones (let the ASGI
    server frame the body). Keeps content-type/encoding and Mcp-Session-Id."""
    return {k: v for k, v in upstream.items() if k.lower() not in _HOP_BY_HOP}


# --- runtime config ---------------------------------------------------------

def _service_token() -> str:
    return os.environ.get("MCP_SERVICE_TOKEN", "")


def _upstream_url() -> str:
    explicit = os.environ.get("MCP_UPSTREAM_URL")
    if explicit:
        return explicit
    host = os.environ.get("SUPERVOID_BACKEND_HOST", "supervoid-backend")
    port = os.environ.get("SUPERVOID_BACKEND_PORT", "8000")
    return f"http://{host}:{port}/mcp"


# --- ASGI app ---------------------------------------------------------------

async def healthz(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "configured": bool(_service_token()),
            "upstream": _upstream_url(),
        }
    )


async def proxy(request: Request) -> StreamingResponse | JSONResponse:
    token = _service_token()
    if not token:
        # Fail closed and loud — never forward unsigned.
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32001, "message": "sign-proxy: MCP_SERVICE_TOKEN not set"},
            },
            status_code=503,
        )

    upstream_url = _upstream_url()
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    fwd = build_forward_headers(request.headers, token)
    body = await request.body()
    client: httpx.AsyncClient = request.app.state.client

    req = client.build_request(request.method, upstream_url, headers=fwd, content=body)
    try:
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as exc:  # connect/read failure to the backend
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32002, "message": f"sign-proxy: upstream unreachable: {exc}"},
            },
            status_code=502,
        )

    async def stream():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        stream(),
        status_code=upstream.status_code,
        headers=build_response_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    # read timeout None keeps long-lived SSE streams open; connect/write bounded.
    timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        app.state.client = client
        yield


app = Starlette(
    routes=[
        Route("/healthz", healthz, methods=["GET"]),
        Route("/mcp", proxy, methods=["GET", "POST", "DELETE"]),
        Route("/mcp/{path:path}", proxy, methods=["GET", "POST", "DELETE"]),
    ],
    lifespan=lifespan,
)
