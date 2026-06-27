"""In-app chat turn for the native SUPERVOID Brain UI.

The OpenAI-compatible Gateway (``/brain/v1``) is the surface LibreChat uses with a
Brain token. This module is the SAME governed turn, but authenticated by the
logged-in SUPERVOID user (the normal ``/api`` session) so the built-in chat works
with no Brain token, no LibreChat and no extra service — and is permission-scoped
per role exactly like the Gateway (it assembles with the user's own permissions
and refuses projects they may not view).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session

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

_EVIDENCE_RE = re.compile(r'source="knowledge_entity:([^"]+)"')


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
    usage: dict = field(default_factory=dict)


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


async def run_turn(
    session: Session,
    *,
    user: User,
    content: str,
    conversation_id: Optional[str] = None,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    profile: Optional[str] = None,
) -> ChatTurn:
    """Run one governed chat turn for ``user``. The caller owns the transaction."""
    content = (content or "").strip()
    if not content:
        raise ValueError("Message content is required.")

    # Project scoping: never chat into a project the user may not view (admin
    # bypass lives inside policy.can).
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

    provider = get_provider()
    caps = provider.capabilities()
    chat_messages = [ChatMessage(role=m["role"], content=m.get("content")) for m in ctx.messages]
    req = ChatRequest(
        messages=chat_messages, model=settings.ai_model, temperature=ctx.temperature,
        max_tokens=ctx.max_tokens, tools=(ctx.tools if (caps.tools and ctx.tools) else None),
        stream=False,
    )
    try:
        if hasattr(provider, "acomplete"):
            result = await provider.acomplete(req)
        else:  # dry-run / sync-only provider
            result = provider.chat(chat_messages, model=settings.ai_model,
                                   temperature=ctx.temperature, max_tokens=ctx.max_tokens)
    except ProviderUnavailableError:
        raise ChatProviderError(503, "The model provider is currently unavailable.")
    except ProviderTimeoutError:
        raise ChatProviderError(504, "The model provider timed out.")
    except MalformedResponseError:
        raise ChatProviderError(502, "Bad response from the model provider.")
    except CapabilityError:
        raise ChatProviderError(400, "The requested capability is not supported.")

    out = result.content or ""
    usage = dict(getattr(result, "usage", None) or {})
    state_version = _state_version(ctx)
    brain.append_message(
        session, conversation, role=BrainMessageRole.ASSISTANT, content=out,
        model=settings.ai_model, provider=provider.name,
        prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
        state_version=state_version,
    )
    return ChatTurn(
        conversation_id=conversation.id, content=out, model=settings.brain_gateway_model,
        state_version=state_version, citations=_citations(ctx), usage=usage,
    )
