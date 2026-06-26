"""The SUPERVOID Brain Gateway — an OpenAI-compatible API surface.

LibreChat (and any OpenAI client) connects HERE, not to vLLM. The gateway
authenticates with a dedicated :class:`BrainAccessToken`, resolves the user /
permitted project / assistant profile / conversation, builds context with the
:class:`ContextAssembler`, calls the model provider (which alone holds the
upstream vLLM key), and persists the turn. It speaks the OpenAI Chat Completions
wire shape (ordinary + streaming) so existing clients work unchanged; SUPERVOID
extension data rides in an optional top-level ``supervoid`` object that strict
clients ignore.

Mounted at ``/brain`` (NOT under the private ``/api`` prefix).
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from secrets import token_hex
from time import perf_counter
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlmodel import Session, select

from app.auth import BrainPrincipal, get_brain_principal
from app.config import settings
from app.db import engine, get_session
from app.models import BrainAccessToken, PermissionScope, User
from app.models.brain import BrainConversation
from app.models.enums import BrainConversationStatus, BrainMessageRole
from app.services import brain, policy
from app.services.ai.providers import get_provider
from app.services.ai.providers.base import (
    CapabilityError,
    ChatMessage,
    ChatRequest,
    MalformedResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.utils.logging import get_logger
from app.utils.middleware import REQUEST_ID_HEADER
from app.utils.throttle import (
    ConcurrencyExceeded,
    ConcurrencyLimiter,
    RateLimiter,
)

log = get_logger("app.brain.gateway")
router = APIRouter(prefix="/brain", tags=["brain-gateway"])

_rate = RateLimiter(
    rate_per_min=settings.brain_gateway_rate_per_min, burst=settings.brain_gateway_burst
)
_conc = ConcurrencyLimiter(max_concurrency=settings.brain_gateway_max_concurrency)

_EVIDENCE_RE = re.compile(r'source="knowledge_entity:([^"]+)"')


# --- OpenAI-shaped helpers --------------------------------------------------
def _error(status_code: int, type_: str, message: str, code: Optional[str] = None,
           *, rid: str = "-", headers: Optional[dict] = None) -> JSONResponse:
    body = {"error": {"message": message, "type": type_, "code": code, "param": None}}
    hdrs = {REQUEST_ID_HEADER: rid}
    if headers:
        hdrs.update(headers)
    return JSONResponse(status_code=status_code, content=body, headers=hdrs)


def _served() -> str:
    return settings.brain_gateway_model


def _estimate_tokens(text: Optional[str]) -> int:
    """A cheap, deterministic token estimate (~4 chars/token). Used only to
    populate a usage object when the provider does not report one (e.g. the
    dry-run provider) — OpenAI clients expect ``usage`` to be present/shaped."""
    return max(1, len((text or "").strip()) // 4) if text and text.strip() else 0


def _ensure_usage(usage: Optional[dict], *, prompt_text: str, completion_text: str) -> dict:
    """Return the provider's usage dict as-is, or synthesize an OpenAI-shaped
    one when the provider reports none. Never raises; always returns a dict
    with the three canonical fields so strict clients don't choke."""
    if isinstance(usage, dict) and usage.get("total_tokens") is not None:
        return usage
    prompt_tokens = _estimate_tokens(prompt_text)
    completion_tokens = _estimate_tokens(completion_text)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated": True,
    }


def _last_user_text(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, list):  # OpenAI content-parts array
                c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
            return c or ""
    return ""


def _evidence_refs(ctx) -> list[dict]:
    """Machine-readable evidence references extracted from the assembled
    untrusted-evidence segment (entity ids), labelled [1], [2], …."""
    seg = next((s for s in ctx.segments if s.name == "Retrieved evidence" and s.included), None)
    if seg is None:
        return []
    ids = _EVIDENCE_RE.findall(seg.text)
    return [
        {"ref": f"knowledge_entity:{eid}", "label": f"[{i + 1}]"}
        for i, eid in enumerate(ids)
    ]


def _token_allows(token: BrainAccessToken, work_id, story_world_id) -> bool:
    """Whether a token's project restrictions permit a request scoped to
    ``work_id`` and/or ``story_world_id``. An empty restriction list means
    unrestricted. Otherwise **every** provided scope must be independently
    covered — an authorised work_id must not let an unauthorised story_world_id
    ride along (and vice-versa)."""
    restr = token.project_restrictions or []
    if not restr:
        return True
    if work_id and not any(r.get("work_id") == work_id for r in restr):
        return False
    if story_world_id and not any(r.get("story_world_id") == story_world_id for r in restr):
        return False
    return True


class _Denied(Exception):
    pass


def _resolve_conversation(
    session: Session, user: User, token: BrainAccessToken, meta: dict, messages: list
) -> BrainConversation:
    is_admin = user.role.value == "admin"
    work_id = meta.get("work_id") or meta.get("project_id")
    story_world_id = meta.get("story_world_id")
    profile = meta.get("assistant_profile")
    if profile:
        profile = profile.replace("_", "-")
    lc_conv_id = meta.get("librechat_conversation_id") or meta.get("conversation_id")

    def _gate(w, s) -> None:
        """NEVER guess access to an unauthorised project: deny unless BOTH the
        token's restrictions AND the user's policy permit project (w, s). Called
        for the explicitly-requested project AND for the effective project of any
        existing conversation we continue."""
        if not (w or s):
            return
        if not _token_allows(token, w, s):
            raise _Denied("This access token is not permitted for the requested project.")
        if not (is_admin or policy.can(
            session, user, PermissionScope.VIEW_PROJECT, work_id=w, story_world_id=s,
        )):
            raise _Denied("You do not have access to the requested project.")

    # Gate the explicitly-requested project up front.
    _gate(work_id, story_world_id)

    title = (_last_user_text(messages) or "Brain conversation")[:120]

    if lc_conv_id:
        conv = session.exec(
            select(BrainConversation)
            .where(
                BrainConversation.owner_user_id == user.id,
                BrainConversation.librechat_conversation_id == lc_conv_id,
            )
            .order_by(BrainConversation.updated_at.desc())
        ).first()
        if conv is not None:
            if work_id or story_world_id:
                conv.work_id = work_id
                conv.story_world_id = story_world_id
            else:
                # Continuing an existing binding without new metadata — re-gate
                # the conversation's CURRENT project against THIS token, so a
                # newly-restricted token can't ride an old project-bound thread.
                _gate(conv.work_id, conv.story_world_id)
            if profile:
                conv.active_profile = profile
            session.add(conv)
            return conv
        return brain.create_conversation(
            session, owner_user_id=user.id, librechat_conversation_id=lc_conv_id,
            work_id=work_id, story_world_id=story_world_id,
            active_profile=profile or "studio-director", title=title,
        )

    if work_id or story_world_id:
        return brain.create_conversation(
            session, owner_user_id=user.id, work_id=work_id, story_world_id=story_world_id,
            active_profile=profile or "studio-director", title=title,
        )

    # No metadata at all: continue the user's general (project-less) Studio
    # Director lane, else open one.
    conv = session.exec(
        select(BrainConversation)
        .where(
            BrainConversation.owner_user_id == user.id,
            BrainConversation.work_id.is_(None),
            BrainConversation.story_world_id.is_(None),
            BrainConversation.status == BrainConversationStatus.ACTIVE,
        )
        .order_by(BrainConversation.updated_at.desc())
    ).first()
    if conv is not None:
        if profile:
            conv.active_profile = profile
            session.add(conv)
        return conv
    return brain.create_conversation(
        session, owner_user_id=user.id, active_profile=profile or "studio-director", title=title,
    )


def _persist_assistant(
    session: Session, conversation, *, content, model, provider_name, usage, finish,
    tool_calls, latency_ms, ctx, retrieval_ids, rid, cancelled=False, reasoning=None,
) -> None:
    usage = usage or {}
    state_version = ctx.versions.get("studio_state") or ctx.versions.get("project_state")
    brain.append_message(
        session, conversation, role=BrainMessageRole.ASSISTANT,
        content=content, model=model, provider=provider_name,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        request_id=rid, state_version=state_version,
        retrieval_ids=retrieval_ids,
        tool_call_ids=[tc.get("id") for tc in tool_calls if tc.get("id")],
        structured_content={
            "latency_ms": round(latency_ms, 2),
            "usage": usage or None,
            "tool_calls": tool_calls,
            "finish_reason": finish,
            "context_checksum": ctx.context_checksum,
            "prefix_hash": ctx.prefix_hash,
            "versions": ctx.versions,
            "reasoning": reasoning,
            "cancelled": cancelled,
        },
    )
    session.commit()


# === endpoints ==============================================================
@router.get("/health")
def health() -> dict:
    """Liveness probe for LibreChat / ops (unauthenticated, no upstream call)."""
    return {"status": "ok", "object": "health", "model": _served(), "provider": settings.ai_provider}


@router.get("/v1/models")
def list_models(principal: BrainPrincipal = Depends(get_brain_principal)) -> dict:
    return {
        "object": "list",
        "data": [
            {"id": _served(), "object": "model", "created": 0, "owned_by": "supervoid"}
        ],
    }


@router.post("/v1/responses")
def responses_not_implemented(
    principal: BrainPrincipal = Depends(get_brain_principal),
) -> JSONResponse:
    """The OpenAI Responses API is deferred (no provider/mock support yet)."""
    return _error(501, "not_implemented",
                  "The /v1/responses API is not implemented; use /v1/chat/completions.",
                  "not_implemented")


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    principal: BrainPrincipal = Depends(get_brain_principal),
    session: Session = Depends(get_session),
):
    rid = getattr(request.state, "request_id", "-")
    user, token = principal.user, principal.token

    if not _rate.allow(user.id):
        return _error(429, "rate_limit_error", "Rate limit exceeded.", "rate_limited",
                      rid=rid, headers={"Retry-After": str(_rate.retry_after(user.id))})

    # Acquire a concurrency slot BEFORE any persistence, so an over-subscribed
    # user is rejected cleanly (HTTP 429) without leaving a dangling user turn.
    # The slot is held through the provider call; for streaming it is handed to
    # the generator, which releases it when the stream closes.
    guard = _conc.guard(user.id)
    try:
        await guard.__aenter__()
    except ConcurrencyExceeded:
        return _error(429, "rate_limit_error", "Too many concurrent requests.",
                      "concurrency_limited", rid=rid, headers={"Retry-After": "1"})

    slot_handed_off = False
    try:
        try:
            body = await request.json()
        except Exception:
            return _error(400, "invalid_request_error", "Request body must be valid JSON.", rid=rid)
        if not isinstance(body, dict):
            return _error(400, "invalid_request_error", "Request body must be a JSON object.", rid=rid)

        model = body.get("model")
        if model not in (_served(), settings.ai_model):
            return _error(400, "invalid_request_error",
                          f"Unknown model '{model}'. Use '{_served()}'.", "model_not_found", rid=rid)
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            return _error(400, "invalid_request_error", "'messages' must be a non-empty array.", rid=rid)
        stream = bool(body.get("stream"))
        meta = body.get("supervoid") or (body.get("extra_body") or {}).get("supervoid") or {}
        if not isinstance(meta, dict):
            meta = {}

        # Resolve conversation binding + project access.
        try:
            conversation = _resolve_conversation(session, user, token, meta, messages)
        except _Denied as exc:
            return _error(403, "permission_error", str(exc), "project_forbidden", rid=rid)

        # Persist the inbound user turn, then assemble (recent turns now include it).
        user_text = _last_user_text(messages)
        brain.append_message(session, conversation, role=BrainMessageRole.USER,
                             content=user_text, request_id=rid)
        ctx = brain.assemble(session, conversation, user=user, model=settings.ai_model,
                             include_evidence=True, question=None, persist=True)
        session.commit()

        refs = _evidence_refs(ctx)
        supervoid_meta = {
            "state_version": ctx.versions.get("studio_state") or ctx.versions.get("project_state"),
            "versions": ctx.versions,
            "citations": refs,
            "policy": {"work_id": conversation.work_id, "story_world_id": conversation.story_world_id,
                       "profile": conversation.active_profile},
            "request_id": rid,
        }

        provider = get_provider()
        caps = provider.capabilities()
        chat_messages = [ChatMessage(role=m["role"], content=m.get("content")) for m in ctx.messages]
        req = ChatRequest(
            messages=chat_messages, model=settings.ai_model,
            temperature=ctx.temperature, max_tokens=ctx.max_tokens,
            tools=(ctx.tools if (caps.tools and ctx.tools) else None),
            stream=stream, request_id=rid,
        )
        conv_id = conversation.id
        served = _served()

        if stream:
            # Persistence happens AFTER the request session is torn down, so capture
            # the bound engine now and open a fresh session on it inside the
            # generator. Using the request session's bind (not the module-level
            # ``engine``) keeps streamed turns on the same DB the request used —
            # correct in production and isolated under the test engine override.
            bind = session.get_bind()
            slot_handed_off = True  # the generator owns the slot now
            return StreamingResponse(
                _stream(provider, caps, req, chat_messages, ctx, refs, supervoid_meta,
                        conv_id, user.id, rid, served, bind, guard),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                         REQUEST_ID_HEADER: rid},
            )

        # --- non-streaming ---
        return await _complete_nonstream(
            session, provider, req, chat_messages, ctx, conversation, refs,
            supervoid_meta, served, rid,
        )
    finally:
        # Release the slot unless it was handed to the streaming generator.
        if not slot_handed_off:
            await guard.__aexit__(None, None, None)


async def _complete_nonstream(session, provider, req, chat_messages, ctx, conversation,
                              refs, supervoid_meta, served, rid):
    try:
        t0 = perf_counter()
        if hasattr(provider, "acomplete"):
            result = await provider.acomplete(req)
        else:  # dry_run / sync-only provider
            result = provider.chat(chat_messages, model=settings.ai_model,
                                   temperature=ctx.temperature, max_tokens=ctx.max_tokens)
        latency_ms = (perf_counter() - t0) * 1000
    except CapabilityError as exc:
        # The request asked for something this provider can't do (e.g. tools).
        log.warning("brain-gateway: capability error · rid=%s · %s", rid, exc)
        return _error(400, "invalid_request_error",
                      "The requested capability is not supported by the model provider.",
                      "unsupported_capability", rid=rid)
    except ProviderUnavailableError as exc:
        # Log the upstream detail server-side (correlatable by request id); return
        # a GENERIC message so no upstream host/url/connection repr leaks to the client.
        log.warning("brain-gateway: provider unavailable · rid=%s · %s", rid, exc)
        return _error(503, "server_error", "The model provider is currently unavailable.",
                      "provider_unavailable", rid=rid)
    except ProviderTimeoutError as exc:
        log.warning("brain-gateway: provider timeout · rid=%s · %s", rid, exc)
        return _error(504, "server_error", "The model provider timed out.", "timeout", rid=rid)
    except MalformedResponseError as exc:
        log.warning("brain-gateway: malformed provider response · rid=%s · %s", rid, exc)
        return _error(502, "server_error", "Bad response from the model provider.", "bad_gateway", rid=rid)

    tool_calls = [
        {"id": tc.id, "type": tc.type, "function": {"name": tc.name, "arguments": tc.arguments}}
        for tc in (result.tool_calls or [])
    ]
    prompt_text = " ".join((m.get("content") or "") for m in ctx.messages)
    usage_out = _ensure_usage(result.usage, prompt_text=prompt_text,
                              completion_text=result.content or "")
    _persist_assistant(
        session, conversation, content=result.content, model=result.model,
        provider_name=result.provider, usage=usage_out, finish=result.finish_reason,
        tool_calls=tool_calls, latency_ms=latency_ms, ctx=ctx, retrieval_ids=refs,
        rid=(result.request_id or rid), reasoning=result.reasoning,
    )

    message = {"role": "assistant", "content": result.content or ""}
    finish = result.finish_reason or "stop"
    if tool_calls:
        message["content"] = result.content  # may be None for a pure tool call
        message["tool_calls"] = tool_calls
        finish = "tool_calls"
    resp = {
        # A gateway-minted, OpenAI-shaped id (consistent with the streaming path).
        # The internal request id stays on the X-Request-ID header + supervoid meta,
        # never leaking into the public completion id.
        "id": f"chatcmpl-{token_hex(12)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": served,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": usage_out,
        "supervoid": supervoid_meta,
    }
    return JSONResponse(content=resp, headers={REQUEST_ID_HEADER: rid})


async def _stream(provider, caps, req, chat_messages, ctx, refs, supervoid_meta,
                  conv_id, user_id, rid, served, bind=None, guard=None):
    stream_id = f"chatcmpl-{token_hex(6)}"
    created = int(time.time())
    acc: list[str] = []
    last_usage = None
    finish = None
    tool_calls_final: list[dict] = []
    cancelled = False
    errored = False

    def frame(delta, finish_reason=None):
        return "data: " + json.dumps({
            "id": stream_id, "object": "chat.completion.chunk", "created": created,
            "model": served, "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }) + "\n\n"

    t0 = perf_counter()
    try:
        # The concurrency slot was acquired by the caller (before any persistence)
        # and is released in this generator's finally.
        if caps.streaming and hasattr(provider, "astream"):
            first = True
            async for chunk in provider.astream(req):
                delta: dict = {}
                if first:
                    delta["role"] = "assistant"
                    first = False
                if chunk.content:
                    delta["content"] = chunk.content
                    acc.append(chunk.content)
                if chunk.tool_calls:
                    # Streamed tool_calls MUST carry an integer `index` — the
                    # OpenAI client merges fragmented call deltas across chunks
                    # by it. Fall back to enumeration when the provider omits it.
                    tcs = [{"index": tc.index if tc.index is not None else i,
                            "id": tc.id, "type": tc.type,
                            "function": {"name": tc.name, "arguments": tc.arguments}}
                           for i, tc in enumerate(chunk.tool_calls)]
                    delta["tool_calls"] = tcs
                    tool_calls_final.extend(tcs)
                if chunk.usage:
                    last_usage = chunk.usage
                if chunk.finish_reason:
                    finish = chunk.finish_reason
                yield frame(delta, chunk.finish_reason)
        else:
            # Synthesize a stream from a single completion (dry_run / non-stream provider).
            if hasattr(provider, "acomplete"):
                result = await provider.acomplete(req)
            else:
                result = provider.chat(chat_messages, model=settings.ai_model,
                                       temperature=ctx.temperature, max_tokens=ctx.max_tokens)
            last_usage = result.usage
            finish = result.finish_reason or "stop"
            acc.append(result.content or "")
            tool_calls_final = [
                {"index": i, "id": tc.id, "type": tc.type,
                 "function": {"name": tc.name, "arguments": tc.arguments}}
                for i, tc in enumerate(result.tool_calls or [])
            ]
            yield frame({"role": "assistant"})
            if result.content:
                yield frame({"content": result.content})
            if tool_calls_final:
                yield frame({"tool_calls": tool_calls_final})
            yield frame({}, finish)

        # Final usage + extension-metadata frame, then the literal terminator.
        prompt_text = " ".join((m.get("content") or "") for m in ctx.messages)
        usage_out = _ensure_usage(last_usage, prompt_text=prompt_text,
                                  completion_text="".join(acc))
        yield "data: " + json.dumps({
            "id": stream_id, "object": "chat.completion.chunk", "created": created,
            "model": served, "choices": [], "usage": usage_out, "supervoid": supervoid_meta,
        }) + "\n\n"
        yield "data: [DONE]\n\n"
    except CapabilityError as exc:
        errored = True
        finish = "error"
        log.warning("brain-gateway: stream capability error · rid=%s · %s", rid, exc)
        yield "data: " + json.dumps({"error": {
              "message": "The requested capability is not supported by the model provider.",
              "type": "invalid_request_error", "code": "unsupported_capability", "param": None}}) + "\n\n"
    except ProviderTimeoutError as exc:
        errored = True
        finish = "error"
        log.warning("brain-gateway: stream provider timeout · rid=%s · %s", rid, exc)
        yield "data: " + json.dumps({"error": {"message": "The model provider timed out.",
              "type": "server_error", "code": "timeout", "param": None}}) + "\n\n"
    except MalformedResponseError as exc:
        errored = True
        finish = "error"
        log.warning("brain-gateway: stream malformed provider response · rid=%s · %s", rid, exc)
        yield "data: " + json.dumps({"error": {"message": "Bad response from the model provider.",
              "type": "server_error", "code": "bad_gateway", "param": None}}) + "\n\n"
    except ProviderUnavailableError as exc:
        errored = True
        finish = "error"
        log.warning("brain-gateway: stream provider unavailable · rid=%s · %s", rid, exc)
        yield "data: " + json.dumps({"error": {"message": "The model provider is currently unavailable.",
              "type": "server_error", "code": "provider_unavailable", "param": None}}) + "\n\n"
    except asyncio.CancelledError:
        cancelled = True
        raise
    finally:
        latency_ms = (perf_counter() - t0) * 1000
        # Don't persist a spurious empty assistant turn when the request was
        # rejected/failed before producing anything (e.g. concurrency 429). A
        # partial stream (some content, or a mid-flight cancellation) is still
        # worth recording.
        produced = bool("".join(acc).strip()) or bool(tool_calls_final)
        skip_persist = errored and not produced and not cancelled
        # Persist in a FRESH session — the request-scoped one may be torn down.
        try:
            with Session(bind or engine) as s:
                conv = s.get(BrainConversation, conv_id)
                if conv is not None and not skip_persist:
                    prompt_text = " ".join((m.get("content") or "") for m in ctx.messages)
                    persist_usage = _ensure_usage(
                        last_usage, prompt_text=prompt_text, completion_text="".join(acc)
                    )
                    _persist_assistant(
                        s, conv, content="".join(acc), model=settings.ai_model,
                        provider_name=settings.ai_provider, usage=persist_usage,
                        finish=(finish or ("cancelled" if cancelled else None)),
                        tool_calls=tool_calls_final, latency_ms=latency_ms, ctx=ctx,
                        retrieval_ids=refs, rid=rid, cancelled=cancelled,
                    )
        except Exception:  # never let persistence break the (already-sent) stream
            log.exception("brain-gateway: failed to persist streamed assistant turn")
        # Release the concurrency slot the caller handed us, exactly once.
        if guard is not None:
            try:
                await guard.__aexit__(None, None, None)
            except Exception:  # pragma: no cover - release must never raise
                log.exception("brain-gateway: failed to release concurrency slot")
