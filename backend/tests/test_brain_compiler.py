"""Tests for the deterministic Brain State Compiler.

The headline guarantees from the spec are proven here:
  * incremental compilation yields the SAME checksum as a full rebuild,
  * compilation is deterministic (stable checksum across fresh runs),
  * a no-op compile creates no new revision,
  * only event-affected sections are rebuilt (others carry forward byte-identical),
  * token budgets are enforced and truncation is deterministic,
  * generated prose never overwrites the canonical structured facts,
  * full rebuild recovers the exact state after a disaster (state rows wiped).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register tables)
from app.models import Author, ProductionItem, StoryWorld, Work
from app.models.brain import BrainStateRevision, ProjectBrainState, StudioBrainState
from app.models.enums import BrainStateType, ProductionItemStatus
from app.services import brain
from app.services.brain import compiler, state_builders as sb
from app.services.brain.events import BrainEventType as ET

D = date(2026, 1, 1)


def _seed(session: Session) -> Work:
    author = Author(full_name="A. Author")
    session.add(author)
    session.commit()
    session.refresh(author)
    world = StoryWorld(name="World One", slug="world-one")
    session.add(world)
    session.commit()
    session.refresh(world)
    work = Work(title="Work One", author_id=author.id, story_world_id=world.id)
    session.add(work)
    session.commit()
    session.refresh(work)
    return work


def _emit(session: Session, work: Work, event_type: str, **kw) -> None:
    brain.emit(
        session, event_type=event_type, aggregate_type="work",
        aggregate_id=work.id, work_id=work.id, story_world_id=work.story_world_id, **kw
    )
    session.commit()


def _wipe_state(session: Session) -> None:
    """Drop all compiled state + revisions (keep events) — forces a from-scratch
    full rebuild, the independent oracle for incremental correctness / DR."""
    for row in session.exec(select(ProjectBrainState)).all():
        session.delete(row)
    for row in session.exec(select(StudioBrainState)).all():
        session.delete(row)
    for row in session.exec(select(BrainStateRevision)).all():
        session.delete(row)
    session.commit()


# --- 1. incremental == full (independently verified) ------------------------
def test_incremental_equals_full_checksum(session: Session) -> None:
    work = _seed(session)
    _emit(session, work, ET.WORK_CREATED)
    compiler.compile_project(session, work_id=work.id, full=True, compile_date=D)
    # more events, then an INCREMENTAL compile
    _emit(session, work, ET.WORK_UPDATED, changes={"genre": "Essays"})
    _emit(session, work, ET.TASK_CREATED)
    to_seq = compiler.head_sequence(session)
    incr = compiler.compile_project(
        session, work_id=work.id, full=False, compile_date=D, to_seq=to_seq
    )
    # Independent oracle: wipe state and FULL-rebuild at the same high-water mark.
    _wipe_state(session)
    full = compiler.compile_project(
        session, work_id=work.id, full=True, compile_date=D, to_seq=to_seq
    )
    assert incr["checksum"] == full["checksum"]


# --- 1b. rights events invalidate next_priorities (regression) --------------
def test_incremental_equals_full_with_rights(session: Session) -> None:
    from datetime import date as _date

    from app.models import Rights

    work = _seed(session)
    _emit(session, work, ET.WORK_CREATED)
    compiler.compile_project(session, work_id=work.id, full=True, compile_date=D)

    # introduce an OVERDUE rights profile + a rights event in the window: this
    # changes both rights_constraints AND next_priorities (derived from it).
    session.add(Rights(work_id=work.id, expiration_date=_date(2020, 1, 1)))
    session.commit()
    brain.emit(
        session, event_type=ET.RIGHTS_UPDATED, aggregate_type="rights",
        aggregate_id="rights-1", work_id=work.id, story_world_id=work.story_world_id,
    )
    session.commit()
    to_seq = compiler.head_sequence(session)
    incr = compiler.compile_project(
        session, work_id=work.id, full=False, compile_date=D, to_seq=to_seq
    )
    state = brain.get_project_state(session, work_id=work.id)
    kinds = {p["kind"] for p in state.structured_state["next_priorities"]}
    assert "rights" in kinds  # the overdue warning surfaced as a priority

    _wipe_state(session)
    full = compiler.compile_project(
        session, work_id=work.id, full=True, compile_date=D, to_seq=to_seq
    )
    assert incr["checksum"] == full["checksum"]


# --- 1c. knowledge-entity continuity findings are in scope (regression) -----
def test_knowledge_entity_findings_included(session: Session) -> None:
    from app.models import (
        AgentFinding,
        AgentRun,
        KnowledgeEntity,
        Manuscript,
        ManuscriptEntityLink,
    )
    from app.models.enums import EntityKind, FindingSeverity

    work = _seed(session)
    ms = Manuscript(title="Draft", work_id=work.id, author_id=work.author_id)
    session.add(ms)
    entity = KnowledgeEntity(name="Hero", slug="hero", kind=EntityKind.CHARACTER)
    session.add(entity)
    run = AgentRun(agent_key="continuity", target_type="work", target_id=work.id)
    session.add(run)
    session.commit()
    session.add(ManuscriptEntityLink(manuscript_id=ms.id, entity_id=entity.id))
    session.add(
        AgentFinding(
            run_id=run.id,
            agent_key="continuity",
            message="continuity drift",
            severity=FindingSeverity.HIGH,
            category="continuity",
            target_type="knowledge_entity",
            target_id=entity.id,
            resolved=False,
        )
    )
    session.commit()
    _emit(session, work, ET.WORK_CREATED)
    compiler.compile_project(session, work_id=work.id, full=True, compile_date=D)
    state = brain.get_project_state(session, work_id=work.id)
    messages = [f["message"] for f in state.structured_state["continuity_findings"]]
    assert "continuity drift" in messages


# --- 2. deterministic across fresh databases --------------------------------
def _fresh_engine() -> Engine:
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _seed_fixed(session: Session) -> Work:
    """Seed with pinned ids so two fresh databases hold identical inputs — this
    isolates the determinism of serialisation/ordering from random UUIDs."""
    session.add(Author(id="auth-1", full_name="A. Author"))
    session.add(StoryWorld(id="world-1", name="World One", slug="world-one"))
    session.commit()
    work = Work(id="work-1", title="Work One", author_id="auth-1", story_world_id="world-1")
    session.add(work)
    session.commit()
    session.refresh(work)
    return work


def test_determinism_stable_checksum() -> None:
    # Studio state carries no wall-clock fields, so with pinned entity ids two
    # independent runs must produce a byte-identical checksum.
    checks = []
    for _ in range(2):
        eng = _fresh_engine()
        with Session(eng) as s:
            work = _seed_fixed(s)
            _emit(s, work, ET.WORK_CREATED)
            _emit(s, work, ET.WORK_UPDATED, changes={"genre": "Essays"})
            r = compiler.compile_studio(s, full=True, compile_date=D)
            checks.append(r["checksum"])
    assert checks[0] == checks[1]


# --- 3. idempotent: no new events => no new revision ------------------------
def test_idempotent_no_new_events(session: Session) -> None:
    work = _seed(session)
    _emit(session, work, ET.WORK_CREATED)
    first = compiler.compile_studio(session, full=True, compile_date=D)
    rev_count_1 = len(brain.list_revisions(session, state_type=BrainStateType.STUDIO))

    second = compiler.compile_studio(session, full=False, compile_date=D)
    rev_count_2 = len(brain.list_revisions(session, state_type=BrainStateType.STUDIO))

    assert second["changed"] is False
    assert second["version"] == first["version"]
    assert rev_count_2 == rev_count_1  # no extra snapshot


# --- 4. cursor advances to the high-water mark ------------------------------
def test_cursor_advances(session: Session) -> None:
    work = _seed(session)
    _emit(session, work, ET.WORK_CREATED)
    _emit(session, work, ET.WORK_UPDATED)
    head = compiler.head_sequence(session)
    compiler.compile_studio(session, full=True, compile_date=D)
    state = brain.get_studio_state(session)
    assert state.source_event_cursor == head


# --- 5. only affected sections rebuilt --------------------------------------
def test_per_section_rebuild_only_affected(session: Session) -> None:
    work = _seed(session)
    _emit(session, work, ET.WORK_CREATED)
    compiler.compile_project(session, work_id=work.id, full=True, compile_date=D)
    before = dict(brain.get_project_state(session, work_id=work.id).structured_state)

    # a single asset event: per the map it touches assets/production/progress only
    brain.emit(
        session, event_type=ET.ASSET_VERSION_PROMOTED, aggregate_type="asset",
        aggregate_id="asset-x", work_id=work.id, story_world_id=work.story_world_id,
    )
    session.commit()
    to_seq = compiler.head_sequence(session)
    compiler.compile_project(session, work_id=work.id, full=False, compile_date=D, to_seq=to_seq)
    after = dict(brain.get_project_state(session, work_id=work.id).structured_state)

    allowed = {
        "assets_approved_versions", "production_hierarchy", "progress", "recent_changes",
    }
    for key in before:
        if key in allowed:
            continue
        assert compiler.canonical_json(before[key]) == compiler.canonical_json(after[key]), key


# --- 6. event→section map covers every event type ---------------------------
def test_event_section_map_coverage() -> None:
    for name in dir(ET):
        if name.startswith("_"):
            continue
        value = getattr(ET, name)
        if not isinstance(value, str) or "." not in value:
            continue
        prefix = value.split(".")[0] + "."
        assert prefix in sb.EVENT_SECTION_MAP, f"{value} has no section mapping"


# --- 7. token budget enforced ----------------------------------------------
def test_token_budget(session: Session) -> None:
    work = _seed(session)
    # Inflate the synopsis well past the cap.
    work.synopsis = "x" * 5000
    session.add(work)
    session.commit()
    _emit(session, work, ET.WORK_CREATED)
    compiler.compile_project(session, work_id=work.id, full=True, compile_date=D)
    compiler.compile_studio(session, full=True, compile_date=D)
    proj = brain.get_project_state(session, work_id=work.id)
    studio = brain.get_studio_state(session)
    assert len(proj.compact_summary) <= 1500
    assert len(studio.compact_summary) <= 1200


# --- 8. truncation is a pure deterministic function -------------------------
def test_truncation_deterministic() -> None:
    s = "abcdefghij"
    assert compiler.truncate(s, 100) == s
    assert compiler.truncate(s, 5) == "abcd…"
    assert compiler.truncate(s, 5) == compiler.truncate(s, 5)


# --- 9. generated prose never overwrites the facts --------------------------
def test_prose_never_overwrites_facts(session: Session) -> None:
    work = _seed(session)
    _emit(session, work, ET.WORK_CREATED)

    # baseline (no LLM)
    base = compiler.compile_studio(session, full=True, compile_date=D)
    base_state = brain.get_studio_state(session)
    base_summary = base_state.compact_summary

    # a compressor that mangles the numbers must be rejected by the guard
    def bad(_text: str) -> str:
        return "Everything is fine. 999999 of everything."

    compiler.compile_studio(session, full=True, compile_date=D, compressor=bad)
    state = brain.get_studio_state(session)
    assert state.checksum == base["checksum"]          # facts unchanged
    assert state.compact_summary == base_summary        # fell back to template
    # the rejected prose is not stored on the revision either
    latest = brain.list_revisions(session, state_type=BrainStateType.STUDIO)[0]
    assert latest.llm_summary is None


# --- 10. LLM on/off never changes the checksum ------------------------------
def test_llm_does_not_affect_checksum(session: Session) -> None:
    work = _seed(session)
    _emit(session, work, ET.WORK_CREATED)
    to_seq = compiler.head_sequence(session)

    # a faithful compressor that preserves every number
    def good(text: str) -> str:
        return text + " (compressed)"

    # Fresh state → the "changed" branch runs the compressor.
    with_llm = compiler.compile_studio(
        session, full=True, compile_date=D, to_seq=to_seq, compressor=good
    )
    assert brain.get_studio_state(session).compact_summary.endswith("(compressed)")

    # Independent rebuild WITHOUT the LLM at the same high-water mark.
    _wipe_state(session)
    no_llm = compiler.compile_studio(session, full=True, compile_date=D, to_seq=to_seq)
    assert with_llm["checksum"] == no_llm["checksum"]  # checksum excludes prose
    assert not brain.get_studio_state(session).compact_summary.endswith("(compressed)")


# --- 11. full rebuild = disaster recovery ----------------------------------
def test_full_rebuild_disaster_recovery(session: Session) -> None:
    work = _seed(session)
    _emit(session, work, ET.WORK_CREATED)
    _emit(session, work, ET.TASK_CREATED)
    good = compiler.compile_project(session, work_id=work.id, full=True, compile_date=D)
    good_checksum = good["checksum"]

    # wipe all compiled state + revisions, keep the events
    for row in session.exec(select(ProjectBrainState)).all():
        session.delete(row)
    for row in session.exec(select(StudioBrainState)).all():
        session.delete(row)
    for row in session.exec(select(BrainStateRevision)).all():
        session.delete(row)
    session.commit()
    assert brain.get_project_state(session, work_id=work.id) is None

    recovered = compiler.compile_project(session, work_id=work.id, full=True, compile_date=D)
    assert recovered["checksum"] == good_checksum


# --- 12. project revisions carry full provenance ---------------------------
def test_revision_records_window(session: Session) -> None:
    work = _seed(session)
    _emit(session, work, ET.WORK_CREATED)
    to_seq = compiler.head_sequence(session)
    compiler.compile_project(session, work_id=work.id, full=True, compile_date=D, to_seq=to_seq)
    state = brain.get_project_state(session, work_id=work.id)
    rev = brain.list_revisions(
        session, state_type=BrainStateType.PROJECT, state_id=state.id
    )[0]
    assert rev.source_event_from == 0
    assert rev.source_event_to == to_seq
    assert rev.compiler_version is not None


# --- 13. revision delta ----------------------------------------------------
def test_revision_delta(session: Session) -> None:
    work = _seed(session)
    _emit(session, work, ET.WORK_CREATED)
    compiler.compile_project(session, work_id=work.id, full=True, compile_date=D)
    state = brain.get_project_state(session, work_id=work.id)
    v1 = brain.list_revisions(session, state_type=BrainStateType.PROJECT, state_id=state.id)[0]

    work.title = "Renamed Work"
    session.add(work)
    _emit(session, work, ET.WORK_UPDATED, changes={"title": "Renamed Work"})
    compiler.compile_project(session, work_id=work.id, full=False, compile_date=D)
    revs = brain.list_revisions(session, state_type=BrainStateType.PROJECT, state_id=state.id)
    v2 = revs[0]

    delta = compiler.revision_delta(session, revision_a_id=v1.id, revision_b_id=v2.id)
    assert "identity" in delta["changed"]
    assert delta["removed"] == [] and delta["added"] == []


# --- 14. project scope isolation -------------------------------------------
def test_project_scope_filter(session: Session) -> None:
    a = _seed(session)
    b_author = session.get(Author, a.author_id)
    b = Work(title="Work Two", author_id=b_author.id)
    session.add(b)
    session.commit()
    session.refresh(b)

    _emit(session, a, ET.WORK_UPDATED, changes={"genre": "x"})
    compiler.compile_project(session, work_id=a.id, full=True, compile_date=D)
    compiler.compile_project(session, work_id=b.id, full=True, compile_date=D)

    before_b = dict(brain.get_project_state(session, work_id=b.id).structured_state)
    # an event on A must not change B's recent_changes
    _emit(session, a, ET.WORK_UPDATED, changes={"genre": "y"})
    compiler.compile_project(session, work_id=b.id, full=False, compile_date=D)
    after_b = dict(brain.get_project_state(session, work_id=b.id).structured_state)
    assert compiler.canonical_json(before_b["recent_changes"]) == compiler.canonical_json(
        after_b["recent_changes"]
    )


# --- 15. stale-state listing matches the cursor comparison -----------------
def test_stale_states_listing(session: Session) -> None:
    work = _seed(session)
    _emit(session, work, ET.WORK_CREATED)
    compiler.compile_studio(session, full=True, compile_date=D)
    compiler.compile_project(session, work_id=work.id, full=True, compile_date=D)
    # both are current now
    stale = compiler.stale_states(session)
    assert stale["count"] == 0

    # a new event leaves the studio + project behind the head
    _emit(session, work, ET.WORK_UPDATED)
    stale = compiler.stale_states(session)
    scopes = {s["scope"] for s in stale["states"]}
    assert "studio" in scopes and "project" in scopes
