from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import LicenceReviewState, LicenceType

if TYPE_CHECKING:
    from app.models.asset import Asset


class LicenceRecord(BaseEntity, table=True):
    """The rights basis for using an asset — who holds the rights, under what
    licence, where, for what, and until when. Drives licence-expiry warnings."""

    __tablename__ = "licence_records"

    asset_id: str = Field(foreign_key="assets.id", index=True)

    rights_holder: Optional[str] = Field(default=None, max_length=300)
    licence_type: LicenceType = Field(default=LicenceType.PROPRIETARY, index=True)
    source: Optional[str] = Field(default=None, max_length=300)
    territory: Optional[str] = Field(default=None, max_length=200)
    permitted_uses: Optional[str] = Field(default=None)
    attribution_requirements: Optional[str] = Field(default=None)
    expiration_date: Optional[date] = Field(default=None, index=True)
    # Storage key of the licence evidence file (contract scan, receipt, …).
    evidence_storage_key: Optional[str] = Field(default=None, max_length=400)
    review_state: LicenceReviewState = Field(
        default=LicenceReviewState.NOT_REVIEWED, index=True
    )
    notes: Optional[str] = Field(default=None)

    asset: "Asset" = Relationship(back_populates="licences")
