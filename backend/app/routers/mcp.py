"""The SUPERVOID MCP server transport (Streamable HTTP).

Mounted at ``/mcp`` (NOT under the private ``/api`` prefix). A single POST
endpoint speaks MCP JSON-RPC; an unauthenticated GET ``/mcp/health`` reports
liveness. Authentication is the internal service credential plus signed
user-context headers — see ``app.services.mcp.auth``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlmodel import Session

from app.config import settings
from app.db import get_session
from app.services import mcp as mcp_svc
from app.services.mcp.auth import MCPAuthError, authenticate
from app.utils.middleware import REQUEST_ID_HEADER

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/health")
def mcp_health() -> dict:
    """Unauthenticated liveness probe (no governance data)."""
    return {
        "status": "ok" if settings.mcp_enabled else "disabled",
        "object": "mcp_health",
        "server": settings.mcp_server_name,
        "configured": bool(settings.mcp_service_token),
        "tool_count": len(mcp_svc.list_tools()),
    }


@router.get("")
def mcp_get() -> Response:
    # We do not offer a server-initiated SSE stream; only POST is supported.
    return JSONResponse(status_code=405, content={"error": "Use POST for MCP."},
                        headers={"Allow": "POST"})


@router.post("")
async def mcp_post(request: Request, session: Session = Depends(get_session)) -> Response:
    rid = getattr(request.state, "request_id", "-")
    try:
        principal = authenticate(session, request.headers)
    except MCPAuthError as exc:
        return JSONResponse(
            status_code=401,
            content={"jsonrpc": "2.0", "id": None,
                     "error": {"code": exc.code, "message": exc.message}},
            headers={REQUEST_ID_HEADER: rid, "WWW-Authenticate": "Bearer"},
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": "Parse error."}},
            headers={REQUEST_ID_HEADER: rid},
        )

    # Streamable HTTP allows a single message or a batch.
    messages = body if isinstance(body, list) else [body]
    responses = []
    for msg in messages:
        resp = mcp_svc.handle_rpc(session, principal, msg)
        if resp is not None:
            responses.append(resp)

    if not responses:
        # Only notifications/responses were sent — acknowledge with no body.
        return Response(status_code=202, headers={REQUEST_ID_HEADER: rid})

    payload = responses if isinstance(body, list) else responses[0]
    return JSONResponse(content=payload, headers={REQUEST_ID_HEADER: rid})
