"""The Memory Review inbox (Prompt 13).

Reviewer-facing actions over the durable memory the analysis job proposes:
``accept``, ``reject``, ``edit``, ``merge``, ``supersede`` and ``expire``.

Two invariants run through every action:

* **Never overwrite.** A correction (edit / supersede / merge) creates a NEW
  row that supersedes the old; the old row is retained as SUPERSEDED with its
  full provenance (source turn, original author, prior content). Only status
  transitions (accept / reject / expire) mutate a row in place.
* **Scoped access.** Studio memory is admin-only; project memory needs APPROVE
  on that Work / StoryWorld; member and conversation memory belong to their
  owner. A reviewer never sees or touches another project's or member's memory.

Accepting / superseding / expiring a *project*- or *studio*-scoped item emits a
``memory.*`` event so the compiled state recompiles and reflects the change.
Member / conversation memory never feeds compiled project/studio state, so those
actions emit nothing.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session

from app.models import BrainMemoryItem, PermissionScope, User, UserRole
from app.models.base import utcnow
from app.models.enums import BrainMemoryVerification, BrainScope
from app.services import brain, policy
from app.services.brain import memory as _memory


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _forbid(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# === access ================================================================
def can_review(session: Session, user: User, item: BrainMemoryItem) -> bool:
    """May this user action this memory item in the review inbox?"""
    if _is_admin(user):
        return True
    if item.scope == BrainScope.STUDIO:
        return False  # studio memory is admin-only
    if item.scope == BrainScope.PROJECT:
        return policy.can(
            session, user, PermissionScope.APPROVE,
            work_id=item.work_id, story_world_id=item.story_world_id,
        )
    if item.scope == BrainScope.MEMBER:
        return item.member_user_id == user.id
    if item.scope == BrainScope.CONVERSATION:
        conv = brain.get_conversation(session, item.conversation_id) if item.conversation_id else None
        return conv is not None and conv.owner_user_id == user.id
    return False


def can_view(session: Session, user: User, item: BrainMemoryItem) -> bool:
    """May this user *see* this item in the inbox (looser than review)?"""
    if _is_admin(user):
        return True
    if item.scope == BrainScope.STUDIO:
        return False
    if item.scope == BrainScope.PROJECT:
        return policy.can(
            session, user, PermissionScope.VIEW_PROJECT,
            work_id=item.work_id, story_world_id=item.story_world_id,
        )
    if item.scope == BrainScope.MEMBER:
        return item.member_user_id == user.id
    if item.scope == BrainScope.CONVERSATION:
        conv = brain.get_conversation(session, item.conversation_id) if item.conversation_id else None
        return conv is not None and conv.owner_user_id == user.id
    return False


def _ensure_can_review(session: Session, user: User, item: BrainMemoryItem) -> None:
    if not can_review(session, user, item):
        _forbid("Not permitted to review this memory item")


def load(session: Session, item_id: str) -> BrainMemoryItem:
    item = brain.get_memory(session, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return item


# === inbox listing =========================================================
def list_inbox(
    session: Session,
    user: User,
    *,
    scope: Optional[BrainScope] = None,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[BrainMemoryItem]:
    """The pending (UNVERIFIED) items this user may review, filtered to their
    access so nothing leaks across members or projects."""
    rows = brain.list_memory(
        session, scope=scope, work_id=work_id, story_world_id=story_world_id,
        verification=BrainMemoryVerification.UNVERIFIED, limit=(limit + offset) * 4,
    )
    visible = [r for r in rows if can_view(session, user, r)]
    return visible[offset:offset + limit]


# === provenance-preserving helpers =========================================
def _emit_memory_event(session: Session, user: User, item: BrainMemoryItem, event_type: str) -> None:
    """Invalidate compiled state for a project/studio memory change. Member /
    conversation memory has no compiled-state footprint, so it emits nothing."""
    if item.scope not in (BrainScope.PROJECT, BrainScope.STUDIO):
        return
    brain.emit(
        session, event_type=event_type, aggregate_type="brain_memory",
        aggregate_id=item.id, work_id=item.work_id, story_world_id=item.story_world_id,
        actor_id=user.id, changes={"verification": item.verification.value},
    )


def _stamp_review(item: BrainMemoryItem, user: User, note: Optional[str]) -> None:
    item.reviewed_by_id = user.id
    item.reviewed_at = utcnow()
    if note is not None:
        item.review_note = note


def _new_from(
    session: Session,
    base: BrainMemoryItem,
    *,
    content: str,
    structured_data: Optional[dict],
    confidence: Optional[float],
    topic_key: Optional[str],
    supersedes_id: str,
) -> BrainMemoryItem:
    """Create a successor item that supersedes ``base``-family, carrying the
    original provenance (source turn, original author). ``create_memory`` marks
    the ``supersedes_id`` target SUPERSEDED for us."""
    new = brain.create_memory(
        session,
        scope=base.scope,
        kind=base.kind,
        content=content,
        created_by_id=base.created_by_id,
        structured_data=structured_data if structured_data is not None else dict(base.structured_data or {}),
        confidence=confidence if confidence is not None else base.confidence,
        work_id=base.work_id,
        story_world_id=base.story_world_id,
        member_user_id=base.member_user_id,
        conversation_id=base.conversation_id,
        source_message_id=base.source_message_id,
        source_event_id=base.source_event_id,
        supersedes_id=supersedes_id,
    )
    new.topic_key = topic_key if topic_key is not None else base.topic_key
    new.risk_level = base.risk_level
    session.add(new)
    return new


# === actions ===============================================================
def accept(
    session: Session, user: User, item: BrainMemoryItem, *, note: Optional[str] = None
) -> BrainMemoryItem:
    """Promote a pending item to VERIFIED. A same-topic verified prior is
    superseded (never overwritten)."""
    _ensure_can_review(session, user, item)
    if item.verification != BrainMemoryVerification.UNVERIFIED:
        raise HTTPException(status_code=409, detail=f"Item is {item.verification.value}, not pending")
    priors = [
        p for p in _memory._verified_same_topic(
            session, scope=item.scope, work_id=item.work_id,
            story_world_id=item.story_world_id, member_user_id=item.member_user_id,
            topic_key=item.topic_key,
        )
        if p.id != item.id
    ]
    for prior in priors:
        prior.verification = BrainMemoryVerification.SUPERSEDED
        session.add(prior)
    if priors:
        item.supersedes_id = priors[0].id
    item.verification = BrainMemoryVerification.VERIFIED
    item.approved_by_id = user.id
    item.auto_accepted = False
    _stamp_review(item, user, note)
    session.add(item)
    session.flush()
    _emit_memory_event(session, user, item, brain.BrainEventType.MEMORY_VERIFIED)
    return item


def reject(
    session: Session, user: User, item: BrainMemoryItem, *, note: Optional[str] = None
) -> BrainMemoryItem:
    """Reject a pending item. It is excluded from compiled state and is never
    auto-resurrected as verified by the analysis job."""
    _ensure_can_review(session, user, item)
    if item.verification not in (
        BrainMemoryVerification.UNVERIFIED, BrainMemoryVerification.VERIFIED
    ):
        raise HTTPException(status_code=409, detail=f"Item is {item.verification.value}; cannot reject")
    was_verified = item.verification == BrainMemoryVerification.VERIFIED
    item.verification = BrainMemoryVerification.REJECTED
    item.approved_by_id = user.id
    _stamp_review(item, user, note)
    session.add(item)
    session.flush()
    if was_verified:  # a previously-live fact dropping out of state
        _emit_memory_event(session, user, item, brain.BrainEventType.MEMORY_SUPERSEDED)
    return item


def edit(
    session: Session, user: User, item: BrainMemoryItem, *,
    content: Optional[str] = None, structured_data: Optional[dict] = None,
    confidence: Optional[float] = None, topic_key: Optional[str] = None,
    note: Optional[str] = None,
) -> BrainMemoryItem:
    """Correct an item WITHOUT overwriting it: a new row supersedes the old,
    preserving the original's verification state and provenance."""
    _ensure_can_review(session, user, item)
    if item.verification in (
        BrainMemoryVerification.SUPERSEDED, BrainMemoryVerification.EXPIRED
    ):
        raise HTTPException(status_code=409, detail=f"Item is {item.verification.value}; cannot edit")
    new = _new_from(
        session, item, content=(content if content is not None else item.content),
        structured_data=structured_data, confidence=confidence, topic_key=topic_key,
        supersedes_id=item.id,
    )
    new.verification = item.verification  # editing a draft keeps it pending
    if new.verification == BrainMemoryVerification.VERIFIED:
        new.approved_by_id = user.id
    _stamp_review(new, user, note)
    session.add(new)
    session.flush()
    if new.verification == BrainMemoryVerification.VERIFIED:
        _emit_memory_event(session, user, new, brain.BrainEventType.MEMORY_VERIFIED)
    return new


def supersede(
    session: Session, user: User, item: BrainMemoryItem, *,
    content: str, structured_data: Optional[dict] = None,
    confidence: Optional[float] = None, topic_key: Optional[str] = None,
    note: Optional[str] = None,
) -> BrainMemoryItem:
    """Replace an item with a newer VERIFIED successor (the old becomes
    SUPERSEDED, provenance preserved)."""
    _ensure_can_review(session, user, item)
    if not (content or "").strip():
        raise HTTPException(status_code=400, detail="A superseding item needs content")
    if item.verification in (
        BrainMemoryVerification.SUPERSEDED, BrainMemoryVerification.EXPIRED,
        BrainMemoryVerification.REJECTED,
    ):
        raise HTTPException(status_code=409, detail=f"Item is {item.verification.value}; cannot supersede")
    new = _new_from(
        session, item, content=content, structured_data=structured_data,
        confidence=confidence, topic_key=topic_key, supersedes_id=item.id,
    )
    new.verification = BrainMemoryVerification.VERIFIED
    new.approved_by_id = user.id
    _stamp_review(new, user, note)
    session.add(new)
    session.flush()
    _emit_memory_event(session, user, new, brain.BrainEventType.MEMORY_VERIFIED)
    return new


def merge(
    session: Session, user: User, *, primary_id: str, source_ids: list[str],
    content: Optional[str] = None, note: Optional[str] = None,
) -> BrainMemoryItem:
    """Merge several same-scope items into one VERIFIED item that supersedes them
    all (every source retired, none overwritten; provenance recorded)."""
    primary = load(session, primary_id)
    sources = [load(session, sid) for sid in source_ids if sid != primary_id]
    members = [primary, *sources]
    if len(members) < 2:
        raise HTTPException(status_code=400, detail="Merge needs at least two distinct items")
    for other in sources:
        if (
            other.scope != primary.scope
            or other.work_id != primary.work_id
            or other.story_world_id != primary.story_world_id
            or other.member_user_id != primary.member_user_id
            or other.kind != primary.kind
        ):
            raise HTTPException(status_code=400, detail="Can only merge items of the same scope and kind")
    for member in members:
        _ensure_can_review(session, user, member)
        if member.verification in (
            BrainMemoryVerification.SUPERSEDED, BrainMemoryVerification.EXPIRED
        ):
            raise HTTPException(status_code=409, detail="Cannot merge a retired item")

    merged_content = (content or "").strip() or "\n".join(
        (m.content or "").strip() for m in members if (m.content or "").strip()
    )
    confidences = [m.confidence for m in members if m.confidence is not None]
    new = _new_from(
        session, primary, content=merged_content,
        structured_data={"merged_from": [m.id for m in members]},
        confidence=max(confidences) if confidences else None,
        topic_key=primary.topic_key, supersedes_id=primary.id,
    )
    for other in sources:  # primary already retired by create_memory(supersedes_id=)
        other.verification = BrainMemoryVerification.SUPERSEDED
        session.add(other)
    new.verification = BrainMemoryVerification.VERIFIED
    new.approved_by_id = user.id
    _stamp_review(new, user, note)
    session.add(new)
    session.flush()
    _emit_memory_event(session, user, new, brain.BrainEventType.MEMORY_VERIFIED)
    return new


def expire(
    session: Session, user: User, item: BrainMemoryItem, *, note: Optional[str] = None
) -> BrainMemoryItem:
    """Retire an item as EXPIRED (drops out of compiled state immediately)."""
    _ensure_can_review(session, user, item)
    if item.verification in (
        BrainMemoryVerification.SUPERSEDED, BrainMemoryVerification.EXPIRED
    ):
        raise HTTPException(status_code=409, detail=f"Item is already {item.verification.value}")
    was_verified = item.verification == BrainMemoryVerification.VERIFIED
    item.verification = BrainMemoryVerification.EXPIRED
    item.expires_at = utcnow()
    _stamp_review(item, user, note)
    session.add(item)
    session.flush()
    if was_verified:
        _emit_memory_event(session, user, item, brain.BrainEventType.MEMORY_EXPIRED)
    return item
