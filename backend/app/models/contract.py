from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import ContractStatus, RightsExclusivity

if TYPE_CHECKING:
    from app.models.author import Author
    from app.models.manuscript import Manuscript
    from app.models.work import Work


class Contract(BaseEntity, table=True):
    __tablename__ = "contracts"

    manuscript_id: str = Field(foreign_key="manuscripts.id", index=True)
    work_id: Optional[str] = Field(
        default=None, foreign_key="works.id", index=True
    )
    author_id: str = Field(foreign_key="authors.id", index=True)
    status: ContractStatus = Field(default=ContractStatus.DRAFT, index=True)
    advance_amount: Optional[Decimal] = Field(
        default=None,
        max_digits=12,
        decimal_places=2,
        ge=0,
    )
    royalty_rate: Optional[float] = Field(default=None, ge=0, le=1)
    currency: str = Field(default="USD", max_length=3)
    rights_territory: Optional[str] = Field(default=None, max_length=100, index=True)
    signed_at: Optional[datetime] = Field(default=None)
    expiration_date: Optional[date] = Field(default=None, index=True)
    terms: Optional[str] = Field(default=None)

    # --- depth (additive; existing rows stay valid) ---
    rights_holder: Optional[str] = Field(default=None, max_length=200)
    exclusivity: RightsExclusivity = Field(
        default=RightsExclusivity.UNSPECIFIED, index=True
    )
    # Term window.
    effective_date: Optional[date] = Field(default=None, index=True)
    term_start_date: Optional[date] = Field(default=None, index=True)
    term_end_date: Optional[date] = Field(default=None, index=True)
    # Option period.
    option_start_date: Optional[date] = Field(default=None)
    option_end_date: Optional[date] = Field(default=None, index=True)
    option_exercised: bool = Field(default=False)
    # Reversion & sublicensing.
    reversion_conditions: Optional[str] = Field(default=None)
    reversion_date: Optional[date] = Field(default=None, index=True)
    sublicensable: bool = Field(default=False)
    # Coverage beyond the single rights_territory.
    territory_coverage: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    language_coverage: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )

    manuscript: "Manuscript" = Relationship(back_populates="contracts")
    work: Optional["Work"] = Relationship(back_populates="contracts")
    author: "Author" = Relationship(back_populates="contracts")
