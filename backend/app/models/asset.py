from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import (
    AssetApprovalStatus,
    AssetLinkTargetType,
    AssetType,
    AssetVisibility,
    CanonState,
)

if TYPE_CHECKING:
    from app.models.licence_record import LicenceRecord
    from app.models.provenance_record import ProvenanceRecord
    from app.models.story_world import StoryWorld
    from app.models.user import User
    from app.models.work import Work


class Asset(BaseEntity, table=True):
    """A reusable, work-centred creative asset.

    Distinct from ``Attachment`` (a manuscript-scoped file record, kept for
    backward compatibility). An Asset is the durable identity for a piece of
    creative material — its bytes live in versioned ``AssetVersion`` rows, and
    it carries provenance and licensing. It is never exposed through the public
    reader; public media uses the curated public projection.
    """

    __tablename__ = "assets"

    title: str = Field(max_length=300, index=True)
    asset_type: AssetType = Field(default=AssetType.IMAGE, index=True)

    work_id: Optional[str] = Field(default=None, foreign_key="works.id", index=True)
    story_world_id: Optional[str] = Field(
        default=None, foreign_key="story_worlds.id", index=True
    )

    canon_status: CanonState = Field(default=CanonState.UNDECIDED, index=True)
    visibility: AssetVisibility = Field(default=AssetVisibility.PRIVATE, index=True)

    owner_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)

    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    description: Optional[str] = Field(default=None)

    # The active version. Stored as a plain id (no FK) to avoid a circular
    # constraint with asset_versions.asset_id; resolved by the service.
    current_version_id: Optional[str] = Field(default=None, index=True)

    work: Optional["Work"] = Relationship()
    story_world: Optional["StoryWorld"] = Relationship()
    owner: Optional["User"] = Relationship()
    versions: list["AssetVersion"] = Relationship(
        back_populates="asset",
        sa_relationship_kwargs={
            "foreign_keys": "[AssetVersion.asset_id]",
            "cascade": "all, delete-orphan",
        },
    )
    links: list["AssetLink"] = Relationship(
        back_populates="asset",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    licences: list["LicenceRecord"] = Relationship(
        back_populates="asset",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    @property
    def owner_name(self) -> Optional[str]:
        return self.owner.full_name if self.owner is not None else None

    @property
    def version_count(self) -> int:
        return len(self.versions)


class AssetVersion(BaseEntity, table=True):
    """One concrete revision of an Asset — the bytes plus their technical and
    review metadata."""

    __tablename__ = "asset_versions"

    asset_id: str = Field(foreign_key="assets.id", index=True)
    version_number: int = Field(default=1, index=True)

    storage_key: str = Field(max_length=400)
    mime_type: str = Field(default="application/octet-stream", max_length=160)
    size_bytes: int = Field(default=0, ge=0)
    checksum: Optional[str] = Field(default=None, max_length=64, index=True)

    width: Optional[int] = Field(default=None, ge=0)
    height: Optional[int] = Field(default=None, ge=0)
    duration_seconds: Optional[float] = Field(default=None, ge=0)

    creator_id: Optional[str] = Field(default=None, foreign_key="users.id", index=True)
    approval_status: AssetApprovalStatus = Field(
        default=AssetApprovalStatus.DRAFT, index=True
    )
    # The version that replaced this one (self-referential, set on promotion).
    superseded_by_id: Optional[str] = Field(
        default=None, foreign_key="asset_versions.id", index=True
    )
    technical_metadata: dict = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    notes: Optional[str] = Field(default=None)

    asset: "Asset" = Relationship(
        back_populates="versions",
        sa_relationship_kwargs={"foreign_keys": "[AssetVersion.asset_id]"},
    )
    creator: Optional["User"] = Relationship()
    provenance: Optional["ProvenanceRecord"] = Relationship(
        back_populates="asset_version",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )

    @property
    def creator_name(self) -> Optional[str]:
        return self.creator.full_name if self.creator is not None else None

    @property
    def is_placeholder(self) -> bool:
        return self.storage_key.startswith("placeholder:")


class AssetLink(BaseEntity, table=True):
    """A connection from an asset (optionally a specific version) to another
    entity — a character, location, page, panel, scene, shot, production task or
    public-reader record. Generic by design (target is type + id)."""

    __tablename__ = "asset_links"

    asset_id: str = Field(foreign_key="assets.id", index=True)
    asset_version_id: Optional[str] = Field(
        default=None, foreign_key="asset_versions.id", index=True
    )
    target_type: AssetLinkTargetType = Field(index=True)
    target_id: str = Field(index=True)
    role: Optional[str] = Field(default=None, max_length=80)
    note: Optional[str] = Field(default=None)

    asset: "Asset" = Relationship(back_populates="links")
    asset_version: Optional["AssetVersion"] = Relationship()
