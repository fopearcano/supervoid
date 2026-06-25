"""Asset-library domain logic: versioning, checksum dedupe, promotion /
rollback, provenance-completeness checks and licence-expiry warnings.

Kept out of the routers so the rules are consistent and testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, func, select

from app.models import (
    Asset,
    AssetApprovalStatus,
    AssetVersion,
    LicenceRecord,
    LicenceReviewState,
    ProvenanceKind,
    ProvenanceRecord,
)


# --- versioning ------------------------------------------------------------


def next_version_number(session: Session, asset_id: str) -> int:
    current_max = session.exec(
        select(func.max(AssetVersion.version_number)).where(
            AssetVersion.asset_id == asset_id
        )
    ).one()
    return (current_max or 0) + 1


def find_versions_by_checksum(
    session: Session,
    checksum: str,
    *,
    asset_id: Optional[str] = None,
) -> list[AssetVersion]:
    """All versions whose bytes match ``checksum`` — the basis for duplicate
    detection (scoped to one asset, or library-wide when ``asset_id`` is None)."""
    if not checksum:
        return []
    stmt = select(AssetVersion).where(AssetVersion.checksum == checksum)
    if asset_id is not None:
        stmt = stmt.where(AssetVersion.asset_id == asset_id)
    return list(session.exec(stmt).all())


def set_current_version(
    session: Session,
    asset: Asset,
    version: AssetVersion,
) -> Asset:
    """Make ``version`` the asset's current version, superseding the previous
    current one. Used by both promotion and rollback. Caller commits."""
    previous_id = asset.current_version_id
    if previous_id and previous_id != version.id:
        previous = session.get(AssetVersion, previous_id)
        if previous is not None:
            previous.superseded_by_id = version.id
            if previous.approval_status == AssetApprovalStatus.APPROVED:
                previous.approval_status = AssetApprovalStatus.SUPERSEDED
            session.add(previous)
    # The new head is no longer superseded by anything.
    version.superseded_by_id = None
    asset.current_version_id = version.id
    session.add(version)
    session.add(asset)
    return asset


# --- provenance completeness ----------------------------------------------


@dataclass
class CompletenessReport:
    complete: bool
    missing: list[str] = field(default_factory=list)
    recommended: list[str] = field(default_factory=list)


# Required fields by provenance kind. ``responsible_user_id`` is always
# required: someone must own the disclosure.
_REQUIRED: dict[ProvenanceKind, tuple[str, ...]] = {
    ProvenanceKind.HUMAN_CREATED: ("responsible_user_id",),
    ProvenanceKind.AI_ASSISTED: (
        "responsible_user_id", "provider", "base_model", "prompt",
        "human_modifications",
    ),
    ProvenanceKind.AI_GENERATED: (
        "responsible_user_id", "provider", "base_model", "prompt",
        "generation_date",
    ),
    ProvenanceKind.MIXED: (
        "responsible_user_id", "provider", "base_model", "prompt",
        "human_modifications",
    ),
}

_RECOMMENDED: dict[ProvenanceKind, tuple[str, ...]] = {
    ProvenanceKind.AI_ASSISTED: ("seed", "settings", "negative_prompt"),
    ProvenanceKind.AI_GENERATED: ("seed", "settings", "negative_prompt", "sampler"),
    ProvenanceKind.MIXED: ("seed", "settings"),
}


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, dict):
        return len(value) == 0
    return False


def provenance_completeness(prov: ProvenanceRecord) -> CompletenessReport:
    """Check that a provenance record carries enough detail for its kind —
    this is the AI-disclosure gate, not an approval (humans still approve)."""
    missing = [
        f for f in _REQUIRED.get(prov.kind, ())
        if _is_empty(getattr(prov, f, None))
    ]
    recommended = [
        f for f in _RECOMMENDED.get(prov.kind, ())
        if _is_empty(getattr(prov, f, None))
    ]
    return CompletenessReport(
        complete=not missing, missing=missing, recommended=recommended
    )


# --- licence expiry --------------------------------------------------------


@dataclass
class LicenceWarning:
    licence_id: str
    asset_id: str
    licence_type: str
    expiration_date: Optional[str]
    status: str  # "expired" | "expiring_soon" | "review_pending"
    days_remaining: Optional[int]


def licence_warnings(
    session: Session,
    *,
    within_days: int = 30,
    today: Optional[date] = None,
) -> list[LicenceWarning]:
    """Licences that are expired, expiring within ``within_days``, or stuck in
    a non-approved review state."""
    today = today or date.today()
    horizon = today + timedelta(days=within_days)
    warnings: list[LicenceWarning] = []

    rows = session.exec(select(LicenceRecord)).all()
    for lic in rows:
        status: Optional[str] = None
        days_remaining: Optional[int] = None
        if lic.expiration_date is not None:
            days_remaining = (lic.expiration_date - today).days
            if lic.expiration_date < today:
                status = "expired"
            elif lic.expiration_date <= horizon:
                status = "expiring_soon"
        if status is None and lic.review_state in (
            LicenceReviewState.NOT_REVIEWED,
            LicenceReviewState.PENDING,
            LicenceReviewState.EXPIRED,
        ):
            status = "review_pending"
        if status is None:
            continue
        warnings.append(
            LicenceWarning(
                licence_id=lic.id,
                asset_id=lic.asset_id,
                licence_type=lic.licence_type.value,
                expiration_date=(
                    lic.expiration_date.isoformat()
                    if lic.expiration_date is not None
                    else None
                ),
                status=status,
                days_remaining=days_remaining,
            )
        )
    # Most urgent first: expired, then soonest expiry, then review issues.
    warnings.sort(
        key=lambda w: (
            0 if w.status == "expired" else 1 if w.status == "expiring_soon" else 2,
            w.days_remaining if w.days_remaining is not None else 10**6,
        )
    )
    return warnings
