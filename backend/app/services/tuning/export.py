"""Versioned JSONL export + train/validation split (Prompt 18).

Only APPROVED, not-yet-exported examples are exported. The split is **by project
and task category** (each project/category group contributes to both train and
validation, deterministically), so neither split is dominated by one project and
no group leaks entirely into one side. Output is plain JSONL — a portable SFT
chat format — plus a manifest of what was included.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.config import settings
from app.models import TuningDataset, TuningExample
from app.models.base import utcnow
from app.models.enums import TuningCandidateStatus, TuningDatasetStatus


def split_by_project_and_category(
    examples: list[TuningExample], val_fraction: float
) -> tuple[list[TuningExample], list[TuningExample]]:
    """Deterministic per-(project, category) split. Each group with ≥2 items
    contributes at least one example to each side; single-item groups go to train."""
    groups: dict[tuple, list[TuningExample]] = defaultdict(list)
    for ex in examples:
        groups[(ex.work_id or "_studio", ex.task_category or "general")].append(ex)

    train: list[TuningExample] = []
    val: list[TuningExample] = []
    for key in sorted(groups.keys()):
        items = sorted(groups[key], key=lambda e: e.id)
        n = len(items)
        if val_fraction <= 0 or n < 2:
            k = 0
        else:
            k = max(1, min(round(n * val_fraction), n - 1))
        # The last k (by id) become validation — stable across runs.
        train.extend(items[: n - k])
        val.extend(items[n - k:])
    return train, val


def _jsonl_record(example: TuningExample, split: str) -> dict:
    """A portable SFT chat record: the input messages with the gold assistant turn
    appended, plus behaviour metadata. No chain-of-thought, no secrets (already
    sanitised on the way in)."""
    messages = [dict(m) for m in (example.messages or [])]
    messages.append({"role": "assistant", "content": example.target_output})
    return {
        "messages": messages,
        "kind": getattr(example.kind, "value", example.kind),
        "task_category": example.task_category,
        "project": example.work_id,
        "expected_tools": example.expected_tools,
        "forbidden_tools": example.forbidden_tools,
        "tool_calls": example.tool_calls,
        "approval": example.approval_behaviour,
        "retrieval": example.retrieval_expectation,
        "refusal": example.refusal,
        "split": split,
        "id": example.id,
    }


def _write_jsonl(path: Path, records: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records]
    text = "\n".join(lines) + ("\n" if lines else "")
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest(train: list[TuningExample], val: list[TuningExample]) -> dict:
    def tally(items, attr):
        out: dict = defaultdict(int)
        for e in items:
            out[getattr(getattr(e, attr), "value", getattr(e, attr)) or "_none"] += 1
        return dict(out)

    allitems = train + val
    return {
        "by_kind": tally(allitems, "kind"),
        "by_project": _count(allitems, lambda e: e.work_id or "_studio"),
        "by_category": _count(allitems, lambda e: e.task_category),
        "by_split": {"train": len(train), "val": len(val)},
        "sensitive_anonymised": sum(1 for e in allitems if e.contains_sensitive),
    }


def _count(items, keyfn) -> dict:
    out: dict = defaultdict(int)
    for e in items:
        out[keyfn(e) or "_none"] += 1
    return dict(out)


def export_dataset(
    session: Session,
    *,
    version: str,
    description: Optional[str] = None,
    created_by_id: Optional[str] = None,
    val_fraction: Optional[float] = None,
    base_dir: Optional[Path] = None,
) -> TuningDataset:
    """Export all APPROVED, not-yet-exported examples to versioned train/val JSONL.

    Refuses to overwrite an existing version or to export fewer than
    ``tuning_min_examples`` examples. Marks every exported example EXPORTED with
    its dataset version + split (freezing it)."""
    version = (version or "").strip()
    if not version:
        raise ValueError("A dataset version is required.")
    if session.exec(select(TuningDataset).where(TuningDataset.version == version)).first():
        raise ValueError(f"Dataset version '{version}' already exists.")

    val_fraction = settings.tuning_val_fraction if val_fraction is None else val_fraction
    examples = list(
        session.exec(
            select(TuningExample).where(
                TuningExample.status == TuningCandidateStatus.APPROVED,
                TuningExample.dataset_version.is_(None),
            )
        ).all()
    )
    if len(examples) < settings.tuning_min_examples:
        raise ValueError(
            f"Need at least {settings.tuning_min_examples} approved examples to export; "
            f"have {len(examples)}."
        )

    train, val = split_by_project_and_category(examples, val_fraction)

    root = (base_dir or (Path(settings.storage_path) / settings.tuning_export_subdir)) / version
    train_hash = _write_jsonl(root / "train.jsonl", [_jsonl_record(e, "train") for e in train])
    val_hash = _write_jsonl(root / "val.jsonl", [_jsonl_record(e, "val") for e in val])
    checksum = hashlib.sha256(f"{train_hash}:{val_hash}".encode("utf-8")).hexdigest()

    now = utcnow()
    for e in train:
        e.status = TuningCandidateStatus.EXPORTED
        e.dataset_version = version
        e.split = "train"
        e.reviewed_at = e.reviewed_at or now
        session.add(e)
    for e in val:
        e.status = TuningCandidateStatus.EXPORTED
        e.dataset_version = version
        e.split = "val"
        e.reviewed_at = e.reviewed_at or now
        session.add(e)

    dataset = TuningDataset(
        version=version,
        description=description,
        status=TuningDatasetStatus.EXPORTED.value,
        example_count=len(examples),
        train_count=len(train),
        val_count=len(val),
        split_strategy="project+category",
        val_fraction=val_fraction,
        train_path=str(root / "train.jsonl"),
        val_path=str(root / "val.jsonl"),
        checksum=checksum,
        manifest=_manifest(train, val),
        created_by_id=created_by_id,
    )
    session.add(dataset)
    session.flush()
    return dataset


def get_dataset(session: Session, dataset_id: str) -> Optional[TuningDataset]:
    return session.get(TuningDataset, dataset_id)


def get_dataset_by_version(session: Session, version: str) -> Optional[TuningDataset]:
    return session.exec(select(TuningDataset).where(TuningDataset.version == version)).first()


def list_datasets(session: Session, *, limit: int = 100, offset: int = 0) -> list[TuningDataset]:
    stmt = select(TuningDataset).order_by(TuningDataset.created_at.desc()).offset(offset).limit(limit)
    return list(session.exec(stmt).all())
