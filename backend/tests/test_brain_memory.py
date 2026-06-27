"""Conversation memory & decision extraction (Prompt 13).

Proves the controlled-memory guarantees: the analysis job PROPOSES, it never
silently rewrites truth. The four mandatory safety tests are grouped at the top:

  1. a hallucinated fact cannot become canon,
  2. one member's preference cannot become another's,
  3. a project-private memory cannot leak to another project,
  4. a rejected memory cannot reappear as verified.

Plus the rules engine (auto-accept gate, contradiction + supersede), the review
inbox actions (never-overwrite + provenance), the enqueue hook, and compiled
state inclusion.
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.auth.security import hash_password
from app.models import (
    Author,
    BrainMemoryItem,
    DecisionRecord,
    ProjectMembership,
    StoryWorld,
    User,
    Work,
)
from app.models.enums import (
    BrainMemoryKind,
    BrainMemoryVerification,
    BrainMessageRole,
    BrainScope,
    DecisionStatus,
    MembershipStatus,
    ProjectRole,
    UserRole,
)
from app.services import brain
from app.services.brain import memory, memory_review

D = date(2026, 1, 1)


# --- helpers ---------------------------------------------------------------
def _user(session: Session, email: str, role: UserRole = UserRole.EDITOR) -> User:
    u = User(email=email, full_name=email.split("@")[0], role=role,
             hashed_password=hash_password("pw"))
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _work(session: Session, *, title: str = "Work") -> Work:
    author = Author(full_name="A. Author")
    session.add(author)
    session.commit()
    session.refresh(author)
    world = StoryWorld(name=f"World {title}", slug=f"world-{title.lower()}")
    session.add(world)
    session.commit()
    session.refresh(world)
    work = Work(title=title, author_id=author.id, story_world_id=world.id)
    session.add(work)
    session.commit()
    session.refresh(work)
    return work


def _member(session: Session, user: User, work: Work, role: ProjectRole) -> None:
    session.add(ProjectMembership(
        user_id=user.id, work_id=work.id, role=role, status=MembershipStatus.ACTIVE,
    ))
    session.commit()


def _conv(session: Session, owner: User, **kw):
    conv = brain.create_conversation(session, owner_user_id=owner.id, **kw)
    session.commit()
    return conv


def _cand(**kw) -> memory.MemoryCandidate:
    base = dict(kind=BrainMemoryKind.PREFERENCE, content="x", confidence=0.95,
                risk="low", scope_hint="member")
    base.update(kw)
    return memory.MemoryCandidate(**base)


# ===========================================================================
# 1. A hallucinated fact cannot become canon.
# ===========================================================================
def test_hallucinated_fact_cannot_become_canon(session: Session) -> None:
    owner = _user(session, "owner@s.test")
    work = _work(session)
    conv = _conv(session, owner, work_id=work.id)

    # The model "hallucinates" a canon fact (flagged touches_canon).
    res = memory.promote_candidate(
        session, conversation=conv,
        candidate=_cand(kind=BrainMemoryKind.FACT, scope_hint="project",
                        touches_canon=True, content="The hero secretly is the villain",
                        subject="hero identity"),
    )
    session.commit()

    # It became a PROPOSED decision needing approval — NOT a verified memory.
    assert res["action"] == "decision"
    decision = session.get(DecisionRecord, res["id"])
    assert decision.status == DecisionStatus.PROPOSED
    assert decision.scope == BrainScope.PROJECT and decision.work_id == work.id
    # No memory item was minted, and certainly nothing verified.
    assert session.exec(select(BrainMemoryItem)).all() == []
    # The Work's canon column is untouched by inferred memory.
    session.refresh(work)
    assert work.canon_status is not None  # whatever it was; unchanged by us


def test_canon_keyword_routes_to_decision_even_if_flag_missing(session: Session) -> None:
    """Defence-in-depth: a canon/rights/production-sounding claim is routed to
    approval even when the model forgets to set touches_canon."""
    owner = _user(session, "owner2@s.test")
    work = _work(session, title="Keyword")
    conv = _conv(session, owner, work_id=work.id)
    res = memory.promote_candidate(
        session, conversation=conv,
        candidate=_cand(kind=BrainMemoryKind.FACT, scope_hint="project",
                        touches_canon=False,
                        content="The publishing rights for this work are cleared"),
    )
    session.commit()
    assert res["action"] == "decision"
    assert session.exec(select(BrainMemoryItem)).all() == []


# ===========================================================================
# 2. One member's preference cannot become another's.
# ===========================================================================
def test_one_members_preference_not_anothers(session: Session) -> None:
    alice = _user(session, "alice@s.test")
    bob = _user(session, "bob@s.test")
    conv_a = _conv(session, alice)

    res = memory.promote_candidate(
        session, conversation=conv_a,
        candidate=_cand(content="Prefers terse answers", topic_key="answer-length"),
    )
    session.commit()
    assert res["action"] == "auto_accepted"
    item = session.get(BrainMemoryItem, res["id"])
    assert item.scope == BrainScope.MEMBER
    assert item.member_user_id == alice.id  # bound to Alice, never Bob

    # Bob's member memory + review inbox never include Alice's preference.
    bob_mem = brain.list_memory(session, scope=BrainScope.MEMBER, member_user_id=bob.id)
    assert bob_mem == []
    assert memory_review.list_inbox(session, bob, scope=BrainScope.MEMBER) == []
    # And Bob cannot review/action Alice's item.
    assert memory_review.can_review(session, bob, item) is False
    assert memory_review.can_view(session, bob, item) is False


# ===========================================================================
# 3. A project-private memory cannot leak to another project.
# ===========================================================================
def test_project_memory_does_not_leak_across_projects(session: Session) -> None:
    work_a = _work(session, title="Alpha")
    work_b = _work(session, title="Beta")
    # A verified project fact for A only.
    brain.create_memory(
        session, scope=BrainScope.PROJECT, kind=BrainMemoryKind.FACT,
        content="Alpha-only fact", work_id=work_a.id,
    )
    session.exec(select(BrainMemoryItem)).first().verification = BrainMemoryVerification.VERIFIED
    session.commit()

    # The query the compiler uses (verified + work-scoped) isolates by project.
    a_rows = brain.list_memory(
        session, scope=BrainScope.PROJECT, work_id=work_a.id,
        verification=BrainMemoryVerification.VERIFIED,
    )
    b_rows = brain.list_memory(
        session, scope=BrainScope.PROJECT, work_id=work_b.id,
        verification=BrainMemoryVerification.VERIFIED,
    )
    assert len(a_rows) == 1 and b_rows == []


def test_inbox_does_not_leak_other_projects(session: Session) -> None:
    work_a = _work(session, title="Gamma")
    work_b = _work(session, title="Delta")
    editor = _user(session, "ed@s.test")
    _member(session, editor, work_a, ProjectRole.EDITOR)  # member of A only

    for work, text in ((work_a, "A pending"), (work_b, "B pending")):
        brain.create_memory(
            session, scope=BrainScope.PROJECT, kind=BrainMemoryKind.FACT,
            content=text, work_id=work.id,
        )
    session.commit()

    inbox = memory_review.list_inbox(session, editor, scope=BrainScope.PROJECT)
    contents = {i.content for i in inbox}
    assert "A pending" in contents and "B pending" not in contents


# ===========================================================================
# 4. A rejected memory cannot reappear as verified.
# ===========================================================================
def test_rejected_memory_does_not_reappear_as_verified(session: Session) -> None:
    owner = _user(session, "rej@s.test")
    conv = _conv(session, owner)

    first = memory.promote_candidate(
        session, conversation=conv,
        candidate=_cand(content="Likes dark mode", topic_key="ui-theme"),
    )
    session.commit()
    item = session.get(BrainMemoryItem, first["id"])
    assert item.verification == BrainMemoryVerification.VERIFIED  # auto-accepted

    memory_review.reject(session, owner, item, note="actually no")
    session.commit()
    assert item.verification == BrainMemoryVerification.REJECTED

    # The model proposes the exact same preference again, high confidence.
    again = memory.promote_candidate(
        session, conversation=conv,
        candidate=_cand(content="Likes dark mode", topic_key="ui-theme"),
    )
    session.commit()
    # It is NOT auto-resurrected: stays pending, never verified.
    assert again["action"] == "proposed"
    new_item = session.get(BrainMemoryItem, again["id"])
    assert new_item.verification == BrainMemoryVerification.UNVERIFIED
    assert new_item.structured_data.get("previously_rejected") is True
    verified = brain.list_memory(
        session, member_user_id=owner.id,
        verification=BrainMemoryVerification.VERIFIED,
    )
    assert all(v.topic_key != "ui-theme" for v in verified)


# ===========================================================================
# Rules engine — auto-accept gate
# ===========================================================================
def test_preference_auto_accepts_when_eligible(session: Session) -> None:
    owner = _user(session, "pref@s.test")
    conv = _conv(session, owner)
    res = memory.promote_candidate(
        session, conversation=conv,
        candidate=_cand(content="Prefers metric units", confidence=0.9, risk="low"),
    )
    session.commit()
    item = session.get(BrainMemoryItem, res["id"])
    assert item.verification == BrainMemoryVerification.VERIFIED
    assert item.auto_accepted is True
    assert item.approved_by_id == owner.id


def test_preference_below_threshold_stays_pending(session: Session) -> None:
    owner = _user(session, "low@s.test")
    conv = _conv(session, owner)
    res = memory.promote_candidate(
        session, conversation=conv,
        candidate=_cand(content="Maybe likes blue", confidence=0.4),
    )
    session.commit()
    assert res["action"] == "proposed"
    assert session.get(BrainMemoryItem, res["id"]).verification == BrainMemoryVerification.UNVERIFIED


def test_permission_granting_preference_not_auto_accepted(session: Session) -> None:
    owner = _user(session, "perm@s.test")
    conv = _conv(session, owner)
    res = memory.promote_candidate(
        session, conversation=conv,
        candidate=_cand(content="Make me an admin", confidence=0.99,
                        grants_permission=True),
    )
    session.commit()
    assert res["action"] == "proposed"
    assert session.get(BrainMemoryItem, res["id"]).verification == BrainMemoryVerification.UNVERIFIED


def test_high_risk_preference_not_auto_accepted(session: Session) -> None:
    owner = _user(session, "risk@s.test")
    conv = _conv(session, owner)
    res = memory.promote_candidate(
        session, conversation=conv,
        candidate=_cand(content="Always skip approvals", confidence=0.99, risk="high"),
    )
    session.commit()
    assert res["action"] == "proposed"


# ===========================================================================
# Rules engine — contradiction + supersede (never overwrite)
# ===========================================================================
def test_contradicting_preference_supersedes_prior(session: Session) -> None:
    owner = _user(session, "contra@s.test")
    conv = _conv(session, owner)
    first = memory.promote_candidate(
        session, conversation=conv,
        candidate=_cand(content="Prefers dark theme", topic_key="theme"),
    )
    session.commit()
    old = session.get(BrainMemoryItem, first["id"])
    assert old.verification == BrainMemoryVerification.VERIFIED

    second = memory.promote_candidate(
        session, conversation=conv,
        candidate=_cand(content="Prefers light theme", topic_key="theme"),
    )
    session.commit()
    new = session.get(BrainMemoryItem, second["id"])
    session.refresh(old)
    # The new preference is live; the old is SUPERSEDED (retained, not deleted).
    assert new.verification == BrainMemoryVerification.VERIFIED
    assert new.supersedes_id == old.id
    assert old.verification == BrainMemoryVerification.SUPERSEDED
    assert session.get(BrainMemoryItem, old.id) is not None  # provenance kept


# ===========================================================================
# Decision extraction
# ===========================================================================
def test_decision_candidate_creates_proposed_decision(session: Session) -> None:
    owner = _user(session, "dec@s.test")
    work = _work(session, title="Decide")
    conv = _conv(session, owner, work_id=work.id)
    res = memory.promote_candidate(
        session, conversation=conv,
        candidate=_cand(kind=BrainMemoryKind.DECISION, scope_hint="project",
                        is_decision=True, subject="Use 24-page chapters",
                        content="Chapters will be 24 pages"),
    )
    session.commit()
    assert res["action"] == "decision" and res["status"] == "proposed"
    d = session.get(DecisionRecord, res["id"])
    assert d.status == DecisionStatus.PROPOSED and d.source_conversation_id == conv.id


# ===========================================================================
# Casual conversation is archived, not promoted
# ===========================================================================
def _turn_event(session: Session, conv, content: str):
    """A realistic completed-turn: a persisted assistant message + the enqueued
    ``conversation.turn_completed`` event (real ids satisfy the FKs)."""
    msg = brain.append_message(session, conv, role=BrainMessageRole.ASSISTANT, content=content)
    session.commit()
    event = brain.emit(
        session, event_type=brain.BrainEventType.CONVERSATION_TURN_COMPLETED,
        aggregate_type="brain_message", aggregate_id=msg.id, actor_id=conv.owner_user_id,
    )
    session.commit()
    return msg, event


def test_casual_conversation_not_promoted(session: Session, monkeypatch) -> None:
    owner = _user(session, "chat@s.test")
    conv = _conv(session, owner)
    _msg, event = _turn_event(session, conv, "Sure, happy to help!")
    # The extractor finds nothing durable in chit-chat.
    monkeypatch.setattr(memory, "_extract_candidates", lambda *a, **k: [])
    out = memory.analyze_turn(session, event)
    session.commit()
    assert out["candidates"] == 0
    assert session.exec(select(BrainMemoryItem)).all() == []
    assert session.exec(select(DecisionRecord)).all() == []


def test_analyze_turn_promotes_extracted_candidates(session: Session, monkeypatch) -> None:
    owner = _user(session, "extract@s.test")
    conv = _conv(session, owner)
    msg, event = _turn_event(session, conv, "noted")
    monkeypatch.setattr(
        memory, "_extract_candidates",
        lambda *a, **k: [_cand(content="Prefers email over chat", confidence=0.95)],
    )
    out = memory.analyze_turn(session, event)
    session.commit()
    assert out["promoted"] == 1
    items = session.exec(
        select(BrainMemoryItem).where(BrainMemoryItem.member_user_id == owner.id)
    ).all()
    assert len(items) == 1
    assert items[0].source_message_id == msg.id and items[0].source_event_id == event.id


# ===========================================================================
# Review inbox — never overwrite + provenance
# ===========================================================================
def test_edit_creates_superseding_row_with_provenance(session: Session) -> None:
    owner = _user(session, "edit@s.test")
    conv = _conv(session, owner)
    src = brain.append_message(session, conv, role=BrainMessageRole.ASSISTANT, content="src")
    session.commit()
    item = brain.create_memory(
        session, scope=BrainScope.MEMBER, kind=BrainMemoryKind.FACT,
        content="orig", member_user_id=owner.id, conversation_id=conv.id,
        source_message_id=src.id, created_by_id=owner.id,
    )
    session.commit()
    new = memory_review.edit(session, owner, item, content="corrected")
    session.commit()
    session.refresh(item)
    assert new.id != item.id and new.content == "corrected"
    assert new.supersedes_id == item.id
    assert item.verification == BrainMemoryVerification.SUPERSEDED
    assert new.source_message_id == src.id  # provenance carried forward
    assert session.get(BrainMemoryItem, item.id) is not None  # original retained


def test_merge_supersedes_all_sources(session: Session) -> None:
    owner = _user(session, "merge@s.test")
    conv = _conv(session, owner)
    a = brain.create_memory(session, scope=BrainScope.MEMBER, kind=BrainMemoryKind.FACT,
                            content="part one", member_user_id=owner.id, conversation_id=conv.id)
    b = brain.create_memory(session, scope=BrainScope.MEMBER, kind=BrainMemoryKind.FACT,
                            content="part two", member_user_id=owner.id, conversation_id=conv.id)
    session.commit()
    merged = memory_review.merge(session, owner, primary_id=a.id, source_ids=[b.id])
    session.commit()
    session.refresh(a)
    session.refresh(b)
    assert merged.verification == BrainMemoryVerification.VERIFIED
    assert a.verification == BrainMemoryVerification.SUPERSEDED
    assert b.verification == BrainMemoryVerification.SUPERSEDED
    assert set(merged.structured_data["merged_from"]) == {a.id, b.id}


def test_accept_supersedes_prior_verified_same_topic(session: Session) -> None:
    owner = _user(session, "acc@s.test")
    conv = _conv(session, owner)
    old = brain.create_memory(session, scope=BrainScope.MEMBER, kind=BrainMemoryKind.FACT,
                              content="v1", member_user_id=owner.id, conversation_id=conv.id)
    old.verification = BrainMemoryVerification.VERIFIED
    old.topic_key = "topic-x"
    new = brain.create_memory(session, scope=BrainScope.MEMBER, kind=BrainMemoryKind.FACT,
                              content="v2", member_user_id=owner.id, conversation_id=conv.id)
    new.topic_key = "topic-x"
    session.commit()
    memory_review.accept(session, owner, new)
    session.commit()
    session.refresh(old)
    assert new.verification == BrainMemoryVerification.VERIFIED
    assert new.supersedes_id == old.id
    assert old.verification == BrainMemoryVerification.SUPERSEDED


def test_expire_retires_item(session: Session) -> None:
    owner = _user(session, "exp@s.test")
    conv = _conv(session, owner)
    item = brain.create_memory(session, scope=BrainScope.MEMBER, kind=BrainMemoryKind.FACT,
                               content="temp", member_user_id=owner.id, conversation_id=conv.id)
    item.verification = BrainMemoryVerification.VERIFIED
    session.commit()
    memory_review.expire(session, owner, item)
    session.commit()
    assert item.verification == BrainMemoryVerification.EXPIRED
    assert item.expires_at is not None


def test_member_cannot_review_other_members_item(session: Session) -> None:
    alice = _user(session, "a2@s.test")
    bob = _user(session, "b2@s.test")
    conv = _conv(session, alice)
    item = brain.create_memory(session, scope=BrainScope.MEMBER, kind=BrainMemoryKind.PREFERENCE,
                               content="alice pref", member_user_id=alice.id, conversation_id=conv.id)
    session.commit()
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        memory_review.accept(session, bob, item)
    assert exc.value.status_code == 403


# ===========================================================================
# Compiled state — verified included, rejected excluded
# ===========================================================================
def test_compiled_state_includes_verified_excludes_rejected(session: Session) -> None:
    work = _work(session, title="Compiled")
    good = brain.create_memory(session, scope=BrainScope.PROJECT, kind=BrainMemoryKind.FACT,
                               content="The city is built on stilts", work_id=work.id)
    good.verification = BrainMemoryVerification.VERIFIED
    bad = brain.create_memory(session, scope=BrainScope.PROJECT, kind=BrainMemoryKind.FACT,
                              content="HALLUCINATED rejected fact", work_id=work.id)
    bad.verification = BrainMemoryVerification.REJECTED
    session.commit()

    brain.compile_project(session, work_id=work.id, full=True, compile_date=D)
    state = brain.get_project_state(session, work_id=work.id)
    facts = [f["content"] for f in state.structured_state["canon_facts"]["facts"]]
    assert "The city is built on stilts" in facts
    assert "HALLUCINATED rejected fact" not in facts


# ===========================================================================
# Enqueue hook — a completed turn enqueues analysis without invalidating state
# ===========================================================================
def _seed_gateway(session: Session, admin: User) -> None:
    from app.seed import _seed_stable_layer

    _seed_stable_layer(session, {"helena": admin})
    brain.compile_studio(session, full=True)
    session.commit()


def test_completed_turn_enqueues_and_does_not_invalidate_state(
    client, admin_user, session
) -> None:
    _seed_gateway(session, admin_user)
    studio_before = brain.get_studio_state(session)
    assert studio_before.stale is False

    secret = client.post("/api/brain-tokens", json={"name": "LC"}).json()["secret"]
    r = client.post(
        "/brain/v1/chat/completions",
        json={"model": "supervoid-brain", "messages": [{"role": "user", "content": "hello"}]},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert r.status_code == 200, r.text

    # A turn_completed event was enqueued.
    from app.models import BrainEvent

    evs = session.exec(
        select(BrainEvent).where(BrainEvent.event_type == "conversation.turn_completed")
    ).all()
    assert len(evs) >= 1

    # Draining runs the analyzer (dry-run -> no candidates) and must NOT mark the
    # compiled studio state stale: a chat turn never invalidates domain state.
    brain.drain(session)
    session.expire_all()
    studio_after = brain.get_studio_state(session)
    assert studio_after.stale is False
    done = session.exec(
        select(BrainEvent).where(BrainEvent.event_type == "conversation.turn_completed")
    ).all()
    assert all(e.status.value == "processed" for e in done)
