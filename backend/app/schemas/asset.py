from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    AssetApprovalStatus,
    AssetLinkTargetType,
    AssetType,
    AssetVisibility,
    CanonState,
)
from app.schemas._common import TimestampedRead


# --- Asset -----------------------------------------------------------------


class AssetCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    asset_type: AssetType = AssetType.IMAGE
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    canon_status: CanonState = CanonState.UNDECIDED
    visibility: AssetVisibility = AssetVisibility.PRIVATE
    owner_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class AssetUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    asset_type: Optional[AssetType] = None
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    canon_status: Optional[CanonState] = None
    visibility: Optional[AssetVisibility] = None
    owner_id: Optional[str] = None
    tags: Optional[list[str]] = None
    description: Optional[str] = None


class AssetRead(TimestampedRead):
    title: str
    asset_type: AssetType
    work_id: Optional[str]
    story_world_id: Optional[str]
    canon_status: CanonState
    visibility: AssetVisibility
    owner_id: Optional[str]
    owner_name: Optional[str] = None
    tags: list[str]
    description: Optional[str]
    current_version_id: Optional[str]
    version_count: int = 0


# --- Asset version ---------------------------------------------------------


class AssetVersionCreate(BaseModel):
    """Create a metadata-only (placeholder) version — no bytes. Real bytes are
    added via the multipart upload endpoint."""

    mime_type: str = Field(default="application/octet-stream", max_length=160)
    width: Optional[int] = Field(default=None, ge=0)
    height: Optional[int] = Field(default=None, ge=0)
    duration_seconds: Optional[float] = Field(default=None, ge=0)
    technical_metadata: dict = Field(default_factory=dict)
    notes: Optional[str] = None


class AssetVersionRead(TimestampedRead):
    asset_id: str
    version_number: int
    storage_key: str
    mime_type: str
    size_bytes: int
    checksum: Optional[str]
    width: Optional[int]
    height: Optional[int]
    duration_seconds: Optional[float]
    creator_id: Optional[str]
    creator_name: Optional[str] = None
    approval_status: AssetApprovalStatus
    superseded_by_id: Optional[str]
    technical_metadata: dict
    notes: Optional[str]
    is_placeholder: bool = False
    is_current: bool = False
    has_provenance: bool = False


class AssetApprovalUpdate(BaseModel):
    approval_status: AssetApprovalStatus


class AssetDetail(AssetRead):
    versions: list[AssetVersionRead] = Field(default_factory=list)
    current_version: Optional[AssetVersionRead] = None
    link_count: int = 0
    licence_count: int = 0


# --- Duplicate detection ---------------------------------------------------


class DuplicateMatch(BaseModel):
    checksum: str
    matches: list[AssetVersionRead] = Field(default_factory=list)


# --- Asset link ------------------------------------------------------------


class AssetLinkCreate(BaseModel):
    target_type: AssetLinkTargetType
    target_id: str
    asset_version_id: Optional[str] = None
    role: Optional[str] = Field(default=None, max_length=80)
    note: Optional[str] = None


class AssetLinkRead(TimestampedRead):
    asset_id: str
    asset_version_id: Optional[str]
    target_type: AssetLinkTargetType
    target_id: str
    role: Optional[str]
    note: Optional[str]
