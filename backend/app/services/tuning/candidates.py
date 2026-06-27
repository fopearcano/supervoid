"""Dataset candidate collection + review workflow (Prompt 18).

Only EXPLICITLY approved examples are ever exported. A candidate is sanitised on
the way in (see ``sanitize``); content that must be excluded outright (unapproved
private contracts, un-anonymised member data) is rejected with a clear reason.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from sqlmodel import Session, func, select

from app.models import TuningExample
from app.models.base import utcnow
from app.models.enums import (
    TuningCandidateStatus,
    TuningExampleKind,
    TuningSourceType,
)
from app.services.tuning.errors import TuningExclusion
from app.services.tuning.sanitize import sanitize_example

_APPROVAL_BEHAVIOURS = {"none", "proposal", "approval_required"}
_RETRIEVAL_EXPECTATIONS = {"unnecessary", "required", "n_a"}


def _content_hash(messages: list, target: str) -> str:
    blob = json.dumps({"m": messages, "t": target}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def propose_example(
    session: Session,
    *,
    kind: TuningExampleKind,
    messages: list,
    target_output: str,
    created_by_id: Optional[str] = None,
    source_type: TuningSourceType = TuningSourceType.MANUAL,
    source_id: Optional[str] = None,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    task_category: str = "general",
    tool_calls: Optional[list] = None,
    expected_tools: Optional[list] = None,
    forbidden_tools: Optional[list] = None,
    approval_behaviour: str = "none",
    retrieval_expectation: str = "n_a",
    refusal: bool = False,
    rationale: str = "",
    anonymised: bool = False,
    allow_contract: bool = False,
) -> TuningExample:
    """Sanitise + record a PENDING candidate. Raises ``TuningExclusion`` when the
    content must be excluded outright (so the caller maps it to a 4xx)."""
    if approval_behaviour not in _APPROVAL_BEHAVIOURS:
        raise ValueError(f"approval_behaviour must be one of {_APPROVAL_BEHAVIOURS}")
    if retrieval_expectation not in _RETRIEVAL_EXPECTATIONS:
        raise ValueError(f"retrieval_expectation must be one of {_RETRIEVAL_EXPECTATIONS}")
    if not messages or not isinstance(messages, list):
        raise ValueError("messages must be a non-empty list of {role, content}")
    if not (target_output or "").strip():
        raise ValueError("target_output is required (the behaviour to teach)")

    result = sanitize_example(
        messages, target_output, allow_contract=allow_contract, anonymised=anonymised
    )
    if not result.ok:
        raise TuningExclusion(result.blocked_reasons)

    example = TuningExample(
        kind=kind,
        status=TuningCandidateStatus.PENDING,
        source_type=source_type,
        source_id=source_id,
        work_id=work_id,
        story_world_id=story_world_id,
        task_category=task_category or "general",
        messages=result.cleaned_messages,
        target_output=result.cleaned_target,
        tool_calls=tool_calls or [],
        expected_tools=expected_tools or [],
        forbidden_tools=forbidden_tools or [],
        approval_behaviour=approval_behaviour,
        retrieval_expectation=retrieval_expectation,
        refusal=bool(refusal),
        rationale=rationale or "",
        anonymised=bool(anonymised),
        contains_sensitive=result.contains_sensitive,
        redactions=result.redactions,
        sanitization_notes=result.notes,
        content_hash=_content_hash(result.cleaned_messages, result.cleaned_target),
        created_by_id=created_by_id,
    )
    session.add(example)
    session.flush()
    return example


def get_example(session: Session, example_id: str) -> Optional[TuningExample]:
    return session.get(TuningExample, example_id)


def list_examples(
    session: Session,
    *,
    status: Optional[TuningCandidateStatus] = None,
    kind: Optional[TuningExampleKind] = None,
    work_id: Optional[str] = None,
    dataset_version: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TuningExample]:
    stmt = select(TuningExample)
    if status is not None:
        stmt = stmt.where(TuningExample.status == status)
    if kind is not None:
        stmt = stmt.where(TuningExample.kind == kind)
    if work_id is not None:
        stmt = stmt.where(TuningExample.work_id == work_id)
    if dataset_version is not None:
        stmt = stmt.where(TuningExample.dataset_version == dataset_version)
    stmt = stmt.order_by(TuningExample.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())


def approve_example(
    session: Session, example: TuningExample, *, reviewer_id: Optional[str] = None,
    note: Optional[str] = None,
) -> TuningExample:
    """Approve a PENDING/REJECTED candidate for inclusion. An already-EXPORTED
    example is frozen (its dataset version is immutable)."""
    if example.status == TuningCandidateStatus.EXPORTED:
        raise ValueError("Exported examples are frozen; create a new candidate.")
    example.status = TuningCandidateStatus.APPROVED
    example.reviewed_by_id = reviewer_id
    example.reviewed_at = utcnow()
    example.review_note = note
    session.add(example)
    session.flush()
    return example


def reject_example(
    session: Session, example: TuningExample, *, reviewer_id: Optional[str] = None,
    note: Optional[str] = None,
) -> TuningExample:
    if example.status == TuningCandidateStatus.EXPORTED:
        raise ValueError("Exported examples are frozen; cannot reject.")
    example.status = TuningCandidateStatus.REJECTED
    example.reviewed_by_id = reviewer_id
    example.reviewed_at = utcnow()
    example.review_note = note
    session.add(example)
    session.flush()
    return example


def counts_by_status(session: Session) -> dict:
    rows = session.exec(
        select(TuningExample.status, func.count(TuningExample.id)).group_by(TuningExample.status)
    ).all()
    return {getattr(s, "value", s): int(n) for s, n in rows}
