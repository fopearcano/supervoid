"""Compatibility + behaviour tests for the SUPERVOID Brain Gateway.

The gateway speaks the OpenAI Chat Completions wire shape. We validate responses
against the official OpenAI Python client's own Pydantic models (the meaningful
compatibility guarantee), drive HTTP through the starlette TestClient, exercise
streaming (mocked via the offline dry_run provider), LibreChat-shaped fixtures,
auth/expiry/revocation, project-restriction denial, rate limiting,
provider-unavailable mapping, secret non-leakage, and persistence.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from openai.types import Model
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from sqlmodel import Session, select

from app.auth.security import hash_brain_token
from app.models import (
    Author,
    BrainAccessToken,
    ProjectMembership,
    User,
    Work,
)
from app.models.base import utcnow
from app.models.brain import BrainConversation, BrainMessage
from app.models.enums import (
    BrainMessageRole,
    MembershipStatus,
    ProjectRole,
    UserRole,
)
from app.routers import brain_gateway as gw
from app.seed import _seed_stable_layer
from app.services import brain
from datetime import timedelta


# --- fixtures / helpers -----------------------------------------------------
def _seed(session: Session, admin: User) -> None:
    _seed_stable_layer(session, {"helena": admin})
    brain.compile_studio(session, full=True)
    session.commit()


def _new_token(client, **body) -> str:
    body.setdefault("name", "LibreChat")
    r = client.post("/api/brain-tokens", json=body)
    assert r.status_code == 201, r.text
    return r.json()["secret"]


def _h(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


def _chat_body(text="ping", **extra):
    body = {"model": "supervoid-brain", "messages": [{"role": "user", "content": text}]}
    body.update(extra)
    return body


# --- 1. OpenAI-client-validated shapes --------------------------------------
def test_models_openai_shape(client, admin_user, session):
    _seed(session, admin_user)
    secret = _new_token(client)
    r = client.get("/brain/v1/models", headers=_h(secret))
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "list"
    model = Model.model_validate(data["data"][0])  # validates with the OpenAI type
    assert model.id == "supervoid-brain" and model.object == "model"


def test_chat_completion_openai_shape(client, admin_user, session):
    _seed(session, admin_user)
    secret = _new_token(client)
    r = client.post("/brain/v1/chat/completions", json=_chat_body(), headers=_h(secret))
    assert r.status_code == 200, r.text
    payload = r.json()
    # The top-level extension object must not break OpenAI parsing.
    completion = ChatCompletion.model_validate({k: v for k, v in payload.items() if k != "supervoid"})
    assert completion.object == "chat.completion"
    assert completion.choices[0].message.role == "assistant"
    assert payload["id"].startswith("chatcmpl-")
    assert payload["model"] == "supervoid-brain"
    assert "supervoid" in payload and "versions" in payload["supervoid"]


def test_curl_shaped_envelope(client, admin_user, session):
    _seed(session, admin_user)
    secret = _new_token(client)
    r = client.post("/brain/v1/chat/completions", json=_chat_body(), headers=_h(secret))
    body = r.json()
    assert set(["id", "object", "created", "model", "choices"]).issubset(body)
    assert body["choices"][0]["message"]["role"] == "assistant"


# --- 2. streaming (mocked via offline dry_run) ------------------------------
def _parse_sse(text: str):
    frames = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            frames.append("[DONE]")
        else:
            frames.append(json.loads(payload))
    return frames


def test_streaming_sse_shape(client, admin_user, session):
    _seed(session, admin_user)
    secret = _new_token(client)
    r = client.post("/brain/v1/chat/completions", json=_chat_body(stream=True), headers=_h(secret))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    frames = _parse_sse(r.text)
    assert frames[-1] == "[DONE]"  # literal terminator
    chunks = [f for f in frames if isinstance(f, dict) and f.get("object") == "chat.completion.chunk"]
    assert chunks, "no chunk frames"
    # first chunk carries the role delta; validate every chunk with the OpenAI type
    assert chunks[0]["choices"][0]["delta"].get("role") == "assistant"
    for ch in chunks:
        ChatCompletionChunk.model_validate({k: v for k, v in ch.items() if k != "supervoid"})
        # extension data must never live inside a delta
        if ch["choices"]:
            assert "supervoid" not in ch["choices"][0]["delta"]
    # a final usage-bearing frame exists
    assert any(isinstance(f, dict) and f.get("usage") is not None and not f.get("choices") for f in frames)


# --- 3. LibreChat-shaped conversation binding -------------------------------
def test_librechat_conversation_binds_and_continues(client, admin_user, session):
    _seed(session, admin_user)
    secret = _new_token(client)
    lc = "lc-conv-123"
    body = _chat_body("hello", extra_body={"supervoid": {"librechat_conversation_id": lc}})
    client.post("/brain/v1/chat/completions", json=body, headers=_h(secret))
    client.post("/brain/v1/chat/completions", json=body, headers=_h(secret))
    convs = session.exec(
        select(BrainConversation).where(BrainConversation.librechat_conversation_id == lc)
    ).all()
    assert len(convs) == 1  # second call CONTINUED, did not duplicate


# --- 4. auth -----------------------------------------------------------------
def test_missing_auth_401(client, admin_user, session):
    _seed(session, admin_user)
    r = client.get("/brain/v1/models", headers={"Authorization": ""})
    assert r.status_code == 401


def test_browser_jwt_rejected(client, admin_user, session, admin_token):
    _seed(session, admin_user)
    # an ordinary browser JWT must NOT authenticate the gateway
    r = client.get("/brain/v1/models", headers=_h(admin_token))
    assert r.status_code == 401


def test_valid_token_updates_last_used(client, admin_user, session):
    _seed(session, admin_user)
    secret = _new_token(client)
    before = session.exec(select(BrainAccessToken)).first().last_used_at
    client.get("/brain/v1/models", headers=_h(secret))
    session.expire_all()
    after = session.exec(select(BrainAccessToken)).first().last_used_at
    assert before is None and after is not None


def test_expired_and_revoked_tokens_401(client, admin_user, session):
    _seed(session, admin_user)
    secret = _new_token(client)
    tok = session.exec(select(BrainAccessToken)).first()
    tok.expires_at = utcnow() - timedelta(days=1)
    session.add(tok)
    session.commit()
    assert client.get("/brain/v1/models", headers=_h(secret)).status_code == 401

    tok.expires_at = None
    tok.revoked_at = utcnow()
    session.add(tok)
    session.commit()
    assert client.get("/brain/v1/models", headers=_h(secret)).status_code == 401


# --- 5. project restrictions / unauthorised projects ------------------------
def _work(session: Session, author_id: str) -> Work:
    w = Work(title="W", author_id=author_id)
    session.add(w)
    session.commit()
    session.refresh(w)
    return w


def test_unauthorised_project_denied(client, admin_user, session):
    _seed(session, admin_user)
    author = Author(full_name="A")
    session.add(author)
    session.commit()
    session.refresh(author)
    work_a = _work(session, author.id)
    work_b = _work(session, author.id)
    # token restricted to work A
    secret = _new_token(client, project_restrictions=[{"work_id": work_a.id}])
    # requesting work B → 403 (token doesn't permit it)
    body = _chat_body(extra_body={"supervoid": {"work_id": work_b.id}})
    r = client.post("/brain/v1/chat/completions", json=body, headers=_h(secret))
    assert r.status_code == 403
    assert r.json()["error"]["type"] == "permission_error"


def test_unauthorised_world_cannot_ride_authorised_work(client, admin_user, session):
    """A token restricted to work A must not permit a request that pairs work A
    with an *unauthorised* story world — every provided scope is gated."""
    _seed(session, admin_user)
    author = Author(full_name="A")
    session.add(author)
    session.commit()
    session.refresh(author)
    work_a = _work(session, author.id)
    secret = _new_token(client, project_restrictions=[{"work_id": work_a.id}])
    body = _chat_body(extra_body={"supervoid": {"work_id": work_a.id,
                                                "story_world_id": "sw-unauth"}})
    r = client.post("/brain/v1/chat/completions", json=body, headers=_h(secret))
    assert r.status_code == 403
    assert r.json()["error"]["type"] == "permission_error"


def test_restricted_token_cannot_continue_foreign_project_thread(
    client, admin_user, session
):
    """A pre-existing conversation bound to work B must not be continuable by a
    token restricted to work A, even when the continuation request sends only the
    LibreChat conversation id (no project metadata)."""
    _seed(session, admin_user)
    author = Author(full_name="A")
    session.add(author)
    session.commit()
    session.refresh(author)
    work_b = _work(session, author.id)
    # A conversation already bound to work B, owned by the admin user.
    conv = brain.create_conversation(
        session, owner_user_id=admin_user.id, librechat_conversation_id="lc-xyz",
        work_id=work_b.id, active_profile="studio-director", title="bound",
    )
    session.commit()
    secret = _new_token(client, project_restrictions=[{"work_id": "work-a-only"}])
    body = _chat_body(extra_body={"supervoid": {"librechat_conversation_id": "lc-xyz"}})
    r = client.post("/brain/v1/chat/completions", json=body, headers=_h(secret))
    assert r.status_code == 403
    assert r.json()["error"]["type"] == "permission_error"


def test_non_member_project_denied(client, session):
    # a non-admin user with no membership requesting a project → 403
    from app.auth.security import hash_password
    from app.auth import create_access_token

    editor = User(email="ed@s.test", full_name="Ed", role=UserRole.EDITOR,
                  hashed_password=hash_password("pw"))
    session.add(editor)
    session.commit()
    session.refresh(editor)
    _seed_stable_layer(session, {"helena": editor})  # editor seeds (only needs id)
    jwt, _ = create_access_token(subject=editor.id, role=editor.role.value)
    tok = client.post("/api/brain-tokens", json={"name": "t"}, headers=_h(jwt))
    secret = tok.json()["secret"]
    author = Author(full_name="A")
    session.add(author)
    session.commit()
    session.refresh(author)
    work = _work(session, author.id)
    body = _chat_body(extra_body={"supervoid": {"work_id": work.id}})
    r = client.post("/brain/v1/chat/completions", json=body, headers=_h(secret))
    assert r.status_code == 403


def test_no_metadata_uses_studio_director(client, admin_user, session):
    _seed(session, admin_user)
    secret = _new_token(client)
    r = client.post("/brain/v1/chat/completions", json=_chat_body(), headers=_h(secret))
    assert r.status_code == 200
    conv = session.exec(select(BrainConversation)).first()
    assert conv.work_id is None and conv.story_world_id is None


# --- 6. rate limiting --------------------------------------------------------
def test_rate_limit_429(client, admin_user, session, monkeypatch):
    _seed(session, admin_user)
    secret = _new_token(client)
    monkeypatch.setattr(gw._rate, "allow", lambda key: False)
    r = client.post("/brain/v1/chat/completions", json=_chat_body(), headers=_h(secret))
    assert r.status_code == 429
    assert r.json()["error"]["type"] == "rate_limit_error"
    assert "Retry-After" in r.headers


# --- 7. provider-unavailable mapping ----------------------------------------
def test_provider_unavailable_503(client, admin_user, session, monkeypatch):
    _seed(session, admin_user)
    secret = _new_token(client)
    from app.services.ai.providers.base import ProviderUnavailableError

    class _Down:
        def capabilities(self):
            from app.services.ai.providers.base import CAPS_VLLM
            return CAPS_VLLM

        async def acomplete(self, req):
            raise ProviderUnavailableError("vllm down at upstream")

    monkeypatch.setattr(gw, "get_provider", lambda: _Down())
    r = client.post("/brain/v1/chat/completions", json=_chat_body(), headers=_h(secret))
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "provider_unavailable"


def test_streaming_provider_error_frame(client, admin_user, session, monkeypatch):
    """A mid-stream provider failure yields an OpenAI-shaped error frame (with
    distinct code + `param`) and closes the stream — no trailing [DONE]."""
    _seed(session, admin_user)
    secret = _new_token(client)
    from app.services.ai.providers.base import CAPS_VLLM, ProviderTimeoutError

    class _Timeout:
        def capabilities(self):
            return CAPS_VLLM

        async def astream(self, req):
            raise ProviderTimeoutError("upstream read timed out")
            yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(gw, "get_provider", lambda: _Timeout())
    r = client.post("/brain/v1/chat/completions", json=_chat_body(stream=True), headers=_h(secret))
    assert r.status_code == 200  # the stream opened before the provider failed
    frames = _parse_sse(r.text)
    err = next(f for f in frames if isinstance(f, dict) and "error" in f)
    assert err["error"]["code"] == "timeout"
    assert err["error"]["param"] is None
    assert "[DONE]" not in frames  # OpenAI closes after an error, no terminator


def test_streamed_tool_calls_carry_index(client, admin_user, session, monkeypatch):
    """Streamed tool_calls deltas must include the integer `index` the OpenAI
    client uses to merge fragmented calls — validate with the OpenAI chunk type."""
    _seed(session, admin_user)
    secret = _new_token(client)
    from app.services.ai.providers.base import CAPS_VLLM, ToolCall

    class _Result:
        content = None
        model = "m"
        provider = "vllm"
        usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        finish_reason = "tool_calls"
        reasoning = None
        request_id = "rid"
        tool_calls = [ToolCall(id="call_1", name="lookup", arguments="{}", type="function", index=0)]

    class _Tooling:
        def capabilities(self):
            return CAPS_VLLM

        async def acomplete(self, req):
            return _Result()

    monkeypatch.setattr(gw, "get_provider", lambda: _Tooling())
    r = client.post("/brain/v1/chat/completions", json=_chat_body(stream=True), headers=_h(secret))
    assert r.status_code == 200
    frames = _parse_sse(r.text)
    tc_frames = [
        f for f in frames
        if isinstance(f, dict) and f.get("choices") and f["choices"][0]["delta"].get("tool_calls")
    ]
    assert tc_frames, "no tool_call delta frame emitted"
    for f in tc_frames:
        for tc in f["choices"][0]["delta"]["tool_calls"]:
            assert tc.get("index") is not None
        ChatCompletionChunk.model_validate({k: v for k, v in f.items() if k != "supervoid"})


def test_capability_error_maps_to_400(client, admin_user, session, monkeypatch):
    """A provider CapabilityError becomes a clean OpenAI 400, not a raw 500."""
    _seed(session, admin_user)
    secret = _new_token(client)
    from app.services.ai.providers.base import CAPS_VLLM, CapabilityError

    class _NoCap:
        def capabilities(self):
            return CAPS_VLLM

        async def acomplete(self, req):
            raise CapabilityError("tools not supported")

    monkeypatch.setattr(gw, "get_provider", lambda: _NoCap())
    r = client.post("/brain/v1/chat/completions", json=_chat_body(), headers=_h(secret))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "unsupported_capability"


def test_concurrency_rejection_persists_nothing(client, admin_user, session, monkeypatch):
    """A concurrency rejection is taken BEFORE any persistence, so it returns a
    clean 429 and leaves neither a dangling user turn nor an empty assistant turn."""
    _seed(session, admin_user)
    secret = _new_token(client)
    from app.utils.throttle import ConcurrencyExceeded

    class _Guard:
        async def __aenter__(self):
            raise ConcurrencyExceeded()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(gw._conc, "guard", lambda key: _Guard())
    before = len(session.exec(select(BrainMessage)).all())
    # Streaming and non-streaming both reject up front.
    r = client.post("/brain/v1/chat/completions", json=_chat_body(stream=True), headers=_h(secret))
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "concurrency_limited"
    r2 = client.post("/brain/v1/chat/completions", json=_chat_body(), headers=_h(secret))
    assert r2.status_code == 429
    session.expire_all()
    after = len(session.exec(select(BrainMessage)).all())
    assert after == before  # nothing persisted on rejection (no dangling turns)


# --- 8. no secret leak -------------------------------------------------------
def test_no_api_key_leak(client, admin_user, session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ai_api_key", "sk-UPSTREAM-SECRET-xyz")
    _seed(session, admin_user)
    secret = _new_token(client)
    r = client.post("/brain/v1/chat/completions", json=_chat_body(), headers=_h(secret))
    assert "sk-UPSTREAM-SECRET-xyz" not in r.text
    # the brain token plaintext is only ever in the create response, never here
    assert secret not in r.text


# --- 9. persistence ----------------------------------------------------------
def test_turn_is_persisted(client, admin_user, session):
    _seed(session, admin_user)
    secret = _new_token(client)
    client.post("/brain/v1/chat/completions", json=_chat_body("remember this"), headers=_h(secret))
    msgs = session.exec(select(BrainMessage).order_by(BrainMessage.created_at)).all()
    roles = [m.role for m in msgs]
    assert BrainMessageRole.USER in roles and BrainMessageRole.ASSISTANT in roles
    assistant = [m for m in msgs if m.role == BrainMessageRole.ASSISTANT][-1]
    assert "latency_ms" in assistant.structured_content
    conv = session.exec(select(BrainConversation)).first()
    assert conv.last_state_version is not None  # advanced by the assistant turn


# --- 10. limiter units (deterministic, no HTTP) -----------------------------
def test_rate_limiter_token_bucket():
    from app.utils.throttle import RateLimiter

    rl = RateLimiter(rate_per_min=60, burst=2)
    assert rl.allow("u") and rl.allow("u")     # burst of 2
    assert not rl.allow("u")                    # third is rejected
    assert rl.allow("other")                    # per-user isolation


def test_concurrency_limiter_blocks_excess():
    from app.utils.throttle import ConcurrencyLimiter, ConcurrencyExceeded

    async def run():
        lim = ConcurrencyLimiter(max_concurrency=1)
        async with lim.guard("u"):
            # a second acquire for the same key must not succeed immediately
            sem = await lim._sem("u")
            assert sem.locked()
        # released now
        async with lim.guard("u"):
            pass

    asyncio.run(run())
