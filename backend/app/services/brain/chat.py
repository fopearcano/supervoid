"""In-app chat turn for the native SUPERVOID Brain UI (with governed tool use).

The OpenAI-compatible Gateway (``/brain/v1``) is the surface LibreChat uses with a
Brain token. This module is the SAME governed turn, but authenticated by the
logged-in SUPERVOID user (the normal ``/api`` session) so the built-in chat works
with no Brain token, no LibreChat and no extra service.

It runs a **bounded tool loop**: the model may call the real MCP **read** and
**proposal** tools (never the approval tools — humans approve), each executed as
the logged-in user so permissions are enforced exactly as everywhere else. Read
tools return only authorised data; proposal tools create PENDING
``AgentActionProposal``s — they never auto-execute.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session

import app.services.mcp.tools  # noqa: F401  (registers the MCP tools)
from app.config import settings
from app.models import User
from app.models.enums import BrainMessageRole, PermissionScope
from app.services import brain, policy
from app.services.ai.providers import ChatMessage, ChatRequest, get_provider
from app.services.ai.providers.base import (
    CapabilityError,
    MalformedResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.services.mcp.auth import MCPPrincipal
from app.services.mcp.registry import MCPToolError, ToolKind, get_tool, list_tools

_EVIDENCE_RE = re.compile(r'source="knowledge_entity:([^"]+)"')

# The model may call read + proposal tools; approval tools are human-only.
_MODEL_TOOL_KINDS = {ToolKind.READ_ONLY, ToolKind.PROPOSAL_ONLY}
_MAX_TOOL_RESULT_CHARS = 6000


class ChatPermissionError(Exception):
    """The user may not chat in the requested project / conversation."""


class ChatProviderError(Exception):
    """The model provider failed — carries the HTTP status to surface."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


@dataclass
class ChatTurn:
    conversation_id: str
    content: str
    model: str
    state_version: Optional[int] = None
    citations: list = field(default_factory=list)
    tools_used: list = field(default_factory=list)
    proposals: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)


# --- tool surface ----------------------------------------------------------
def _tool_schemas() -> list[dict]:
    """OpenAI function schemas for the MCP read + proposal tools."""
    return [
        {"type": "function", "function": {
            "name": spec.name, "description": spec.description, "parameters": spec.input_schema}}
        for spec in list_tools() if spec.kind in _MODEL_TOOL_KINDS
    ]


def _principal(user: User, request_id: str) -> MCPPrincipal:
    return MCPPrincipal(user=user, librechat_user_id=None, email=user.email,
                        declared_role=getattr(user.role, "value", str(user.role)),
                        request_id=request_id)


def _exec_tool(session: Session, principal: MCPPrincipal, name: str, arguments: str,
               allowed: set[str]) -> dict:
    """Execute one MCP tool call as the principal. Errors are returned (not raised)
    so the model can see them and adjust."""
    if name not in allowed:
        return {"error": f"Tool '{name}' is not available.", "code": "not_allowed"}
    spec = get_tool(name)
    if spec is None:
        return {"error": f"Unknown tool '{name}'.", "code": "unknown_tool"}
    try:
        args = json.loads(arguments or "{}")
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        return {"error": "Invalid tool arguments (not JSON).", "code": "invalid_args"}
    try:
        return {"result": spec.handler(session, principal, args)}
    except MCPToolError as exc:
        return {"error": exc.message, "code": exc.code}
    except Exception as exc:  # noqa: BLE001 - surface to the model, never crash the turn
        return {"error": str(exc), "code": "tool_error"}


def _citations(ctx) -> list:
    seg = next((s for s in ctx.segments if s.name == "Retrieved evidence" and s.included), None)
    if seg is None:
        return []
    return [
        {"ref": f"knowledge_entity:{eid}", "label": f"[{i + 1}]"}
        for i, eid in enumerate(_EVIDENCE_RE.findall(seg.text))
    ]


def _state_version(ctx) -> Optional[int]:
    return ctx.versions.get("project_state") or ctx.versions.get("studio_state")


async def _complete(provider, ctx, messages: list, tools: Optional[list]):
    """One provider round-trip (async ``acomplete`` when available, else sync chat)."""
    try:
        if hasattr(provider, "acomplete"):
            return await provider.acomplete(ChatRequest(
                messages=messages, model=settings.ai_model, temperature=ctx.temperature,
                max_tokens=ctx.max_tokens, tools=tools, stream=False))
        return provider.chat(messages, model=settings.ai_model,
                             temperature=ctx.temperature, max_tokens=ctx.max_tokens)
    except ProviderUnavailableError:
        raise ChatProviderError(503, "The model provider is currently unavailable.")
    except ProviderTimeoutError:
        raise ChatProviderError(504, "The model provider timed out.")
    except MalformedResponseError:
        raise ChatProviderError(502, "Bad response from the model provider.")
    except CapabilityError:
        raise ChatProviderError(400, "The requested capability is not supported.")


async def run_turn(
    session: Session,
    *,
    user: User,
    content: str,
    conversation_id: Optional[str] = None,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    profile: Optional[str] = None,
    provider=None,
) -> ChatTurn:
    """Run one governed chat turn for ``user``. The caller owns the transaction."""
    content = (content or "").strip()
    if not content:
        raise ValueError("Message content is required.")

    if (work_id or story_world_id) and not policy.can(
        session, user, PermissionScope.VIEW_PROJECT, work_id=work_id, story_world_id=story_world_id
    ):
        raise ChatPermissionError("Not permitted for this project.")

    conversation = None
    if conversation_id:
        conversation = brain.get_conversation(session, conversation_id)
        if conversation is None or conversation.owner_user_id != user.id:
            raise ChatPermissionError("Conversation not found.")
    if conversation is None:
        conversation = brain.create_conversation(
            session, owner_user_id=user.id, work_id=work_id, story_world_id=story_world_id,
            active_profile=(profile or "studio-director").replace("_", "-"),
        )

    brain.append_message(session, conversation, role=BrainMessageRole.USER, content=content)
    ctx = brain.assemble(session, conversation, user=user, model=settings.ai_model,
                         include_evidence=True, persist=True)

    provider = provider or get_provider()
    caps = provider.capabilities()
    tool_schemas = _tool_schemas() if getattr(caps, "tools", False) else None
    allowed = {t["function"]["name"] for t in tool_schemas} if tool_schemas else set()
    principal = _principal(user, request_id=f"chat-{conversation.id}")

    messages = [ChatMessage(role=m["role"], content=m.get("content")) for m in ctx.messages]
    tools_used: list[str] = []
    proposals: list[dict] = []
    total_calls = 0

    result = await _complete(provider, ctx, messages, tool_schemas)
    for _round in range(settings.agent_max_tool_rounds):
        calls = (result.tool_calls or []) if tool_schemas else []
        if not calls:
            break
        messages.append(ChatMessage(
            role="assistant", content=result.content or "",
            tool_calls=[{"id": tc.id, "type": "function",
                         "function": {"name": tc.name, "arguments": tc.arguments}} for tc in calls],
        ))
        for tc in calls:
            if total_calls >= settings.agent_max_tool_calls:
                out = {"error": "Tool-call budget exhausted for this turn.", "code": "budget"}
            else:
                total_calls += 1
                out = _exec_tool(session, principal, tc.name, tc.arguments, allowed)
                tools_used.append(tc.name)
                res = out.get("result")
                if isinstance(res, dict) and (res.get("proposal_id") or res.get("requires_approval")):
                    proposals.append({"tool": tc.name, "proposal_id": res.get("proposal_id"),
                                      "status": res.get("status")})
            messages.append(ChatMessage(
                role="tool", name=tc.name, tool_call_id=tc.id,
                content=json.dumps(out, default=str)[:_MAX_TOOL_RESULT_CHARS],
            ))
        result = await _complete(provider, ctx, messages, tool_schemas)

    out_content = result.content or ""
    usage = dict(getattr(result, "usage", None) or {})
    state_version = _state_version(ctx)
    seen: set[str] = set()
    tools_unique = [t for t in tools_used if not (t in seen or seen.add(t))]
    brain.append_message(
        session, conversation, role=BrainMessageRole.ASSISTANT, content=out_content,
        model=settings.ai_model, provider=provider.name,
        prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
        state_version=state_version,
        structured_content={"tools_used": tools_unique, "proposals": proposals},
    )
    return ChatTurn(
        conversation_id=conversation.id, content=out_content, model=settings.brain_gateway_model,
        state_version=state_version, citations=_citations(ctx), tools_used=tools_unique,
        proposals=proposals, usage=usage,
    )
