"""Schemas for the optional fine-tuning data pipeline (Prompt 18)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    AdapterStatus,
    TuningCandidateStatus,
    TuningExampleKind,
    TuningSourceType,
)


# --- candidates ------------------------------------------------------------
class TuningExampleCreate(BaseModel):
    kind: TuningExampleKind
    messages: list[dict] = Field(min_length=1)
    target_output: str = Field(min_length=1)
    source_type: TuningSourceType = TuningSourceType.MANUAL
    source_id: Optional[str] = None
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    task_category: str = "general"
    tool_calls: list[Any] = Field(default_factory=list)
    expected_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    approval_behaviour: str = "none"          # none|proposal|approval_required
    retrieval_expectation: str = "n_a"        # unnecessary|required|n_a
    refusal: bool = False
    rationale: str = ""
    anonymised: bool = False
    allow_contract: bool = False              # only honoured together with anonymised


class TuningReviewRequest(BaseModel):
    note: Optional[str] = None


class TuningExampleRead(BaseModel):
    id: str
    kind: TuningExampleKind
    status: TuningCandidateStatus
    source_type: TuningSourceType
    source_id: Optional[str] = None
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    task_category: str
    messages: list[Any]
    target_output: str
    tool_calls: list[Any]
    expected_tools: list[Any]
    forbidden_tools: list[Any]
    approval_behaviour: str
    retrieval_expectation: str
    refusal: bool
    rationale: str
    anonymised: bool
    contains_sensitive: bool
    redactions: list[Any]
    sanitization_notes: list[Any]
    dataset_version: Optional[str] = None
    split: Optional[str] = None
    created_by_id: Optional[str] = None
    reviewed_by_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    created_at: datetime


# --- datasets --------------------------------------------------------------
class DatasetExportRequest(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    description: Optional[str] = None
    val_fraction: Optional[float] = Field(default=None, ge=0.0, le=0.9)


class TuningDatasetRead(BaseModel):
    id: str
    version: str
    description: Optional[str] = None
    status: str
    example_count: int
    train_count: int
    val_count: int
    split_strategy: str
    val_fraction: float
    train_path: Optional[str] = None
    val_path: Optional[str] = None
    checksum: Optional[str] = None
    manifest: dict
    created_by_id: Optional[str] = None
    created_at: datetime


# --- adapters --------------------------------------------------------------
class AdapterRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_model: Optional[str] = None
    dataset_version: Optional[str] = None
    training_parameters: Optional[dict] = None
    licence: str = "proprietary"
    artifact_ref: Optional[str] = None
    notes: Optional[str] = None


class AdapterEvaluateRequest(BaseModel):
    """Run the project corpus against the configured provider, or record an
    externally-produced base-vs-adapter comparison directly."""
    base_aggregate: Optional[dict] = None
    adapter_aggregate: Optional[dict] = None
    base_model_name: Optional[str] = None
    adapter_model_name: Optional[str] = None


class AdapterActionRequest(BaseModel):
    reason: Optional[str] = None


class TuningAdapterRead(BaseModel):
    id: str
    name: str
    base_model: str
    dataset_version: Optional[str] = None
    training_parameters: dict
    licence: str
    artifact_ref: Optional[str] = None
    status: AdapterStatus
    evaluation_results: dict
    beats_base: Optional[bool] = None
    permissions_preserved: Optional[bool] = None
    approval_preserved: Optional[bool] = None
    deploy_blocked_reason: Optional[str] = None
    evaluated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    deployed_at: Optional[datetime] = None
    rolled_back_at: Optional[datetime] = None
    created_by_id: Optional[str] = None
    approved_by_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
