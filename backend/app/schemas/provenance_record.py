from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import CommercialUseReviewStatus, ProvenanceKind
from app.schemas._common import TimestampedRead


class ProvenanceWrite(BaseModel):
    """Create or replace the provenance of an asset version."""

    kind: ProvenanceKind = ProvenanceKind.HUMAN_CREATED
    provider: Optional[str] = Field(default=None, max_length=160)
    base_model: Optional[str] = Field(default=None, max_length=200)
    base_model_version: Optional[str] = Field(default=None, max_length=120)
    adapter_identifiers: Optional[str] = None
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    seed: Optional[int] = None
    sampler: Optional[str] = Field(default=None, max_length=120)
    settings: dict = Field(default_factory=dict)
    source_references: Optional[str] = None
    controlnet_inputs: Optional[str] = None
    generating_workflow: Optional[str] = Field(default=None, max_length=300)
    human_modifications: Optional[str] = None
    generation_date: Optional[datetime] = None
    responsible_user_id: Optional[str] = None
    commercial_use_review: CommercialUseReviewStatus = (
        CommercialUseReviewStatus.NOT_REVIEWED
    )


class ProvenanceRead(TimestampedRead):
    asset_version_id: str
    kind: ProvenanceKind
    provider: Optional[str]
    base_model: Optional[str]
    base_model_version: Optional[str]
    adapter_identifiers: Optional[str]
    prompt: Optional[str]
    negative_prompt: Optional[str]
    seed: Optional[int]
    sampler: Optional[str]
    settings: dict
    source_references: Optional[str]
    controlnet_inputs: Optional[str]
    generating_workflow: Optional[str]
    human_modifications: Optional[str]
    generation_date: Optional[datetime]
    responsible_user_id: Optional[str]
    responsible_user_name: Optional[str] = None
    commercial_use_review: CommercialUseReviewStatus


class ProvenanceCompletenessRead(BaseModel):
    complete: bool
    missing: list[str]
    recommended: list[str]
