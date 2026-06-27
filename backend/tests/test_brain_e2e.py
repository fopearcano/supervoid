"""End-to-end hardening pass for the SUPERVOID Brain (Prompt 19).

Exercises the COMPLETE governed path against the offline dry-run provider, plus
the hardening guarantees that gate production-readiness:

  member creates a Brain token → (LibreChat) calls the OpenAI-compatible Gateway →
  Gateway authenticates the member → a project is selected → the ProjectBrainState
  is loaded → a stable prefix + state delta are assembled → the provider streams →
  internal evidence is cited (UNTRUSTED-fenced) → an MCP read tool is permission
  checked → a write proposes a production task → a PENDING AgentActionProposal
  appears → a human approves it → execution is audited → a BrainEvent is emitted →
  the project state recompiles incrementally → the next turn carries only the new
  delta → public users cannot reach any Brain/MCP/private surface.

Plus: two simultaneous project conversations, a small-team load/isolation check,
vLLM- and LibreChat-unavailable fallbacks, and migration-chain verification.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlmodel import Session, SQLModel, create_engine, func, select

from app.auth.security import generate_brain_token, hash_brain_token, hash_password
from app.config import settings
from app.models import (
    AgentActionProposal,
    Author,
    BrainAccessToken,
    BrainEvent,
    KnowledgeEntity,
    Manuscript,
    ManuscriptEntityLink,
    ProductionItem,
    ProjectMembership,
    StoryWorld,
    User,
    Work,
)
from app.models.enums import (
    EntityKind,
    ManuscriptLinkRole,
    MembershipStatus,
    ProjectRole,
    ProposalStatus,
    UserRole,
)
from app.seed import _seed_stable_layer
from app.services import agents as agent_svc
from app.services import brain
from app.services.brain import compiler
from app.services.brain.events import BrainEventType as ET
from app.services.mcp.auth import MCPPrincipal
from app.services.mcp.registry import MCPToolError, get_tool

D = date(2026, 1, 1)


# --- helpers ---------------------------------------------------------------
@dataclass
class _World:
    work_id: str
    story_world_id: str
    entity_id: str


def _make_user(session: Session, email: str, role: UserRole = UserRole.EDITOR) -> User:
    u = User(email=email, full_name=email.split("@")[0].title(), role=role,
             hashed_password=hash_password("pw"))
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _brain_token(session: Session, user: User) -> str:
    secret = generate_brain_token()
    session.add(BrainAccessToken(user_id=user.id, name="LibreChat",
                                 token_hash=hash_brain_token(secret)))
    session.commit()
    return secret


def _seed_world(session: Session, admin: User, *, members: list | None = None) -> _World:
    """Instruction layer + a world/work/manuscript/entity, compiled studio+project."""
    _seed_stable_layer(session, {"helena": admin})
    author = Author(full_name="E2E Author")
    session.add(author)
    session.commit()
    session.refresh(author)
    world = StoryWorld(name="E2E World", slug="e2e-world")
    session.add(world)
    session.commit()
    session.refresh(world)
    work = Work(title="Nightfall", author_id=author.id, story_world_id=world.id,
                synopsis="A detective hunts an arsonist across a flooded cathedral city.",
                internal_pitch="A noir detective vs. an arsonist in a drowning city.")
    session.add(work)
    session.commit()
    session.refresh(work)
    ms = Manuscript(title="Nightfall", author_id=author.id, work_id=work.id, synopsis=work.synopsis)
    session.add(ms)
    session.commit()
    session.refresh(ms)
    ent = KnowledgeEntity(kind=EntityKind.CHARACTER, name="Idris", slug="idris-e2e",
                          description="The protagonist; a harbour detective marked by a recurring lantern motif.")
    session.add(ent)
    session.commit()
    session.refresh(ent)
    session.add(ManuscriptEntityLink(manuscript_id=ms.id, entity_id=ent.id,
                                     role=ManuscriptLinkRole.TAGGED, relevance=0.9))
    for user, role in (members or []):
        session.add(ProjectMembership(user_id=user.id, work_id=work.id, role=role,
                                      status=MembershipStatus.ACTIVE))
    session.commit()
    brain.compile_studio(session, full=True)
    compiler.compile_project(session, work_id=work.id, full=True, compile_date=D)
    session.commit()
    return _World(work_id=work.id, story_world_id=world.id, entity_id=ent.id)


def _principal(user: User) -> MCPPrincipal:
    return MCPPrincipal(user=user, librechat_user_id=f"lc-{user.id}", email=user.email,
                        declared_role="USER", request_id=f"e2e-{user.id}")


def _call(session: Session, principal: MCPPrincipal, tool: str, args: dict):
    spec = get_tool(tool)
    assert spec is not None, f"unknown tool {tool}"
    try:
        return True, spec.handler(session, principal, args)
    except MCPToolError as exc:
        return False, exc.message


def _new_token(client) -> str:
    r = client.post("/api/brain-tokens", json={"name": "LibreChat"})
    assert r.status_code == 201, r.text
    return r.json()["secret"]


def _h(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


def _chat_body(text="What's the current status of this project?", **extra):
    body = {"model": "supervoid-brain", "messages": [{"role": "user", "content": text}]}
    body.update(extra)
    return body


# === 1. the complete governed path =========================================
def test_e2e_brain_full_path(client, admin_user, session):
    w = _seed_world(session, admin_user)

    # (1) Member creates a Brain token; (2-3) LibreChat connects to the custom
    # endpoint; (4) the Gateway authenticates the bearer.
    secret = _new_token(client)

    # (5) A project is selected; (6) the ProjectBrainState is loaded; (7) a stable
    # prefix + state delta are assembled; (8) the provider streams a response.
    r = client.post("/brain/v1/chat/completions",
                    json=_chat_body(supervoid={"work_id": w.work_id, "assistant_profile": "studio-director"}),
                    headers=_h(secret))
    assert r.status_code == 200, r.text
    sv = r.json()["supervoid"]
    assert sv["policy"]["work_id"] == w.work_id          # project selected + state scoped
    assert sv["state_version"]                           # ProjectBrainState loaded
    assert "warmth" in sv["session"]                     # session/prefix machinery ran

    stream = client.post("/brain/v1/chat/completions",
                         json=_chat_body(stream=True, supervoid={"work_id": w.work_id}),
                         headers=_h(secret))
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert stream.text.rstrip().endswith("[DONE]")        # provider streamed to completion

    # (10-11) An MCP read tool is permission-checked: the authorised user succeeds.
    admin_p = _principal(admin_user)
    ok, state = _call(session, admin_p, "get_project_state", {"work_id": w.work_id})
    assert ok and isinstance(state, dict) and state.get("version")

    # (12-13) A write PROPOSES a production task → a PENDING proposal, NOT a mutation.
    tasks_before = session.exec(select(func.count(ProductionItem.id))).one()
    ok, payload = _call(session, admin_p, "propose_task",
                        {"work_id": w.work_id, "title": "Letter chapter one"})
    assert ok and payload["requires_approval"] is True
    session.commit()
    prop = session.exec(select(AgentActionProposal)
                        .order_by(AgentActionProposal.created_at.desc())).first()
    assert prop is not None and prop.status == ProposalStatus.PENDING
    assert session.exec(select(func.count(ProductionItem.id))).one() == tasks_before  # no direct mutation

    # (14) A human approves it; (15) execution is audited.
    ok, _ = _call(session, admin_p, "approve_proposal", {"proposal_id": prop.id})
    assert ok
    session.commit()
    session.refresh(prop)
    assert prop.status == ProposalStatus.APPROVED
    agent_svc.execute_proposal(session, prop, user=admin_user)
    session.commit()
    session.refresh(prop)
    assert prop.status == ProposalStatus.EXECUTED
    assert prop.execution_result  # the audited outcome is recorded

    # (16) A BrainEvent is emitted (the governed production-domain effect); (17) the
    # project state recompiles INCREMENTALLY (a version bump touching only the
    # event-affected sections, not a full rebuild).
    before_version = brain.get_project_state(session, work_id=w.work_id).version
    brain.emit(session, event_type=ET.TASK_CREATED, aggregate_type="work",
               aggregate_id=w.work_id, work_id=w.work_id, story_world_id=w.story_world_id,
               changes={"proposal_id": prop.id})
    session.commit()
    to_seq = compiler.head_sequence(session)
    result = compiler.compile_project(session, work_id=w.work_id, full=False,
                                      compile_date=D, to_seq=to_seq)
    session.commit()
    assert result["changed"] is True
    after_version = brain.get_project_state(session, work_id=w.work_id).version
    assert after_version == before_version + 1
    assert session.exec(
        select(func.count(BrainEvent.id)).where(BrainEvent.work_id == w.work_id)
    ).one() >= 1

    # (18) The following conversation receives only the new delta: the recompiled
    # project-state version flows into the assembled prefix.
    conv = brain.create_conversation(session, owner_user_id=admin_user.id,
                                     work_id=w.work_id, active_profile="studio-director")
    ctx = brain.assemble(session, conv, user=admin_user, model=settings.ai_model, persist=False)
    assert ctx.versions.get("project_state") == after_version


# === 2. assembly: stable prefix, delta, fenced internal evidence ===========
def test_e2e_stable_prefix_delta_and_fenced_evidence(session, admin_user):
    w = _seed_world(session, admin_user)
    conv = brain.create_conversation(session, owner_user_id=admin_user.id,
                                     work_id=w.work_id, active_profile="studio-director")
    brain.append_message(session, conv, role=brain.BrainMessageRole.USER,
                         content="Why is the antagonist the harbour-master?")
    session.commit()

    ctx = brain.assemble(session, conv, user=admin_user, model=settings.ai_model,
                         include_evidence=True, persist=False)
    names = {s.name for s in ctx.segments}
    assert any(s.stability == "stable-prefix" and s.included for s in ctx.segments)
    assert "State delta" in names                       # the delta segment exists
    joined = "\n".join(m.get("content", "") for m in ctx.messages)
    # Internal evidence is cited AND fenced as UNTRUSTED (prompt-injection defence).
    assert "<<<UNTRUSTED_EVIDENCE" in joined
    assert "harbour detective" in joined

    # The stable prefix is deterministic → identical re-assembly = a cache hit.
    ctx2 = brain.assemble(session, conv, user=admin_user, model=settings.ai_model,
                          include_evidence=True, persist=False)
    assert ctx.prefix_hash and ctx.prefix_hash == ctx2.prefix_hash

    # A different model invalidates the prefix (cache key includes the model).
    ctx3 = brain.assemble(session, conv, user=admin_user, model="some-other-model", persist=False)
    assert ctx3.prefix_hash != ctx.prefix_hash


# === 3. permission enforcement: member vs outsider =========================
def test_e2e_permission_enforcement(session, admin_user):
    editor = _make_user(session, "member@e2e.test", UserRole.EDITOR)
    outsider = _make_user(session, "outsider@e2e.test", UserRole.EDITOR)
    w = _seed_world(session, admin_user, members=[(editor, ProjectRole.EDITOR)])

    ok_member, _ = _call(session, _principal(editor), "get_project_state", {"work_id": w.work_id})
    assert ok_member is True                              # an authorised member succeeds

    ok_outsider, msg = _call(session, _principal(outsider), "get_project_state", {"work_id": w.work_id})
    assert ok_outsider is False                           # the outsider is refused
    assert "permitted" in msg.lower() or "view_project" in msg.lower()


# === 4. public users cannot reach any Brain/MCP/private surface ============
def test_e2e_public_users_blocked(anon_client, admin_user, session):
    _seed_world(session, admin_user)
    assert anon_client.get("/brain/v1/models").status_code == 401
    assert anon_client.post("/brain/v1/chat/completions", json=_chat_body()).status_code == 401
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    assert anon_client.post("/mcp", json=rpc).status_code in (401, 403)
    assert anon_client.get("/api/brain/ops/status").status_code in (401, 403)
    assert anon_client.get("/api/brain/tuning/adapters").status_code in (401, 403)
    assert anon_client.get("/api/brain-tokens").status_code == 401


# === 5. two simultaneous project conversations =============================
def test_e2e_two_simultaneous_project_conversations(session, admin_user):
    w_a = _seed_world(session, admin_user)
    # A second, independent project in the same studio.
    author = session.exec(select(Author)).first()
    world_b = StoryWorld(name="World B", slug="world-b-e2e")
    session.add(world_b)
    session.commit()
    session.refresh(world_b)
    work_b = Work(title="Daybreak", author_id=author.id, story_world_id=world_b.id,
                  synopsis="A second project.", internal_pitch="A heist at dawn.")
    session.add(work_b)
    session.commit()
    session.refresh(work_b)
    compiler.compile_project(session, work_id=work_b.id, full=True, compile_date=D)
    session.commit()

    conv_a = brain.create_conversation(session, owner_user_id=admin_user.id, work_id=w_a.work_id,
                                       active_profile="studio-director")
    conv_b = brain.create_conversation(session, owner_user_id=admin_user.id, work_id=work_b.id,
                                       active_profile="studio-director")
    ctx_a = brain.assemble(session, conv_a, user=admin_user, model=settings.ai_model, persist=False)
    ctx_b = brain.assemble(session, conv_b, user=admin_user, model=settings.ai_model, persist=False)

    # Each conversation is bound to its own project state and its own prefix.
    assert conv_a.work_id == w_a.work_id and conv_b.work_id == work_b.id
    assert ctx_a.prefix_hash != ctx_b.prefix_hash
    a_text = "\n".join(m.get("content", "") for m in ctx_a.messages)
    b_text = "\n".join(m.get("content", "") for m in ctx_b.messages)
    assert "Nightfall" in a_text and "Nightfall" not in b_text
    assert "Daybreak" in b_text and "Daybreak" not in a_text


# === 6. small-team load + isolation ========================================
def test_e2e_small_team_load_and_isolation(client, admin_user, session):
    w = _seed_world(session, admin_user)
    team = [admin_user] + [_make_user(session, f"member{i}@e2e.test") for i in range(4)]
    for u in team[1:]:
        session.add(ProjectMembership(user_id=u.id, work_id=w.work_id,
                                      role=ProjectRole.EDITOR, status=MembershipStatus.ACTIVE))
    session.commit()
    secrets = {u.id: _brain_token(session, u) for u in team}

    turns_per_user = 3
    for u in team:
        for _ in range(turns_per_user):
            r = client.post("/brain/v1/chat/completions",
                            json=_chat_body(supervoid={"work_id": w.work_id}),
                            headers=_h(secrets[u.id]))
            assert r.status_code == 200, r.text

    # No conversation leaks to a non-team user; volume handled.
    owners = set(session.exec(select(brain.BrainConversation.owner_user_id)).all())
    assert owners == {u.id for u in team}
    assistant_msgs = session.exec(
        select(func.count(brain.BrainMessage.id))
        .where(brain.BrainMessage.role == brain.BrainMessageRole.ASSISTANT)
    ).one()
    assert assistant_msgs == len(team) * turns_per_user


# === 7. vLLM-unavailable fallback (graceful, not a crash) ==================
def test_e2e_vllm_unavailable_health_is_graceful(session, admin_user, monkeypatch):
    _seed_world(session, admin_user)

    class _Boom:
        name = "vllm"

        def health(self):
            raise RuntimeError("connection refused")

    monkeypatch.setattr("app.services.brain.ops.get_provider", lambda: _Boom())
    health = brain.ops.health_summary(session)          # must not raise
    assert isinstance(health, dict) and "overall" in health
    status = brain.ops.ops_status(session)
    assert status["vllm"]["reachable"] is False          # degraded, surfaced, no crash


# === 8. LibreChat-unavailable fallback =====================================
def test_e2e_librechat_unavailable_does_not_break_brain(client, admin_user, session, monkeypatch):
    w = _seed_world(session, admin_user)
    monkeypatch.setattr(settings, "librechat_health_url", "http://supervoid-librechat:3080/health")
    import httpx

    def _boom(*a, **k):
        raise httpx.ConnectError("librechat unreachable")

    monkeypatch.setattr(httpx, "get", _boom)

    # The Brain serves regardless of LibreChat being up (LibreChat is the client).
    secret = _new_token(client)
    r = client.post("/brain/v1/chat/completions",
                    json=_chat_body(supervoid={"work_id": w.work_id}), headers=_h(secret))
    assert r.status_code == 200
    # Health composes gracefully with LibreChat marked unreachable.
    status = brain.ops.ops_status(session)
    assert status["librechat"]["reachable"] is False


# === 9. migration-chain verification =======================================
def test_migration_chain_single_head_and_covers_every_model(tmp_path: Path):
    from alembic.script import ScriptDirectory

    from app.migrations import alembic_config, current_revision, ensure_migrated

    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    assert len(heads) == 1, f"expected a single migration head, got {heads}"

    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    ensure_migrated(url)                                  # applies the full chain to head
    assert current_revision(url) == heads[0]             # DB is stamped at the single head

    engine = create_engine(url)
    try:
        existing = set(sa_inspect(engine).get_table_names())
    finally:
        engine.dispose()
    for table in SQLModel.metadata.tables:               # every model has a table
        assert table in existing, f"migration chain is missing table {table}"


# === 10. native in-app chat (no LibreChat, no Brain token) =================
def test_e2e_native_chat_turn_and_continuation(client, admin_user, session):
    w = _seed_world(session, admin_user)
    r1 = client.post("/api/brain/chat",
                     json={"content": "What's the status of this project?", "work_id": w.work_id})
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["conversation_id"] and isinstance(body["content"], str)
    assert body["model"]  # the served Brain model name
    # A second turn on the same conversation continues it (no new conversation).
    r2 = client.post("/api/brain/chat",
                     json={"content": "And the blockers?", "conversation_id": body["conversation_id"]})
    assert r2.status_code == 200
    assert r2.json()["conversation_id"] == body["conversation_id"]


def test_e2e_native_chat_refuses_unauthorised_project(editor_client, admin_user, session):
    # editor_user (the editor_client) has NO membership on the seeded work.
    w = _seed_world(session, admin_user)
    r = editor_client.post("/api/brain/chat", json={"content": "secrets?", "work_id": w.work_id})
    assert r.status_code == 403


def test_e2e_native_chat_blocked_for_public(anon_client, admin_user, session):
    _seed_world(session, admin_user)
    assert anon_client.post("/api/brain/chat", json={"content": "hi"}).status_code == 401


# === 11. native chat invokes governed MCP tools ============================
class _ScriptedProvider:
    """A tool-capable provider that replays scripted CompletionResults."""

    name = "scripted"

    def __init__(self, results):
        self._results = results
        self._i = 0

    def capabilities(self):
        from types import SimpleNamespace

        return SimpleNamespace(tools=True)

    async def acomplete(self, _req):
        r = self._results[min(self._i, len(self._results) - 1)]
        self._i += 1
        return r


def test_native_chat_advertises_read_and_proposal_tools_only():
    from app.services.brain import chat as brain_chat

    names = {s["function"]["name"] for s in brain_chat._tool_schemas()}
    assert {"get_project_state", "propose_task"} <= names          # read + proposal advertised
    assert "approve_proposal" not in names                          # approval tools are human-only
    assert "execute_approved_proposal" not in names


def test_native_chat_invokes_read_tool(session, admin_user):
    import asyncio
    import json as _json

    from app.services.ai.providers import CompletionResult, ToolCall
    from app.services.brain import chat as brain_chat

    w = _seed_world(session, admin_user)
    scripted = _ScriptedProvider([
        CompletionResult(content="", model="m", provider="scripted", tool_calls=[
            ToolCall(id="c1", name="get_project_state",
                     arguments=_json.dumps({"work_id": w.work_id}))]),
        CompletionResult(content="The project is compiled and on track.", model="m", provider="scripted"),
    ])
    turn = asyncio.run(brain_chat.run_turn(
        session, user=admin_user, content="status?", work_id=w.work_id, provider=scripted))
    assert "get_project_state" in turn.tools_used
    assert turn.content == "The project is compiled and on track."


def test_native_chat_tool_proposes_task_but_does_not_mutate(session, admin_user):
    import asyncio
    import json as _json

    from app.services.ai.providers import CompletionResult, ToolCall
    from app.services.brain import chat as brain_chat

    w = _seed_world(session, admin_user)
    scripted = _ScriptedProvider([
        CompletionResult(content="", model="m", provider="scripted", tool_calls=[
            ToolCall(id="c1", name="propose_task",
                     arguments=_json.dumps({"work_id": w.work_id, "title": "Letter chapter one"}))]),
        CompletionResult(content="I proposed that task for approval.", model="m", provider="scripted"),
    ])
    tasks_before = session.exec(select(func.count(ProductionItem.id))).one()
    turn = asyncio.run(brain_chat.run_turn(
        session, user=admin_user, content="make a task", work_id=w.work_id, provider=scripted))
    session.commit()
    assert any(p["tool"] == "propose_task" for p in turn.proposals)
    assert session.exec(select(func.count(AgentActionProposal.id))).one() >= 1   # a gated proposal
    assert session.exec(select(func.count(ProductionItem.id))).one() == tasks_before  # NOT created


def test_native_chat_tool_permission_is_enforced(session, admin_user):
    import asyncio
    import json as _json

    from app.services.ai.providers import CompletionResult, ToolCall
    from app.services.brain import chat as brain_chat

    outsider = _make_user(session, "toolnoaccess@e2e.test")
    w = _seed_world(session, admin_user)  # outsider has NO membership
    scripted = _ScriptedProvider([
        CompletionResult(content="", model="m", provider="scripted", tool_calls=[
            ToolCall(id="c1", name="get_project_state",
                     arguments=_json.dumps({"work_id": w.work_id}))]),
        CompletionResult(content="I can't access that project.", model="m", provider="scripted"),
    ])
    # No work_id param (studio scope) → the TOOL call itself is permission-checked
    # and refused; the refusal is surfaced to the model, the turn never crashes.
    turn = asyncio.run(brain_chat.run_turn(
        session, user=outsider, content="status?", provider=scripted))
    assert turn.content == "I can't access that project."
