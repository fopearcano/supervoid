"""The Brain stateful-session service (Prompt 8).

Sits ON TOP of the ContextAssembler + BrainCheckpoint: it records the live
prefix signature, the event cursor, and the hot/warm/cold lifecycle for each
conversation, and decides whether the next turn is prefix-cache *eligible*. It
NEVER asserts vLLM durably remembers a conversation — vLLM prefix caching is an
optimisation we make eligible; this session row is the source of truth.

Conventions: functions add+flush but do NOT commit (the caller owns the txn),
except the lifecycle sweep / prewarm passes which run standalone and commit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.config import settings
from app.models import (
    BrainCheckpoint,
    BrainConversation,
    BrainSession,
    DecisionRecord,
    User,
)
from app.models.base import utcnow
from app.models.enums import (
    BrainConversationStatus,
    BrainMemoryKind,
    BrainScope,
    BrainSessionWarmth,
    DecisionStatus,
    StoryWorldStatus,
    WorkStatus,
)
from app.services import brain
from app.services.brain import compiler
from app.services.brain.session_signature import (
    InvalidationResult,
    PrefixSignature,
    TurnMetrics,
    compute_turn_metrics,
    diff_signature,
    is_warm_eligible,
)
from app.utils.logging import get_logger

log = get_logger("app.brain.session")

# Project statuses that make a project "archived" for prewarming purposes.
_DEAD_WORK_STATUS = {WorkStatus.ARCHIVED, WorkStatus.CANCELLED, WorkStatus.ON_HOLD}
_DEAD_WORLD_STATUS = {StoryWorldStatus.ARCHIVED, StoryWorldStatus.DORMANT}


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite round-trips naive datetimes; utcnow() is aware. Normalise to naive
    before any subtraction so idle-age maths never raises a TypeError."""
    return dt.replace(tzinfo=None) if (dt is not None and dt.tzinfo is not None) else dt


# === CRUD ==================================================================
def get_session_row(session: Session, conversation_id: str) -> Optional[BrainSession]:
    return session.exec(
        select(BrainSession).where(BrainSession.conversation_id == conversation_id)
    ).first()


def get_or_create_session(session: Session, conversation: BrainConversation) -> BrainSession:
    sess = get_session_row(session, conversation.id)
    if sess is None:
        sess = BrainSession(
            conversation_id=conversation.id,
            work_id=conversation.work_id,
            story_world_id=conversation.story_world_id,
            active_profile=conversation.active_profile,
            warmth=BrainSessionWarmth.HOT,
        )
        session.add(sess)
        session.flush()
    return sess


# === per-turn decision =====================================================
@dataclass(frozen=True)
class TurnDecision:
    prev_signature: Optional[PrefixSignature]  # snapshotted BEFORE assemble ran
    curr_signature: PrefixSignature
    invalidation: InvalidationResult
    prefix_cache_eligible: bool
    warmth: BrainSessionWarmth


def begin_turn(
    session: Session,
    conversation: BrainConversation,
    ctx,
    *,
    prev_prefix_hash: Optional[str],
    prev_signature: Optional[PrefixSignature],
) -> TurnDecision:
    """Compare the prior signature (snapshotted BEFORE ``assemble`` persisted the
    new checkpoint) to the just-assembled context, advance the single
    ``BrainSession`` row, and return the decision. add+flush only — the gateway's
    existing commit persists it."""
    sess = get_or_create_session(session, conversation)
    studio_state = brain.get_studio_state(session)
    project_state = (
        brain.get_project_state(
            session, work_id=conversation.work_id, story_world_id=conversation.story_world_id
        )
        if (conversation.work_id or conversation.story_world_id)
        else None
    )
    curr_sig = PrefixSignature.from_context(
        ctx, conversation, studio_state=studio_state, project_state=project_state
    )
    invalidation = diff_signature(prev_signature, curr_sig)
    eligible = is_warm_eligible(prev_signature, curr_sig)
    # Compute every derived value (incl. the only query, head_sequence) BEFORE
    # touching the row, so the mutation block is pure attribute assignment and a
    # partial/inconsistent session row can never be flushed by the shared commit.
    cursor = compiler.head_sequence(session)
    now = utcnow()

    sess.work_id = conversation.work_id
    sess.story_world_id = conversation.story_world_id
    sess.active_profile = conversation.active_profile
    sess.model = curr_sig.model
    sess.last_prefix_hash = curr_sig.prefix_hash
    sess.constitution_version = curr_sig.constitution_version
    sess.profile_version = curr_sig.profile_version
    sess.studio_state_version = curr_sig.studio_state_version
    sess.project_state_version = curr_sig.project_state_version
    sess.studio_state_checksum = curr_sig.studio_state_checksum
    sess.project_state_checksum = curr_sig.project_state_checksum
    sess.permissions_fingerprint = curr_sig.permissions_fingerprint
    sess.last_event_cursor = cursor
    sess.last_activity_at = now
    sess.warmth = BrainSessionWarmth.HOT
    sess.turn_count += 1
    # A cold start (no prior signature) is NOT an invalidation — only count an
    # actual rule firing on a subsequent turn.
    if invalidation.reasons:
        sess.invalidation_count += 1
        sess.last_invalidation_reason = (
            invalidation.primary.value if invalidation.primary else None
        )
    session.add(sess)
    session.flush()
    return TurnDecision(
        prev_signature=prev_signature,
        curr_signature=curr_sig,
        invalidation=invalidation,
        prefix_cache_eligible=eligible,
        warmth=sess.warmth,
    )


def record_metrics(
    ctx,
    *,
    prefix_cache_eligible: bool,
    invalidation: InvalidationResult,
    usage,
    response_latency_ms: Optional[float],
    ttft_ms: Optional[float],
    warmth: Optional[str],
) -> TurnMetrics:
    """Thin DB-free wrapper over compute_turn_metrics (kept here so callers use a
    single ``brain.session.*`` surface)."""
    return compute_turn_metrics(
        ctx,
        prefix_cache_eligible=prefix_cache_eligible,
        invalidation=invalidation,
        usage=usage,
        response_latency_ms=response_latency_ms,
        ttft_ms=ttft_ms,
        warmth=warmth,
    )


# === hot / warm / cold lifecycle ==========================================
def classify_warmth(
    session: Session, sess: BrainSession, *, now: Optional[datetime] = None
) -> BrainSessionWarmth:
    """HOT = recently active conversation; WARM = idle but a saved checkpoint for
    last_prefix_hash + compiled state exist; COLD = archived, aged out, or no
    checkpoint to resume from."""
    now = _naive(now or utcnow())
    conv = brain.get_conversation(session, sess.conversation_id)
    if conv is not None and conv.status == BrainConversationStatus.ARCHIVED:
        return BrainSessionWarmth.COLD
    if sess.last_activity_at is None:
        return BrainSessionWarmth.COLD
    idle_min = (now - _naive(sess.last_activity_at)).total_seconds() / 60
    if idle_min <= settings.brain_session_hot_window_minutes:
        return BrainSessionWarmth.HOT
    has_ckpt = bool(
        session.exec(
            select(BrainCheckpoint).where(
                BrainCheckpoint.conversation_id == sess.conversation_id,
                BrainCheckpoint.prefix_hash == sess.last_prefix_hash,
            )
        ).first()
    )
    if idle_min <= settings.brain_session_warm_window_hours * 60 and has_ckpt:
        return BrainSessionWarmth.WARM
    return BrainSessionWarmth.COLD


def sweep_lifecycle(
    session: Session,
    *,
    now: Optional[datetime] = None,
    batch: Optional[int] = None,
    archive: bool = True,
) -> dict:
    """Reclassify warmth for all sessions; on →COLD past the archive horizon,
    mark the conversation ARCHIVED (opt-in via ``archive``). NEVER deletes
    messages — cold means the full archive is retained. Per-session failures are
    isolated. Commits. Returns counts."""
    now_naive = _naive(now or utcnow())
    limit = batch or 1000
    rows = session.exec(
        select(BrainSession).order_by(BrainSession.last_activity_at).limit(limit)
    ).all()
    counts = {"scanned": 0, "hot": 0, "warm": 0, "cold": 0, "archived": 0}
    horizon_min = settings.brain_session_archive_horizon_days * 24 * 60
    for sess in rows:
        counts["scanned"] += 1
        try:
            warmth = classify_warmth(session, sess, now=now)
            sess.warmth = warmth
            counts[warmth.value] += 1
            session.add(sess)
            if (
                archive
                and warmth == BrainSessionWarmth.COLD
                and sess.last_activity_at is not None
            ):
                idle_min = (
                    now_naive - _naive(sess.last_activity_at)
                ).total_seconds() / 60
                if idle_min > horizon_min:
                    conv = brain.get_conversation(session, sess.conversation_id)
                    if conv is not None and conv.status != BrainConversationStatus.ARCHIVED:
                        conv.status = BrainConversationStatus.ARCHIVED
                        session.add(conv)
                        counts["archived"] += 1
        except Exception:  # isolate one bad row from the whole sweep
            log.exception("session sweep failed for conversation=%s", sess.conversation_id)
    session.commit()
    return counts


def mark_project_cold(
    session: Session, *, work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
) -> dict:
    """Operator control (Prompt 16): mark every session for a project COLD so its
    prefix-cache is treated as evicted (it will be re-primed on the next turn or
    by prewarm). Messages are never deleted. Commits. Returns a count."""
    if not (work_id or story_world_id):
        return {"marked": 0}
    stmt = select(BrainSession)
    if work_id:
        stmt = stmt.where(BrainSession.work_id == work_id)
    else:
        stmt = stmt.where(BrainSession.story_world_id == story_world_id)
    marked = 0
    for sess in session.exec(stmt).all():
        sess.warmth = BrainSessionWarmth.COLD
        session.add(sess)
        marked += 1
    session.commit()
    return {"marked": marked, "work_id": work_id, "story_world_id": story_world_id}


# === prewarming ============================================================
def _project_is_active(session: Session, sess: BrainSession) -> bool:
    """A session's project must not be archived to be prewarmed."""
    from app.models import StoryWorld, Work

    if sess.work_id:
        work = session.get(Work, sess.work_id)
        return work is not None and work.status not in _DEAD_WORK_STATUS
    if sess.story_world_id:
        world = session.get(StoryWorld, sess.story_world_id)
        return world is not None and world.status not in _DEAD_WORLD_STATUS
    return True  # project-less Studio Director lanes are eligible


# Module-level token bucket — best-effort, per-process (consistent with the
# gateway's limiter). Keyed by a constant so the whole prewarm pass shares a budget.
from app.utils.throttle import RateLimiter  # noqa: E402

_prewarm_rate = RateLimiter(
    rate_per_min=settings.brain_prewarm_rate_per_min, burst=settings.brain_prewarm_burst
)


def prewarm_active(
    session: Session, *, provider=None, limit: Optional[int] = None
) -> dict:
    """Optionally submit a zero/small-output request to the provider for ACTIVE
    project prefixes, making vLLM's prefix cache eligible. Best-effort priming
    only — it NEVER asserts vLLM retained anything. dry_run / sync-only providers
    are a no-op (no socket). Returns a structured summary."""
    from app.services.ai.providers import get_provider
    from app.services.ai.providers.base import ChatMessage, ChatRequest

    provider = provider or get_provider()
    summary = {"selected": 0, "prewarmed": 0, "skipped": 0, "rate_limited": 0, "reason": None}

    # Offline / dry-run path: never open a socket.
    if settings.ai_provider == "dry_run" or not hasattr(provider, "acomplete"):
        summary["reason"] = "provider=dry_run"
        return summary

    cap = limit or settings.brain_prewarm_batch
    cooldown = settings.brain_prewarm_cooldown_seconds
    now = _naive(utcnow())
    candidates = session.exec(
        select(BrainSession)
        .where(BrainSession.warmth == BrainSessionWarmth.HOT)
        .order_by(BrainSession.last_activity_at.desc())
    ).all()

    import asyncio

    for sess in candidates:
        if summary["prewarmed"] >= cap:
            break
        conv = brain.get_conversation(session, sess.conversation_id)
        if conv is None or conv.status != BrainConversationStatus.ACTIVE:
            summary["skipped"] += 1
            continue
        if not _project_is_active(session, sess):
            summary["skipped"] += 1
            continue
        if sess.last_prewarmed_at is not None:
            since = (now - _naive(sess.last_prewarmed_at)).total_seconds()
            if since < cooldown:
                summary["skipped"] += 1
                continue
        if not _prewarm_rate.allow("prewarm"):
            summary["rate_limited"] += 1
            break  # budget exhausted; remaining picked up next pass
        summary["selected"] += 1
        owner = session.get(User, conv.owner_user_id)
        if owner is None:
            summary["skipped"] += 1
            continue
        try:
            ctx = brain.assemble(
                session, conv, user=owner, model=settings.ai_model,
                include_evidence=False, question=None, persist=False,
            )
            req = ChatRequest(
                messages=[ChatMessage(role=m["role"], content=m.get("content")) for m in ctx.messages],
                model=settings.ai_model, temperature=0.0, max_tokens=1, stream=False,
            )
            asyncio.run(provider.acomplete(req))
            sess.last_prewarmed_at = utcnow()
            session.add(sess)
            summary["prewarmed"] += 1
        except Exception:  # isolate one failed prime from the pass
            log.exception("prewarm failed for conversation=%s", sess.conversation_id)
            summary["skipped"] += 1
    session.commit()
    return summary


# === compaction ============================================================
_TASK_MARKER = re.compile(r"^\s*(DECISION|TASK|TODO|ACTION|COMMITMENT)\s*[:\-]\s*(.+)$",
                          re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class CompactionResult:
    conversation_id: str
    extracted_decisions: list  # DecisionRecord ids for the conversation
    approved_decisions: list  # APPROVED ids force-retained
    extracted_tasks: list
    memory_item_id: Optional[str]
    retained_message_count: int  # == total messages (never reduced)
    used_llm: bool


def should_compact(session: Session, conversation: BrainConversation) -> bool:
    count = len(brain.list_messages(session, conversation.id, limit=1000))
    return count > settings.brain_session_compact_after_turns


def _conversation_decisions(session: Session, conversation_id: str) -> list:
    return list(
        session.exec(
            select(DecisionRecord)
            .where(DecisionRecord.source_conversation_id == conversation_id)
            .order_by(DecisionRecord.created_at)
        ).all()
    )


def compact_conversation(
    session: Session, conversation: BrainConversation, *, compressor=None
) -> CompactionResult:
    """Compact a conversation deterministically: extract decisions/tasks, persist
    a durable digest, and RETAIN every original message. Approved decisions are
    NEVER silently dropped — a hard post⊇pre check fails closed. An optional LLM
    summary is a SECONDARY artifact only, fact-guarded, and never replaces the
    deterministic facts. add+flush only (caller commits)."""
    messages = brain.list_messages(session, conversation.id, limit=10000)

    # 1. Deterministic decision extraction (authoritative — referenced, not rewritten).
    decisions = _conversation_decisions(session, conversation.id)
    approved_pre = sorted(
        d.id for d in decisions if d.status == DecisionStatus.APPROVED
    )
    decision_lines = [
        f"DECISION[{d.status.value}]: {d.subject} — {d.decision}" for d in decisions
    ]

    # 2. Deterministic task/commitment extraction from message text (regex, no model).
    tasks: list[str] = []
    for m in messages:
        for marker, body in _TASK_MARKER.findall(m.content or ""):
            tasks.append(f"{marker.upper()}: {body.strip()}")
    # plus any persisted decision/commitment memory for this conversation
    for item in brain.list_memory(
        session, conversation_id=conversation.id, limit=500
    ):
        if item.kind in (BrainMemoryKind.DECISION, BrainMemoryKind.COMMITMENT):
            tasks.append(f"{item.kind.value.upper()}: {item.content}")

    # 3. Deterministic digest (the PRIMARY artifact). Approved decisions are
    #    force-included verbatim so they can never be dropped.
    digest_parts = ["CONVERSATION COMPACTION (deterministic)"]
    if decision_lines:
        digest_parts.append("Decisions:\n" + "\n".join(decision_lines))
    if tasks:
        digest_parts.append("Tasks / commitments:\n" + "\n".join(sorted(set(tasks))))
    deterministic_digest = "\n\n".join(digest_parts)

    # Hard invariant: the digest must reference every approved decision.
    for d in decisions:
        if d.status == DecisionStatus.APPROVED and d.id not in deterministic_digest \
                and d.subject not in deterministic_digest:
            raise RuntimeError(
                f"compaction would drop approved decision {d.id}; refusing to write a lossy summary"
            )

    # 4. Optional LLM summary — SECONDARY, fact-guarded, never gates retention.
    used_llm = False
    llm_summary = None
    if compressor is not None and settings.brain_session_compaction_use_llm:
        try:
            candidate = compressor(deterministic_digest)
            if candidate and compiler._preserves_facts(deterministic_digest, candidate):
                llm_summary = candidate
                used_llm = True
        except Exception:
            log.exception("compaction LLM summary failed; using deterministic digest")

    structured = {
        "kind": "conversation_compaction",
        "decision_ids": [d.id for d in decisions],
        "approved_decision_ids": approved_pre,
        "tasks": sorted(set(tasks)),
        "llm_summary": llm_summary,
        "compacted_at": utcnow().isoformat(),
    }
    item = brain.create_memory(
        session,
        scope=BrainScope.CONVERSATION,
        kind=BrainMemoryKind.PROCEDURE,
        content=deterministic_digest,
        conversation_id=conversation.id,
        structured_data=structured,
        work_id=conversation.work_id,
        story_world_id=conversation.story_world_id,
    )

    # Record the compaction boundary on the session (messages are NOT deleted).
    sess = get_or_create_session(session, conversation)
    if messages:
        sess.last_message_id = messages[-1].id
    session.add(sess)
    session.flush()

    return CompactionResult(
        conversation_id=conversation.id,
        extracted_decisions=[d.id for d in decisions],
        approved_decisions=approved_pre,
        extracted_tasks=sorted(set(tasks)),
        memory_item_id=item.id,
        retained_message_count=len(messages),
        used_llm=used_llm,
    )
