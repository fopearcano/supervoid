from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import CommercialUseReviewStatus, ProvenanceKind

if TYPE_CHECKING:
    from app.models.asset import AssetVersion
    from app.models.user import User


class ProvenanceRecord(BaseEntity, table=True):
    """How an asset version came to be — the basis for AI-disclosure and
    commercial-use review. Captures whether it was human-made, AI-assisted,
    AI-generated or mixed, and (for AI) the model, prompts, seed and settings."""

    __tablename__ = "provenance_records"

    asset_version_id: str = Field(foreign_key="asset_versions.id", index=True)

    kind: ProvenanceKind = Field(default=ProvenanceKind.HUMAN_CREATED, index=True)

    # The generating model / provider (null for purely human work). Named to
    # avoid Pydantic's protected ``model_`` namespace.
    provider: Optional[str] = Field(default=None, max_length=160)
    base_model: Optional[str] = Field(default=None, max_length=200)
    base_model_version: Optional[str] = Field(default=None, max_length=120)
    # LoRA / adapter identifiers (free text or comma-separated list).
    adapter_identifiers: Optional[str] = Field(default=None)

    prompt: Optional[str] = Field(default=None)
    negative_prompt: Optional[str] = Field(default=None)
    seed: Optional[int] = Field(default=None)
    sampler: Optional[str] = Field(default=None, max_length=120)
    # Sampler / generation settings (steps, cfg scale, scheduler, …).
    settings: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    # Source references and ControlNet / reference inputs (paths, urls, ids).
    source_references: Optional[str] = Field(default=None)
    controlnet_inputs: Optional[str] = Field(default=None)
    generating_workflow: Optional[str] = Field(default=None, max_length=300)

    human_modifications: Optional[str] = Field(default=None)
    generation_date: Optional[datetime] = Field(default=None)
    responsible_user_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    commercial_use_review: CommercialUseReviewStatus = Field(
        default=CommercialUseReviewStatus.NOT_REVIEWED, index=True
    )

    asset_version: "AssetVersion" = Relationship(back_populates="provenance")
    responsible_user: Optional["User"] = Relationship()

    @property
    def responsible_user_name(self) -> Optional[str]:
        return (
            self.responsible_user.full_name
            if self.responsible_user is not None
            else None
        )
