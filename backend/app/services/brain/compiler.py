"""The deterministic Brain State Compiler.

Maintains a ready-to-use, compact mental state *before* a user asks a question.
It assembles the studio and per-project structured state from the deterministic
builders in :mod:`app.services.brain.state_builders`, derives a compact textual
summary (templates first, optional guarded LLM prose compression), and persists
the result as the current state plus an immutable revision — advancing the
per-state event cursor.

Guarantees
----------
* **Deterministic.** ``structured_state`` is built purely from SQL/services; the
  checksum is ``sha256`` over a canonical JSON encoding (sorted keys, normalised
  enums/dates). Re-running over the same data at the same ``compile_date``
  yields a byte-identical state.
* **Incremental == full.** An incremental compile (consume new events → rebuild
  only affected sections → carry the rest forward) produces the *same* checksum
  as a full rebuild at the same high-water mark. Tests assert this.
* **Facts are authoritative.** The optional LLM only ever rewrites the *prose
  summary*, never the structured facts, and only when a deterministic guard
  proves the numbers were preserved.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, datetime
from enum import Enum
from typing import Callable, Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.config import settings
from app.models import StoryWorld, Work
from app.models.brain import (
    BrainEvent,
    BrainStateRevision,
    ProjectBrainState,
)
from app.models.enums import BrainStateStatus, BrainStateType
from app.services import brain
from app.services.brain import state_builders as sb

# A compressor takes the deterministic summary text and returns compressed prose
# (or None to decline). Injected in tests; real LLM wiring stays opt-in.
Compressor = Callable[[str], Optional[str]]

# --- token budgets (char caps; ~4 chars/token, no tokenizer dependency) -----
_SUMMARY_TOTAL = {"studio": 1200, "project": 1500}
_SUMMARY_LINE = {"studio": 140, "project": 160}
_SYNOPSIS_LINE = 400
_LLM_CAP = {"studio": 600, "project": 700}


# === canonical serialisation + checksum ====================================
def _canon_default(o):
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def canonical_json(obj) -> str:
    """Stable JSON: sorted keys, compact separators, normalised enums/dates."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_canon_default,
    )


def checksum(structured_state: dict) -> str:
    """SHA-256 over the canonical structured state only (never the summary,
    version, or any wall-clock timestamp)."""
    return hashlib.sha256(canonical_json(structured_state).encode("utf-8")).hexdigest()


# === token-budget helpers ===================================================
def truncate(text: str, cap: int) -> str:
    """Deterministic character-count truncation with a trailing ellipsis."""
    if text is None:
        return ""
    if len(text) <= cap:
        return text
    return text[: cap - 1].rstrip() + "…"


def _line(label: str, value: str, *, cap: int) -> str:
    return truncate(f"{label}: {value}", cap)


# === summary templates (deterministic) =====================================
def render_studio_summary(state: dict) -> str:
    cap = _SUMMARY_LINE["studio"]
    ident = state.get("identity", {})
    works = state.get("active_works", {})
    worlds = state.get("active_story_worlds", {})
    releases = state.get("releases", {})
    blockers = state.get("major_blockers", [])
    approvals = state.get("pending_approvals", {}).get("counts", {})
    rights = state.get("rights_warnings", [])
    assets = state.get("asset_health", {})
    collab = state.get("collaborator_load", {})
    integ = state.get("integration_health", [])
    priorities = state.get("strategic_priorities", [])

    overdue = sum(1 for r in rights if r.get("status") == "overdue")
    soon = sum(1 for r in rights if r.get("status") == "due_soon")
    unhealthy = sum(1 for i in integ if i.get("status") not in ("active", None))
    lines = [
        f"{ident.get('name', 'SUPERVOID')} v{ident.get('version', '')} — "
        f"{works.get('total', 0)} works ({len(works.get('active', []))} active) "
        f"across {len(ident.get('divisions', []))} divisions; "
        f"{len(worlds.get('active', []))} live worlds.",
        _line("Releases", f"{len(releases.get('published', []))} published, "
              f"{len(releases.get('upcoming', []))} upcoming", cap=cap),
        _line("Blockers", str(len(blockers))
              + (f" (top: {blockers[0]['title']})" if blockers else ""), cap=cap),
        _line("Pending approvals",
              f"{approvals.get('approval_request', 0)} requests / "
              f"{approvals.get('agent_proposal', 0)} agent / "
              f"{approvals.get('publication', 0)} publication", cap=cap),
        _line("Rights", f"{overdue} overdue, {soon} due soon", cap=cap),
        _line("Assets", f"{assets.get('missing_files', 0)} missing files, "
              f"{assets.get('unapproved_versions', 0)} unapproved, "
              f"{assets.get('expiring_licences', 0)} expiring licences", cap=cap),
        _line("Collaborators", f"{collab.get('total_active', 0)} active", cap=cap),
        _line("Integrations", f"{unhealthy} needing attention of {len(integ)}", cap=cap),
        _line("Priorities", "; ".join(
            p.get("subject") or p.get("content") or "" for p in priorities[:3]
        ) or "none recorded", cap=cap),
    ]
    return truncate("\n".join(lines), _SUMMARY_TOTAL["studio"])


def render_project_summary(state: dict) -> str:
    cap = _SUMMARY_LINE["project"]
    ident = state.get("identity", {})
    name = ident.get("title") or ident.get("name") or ident.get("id", "")
    md = state.get("medium_division", {})
    syn = state.get("canonical_synopsis", {})
    phase = state.get("creative_phase", {})
    progress = state.get("progress", {}).get("tasks", {})
    blocked = state.get("blocked_tasks", [])
    approvals = state.get("pending_approvals", {}).get("counts", {})
    rights = state.get("rights_constraints", {})
    questions = state.get("unresolved_questions", [])
    priorities = state.get("next_priorities", [])
    chars = state.get("characters", [])
    locs = state.get("locations", [])

    rights_warn = sum(1 for w in rights.get("warnings", []) if w.get("status") == "overdue")
    lines = [
        _line("Project", f"{name} [{ident.get('scope', '')}]"
              + (f" · {md.get('medium')}/{md.get('division')}" if md.get("medium") else ""),
              cap=cap),
        _line("Synopsis", syn.get("synopsis") or "—", cap=_SYNOPSIS_LINE),
        _line("Phase", f"{phase.get('work_status') or phase.get('world_status') or ''}"
              + (f" / {phase.get('editorial_phase')}" if phase.get("editorial_phase") else ""),
              cap=cap),
        _line("Progress", f"{progress.get('completion_pct', 0)}% — "
              f"{progress.get('done', 0)}/{progress.get('total', 0)} tasks, "
              f"{progress.get('blocked', 0)} blocked, {progress.get('overdue', 0)} overdue",
              cap=cap),
        _line("Cast", f"{len(chars)} characters, {len(locs)} locations", cap=cap),
        _line("Approvals", f"{approvals.get('approval_request', 0)} requests / "
              f"{approvals.get('agent_proposal', 0)} agent / "
              f"{approvals.get('publication', 0)} publication", cap=cap),
        _line("Rights", f"{len(rights.get('profiles', []))} profiles, "
              f"{rights_warn} overdue warnings", cap=cap),
        _line("Open questions", str(len(questions)), cap=cap),
        _line("Next", "; ".join(p.get("label") or "" for p in priorities[:3])
              or "none", cap=cap),
    ]
    return truncate("\n".join(lines), _SUMMARY_TOTAL["project"])


# === optional, guarded LLM prose compression ===============================
_NUM_RE = re.compile(r"\d+")


def _preserves_facts(template: str, prose: str) -> bool:
    """Every numeric token in the deterministic template must survive in the
    LLM prose. Guards against the model altering counts/versions/dates."""
    template_nums = _NUM_RE.findall(template)
    prose_nums = set(_NUM_RE.findall(prose))
    return all(n in prose_nums for n in template_nums)


def _maybe_compress(
    template: str, compressor: Optional[Compressor], *, kind: str
) -> tuple[str, Optional[str], Optional[str]]:
    """Return ``(compact_summary, llm_summary, assist_version)``.

    Default (no compressor, LLM off): the deterministic template, capped. When a
    compressor is supplied it may replace the prose *only* if it preserves every
    fact; otherwise we fall back to the template. The LLM never touches the
    structured state or the checksum.
    """
    compact = truncate(template, _SUMMARY_TOTAL[kind])
    if compressor is None and not settings.brain_compiler_use_llm:
        return compact, None, None
    if compressor is None:
        return compact, None, None
    try:
        prose = compressor(template)
    except Exception:
        return compact, None, None
    if prose and _preserves_facts(template, prose):
        return truncate(prose, _LLM_CAP[kind]), prose, f"{settings.brain_compiler_version}-llm"
    return compact, None, None


# === event window + high-water mark ========================================
def head_sequence(session: Session) -> int:
    return int(session.exec(select(func.max(BrainEvent.sequence))).one() or 0)


def _events_window(
    session: Session,
    *,
    from_seq: int,
    to_seq: int,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
) -> list[BrainEvent]:
    if to_seq <= from_seq:
        return []
    events = brain.list_events(session, after_sequence=from_seq, limit=1_000_000)
    out = []
    for e in events:
        if e.sequence > to_seq:
            continue
        if work_id is not None:
            if not (
                e.work_id == work_id
                or (e.aggregate_type == "work" and e.aggregate_id == work_id)
            ):
                continue
        elif story_world_id is not None:
            if not (
                e.story_world_id == story_world_id
                or (e.aggregate_type == "story_world" and e.aggregate_id == story_world_id)
            ):
                continue
        out.append(e)
    return out


def _digest(text: Optional[str], cap: int = 400) -> Optional[str]:
    return truncate(text, cap) if text else None


# === studio compilation ====================================================
def compile_studio(
    session: Session,
    *,
    full: bool = False,
    compile_date: Optional[date] = None,
    to_seq: Optional[int] = None,
    compressor: Optional[Compressor] = None,
    commit: bool = True,
) -> dict:
    compile_date = compile_date or date.today()
    to_seq = head_sequence(session) if to_seq is None else to_seq
    state = brain.get_studio_state(session)
    from_seq = state.source_event_cursor if state else 0
    fresh = state is None
    if fresh:
        full = True

    if full:
        affected = set(sb.STUDIO_ORDER)
    else:
        events = _events_window(session, from_seq=from_seq, to_seq=to_seq)
        affected = sb.affected_sections(events, "studio")

    new_state: dict = {} if full else copy.deepcopy(state.structured_state or {})
    for section in sb.STUDIO_ORDER:
        if full or section in affected or section not in new_state:
            new_state[section] = sb.STUDIO_SECTIONS[section](
                session, compile_date=compile_date
            )
    new_state = {k: new_state[k] for k in sb.STUDIO_ORDER}

    new_checksum = checksum(new_state)
    template = render_studio_summary(new_state)

    if not fresh and state.checksum == new_checksum:
        # No-op: nothing changed. Refresh the cursor / clear staleness only and
        # leave the prose columns untouched (never re-run the LLM on a no-op).
        brain.set_studio_state(
            session,
            structured_state=new_state,
            version=state.version,
            status=BrainStateStatus.READY,
            compact_summary=state.compact_summary,
            checksum=new_checksum,
            compiler_version=settings.brain_compiler_version,
            assist_version=state.assist_version,
            source_event_cursor=to_seq,
            stale=False,
            snapshot=False,
            llm_summary=None,
        )
        if commit:
            session.commit()
        return _result("studio", state.version, new_checksum, False, from_seq, to_seq)

    compact, llm_summary, assist_version = _maybe_compress(
        template, compressor, kind="studio"
    )
    new_version = (state.version + 1) if state else 1
    previous_version = state.version if state else None
    saved = brain.set_studio_state(
        session,
        structured_state=new_state,
        version=new_version,
        status=BrainStateStatus.READY,
        compact_summary=compact,
        checksum=new_checksum,
        compiler_version=settings.brain_compiler_version,
        assist_version=assist_version,
        source_event_cursor=to_seq,
        stale=False,
        snapshot=False,
        llm_summary=llm_summary,
    )
    brain.record_revision(
        session,
        state_type=BrainStateType.STUDIO,
        state_id=saved.id,
        version=new_version,
        previous_version=previous_version,
        deterministic_payload=new_state,
        llm_summary=llm_summary,
        source_event_from=from_seq,
        source_event_to=to_seq,
        compiler_version=settings.brain_compiler_version,
    )
    if commit:
        session.commit()
    return _result("studio", new_version, new_checksum, True, from_seq, to_seq)


# === project compilation ===================================================
def _resolve_scope(
    session: Session, work_id: Optional[str], story_world_id: Optional[str]
) -> tuple[Optional[Work], Optional[StoryWorld]]:
    if work_id:
        return session.get(Work, work_id), None
    return None, session.get(StoryWorld, story_world_id)


def compile_project(
    session: Session,
    *,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    full: bool = False,
    compile_date: Optional[date] = None,
    to_seq: Optional[int] = None,
    compressor: Optional[Compressor] = None,
    commit: bool = True,
) -> dict:
    if bool(work_id) == bool(story_world_id):
        raise ValueError("compile_project requires exactly one of work_id / story_world_id")
    compile_date = compile_date or date.today()
    to_seq = head_sequence(session) if to_seq is None else to_seq

    work, story_world = _resolve_scope(session, work_id, story_world_id)
    if work_id and work is None:
        raise ValueError(f"Work {work_id} not found")
    if story_world_id and story_world is None:
        raise ValueError(f"StoryWorld {story_world_id} not found")

    state = brain.get_project_state(
        session, work_id=work_id, story_world_id=story_world_id
    )
    from_seq = state.source_event_cursor if state else 0
    fresh = state is None
    if fresh:
        full = True

    ctx = sb.ProjectCtx(
        work=work,
        story_world=story_world,
        work_id=work_id,
        story_world_id=story_world_id,
        compile_date=compile_date,
        to_seq=to_seq,
    )

    if full:
        affected = set(sb.PROJECT_ORDER)
    else:
        events = _events_window(
            session,
            from_seq=from_seq,
            to_seq=to_seq,
            work_id=work_id,
            story_world_id=story_world_id,
        )
        affected = sb.affected_sections(events, "project")

    new_state: dict = {} if full else copy.deepcopy(state.structured_state or {})
    for section in sb.PROJECT_ORDER:
        if full or section in affected or section not in new_state:
            new_state[section] = sb.PROJECT_SECTIONS[section](session, ctx)
    new_state = {k: new_state[k] for k in sb.PROJECT_ORDER}

    new_checksum = checksum(new_state)
    template = render_project_summary(new_state)

    # Mirror selected sections into their dedicated columns (deterministic).
    canon = new_state.get("canon_facts", {})
    canon_digest = _digest(canon.get("canon_summary")) or canonical_json(canon)[:400]
    production_digest = canonical_json(new_state.get("progress", {}))[:400]
    open_questions = new_state.get("unresolved_questions", [])
    priorities = new_state.get("next_priorities", [])
    recent_changes = new_state.get("recent_changes", [])

    if not fresh and state.checksum == new_checksum:
        # No-op: refresh cursor / clear staleness, preserve the prose summary.
        brain.set_project_state(
            session,
            structured_state=new_state,
            work_id=work_id,
            story_world_id=story_world_id,
            version=state.version,
            status=BrainStateStatus.READY,
            compact_summary=state.compact_summary,
            canon_digest=canon_digest,
            production_digest=production_digest,
            open_questions=open_questions,
            priorities=priorities,
            recent_changes=recent_changes,
            checksum=new_checksum,
            source_event_cursor=to_seq,
            stale=False,
            snapshot=False,
            llm_summary=None,
        )
        if commit:
            session.commit()
        return _result("project", state.version, new_checksum, False, from_seq, to_seq,
                       work_id=work_id, story_world_id=story_world_id)

    compact, llm_summary, assist_version = _maybe_compress(
        template, compressor, kind="project"
    )
    new_version = (state.version + 1) if state else 1
    previous_version = state.version if state else None
    saved = brain.set_project_state(
        session,
        structured_state=new_state,
        work_id=work_id,
        story_world_id=story_world_id,
        version=new_version,
        status=BrainStateStatus.READY,
        compact_summary=compact,
        canon_digest=canon_digest,
        production_digest=production_digest,
        open_questions=open_questions,
        priorities=priorities,
        recent_changes=recent_changes,
        checksum=new_checksum,
        source_event_cursor=to_seq,
        stale=False,
        snapshot=False,
        llm_summary=llm_summary,
    )
    # Record the immutable revision ourselves so it carries full provenance
    # (set_project_state's own snapshot hardcodes compiler_version=None and omits
    # source_event_from).
    brain.record_revision(
        session,
        state_type=BrainStateType.PROJECT,
        state_id=saved.id,
        version=new_version,
        previous_version=previous_version,
        deterministic_payload=new_state,
        llm_summary=llm_summary,
        source_event_from=from_seq,
        source_event_to=to_seq,
        compiler_version=settings.brain_compiler_version,
    )
    if commit:
        session.commit()
    return _result("project", new_version, new_checksum, True, from_seq, to_seq,
                   work_id=work_id, story_world_id=story_world_id)


def _result(scope, version, cs, changed, from_seq, to_seq, **extra) -> dict:
    return {
        "scope": scope,
        "version": version,
        "checksum": cs,
        "changed": changed,
        "from_seq": from_seq,
        "to_seq": to_seq,
        **extra,
    }


# === batch: compile every stale state ======================================
def compile_stale(
    session: Session,
    *,
    batch: Optional[int] = None,
    compile_date: Optional[date] = None,
    compressor: Optional[Compressor] = None,
) -> dict:
    """Compile the studio (if stale or behind) and every stale project state.

    Each state compiles in its own transaction; a failure isolates to that state
    (marked FAILED) without aborting the batch — mirroring the outbox consumer.
    """
    batch = batch or settings.brain_compiler_batch
    compile_date = compile_date or date.today()
    to_seq = head_sequence(session)
    results: dict = {"to_seq": to_seq, "studio": None, "projects": [], "failed": []}

    studio = brain.get_studio_state(session)
    if studio is None or studio.stale or studio.source_event_cursor < to_seq:
        try:
            results["studio"] = compile_studio(
                session, compile_date=compile_date, to_seq=to_seq, compressor=compressor
            )
        except Exception as exc:  # pragma: no cover - defensive
            session.rollback()
            results["failed"].append({"scope": "studio", "error": str(exc)})

    # Candidate filter is cheap (global head); refine per scope below so we
    # agree with stale_states() and don't churn out-of-scope projects.
    candidates = session.exec(
        select(ProjectBrainState)
        .where(
            (ProjectBrainState.stale == True)  # noqa: E712
            | (ProjectBrainState.status == BrainStateStatus.STALE)
            | (ProjectBrainState.source_event_cursor < to_seq)
        )
        .order_by(ProjectBrainState.id)
        .limit(batch)
    ).all()
    stale_projects = [
        ps
        for ps in candidates
        if ps.stale
        or ps.status == BrainStateStatus.STALE
        or ps.source_event_cursor
        < _scope_head(session, work_id=ps.work_id, story_world_id=ps.story_world_id)
    ]
    for ps in stale_projects:
        try:
            results["projects"].append(
                compile_project(
                    session,
                    work_id=ps.work_id,
                    story_world_id=ps.story_world_id,
                    compile_date=compile_date,
                    to_seq=to_seq,
                    compressor=compressor,
                )
            )
        except Exception as exc:
            session.rollback()
            ref = ps.work_id or ps.story_world_id
            results["failed"].append({"scope": "project", "ref": ref, "error": str(exc)})
            _mark_failed(session, ps.work_id, ps.story_world_id)
    return results


def _mark_failed(session: Session, work_id, story_world_id) -> None:
    ps = brain.get_project_state(session, work_id=work_id, story_world_id=story_world_id)
    if ps is not None:
        ps.status = BrainStateStatus.FAILED
        ps.stale = True
        session.add(ps)
        session.commit()


# === read-only health / stale / delta (for the API) ========================
def _state_health(state) -> Optional[dict]:
    if state is None:
        return None
    head = None  # filled by caller
    return {
        "version": state.version,
        "status": state.status.value,
        "stale": state.stale,
        "checksum": state.checksum,
        "compiled_at": state.compiled_at.isoformat() if state.compiled_at else None,
        "source_event_cursor": state.source_event_cursor,
    }


def compiler_health(session: Session) -> dict:
    head = head_sequence(session)
    studio = brain.get_studio_state(session)
    studio_h = _state_health(studio)
    if studio_h is not None:
        studio_h["lag"] = head - studio.source_event_cursor

    projects = session.exec(
        select(ProjectBrainState).order_by(ProjectBrainState.id)
    ).all()
    proj_h = []
    for ps in projects:
        h = _state_health(ps)
        h["work_id"] = ps.work_id
        h["story_world_id"] = ps.story_world_id
        h["lag"] = head - ps.source_event_cursor
        proj_h.append(h)

    return {
        "head_sequence": head,
        "compiler_version": settings.brain_compiler_version,
        "outbox": brain.outbox_status(session),
        "studio": studio_h,
        "projects": proj_h,
    }


def _scope_head(session: Session, *, work_id=None, story_world_id=None) -> int:
    stmt = select(func.max(BrainEvent.sequence))
    if work_id:
        stmt = stmt.where(
            (BrainEvent.work_id == work_id)
            | ((BrainEvent.aggregate_type == "work") & (BrainEvent.aggregate_id == work_id))
        )
    else:
        stmt = stmt.where(
            (BrainEvent.story_world_id == story_world_id)
            | ((BrainEvent.aggregate_type == "story_world") & (BrainEvent.aggregate_id == story_world_id))
        )
    return int(session.exec(stmt).one() or 0)


def stale_states(session: Session) -> dict:
    """States that need (re)compilation: flagged stale, in STALE status, or whose
    cursor trails the latest in-scope event. Read-only (does not mutate)."""
    head = head_sequence(session)
    out: list[dict] = []

    studio = brain.get_studio_state(session)
    if studio is None or studio.stale or studio.status == BrainStateStatus.STALE or studio.source_event_cursor < head:
        out.append(
            {
                "scope": "studio",
                "id": studio.id if studio else None,
                "version": studio.version if studio else 0,
                "stale": True if studio is None else studio.stale,
                "cursor": studio.source_event_cursor if studio else 0,
                "head": head,
                "reason": "missing" if studio is None else (
                    "flagged" if (studio.stale or studio.status == BrainStateStatus.STALE)
                    else "behind"
                ),
            }
        )

    for ps in session.exec(select(ProjectBrainState).order_by(ProjectBrainState.id)).all():
        scope_head = _scope_head(session, work_id=ps.work_id, story_world_id=ps.story_world_id)
        behind = ps.source_event_cursor < scope_head
        if ps.stale or ps.status == BrainStateStatus.STALE or behind:
            out.append(
                {
                    "scope": "project",
                    "id": ps.id,
                    "work_id": ps.work_id,
                    "story_world_id": ps.story_world_id,
                    "version": ps.version,
                    "stale": ps.stale,
                    "cursor": ps.source_event_cursor,
                    "head": scope_head,
                    "reason": "flagged" if (ps.stale or ps.status == BrainStateStatus.STALE) else "behind",
                }
            )

    return {"head_sequence": head, "count": len(out), "states": out}


def revision_delta(session: Session, *, revision_a_id: str, revision_b_id: str) -> dict:
    """Deterministic section-level diff between two revisions' payloads."""
    a = session.get(BrainStateRevision, revision_a_id)
    b = session.get(BrainStateRevision, revision_b_id)
    if a is None or b is None:
        raise ValueError("revision not found")
    pa = a.deterministic_payload or {}
    pb = b.deterministic_payload or {}
    keys_a, keys_b = set(pa), set(pb)
    added = sorted(keys_b - keys_a)
    removed = sorted(keys_a - keys_b)
    changed = sorted(
        k for k in (keys_a & keys_b)
        if canonical_json(pa[k]) != canonical_json(pb[k])
    )
    return {
        "from": {"id": a.id, "version": a.version, "state_type": a.state_type.value},
        "to": {"id": b.id, "version": b.version, "state_type": b.state_type.value},
        "added": added,
        "removed": removed,
        "changed": changed,
    }
