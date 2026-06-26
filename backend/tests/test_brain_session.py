"""Tests for the Brain stateful-session + prefix-cache strategy (Prompt 8).

Headline guarantee: repeated turns generate an IDENTICAL stable prefix until an
invalidating event occurs — with one test per invalidation rule, each proving the
prefix_hash is stable across plain turns and moves (with the correct machine
reason) on the triggering event. Plus metrics, the non-tautological eligibility
estimate, the hot/warm/cold lifecycle, prewarming (dry-run-safe, archived
excluded, rate-limited), and compaction that retains messages and never drops
approved decisions.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from app.auth.security import hash_password
from app.models import (
    Author,
    BrainCheckpoint,
    BrainMessage,
    BrainSession,
    ProjectMembership,
    StoryWorld,
    User,
    Work,
)
from app.models.base import utcnow
from app.models.enums import (
    BrainConversationStatus,
    BrainMessageRole,
    BrainScope,
    BrainSessionWarmth,
    DecisionStatus,
    MembershipStatus,
    ProjectRole,
    SessionInvalidationReason as RR,
    UserRole,
    WorkStatus,
)
from app.seed import _seed_stable_layer
from app.services import brain
from app.services.brain import session as session_svc
from app.services.brain.events import BrainEventType as ET

D = date(2026, 1, 1)


# --- helpers ---------------------------------------------------------------
def _user(session: Session, email: str, role: UserRole) -> User:
    u = User(email=email, full_name=email.split("@")[0], role=role,
             hashed_password=hash_password("pw"))
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _seed_layer(session: Session) -> User:
    admin = _user(session, "admin@s.test", UserRole.ADMIN)
    _seed_stable_layer(session, {"helena": admin})
    brain.compile_studio(session, full=True)
    session.commit()
    return admin


def _work(session: Session, *, status: WorkStatus = WorkStatus.IN_DEVELOPMENT) -> Work:
    a = Author(full_name="A")
    session.add(a)
    session.commit()
    session.refresh(a)
    w = Work(title="W", author_id=a.id, status=status)
    session.add(w)
    session.commit()
    session.refresh(w)
    return w


def _member(session: Session, user: User, work: Work, role: ProjectRole) -> ProjectMembership:
    m = ProjectMembership(
        user_id=user.id, work_id=work.id, role=role, status=MembershipStatus.ACTIVE,
    )
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def _sig(session: Session, conv, user, *, model=None):
    """Assemble read-only and build the PrefixSignature (+ the authoritative
    prefix_hash) for the current state."""
    ctx = brain.assemble(
        session, conv, user=user, model=model, include_evidence=True, persist=False
    )
    studio = brain.get_studio_state(session)
    proj = (
        brain.get_project_state(session, work_id=conv.work_id, story_world_id=conv.story_world_id)
        if (conv.work_id or conv.story_world_id) else None
    )
    sig = brain.PrefixSignature.from_context(ctx, conv, studio_state=studio, project_state=proj)
    return sig, ctx.prefix_hash


def _studio_conv(session: Session, owner) -> "object":
    conv = brain.create_conversation(
        session, owner_user_id=owner.id, active_profile="studio-director"
    )
    session.commit()
    return conv


# === headline identity test ================================================
def test_repeated_turns_identical_prefix_until_event(session: Session) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    a_sig, a_hash = _sig(session, conv, admin)
    # a plain new user turn must NOT move the prefix
    brain.append_message(session, conv, role=BrainMessageRole.USER, content="another question")
    session.commit()
    b_sig, b_hash = _sig(session, conv, admin)
    assert a_hash == b_hash
    result = brain.diff_signature(a_sig, b_sig)
    assert result.invalidated is False and result.reasons == ()
    assert brain.is_warm_eligible(a_sig, b_sig) is True


# === one test per invalidation rule ========================================
def test_invalidation_constitution_version(session: Session) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    before, before_h = _sig(session, conv, admin)
    brain.instruction.add_version(
        session, "constitution", "studio-constitution",
        fields={"body": "New standing rules.", "notes": "v2"}, created_by_id=admin.id,
    )
    session.commit()
    after, after_h = _sig(session, conv, admin)
    result = brain.diff_signature(before, after)
    assert RR.CONSTITUTION_CHANGED in result.reasons
    assert before_h != after_h


def test_invalidation_profile_changed(session: Session) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    before, before_h = _sig(session, conv, admin)
    brain.instruction.add_version(
        session, "profile", "studio-director",
        fields={
            "purpose": "A changed purpose", "permitted_domains": [],
            "required_project_scope": False, "available_tools": [], "tone": "brisk",
            "response_format": "prose", "approval_policy": "default",
            "default_temperature": 0.3, "output_limit": 1500,
            "model_preference": "inherit", "required_scopes": [], "notes": None,
        },
        created_by_id=admin.id,
    )
    session.commit()
    after, after_h = _sig(session, conv, admin)
    assert RR.PROFILE_CHANGED in brain.diff_signature(before, after).reasons
    assert before_h != after_h


def test_invalidation_permissions_changed(session: Session) -> None:
    admin = _seed_layer(session)
    editor = _user(session, "ed@s.test", UserRole.EDITOR)
    work = _work(session)
    membership = _member(session, editor, work, ProjectRole.VIEWER)
    conv = brain.create_conversation(
        session, owner_user_id=editor.id, work_id=work.id, active_profile="studio-director"
    )
    session.commit()
    before, before_h = _sig(session, conv, editor)
    # upgrade the project role → resolved scopes (and the fingerprint) change
    membership.role = ProjectRole.EDITOR
    session.add(membership)
    session.commit()
    after, after_h = _sig(session, conv, editor)
    assert before.permissions_fingerprint != after.permissions_fingerprint
    assert RR.PERMISSIONS_CHANGED in brain.diff_signature(before, after).reasons
    assert before_h != after_h


def test_invalidation_project_changed(session: Session) -> None:
    admin = _seed_layer(session)
    work_a = _work(session)
    work_b = _work(session)
    # Give work_b real compiled state so switching to it visibly changes the
    # project segment (two stateless projects would share an empty project
    # segment — PROJECT_CHANGED would still fire, but the prefix wouldn't move).
    brain.emit(session, event_type=ET.WORK_CREATED, aggregate_type="work",
               aggregate_id=work_b.id, work_id=work_b.id)
    session.commit()
    brain.compile_project(session, work_id=work_b.id, full=True)
    session.commit()
    conv = brain.create_conversation(
        session, owner_user_id=admin.id, work_id=work_a.id, active_profile="studio-director"
    )
    session.commit()
    before, before_h = _sig(session, conv, admin)
    conv.work_id = work_b.id
    session.add(conv)
    session.commit()
    after, after_h = _sig(session, conv, admin)
    result = brain.diff_signature(before, after)
    assert RR.PROJECT_CHANGED in result.reasons
    assert result.primary == RR.PROJECT_CHANGED  # project binding takes priority
    assert before_h != after_h


def test_invalidation_studio_state_changed(session: Session) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)  # admin sees studio state
    before, before_h = _sig(session, conv, admin)
    # mutate the studio: a new work + event, then recompile studio N→N+1
    work = _work(session)
    brain.emit(session, event_type=ET.WORK_CREATED, aggregate_type="work",
               aggregate_id=work.id, work_id=work.id)
    session.commit()
    brain.compile_studio(session, full=False)
    session.commit()
    after, after_h = _sig(session, conv, admin)
    assert after.studio_state_version != before.studio_state_version
    assert RR.STUDIO_STATE_CHANGED in brain.diff_signature(before, after).reasons
    assert before_h != after_h


def test_invalidation_project_state_changed(session: Session) -> None:
    admin = _seed_layer(session)
    work = _work(session)
    brain.emit(session, event_type=ET.WORK_CREATED, aggregate_type="work",
               aggregate_id=work.id, work_id=work.id)
    session.commit()
    brain.compile_project(session, work_id=work.id, full=True)
    session.commit()
    conv = brain.create_conversation(
        session, owner_user_id=admin.id, work_id=work.id, active_profile="studio-director"
    )
    session.commit()
    # baseline persisted assemble → records a COLD checkpoint for the v1 prefix
    ctx1 = brain.assemble(session, conv, user=admin, include_evidence=True, persist=True)
    session.commit()
    before, before_h = _sig(session, conv, admin)

    # advance the project state N→N+1
    brain.emit(session, event_type=ET.WORK_UPDATED, aggregate_type="work",
               aggregate_id=work.id, work_id=work.id, changes={"genre": "Essays"})
    session.commit()
    brain.compile_project(session, work_id=work.id, full=False)
    session.commit()
    after, after_h = _sig(session, conv, admin)
    assert after.project_state_version != before.project_state_version
    assert after.project_state_checksum != before.project_state_checksum
    assert RR.PROJECT_STATE_CHANGED in brain.diff_signature(before, after).reasons
    assert before_h != after_h

    # "create a new checkpoint": a persisted assemble at v2 must add a COLD row
    brain.assemble(session, conv, user=admin, include_evidence=True, persist=True)
    session.commit()
    ckpts = session.exec(
        select(BrainCheckpoint).where(BrainCheckpoint.conversation_id == conv.id)
    ).all()
    hashes = {c.prefix_hash for c in ckpts}
    assert before_h in hashes and after_h in hashes  # both prefixes have checkpoints


def test_studio_recompile_invisible_to_non_admin_session(session: Session) -> None:
    """A non-admin project-scoped session never has studio state in its prefix, so
    a studio recompile must NOT register as a change for it (no false
    STUDIO_STATE_CHANGED, prefix stays warm-eligible)."""
    admin = _seed_layer(session)
    editor = _user(session, "ed2@s.test", UserRole.EDITOR)
    work = _work(session)
    _member(session, editor, work, ProjectRole.EDITOR)
    conv = brain.create_conversation(
        session, owner_user_id=editor.id, work_id=work.id, active_profile="studio-director"
    )
    session.commit()
    before, before_h = _sig(session, conv, editor)
    assert before.studio_state_checksum is None  # studio omitted from this prefix
    # advance the studio state
    other = _work(session)
    brain.emit(session, event_type=ET.WORK_CREATED, aggregate_type="work",
               aggregate_id=other.id, work_id=other.id)
    session.commit()
    brain.compile_studio(session, full=False)
    session.commit()
    after, after_h = _sig(session, conv, editor)
    result = brain.diff_signature(before, after)
    assert RR.STUDIO_STATE_CHANGED not in result.reasons
    assert before_h == after_h  # the prefix the non-admin sees is unchanged
    assert brain.is_warm_eligible(before, after) is True


def test_invalidation_model_changed(session: Session) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    before, before_h = _sig(session, conv, admin, model="model-a")
    after, after_h = _sig(session, conv, admin, model="model-b")
    assert RR.MODEL_OR_TEMPLATE_CHANGED in brain.diff_signature(before, after).reasons
    assert before_h != after_h


def test_invalidation_agrees_with_prefix_hash(session: Session) -> None:
    """For non-state rules the component diff must agree with the authoritative
    byte hash: invalidated iff the prefix_hash moved."""
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    a, a_h = _sig(session, conv, admin)
    # no change
    b, b_h = _sig(session, conv, admin)
    assert brain.diff_signature(a, b).invalidated == (a_h != b_h) == False  # noqa: E712
    # constitution bump
    brain.instruction.add_version(
        session, "constitution", "studio-constitution",
        fields={"body": "Changed.", "notes": "v2"}, created_by_id=admin.id,
    )
    session.commit()
    c, c_h = _sig(session, conv, admin)
    assert brain.diff_signature(a, c).invalidated == (a_h != c_h) == True  # noqa: E712


# === metrics ===============================================================
def test_turn_metrics_partition(session: Session) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    ctx = brain.assemble(session, conv, user=admin, include_evidence=True, persist=False)
    inv = brain.diff_signature(None, _sig(session, conv, admin)[0])
    m = brain.compute_turn_metrics(
        ctx, prefix_cache_eligible=False, invalidation=inv, usage=None,
        response_latency_ms=12.0, ttft_ms=None, warmth="hot",
    )
    included = [s for s in ctx.segments if s.included]
    assert m.stable_prefix_tokens + m.suffix_tokens == sum(s.tokens for s in included)
    delta_seg = next((s for s in included if s.name == "State delta"), None)
    assert m.state_delta_tokens == (delta_seg.tokens if delta_seg else 0)
    assert m.prompt_tokens == sum(s.tokens for s in included)  # no provider usage → estimate
    assert m.prefix_cache_eligible is False
    d = m.as_dict()
    assert set(d) >= {
        "prompt_tokens", "stable_prefix_tokens", "suffix_tokens", "state_delta_tokens",
        "prefix_cache_eligible", "time_to_first_token_ms", "response_latency_ms",
        "invalidation_reasons",
    }


# === begin_turn over a session row =========================================
def test_begin_turn_advances_session_and_cursor(session: Session) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    # turn 1 (cold start)
    prior = session_svc.get_or_create_session(session, conv)
    prev_sig = brain.PrefixSignature.from_session(prior)
    ctx1 = brain.assemble(session, conv, user=admin, persist=True)
    t1 = session_svc.begin_turn(session, conv, ctx1, prev_prefix_hash=None, prev_signature=prev_sig)
    session.commit()
    assert t1.prefix_cache_eligible is False  # nothing to compare against yet
    row = session_svc.get_session_row(session, conv.id)
    assert row.turn_count == 1 and row.last_prefix_hash == ctx1.prefix_hash
    assert row.warmth == BrainSessionWarmth.HOT

    # turn 2 (no change) → eligible
    prior2 = session_svc.get_or_create_session(session, conv)
    prev_sig2 = brain.PrefixSignature.from_session(prior2)
    ctx2 = brain.assemble(session, conv, user=admin, persist=True)
    t2 = session_svc.begin_turn(session, conv, ctx2, prev_prefix_hash=row.last_prefix_hash,
                                prev_signature=prev_sig2)
    session.commit()
    assert t2.prefix_cache_eligible is True
    assert session_svc.get_session_row(session, conv.id).turn_count == 2


# === hot / warm / cold =====================================================
def test_classify_warmth_tiers(session: Session) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    ctx = brain.assemble(session, conv, user=admin, persist=True)
    sess = session_svc.begin_turn(
        session, conv, ctx, prev_prefix_hash=None,
        prev_signature=None,
    )
    session.commit()
    row = session_svc.get_session_row(session, conv.id)
    now = utcnow().replace(tzinfo=None)

    # fresh activity → HOT
    row.last_activity_at = now
    assert session_svc.classify_warmth(session, row, now=now) == BrainSessionWarmth.HOT
    # idle within warm window with a saved checkpoint → WARM
    row.last_activity_at = now - timedelta(hours=2)
    assert session_svc.classify_warmth(session, row, now=now) == BrainSessionWarmth.WARM
    # very old → COLD
    row.last_activity_at = now - timedelta(days=30)
    assert session_svc.classify_warmth(session, row, now=now) == BrainSessionWarmth.COLD
    # archived conversation → COLD regardless of recency
    row.last_activity_at = now
    conv.status = BrainConversationStatus.ARCHIVED
    session.add(conv)
    session.commit()
    assert session_svc.classify_warmth(session, row, now=now) == BrainSessionWarmth.COLD


def test_sweep_demotes_and_archives(session: Session) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    ctx = brain.assemble(session, conv, user=admin, persist=True)
    session_svc.begin_turn(session, conv, ctx, prev_prefix_hash=None, prev_signature=None)
    session.commit()
    row = session_svc.get_session_row(session, conv.id)
    # age it past the archive horizon
    row.last_activity_at = utcnow().replace(tzinfo=None) - timedelta(days=60)
    session.add(row)
    session.commit()
    msgs_before = len(brain.list_messages(session, conv.id, limit=1000))
    result = session_svc.sweep_lifecycle(session, archive=True)
    assert result["scanned"] >= 1 and result["cold"] >= 1 and result["archived"] >= 1
    # messages are NEVER deleted by the sweep
    assert len(brain.list_messages(session, conv.id, limit=1000)) == msgs_before
    refreshed = brain.get_conversation(session, conv.id)
    assert refreshed.status == BrainConversationStatus.ARCHIVED


# === prewarming ============================================================
def test_prewarm_dry_run_noop(session: Session) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    ctx = brain.assemble(session, conv, user=admin, persist=True)
    session_svc.begin_turn(session, conv, ctx, prev_prefix_hash=None, prev_signature=None)
    session.commit()
    result = session_svc.prewarm_active(session)  # default provider = dry_run
    assert result["prewarmed"] == 0 and result["reason"] == "provider=dry_run"


def test_prewarm_excludes_archived_projects(session: Session, monkeypatch) -> None:
    admin = _seed_layer(session)
    archived = _work(session, status=WorkStatus.ARCHIVED)
    conv = brain.create_conversation(
        session, owner_user_id=admin.id, work_id=archived.id, active_profile="studio-director"
    )
    session.commit()
    ctx = brain.assemble(session, conv, user=admin, persist=True)
    session_svc.begin_turn(session, conv, ctx, prev_prefix_hash=None, prev_signature=None)
    session.commit()

    calls = {"n": 0}

    class _FakeProvider:
        async def acomplete(self, req):
            calls["n"] += 1
            class _R:  # minimal CompletionResult-ish
                content = ""
                usage = None
            return _R()

    # pretend a real provider is configured so prewarm would otherwise fire
    monkeypatch.setattr("app.config.settings.ai_provider", "vllm")
    result = session_svc.prewarm_active(session, provider=_FakeProvider())
    assert calls["n"] == 0  # archived project never selected
    assert result["prewarmed"] == 0


def test_prewarm_rate_limited(session: Session, monkeypatch) -> None:
    admin = _seed_layer(session)
    # several active, project-less HOT sessions
    convs = []
    for i in range(5):
        c = brain.create_conversation(
            session, owner_user_id=admin.id, active_profile="studio-director", title=f"c{i}"
        )
        session.commit()
        ctx = brain.assemble(session, c, user=admin, persist=True)
        session_svc.begin_turn(session, c, ctx, prev_prefix_hash=None, prev_signature=None)
        session.commit()
        convs.append(c)

    class _FakeProvider:
        async def acomplete(self, req):
            class _R:
                content = ""
                usage = None
            return _R()

    monkeypatch.setattr("app.config.settings.ai_provider", "vllm")
    # a 2-token budget bucket: only 2 primes before the pass stops
    from app.utils.throttle import RateLimiter
    monkeypatch.setattr(session_svc, "_prewarm_rate", RateLimiter(rate_per_min=1, burst=2))
    result = session_svc.prewarm_active(session, provider=_FakeProvider())
    assert result["prewarmed"] <= 2
    assert result["rate_limited"] >= 1


# === compaction ============================================================
def _decision(session: Session, conv, *, subject, approve=False, admin=None) -> "object":
    d = brain.create_decision(
        session, scope=BrainScope.CONVERSATION, subject=subject, decision="do it",
        source_conversation_id=conv.id,
    )
    session.commit()
    if approve:
        brain.decide_decision(session, d, approve=True, approver_id=admin.id if admin else None)
        session.commit()
    return d


def test_compaction_retains_messages_and_keeps_approved_decisions(session: Session) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    brain.append_message(session, conv, role=BrainMessageRole.USER,
                         content="TASK: ship chapter 3")
    brain.append_message(session, conv, role=BrainMessageRole.ASSISTANT, content="ok")
    session.commit()
    approved = _decision(session, conv, subject="Chapter 3 ending", approve=True, admin=admin)
    proposed = _decision(session, conv, subject="Cover concept", approve=False)

    msgs_before = len(brain.list_messages(session, conv.id, limit=1000))
    result = session_svc.compact_conversation(session, conv)
    session.commit()

    # every original message retained
    assert result.retained_message_count == msgs_before
    assert len(brain.list_messages(session, conv.id, limit=1000)) == msgs_before
    # the approved decision is force-retained
    assert approved.id in result.approved_decisions
    assert approved.id in result.extracted_decisions
    # a durable conversation-scoped digest memory item was written, naming the decision
    items = brain.list_memory(session, conversation_id=conv.id)
    assert result.memory_item_id in {i.id for i in items}
    digest = next(i for i in items if i.id == result.memory_item_id)
    assert "Chapter 3 ending" in digest.content  # approved decision survives verbatim
    # the deterministic task extract is present
    assert any("ship chapter 3" in t for t in result.extracted_tasks)
    assert result.used_llm is False


def test_compaction_llm_is_secondary(session: Session, monkeypatch) -> None:
    admin = _seed_layer(session)
    conv = _studio_conv(session, admin)
    _decision(session, conv, subject="Keep number 7 in canon", approve=True, admin=admin)
    monkeypatch.setattr("app.config.settings.brain_session_compaction_use_llm", True)

    # fact-mangling compressor (drops the "7") → guard rejects, deterministic stays
    r1 = session_svc.compact_conversation(session, conv, compressor=lambda t: "a short blurb")
    session.commit()
    assert r1.used_llm is False

    # fact-preserving compressor → accepted as a SECONDARY artifact
    r2 = session_svc.compact_conversation(session, conv, compressor=lambda t: t + " (tl;dr)")
    session.commit()
    assert r2.used_llm is True
    # the structured decision extract is unchanged regardless of the LLM
    assert r1.extracted_decisions == r2.extracted_decisions


# === gateway integration (dry_run, TestClient) =============================
def _gw_seed(session: Session, admin: User) -> None:
    _seed_stable_layer(session, {"helena": admin})
    brain.compile_studio(session, full=True)
    session.commit()


def _token(client) -> str:
    r = client.post("/api/brain-tokens", json={"name": "LibreChat"})
    assert r.status_code == 201, r.text
    return r.json()["secret"]


def _h(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


def _body(text="ping"):
    return {"model": "supervoid-brain", "messages": [{"role": "user", "content": text}]}


def test_metrics_persisted_and_meta_unchanged(client, admin_user, session) -> None:
    _gw_seed(session, admin_user)
    secret = _token(client)
    r = client.post("/brain/v1/chat/completions", json=_body("remember me"), headers=_h(secret))
    assert r.status_code == 200, r.text
    payload = r.json()
    sv = payload["supervoid"]
    # pre-existing meta keys are untouched (regression guard)
    assert {"state_version", "versions", "citations", "policy", "request_id"} <= set(sv)
    # the new session block is present and well-formed
    assert "session" in sv
    assert set(sv["session"]) == {"warmth", "prefix_cache_eligible", "invalidation_reasons"}
    # the assistant message carries all 8 metric fields
    assistant = [
        m for m in session.exec(select(BrainMessage)).all()
        if m.role == BrainMessageRole.ASSISTANT
    ][-1]
    metrics = assistant.structured_content["session_metrics"]
    for k in ("prompt_tokens", "stable_prefix_tokens", "suffix_tokens", "state_delta_tokens",
              "prefix_cache_eligible", "time_to_first_token_ms", "response_latency_ms",
              "invalidation_reasons"):
        assert k in metrics
    # the OpenAI envelope still validates without the supervoid extension
    from openai.types.chat import ChatCompletion
    ChatCompletion.model_validate({k: v for k, v in payload.items() if k != "supervoid"})


def test_eligibility_not_tautological(client, admin_user, session) -> None:
    _gw_seed(session, admin_user)
    secret = _token(client)

    def _post(text):
        r = client.post("/brain/v1/chat/completions", json=_body(text), headers=_h(secret))
        assert r.status_code == 200, r.text
        return r.json()["supervoid"]["session"]

    s1 = _post("turn one")
    assert s1["prefix_cache_eligible"] is False  # cold start
    s2 = _post("turn two")
    assert s2["prefix_cache_eligible"] is True   # unchanged prefix → eligible
    # invalidate via a constitution bump, then a third turn is cold again
    brain.instruction.add_version(
        session, "constitution", "studio-constitution",
        fields={"body": "Brand new rules.", "notes": "v2"}, created_by_id=admin_user.id,
    )
    session.commit()
    s3 = _post("turn three")
    assert s3["prefix_cache_eligible"] is False
    assert "constitution_version_changed" in s3["invalidation_reasons"]


def test_session_layer_failure_does_not_500(client, admin_user, session, monkeypatch) -> None:
    _gw_seed(session, admin_user)
    secret = _token(client)

    def _boom(*a, **k):
        raise RuntimeError("session layer exploded")

    monkeypatch.setattr(session_svc, "begin_turn", _boom)
    r = client.post("/brain/v1/chat/completions", json=_body("still works"), headers=_h(secret))
    assert r.status_code == 200  # the gateway try/except shields the completion
    assert "session" not in r.json()["supervoid"]  # no decision → no session meta


# === endpoint auth + serialization ========================================
def test_session_endpoints_owner_and_admin_gating(client, editor_client, admin_user, session) -> None:
    """Owner-or-admin on the session read; ADMIN_ONLY on ops + the invalidation
    diagnostic. A non-owner non-admin cannot read another user's session."""
    _gw_seed(session, admin_user)
    conv = brain.create_conversation(
        session, owner_user_id=admin_user.id, active_profile="studio-director"
    )
    session.commit()

    # owner (admin) reads its own session; checksums never leak in the read schema
    r = client.get(f"/api/brain/conversations/{conv.id}/session")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conversation_id"] == conv.id and body["warmth"] == "hot"
    assert "studio_state_checksum" not in body and "project_state_checksum" not in body

    # an unrelated editor cannot read the admin's session
    assert editor_client.get(f"/api/brain/conversations/{conv.id}/session").status_code == 403
    # admin-only ops reject a non-admin
    assert editor_client.get("/api/brain/sessions").status_code == 403
    assert editor_client.post("/api/brain/sessions/sweep").status_code == 403
    assert editor_client.post("/api/brain/sessions/prewarm").status_code == 403
    assert editor_client.get(
        f"/api/brain/conversations/{conv.id}/session/invalidation"
    ).status_code == 403


def test_sessions_warmth_filter_and_compact_endpoint(client, admin_user, session) -> None:
    _gw_seed(session, admin_user)
    conv = brain.create_conversation(
        session, owner_user_id=admin_user.id, active_profile="studio-director"
    )
    brain.append_message(session, conv, role=BrainMessageRole.USER, content="TASK: do x")
    session_svc.get_or_create_session(session, conv)  # warmth HOT
    session.commit()

    rows = client.get("/api/brain/sessions", params={"warmth": "hot"}).json()
    assert any(r["conversation_id"] == conv.id for r in rows)
    cold = client.get("/api/brain/sessions", params={"warmth": "cold"}).json()
    assert not any(r["conversation_id"] == conv.id for r in cold)

    # CompactionResult dataclass serialises through CompactionResultRead
    r = client.post(f"/api/brain/conversations/{conv.id}/session/compact")
    assert r.status_code == 200, r.text
    assert set(r.json()) >= {
        "conversation_id", "extracted_decisions", "approved_decisions",
        "extracted_tasks", "memory_item_id", "retained_message_count", "used_llm",
    }
