"""Conversation memory & decision extraction (Prompt 13).

After every completed Brain response the gateway enqueues a
``conversation.turn_completed`` event; the outbox consumer routes it here. The
job *proposes* durable items — it never silently rewrites the studio's truth:

* **Casual conversation** is archived (the messages persist) but produces no
  durable memory.
* **Canon / rights / production** claims never become inferred memory. They
  become a PROPOSED :class:`DecisionRecord` that needs approval — the structured
  domain records remain the only source of canonical truth.
* A **member preference** may be *auto-accepted* (verified without review) ONLY
  when it concerns the same user, is low-risk, clears the confidence threshold,
  and neither grants permissions nor alters canon. Everything else lands in the
  Memory Review inbox as UNVERIFIED.
* **Contradictions** with current *verified* state are detected; a superseding
  preference retires the old one (we never overwrite — we supersede and keep
  provenance). A previously *rejected* topic is never auto-resurrected.

The extraction step (the model call) is best-effort and isolated: any failure
yields zero candidates, so a bad model response never dead-letters the turn. The
promotion rules below are fully deterministic and are what the tests exercise.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session

from app.config import settings
from app.models import BrainMemoryItem, BrainMessage
from app.models.base import utcnow
from app.models.enums import (
    BrainMemoryKind,
    BrainMemoryVerification,
    BrainMessageRole,
    BrainScope,
)
from app.services import brain


# === candidate model =======================================================
@dataclass
class MemoryCandidate:
    """One extracted item proposed by the analysis model (pre-promotion)."""

    kind: BrainMemoryKind
    content: str
    confidence: Optional[float] = None
    topic_key: Optional[str] = None
    scope_hint: str = "conversation"  # member | project | studio | conversation
    risk: str = "low"  # low | medium | high
    touches_canon: bool = False  # canon / rights / production claim
    grants_permission: bool = False  # changes roles / access
    is_decision: bool = False
    subject: Optional[str] = None  # for decisions
    rationale: Optional[str] = None
    alternatives: list = field(default_factory=list)
    affected_entities: list = field(default_factory=list)


# Canon / rights / production vocabulary. Defence-in-depth: even if the model
# forgets to flag ``touches_canon``, a claim that reads like canon/rights/
# production is still routed to the approval path rather than to memory.
_CANON_RE = re.compile(
    r"\b(canon|canonical|rights?|licen[cs]e|clearance|copyright|trademark|"
    r"contract|royalt|production status|publish(ed|ing)?|release date|"
    r"ship date|deadline|in production|greenlit)\b",
    re.IGNORECASE,
)
_PERMISSION_RE = re.compile(
    r"\b(permission|role|grant|access|admin|owner|approver|privilege)\b",
    re.IGNORECASE,
)


def _normalise_topic(text: str) -> str:
    """A stable, lowercase slug used to match items about the same subject."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:200]


def _looks_like_canon(content: str, topic_key: Optional[str]) -> bool:
    return bool(_CANON_RE.search(content or "") or _CANON_RE.search(topic_key or ""))


def _looks_like_permission(content: str) -> bool:
    return bool(_PERMISSION_RE.search(content or ""))


# === scope resolution ======================================================
def _resolve_scope(conversation, candidate: MemoryCandidate):
    """Map a candidate's hint onto a concrete (scope, work_id, story_world_id,
    member_user_id). A 'project' hint without a project binding falls back to the
    owner-private CONVERSATION scope so nothing can leak across projects."""
    hint = (candidate.scope_hint or "").lower()
    owner = conversation.owner_user_id
    if candidate.kind == BrainMemoryKind.PREFERENCE or hint == "member":
        return BrainScope.MEMBER, None, None, owner
    if hint == "project":
        if conversation.work_id or conversation.story_world_id:
            return BrainScope.PROJECT, conversation.work_id, conversation.story_world_id, None
        return BrainScope.CONVERSATION, None, None, None
    if hint == "studio":
        return BrainScope.STUDIO, None, None, None
    return BrainScope.CONVERSATION, None, None, None


# === contradiction / rejected detection ====================================
def _verified_same_topic(
    session: Session, *, scope, work_id, story_world_id, member_user_id, topic_key
) -> list[BrainMemoryItem]:
    """Verified items in the SAME scope sharing this topic_key (contradictions /
    supersedable priors). Empty without a topic_key (we never guess)."""
    if not topic_key:
        return []
    rows = brain.list_memory(
        session, scope=scope, work_id=work_id, story_world_id=story_world_id,
        member_user_id=member_user_id, verification=BrainMemoryVerification.VERIFIED,
        limit=500,
    )
    return [r for r in rows if r.topic_key == topic_key]


def _rejected_twin(
    session: Session, *, scope, work_id, story_world_id, member_user_id, topic_key
) -> bool:
    """True if this exact topic was already REJECTED in this scope — so it is
    never auto-resurrected as verified."""
    if not topic_key:
        return False
    rows = brain.list_memory(
        session, scope=scope, work_id=work_id, story_world_id=story_world_id,
        member_user_id=member_user_id, verification=BrainMemoryVerification.REJECTED,
        limit=500,
    )
    return any(r.topic_key == topic_key for r in rows)


def _can_auto_accept(
    candidate: MemoryCandidate, *, scope, member_user_id, owner_id,
    touches_canon: bool, grants_permission: bool, rejected_twin: bool,
) -> bool:
    """A preference auto-accepts ONLY when every guard holds (see module docs)."""
    return (
        candidate.kind == BrainMemoryKind.PREFERENCE
        and scope == BrainScope.MEMBER
        and member_user_id == owner_id                       # same user
        and (candidate.risk or "low") == "low"               # low risk
        and (candidate.confidence or 0.0)
        >= settings.brain_memory_auto_accept_min_confidence  # confidence
        and not touches_canon                                # never alters canon
        and not grants_permission                            # never grants perms
        and not rejected_twin                                # never resurrects a reject
    )


# === promotion (deterministic rules) =======================================
def promote_candidate(
    session: Session,
    *,
    conversation,
    candidate: MemoryCandidate,
    source_message_id: Optional[str] = None,
    source_event_id: Optional[str] = None,
) -> dict:
    """Apply the Prompt 13 rules to one candidate and persist the outcome.

    Returns a small dict describing what happened (for logging / tests). Adds +
    flushes; the caller (consumer savepoint or a test) owns the commit."""
    content = (candidate.content or "").strip()
    if not content:
        return {"action": "skipped", "reason": "empty"}

    topic_key = candidate.topic_key or _normalise_topic(content)
    touches_canon = candidate.touches_canon or _looks_like_canon(content, topic_key)
    grants_permission = candidate.grants_permission or _looks_like_permission(content)
    scope, work_id, story_world_id, member_user_id = _resolve_scope(conversation, candidate)

    # --- canon / rights / production: NEVER inferred memory -> a PROPOSED
    # decision that needs approval (structured domain records stay the truth). --
    if touches_canon or candidate.is_decision or candidate.kind == BrainMemoryKind.DECISION:
        d_scope = scope if scope in (BrainScope.PROJECT, BrainScope.STUDIO) else BrainScope.STUDIO
        d_work = work_id if d_scope == BrainScope.PROJECT else None
        d_world = story_world_id if d_scope == BrainScope.PROJECT else None
        record = brain.create_decision(
            session,
            scope=d_scope,
            subject=(candidate.subject or content)[:300],
            decision=content,
            proposer_id=conversation.owner_user_id,
            rationale=candidate.rationale,
            alternatives=candidate.alternatives,
            affected_entities=candidate.affected_entities,
            work_id=d_work,
            story_world_id=d_world,
            source_conversation_id=conversation.id,
        )
        return {
            "action": "decision",
            "id": record.id,
            "status": record.status.value,
            "touches_canon": touches_canon,
        }

    # --- everything else becomes a memory PROPOSAL (UNVERIFIED) --------------
    risk = (candidate.risk or "low").lower()
    if risk not in ("low", "medium", "high"):
        risk = "medium"
    contradictions = _verified_same_topic(
        session, scope=scope, work_id=work_id, story_world_id=story_world_id,
        member_user_id=member_user_id, topic_key=topic_key,
    )
    contradictions = [c for c in contradictions if (c.content or "").strip() != content]
    rejected = _rejected_twin(
        session, scope=scope, work_id=work_id, story_world_id=story_world_id,
        member_user_id=member_user_id, topic_key=topic_key,
    )

    structured = {"proposed_by": "memory_analysis"}
    if contradictions:
        structured["contradicts"] = [c.id for c in contradictions]
    if rejected:
        structured["previously_rejected"] = True

    item = brain.create_memory(
        session,
        scope=scope,
        kind=candidate.kind,
        content=content,
        created_by_id=conversation.owner_user_id,
        structured_data=structured,
        confidence=candidate.confidence,
        work_id=work_id,
        story_world_id=story_world_id,
        member_user_id=member_user_id,
        conversation_id=conversation.id,
        source_message_id=source_message_id,
        source_event_id=source_event_id,
    )
    item.topic_key = topic_key
    item.risk_level = risk
    session.add(item)
    session.flush()

    # --- auto-accept (preferences only) -------------------------------------
    if _can_auto_accept(
        candidate, scope=scope, member_user_id=member_user_id,
        owner_id=conversation.owner_user_id, touches_canon=touches_canon,
        grants_permission=grants_permission, rejected_twin=rejected,
    ):
        # A superseding preference retires the prior verified one(s) — never an
        # overwrite; the old rows stay as SUPERSEDED with full provenance.
        for prior in contradictions:
            prior.verification = BrainMemoryVerification.SUPERSEDED
            session.add(prior)
        if contradictions:
            item.supersedes_id = contradictions[0].id
        item.verification = BrainMemoryVerification.VERIFIED
        item.auto_accepted = True
        item.approved_by_id = conversation.owner_user_id
        item.reviewed_by_id = "system"
        item.reviewed_at = utcnow()
        session.add(item)
        session.flush()
        return {"action": "auto_accepted", "id": item.id, "kind": item.kind.value}

    return {
        "action": "proposed",
        "id": item.id,
        "kind": item.kind.value,
        "scope": scope.value,
        "contradicts": structured.get("contradicts", []),
    }


# === extraction (best-effort model call) ===================================
def _recent_transcript(messages: list[BrainMessage]) -> str:
    """Render the recent turns as a compact transcript for the extractor."""
    lines: list[str] = []
    for m in messages:
        if m.role not in (BrainMessageRole.USER, BrainMessageRole.ASSISTANT):
            continue
        role = "USER" if m.role == BrainMessageRole.USER else "ASSISTANT"
        text = (m.content or "").strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines[-(settings.brain_memory_recent_turns * 2):])


_EXTRACTION_SYSTEM = (
    "You extract durable, reusable memory from a SUPERVOID Brain conversation. "
    "Return STRICT JSON: {\"candidates\": [ ... ]}. Each candidate has: kind "
    "(one of fact, preference, procedure, decision, commitment, "
    "unresolved_question, task_suggestion), content (one concise sentence), "
    "topic_key (short stable slug), confidence (0..1), risk (low|medium|high), "
    "scope_hint (member|project|studio|conversation), touches_canon (bool), "
    "grants_permission (bool), is_decision (bool). RULES: (1) Ignore casual "
    "chit-chat — return an empty list when nothing durable was said. (2) NEVER "
    "assert canon, rights, or production-status facts as memory; set "
    "touches_canon=true for any such claim so a human can approve it. (3) Set "
    "grants_permission=true for anything about roles, access or permissions. "
    "(4) A user's stated preference is scope_hint=member about themselves."
)


def _extract_candidates(
    session: Session, conversation, messages: list[BrainMessage]
) -> list[MemoryCandidate]:
    """Ask the model for candidate memory. Best-effort: returns [] on any error,
    an unsupported provider, or a non-conforming response (so the turn is never
    dead-lettered, and dry-run/offline simply proposes nothing)."""
    if not settings.brain_memory_analysis_enabled:
        return []
    transcript = _recent_transcript(messages)
    if not transcript:
        return []
    try:
        import json

        from app.services.ai.providers import get_provider
        from app.services.ai.providers.base import ChatMessage

        provider = get_provider()
        model = settings.brain_memory_analysis_model or settings.ai_model
        msgs = [
            ChatMessage(role="system", content=_EXTRACTION_SYSTEM),
            ChatMessage(role="user", content=f"Conversation:\n{transcript}"),
        ]
        result = provider.chat(msgs, model=model, temperature=0.0)
        raw = (getattr(result, "content", "") or "").strip()
        if not raw:
            return []
        data = json.loads(raw)
        return _parse_candidates(data)
    except Exception:  # noqa: BLE001 — extraction is best-effort, never fatal
        return []


def _parse_candidates(data: object) -> list[MemoryCandidate]:
    """Coerce a parsed model payload into validated candidates (lenient on
    optional fields, strict on the kind enum)."""
    items = data.get("candidates") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out: list[MemoryCandidate] = []
    valid = {k.value for k in BrainMemoryKind}
    for entry in items:
        if not isinstance(entry, dict):
            continue
        kind_raw = str(entry.get("kind", "")).lower()
        if kind_raw not in valid:
            continue
        content = str(entry.get("content", "")).strip()
        if not content:
            continue
        conf = entry.get("confidence")
        try:
            conf = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf = None
        out.append(
            MemoryCandidate(
                kind=BrainMemoryKind(kind_raw),
                content=content,
                confidence=conf,
                topic_key=(str(entry["topic_key"]).strip() if entry.get("topic_key") else None),
                scope_hint=str(entry.get("scope_hint", "conversation")).lower(),
                risk=str(entry.get("risk", "low")).lower(),
                touches_canon=bool(entry.get("touches_canon", False)),
                grants_permission=bool(entry.get("grants_permission", False)),
                is_decision=bool(entry.get("is_decision", False)),
                subject=(str(entry["subject"]) if entry.get("subject") else None),
                rationale=(str(entry["rationale"]) if entry.get("rationale") else None),
                alternatives=entry.get("alternatives") or [],
                affected_entities=entry.get("affected_entities") or [],
            )
        )
    return out


# === orchestration =========================================================
def analyze_turn(session: Session, event) -> dict:
    """Process one ``conversation.turn_completed`` event: load the turn, extract
    candidates, and promote each under the rules. Adds + flushes within the
    consumer's savepoint (the consumer commits)."""
    if not settings.brain_memory_analysis_enabled:
        return {"action": "disabled"}
    message = session.get(BrainMessage, event.aggregate_id)
    if message is None:
        return {"action": "skipped", "reason": "message_gone"}
    conversation = brain.get_conversation(session, message.conversation_id)
    if conversation is None:
        return {"action": "skipped", "reason": "conversation_gone"}

    messages = brain.list_messages(
        session, conversation.id, limit=settings.brain_memory_recent_turns * 4
    )
    candidates = _extract_candidates(session, conversation, messages)
    cap = settings.brain_memory_max_candidates_per_turn
    results = [
        promote_candidate(
            session, conversation=conversation, candidate=cand,
            source_message_id=message.id, source_event_id=event.id,
        )
        for cand in candidates[:cap]
    ]
    return {"candidates": len(candidates), "promoted": len(results), "results": results}
