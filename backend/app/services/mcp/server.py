"""MCP JSON-RPC dispatch for the SUPERVOID tool layer (Streamable HTTP).

Implements the minimal MCP method set — ``initialize``, ``tools/list``,
``tools/call``, ``ping`` and the ``notifications/initialized`` notification —
without a heavyweight SDK. Authentication + the SUPERVOID user mapping happen at
the transport layer (the router); here we dispatch already-authenticated calls.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlmodel import Session

from app.config import settings
from app.services.mcp.registry import MCPToolError, get_tool, list_tools

PROTOCOL_VERSION = "2025-06-18"

SERVER_INSTRUCTIONS = (
    "SUPERVOID exposes a GOVERNED tool layer — not raw database access. Every "
    "tool re-checks the calling user's permissions through the SUPERVOID policy "
    "service.\n\n"
    "Tool kinds (see each tool's annotations):\n"
    "- read-only: returns ONLY records the user is authorised to see.\n"
    "- proposal-only: NEVER mutates directly; it creates a gated proposal that a "
    "human must approve. Production/asset/publication/rights proposals appear in "
    "list_action_proposals; narrative decisions appear via get_recent_decisions.\n"
    "- destructive / external: also proposal-gated and always require an "
    "administrator's approval.\n"
    "- approval: approve_proposal / reject_proposal / execute_approved_proposal "
    "act ONLY for a user who holds the approval scope; high-risk actions require "
    "an administrator. Never assume you may approve your own proposals.\n\n"
    "Publishing, rights, and deletion are never performed automatically — they "
    "are recorded for a human to carry out through the audited UI. Prefer "
    "get_studio_state / get_project_state / get_project_delta for grounding "
    "before proposing anything."
)


def _result(id_, result) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_, code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": err}


def _tool_content(payload) -> dict:
    """A tools/call result: a text block (compact JSON) + structuredContent."""
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
    out = {"content": [{"type": "text", "text": text}], "isError": False}
    if not isinstance(payload, str):
        out["structuredContent"] = payload
    return out


def handle_rpc(session: Session, principal, message: dict) -> Optional[dict]:
    """Dispatch one JSON-RPC message. Returns the response object, or ``None`` for
    a notification (no response). Commits/rolls back around a tools/call."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, -32600, "Invalid JSON-RPC request.")
    method = message.get("method")
    msg_id = message.get("id")
    is_notification = "id" not in message
    params = message.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion") or PROTOCOL_VERSION
        return _result(msg_id, {
            "protocolVersion": requested,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": settings.mcp_server_name, "version": settings.app_version},
            "instructions": SERVER_INSTRUCTIONS,
        })

    if method == "notifications/initialized" or (method and method.startswith("notifications/")):
        return None  # notifications get no response

    if method == "ping":
        return _result(msg_id, {})

    if method == "tools/list":
        return _result(msg_id, {"tools": [spec.describe() for spec in list_tools()]})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        spec = get_tool(name)
        if spec is None:
            return _result(msg_id, {
                "content": [{"type": "text", "text": f"Unknown tool '{name}'."}],
                "isError": True,
            })
        from app.utils.logging import log_event

        rid = getattr(principal, "request_id", None)
        try:
            payload = spec.handler(session, principal, args)
            session.commit()
            log_event("mcp.tool_call", rid=rid, tool=name,
                      user=getattr(principal.user, "id", None), is_error=False)
            return _result(msg_id, _tool_content(payload))
        except MCPToolError as exc:
            session.rollback()
            log_event("mcp.tool_call", rid=rid, tool=name,
                      user=getattr(principal.user, "id", None), is_error=True, code=exc.code)
            return _result(msg_id, {
                "content": [{"type": "text", "text": exc.message}],
                "isError": True,
                "structuredContent": {"error": exc.message, "code": exc.code},
            })
        except Exception as exc:  # noqa: BLE001 - never leak internals; surface a generic error
            session.rollback()
            from app.utils.logging import get_logger

            get_logger("app.mcp").exception("mcp tool '%s' failed", name)
            return _result(msg_id, {
                "content": [{"type": "text", "text": "Tool execution failed."}],
                "isError": True,
            })

    if is_notification:
        return None
    return _error(msg_id, -32601, f"Method not found: {method}")
