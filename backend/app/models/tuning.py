"""Optional fine-tuning data pipeline (Prompt 18).

PREPARED, not auto-run. Nothing here trains or deploys a model automatically.

* ``TuningExample`` — a candidate training record. The goal is to teach
  BEHAVIOUR (strong/corrected responses, correct tool choices, correct refusals,
  good plans, structured proposals, approval gating, when retrieval is / is not
  needed) — NEVER current project facts. Every example is sanitised on the way in
  (chain-of-thought stripped; secrets / private member data / unapproved private
  contracts excluded) and only an EXPLICITLY approved example is ever exported.
* ``TuningDataset`` — a versioned export (train/val JSONL split by project + task
  category) with a manifest of what was included and excluded.
* ``TuningAdapter`` — the adapter registry: base model, dataset version, training
  parameters, licence, project-evaluation results and deployment status. An
  adapter is deployed only when it beats the base on the project evaluation
  without weakening permissions or approval behaviour; rollback returns to base.

No raw weights or binary artefacts are stored in the database — only metadata and
a reference (``artifact_ref``) to where an adapter would live on the GPU host.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field

from app.models.base import BaseEntity, utcnow
from app.models.enums import (
    AdapterStatus,
    TuningCandidateStatus,
    TuningExampleKind,
    TuningSourceType,
)


class TuningExample(BaseEntity, table=True):
    """One candidate fine-tuning example (behaviour, not facts).

    ``messages`` is the input chat context; ``target_output`` is the gold
    assistant turn to learn. ``contains_sensitive`` records that the sanitiser
    found (and ``redactions`` lists) excluded content; such an example is only
    admissible when explicitly anonymised."""

    __tablename__ = "tuning_examples"
    __table_args__ = (
        Index("ix_tuning_examples_status_kind", "status", "kind"),
        Index("ix_tuning_examples_dataset", "dataset_version", "split"),
        Index("ix_tuning_examples_project_category", "work_id", "task_category"),
    )

    kind: TuningExampleKind = Field(index=True)
    status: TuningCandidateStatus = Field(default=TuningCandidateStatus.PENDING, index=True)

    # Provenance (kept as plain ids; the example is decoupled from live records).
    source_type: TuningSourceType = Field(default=TuningSourceType.MANUAL, index=True)
    source_id: Optional[str] = Field(default=None, max_length=64, index=True)

    # Split keys: which project + task category this example belongs to.
    work_id: Optional[str] = Field(default=None, index=True)
    story_world_id: Optional[str] = Field(default=None)
    task_category: str = Field(default="general", max_length=60, index=True)

    # The behaviour to teach.
    messages: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    target_output: str = Field(default="")
    tool_calls: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    expected_tools: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    forbidden_tools: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    approval_behaviour: str = Field(default="none", max_length=30)   # none|proposal|approval_required
    retrieval_expectation: str = Field(default="n_a", max_length=20)  # unnecessary|required|n_a
    refusal: bool = Field(default=False)
    rationale: str = Field(default="", max_length=1000)

    # Safety / sanitisation record.
    anonymised: bool = Field(default=False)
    contains_sensitive: bool = Field(default=False, index=True)
    redactions: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    sanitization_notes: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    content_hash: Optional[str] = Field(default=None, max_length=64, index=True)

    # Review trail.
    created_by_id: Optional[str] = Field(default=None, index=True)
    reviewed_by_id: Optional[str] = Field(default=None)
    reviewed_at: Optional[datetime] = Field(default=None)
    review_note: Optional[str] = Field(default=None, max_length=500)

    # Export linkage (set when included in a dataset version).
    dataset_version: Optional[str] = Field(default=None, max_length=40, index=True)
    split: Optional[str] = Field(default=None, max_length=10)  # train|val


class TuningDataset(BaseEntity, table=True):
    """A versioned, exported dataset (train/val JSONL split by project + category)."""

    __tablename__ = "tuning_datasets"
    __table_args__ = (
        Index("ix_tuning_datasets_version", "version", unique=True),
    )

    version: str = Field(max_length=40)
    description: Optional[str] = Field(default=None, max_length=500)
    status: str = Field(default="exported", max_length=20, index=True)

    example_count: int = Field(default=0, ge=0)
    train_count: int = Field(default=0, ge=0)
    val_count: int = Field(default=0, ge=0)
    split_strategy: str = Field(default="project+category", max_length=40)
    val_fraction: float = Field(default=0.2)

    train_path: Optional[str] = Field(default=None, max_length=300)
    val_path: Optional[str] = Field(default=None, max_length=300)
    checksum: Optional[str] = Field(default=None, max_length=64)
    manifest: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    created_by_id: Optional[str] = Field(default=None, index=True)


class TuningAdapter(BaseEntity, table=True):
    """A LoRA/PEFT adapter in the registry.

    The registry records everything a deployment decision needs: the base model,
    the dataset version it was trained on, the training parameters, the licence,
    the project-evaluation results, and the deployment status. The gate fields
    (``beats_base`` / ``permissions_preserved`` / ``approval_preserved``) capture
    the deploy decision; only one adapter is ever DEPLOYED at a time."""

    __tablename__ = "tuning_adapters"
    __table_args__ = (
        Index("ix_tuning_adapters_name", "name"),
    )

    name: str = Field(max_length=120)
    base_model: str = Field(max_length=160)
    dataset_version: Optional[str] = Field(default=None, max_length=40, index=True)

    training_parameters: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    licence: str = Field(default="proprietary", max_length=80)
    artifact_ref: Optional[str] = Field(default=None, max_length=300)  # path/URI on the GPU host

    status: AdapterStatus = Field(default=AdapterStatus.REGISTERED, index=True)
    evaluation_results: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    # Deploy gate verdict (computed from the project evaluation).
    beats_base: Optional[bool] = Field(default=None)
    permissions_preserved: Optional[bool] = Field(default=None)
    approval_preserved: Optional[bool] = Field(default=None)
    deploy_blocked_reason: Optional[str] = Field(default=None, max_length=300)

    evaluated_at: Optional[datetime] = Field(default=None)
    approved_at: Optional[datetime] = Field(default=None)
    deployed_at: Optional[datetime] = Field(default=None)
    rolled_back_at: Optional[datetime] = Field(default=None)

    created_by_id: Optional[str] = Field(default=None, index=True)
    approved_by_id: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None, max_length=1000)
