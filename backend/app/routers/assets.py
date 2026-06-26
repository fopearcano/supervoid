"""The central SUPERVOID Asset Library (private).

A reusable, work-centred, versioned asset domain with provenance and licensing.
Distinct from manuscript ``Attachment``s (kept for compatibility). Everything
here is private: all routes require authentication, downloads/previews are
auth-gated, and **assets are never exposed through the public reader** — public
media uses the curated public projection.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlmodel import Session, func, select

from app.auth import ADMIN_ONLY, AUTHED, get_current_user
from app.db import get_session
from app.models import (
    Asset,
    AssetLink,
    AssetType,
    AssetVersion,
    AssetVisibility,
    CanonState,
    LicenceRecord,
    ProvenanceRecord,
    StoryWorld,
    User,
    Work,
)
from app.models.enums import AssetLinkTargetType
from app.schemas.asset import (
    AssetApprovalUpdate,
    AssetCreate,
    AssetDetail,
    AssetLinkCreate,
    AssetLinkRead,
    AssetRead,
    AssetUpdate,
    AssetVersionCreate,
    AssetVersionRead,
    DuplicateMatch,
)
from app.schemas.licence_record import (
    LicenceCreate,
    LicenceRead,
    LicenceUpdate,
    LicenceWarningRead,
)
from app.schemas.provenance_record import (
    ProvenanceCompletenessRead,
    ProvenanceRead,
    ProvenanceWrite,
)
from app.services import assets as asset_service
from app.services import brain
from app.services.storage import get_storage, safe_filename
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

# Whole library is private.
router = APIRouter(prefix="/assets", tags=["assets"], dependencies=AUTHED)


class AssetSortBy(str, Enum):
    TITLE = "title"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    TYPE = "asset_type"


_SORT_COLUMNS = {
    AssetSortBy.TITLE: Asset.title,
    AssetSortBy.CREATED_AT: Asset.created_at,
    AssetSortBy.UPDATED_AT: Asset.updated_at,
    AssetSortBy.TYPE: Asset.asset_type,
}


# --- read builders ---------------------------------------------------------


def _version_read(version: AssetVersion, *, current_id: Optional[str]) -> AssetVersionRead:
    read = AssetVersionRead.model_validate(version)
    read.is_current = version.id == current_id
    read.has_provenance = version.provenance is not None
    return read


def _asset_read(asset: Asset) -> AssetRead:
    return AssetRead.model_validate(asset)


def _asset_detail(session: Session, asset: Asset) -> AssetDetail:
    detail = AssetDetail.model_validate(asset)
    versions = sorted(asset.versions, key=lambda v: v.version_number)
    detail.versions = [
        _version_read(v, current_id=asset.current_version_id) for v in versions
    ]
    if asset.current_version_id:
        current = session.get(AssetVersion, asset.current_version_id)
        detail.current_version = (
            _version_read(current, current_id=asset.current_version_id)
            if current is not None
            else None
        )
    detail.link_count = session.exec(
        select(func.count()).select_from(AssetLink).where(AssetLink.asset_id == asset.id)
    ).one()
    detail.licence_count = session.exec(
        select(func.count())
        .select_from(LicenceRecord)
        .where(LicenceRecord.asset_id == asset.id)
    ).one()
    return detail


# --- library-wide static routes (declared before /{asset_id}) --------------


@router.get("/licence-warnings", response_model=list[LicenceWarningRead])
def licence_warnings(
    session: Session = Depends(get_session),
    within_days: int = Query(default=30, ge=0, le=3650),
) -> list[LicenceWarningRead]:
    return [
        LicenceWarningRead(
            licence_id=w.licence_id,
            asset_id=w.asset_id,
            licence_type=w.licence_type,
            expiration_date=w.expiration_date,
            status=w.status,
            days_remaining=w.days_remaining,
        )
        for w in asset_service.licence_warnings(session, within_days=within_days)
    ]


@router.get("/versions/by-checksum/{checksum}", response_model=DuplicateMatch)
def versions_by_checksum(
    checksum: str, session: Session = Depends(get_session)
) -> DuplicateMatch:
    matches = asset_service.find_versions_by_checksum(session, checksum)
    return DuplicateMatch(
        checksum=checksum,
        matches=[_version_read(v, current_id=None) for v in matches],
    )


# --- asset CRUD ------------------------------------------------------------


@router.get("", response_model=Page[AssetRead])
def list_assets(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    q: Optional[str] = Query(default=None, description="Search title"),
    asset_type: Optional[AssetType] = Query(default=None),
    work_id: Optional[str] = Query(default=None),
    story_world_id: Optional[str] = Query(default=None),
    canon_status: Optional[CanonState] = Query(default=None),
    visibility: Optional[AssetVisibility] = Query(default=None),
    owner_id: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None, description="Match one tag"),
    sort_by: AssetSortBy = Query(default=AssetSortBy.UPDATED_AT),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
) -> Page[AssetRead]:
    stmt = select(Asset)
    if q:
        stmt = stmt.where(Asset.title.ilike(f"%{q}%"))
    if asset_type is not None:
        stmt = stmt.where(Asset.asset_type == asset_type)
    if work_id is not None:
        stmt = stmt.where(Asset.work_id == work_id)
    if story_world_id is not None:
        stmt = stmt.where(Asset.story_world_id == story_world_id)
    if canon_status is not None:
        stmt = stmt.where(Asset.canon_status == canon_status)
    if visibility is not None:
        stmt = stmt.where(Asset.visibility == visibility)
    if owner_id is not None:
        stmt = stmt.where(Asset.owner_id == owner_id)

    column = _SORT_COLUMNS[sort_by]
    stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())
    items, total = paginate(session, stmt, params)

    # Tag filtering is applied in Python (JSON array column, portable across
    # SQLite/Postgres). Applied post-pagination on the page slice.
    results = list(items)
    if tag is not None:
        results = [a for a in results if tag in (a.tags or [])]
    return Page[AssetRead](
        items=[_asset_read(a) for a in results],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.post("", response_model=AssetDetail, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AssetDetail:
    if payload.work_id is not None:
        ensure_exists(session, Work, payload.work_id, name="Work")
    if payload.story_world_id is not None:
        ensure_exists(session, StoryWorld, payload.story_world_id, name="StoryWorld")
    if payload.owner_id is not None:
        ensure_exists(session, User, payload.owner_id, name="User")
    data = payload.model_dump()
    data.setdefault("owner_id", None)
    if data.get("owner_id") is None:
        data["owner_id"] = user.id
    asset = Asset(**data)
    session.add(asset)
    brain.emit(
        session, event_type=brain.BrainEventType.ASSET_CREATED,
        aggregate_type="asset", aggregate_id=asset.id,
        work_id=asset.work_id, story_world_id=asset.story_world_id,
        actor_id=user.id,
        changes={"title": asset.title, "asset_type": asset.asset_type.value},
    )
    session.commit()
    session.refresh(asset)
    return _asset_detail(session, asset)


@router.get("/{asset_id}", response_model=AssetDetail)
def get_asset(asset_id: str, session: Session = Depends(get_session)) -> AssetDetail:
    asset = get_or_404(session, Asset, asset_id, name="Asset")
    return _asset_detail(session, asset)


@router.patch("/{asset_id}", response_model=AssetDetail)
def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    session: Session = Depends(get_session),
) -> AssetDetail:
    asset = get_or_404(session, Asset, asset_id, name="Asset")
    if payload.work_id is not None:
        ensure_exists(session, Work, payload.work_id, name="Work")
    if payload.story_world_id is not None:
        ensure_exists(session, StoryWorld, payload.story_world_id, name="StoryWorld")
    if payload.owner_id is not None:
        ensure_exists(session, User, payload.owner_id, name="User")
    apply_patch(asset, payload)
    session.add(asset)
    brain.emit(
        session, event_type=brain.BrainEventType.ASSET_UPDATED,
        aggregate_type="asset", aggregate_id=asset.id,
        work_id=asset.work_id, story_world_id=asset.story_world_id,
        changes=payload.model_dump(exclude_unset=True),
    )
    session.commit()
    session.refresh(asset)
    return _asset_detail(session, asset)


@router.delete(
    "/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY
)
def delete_asset(asset_id: str, session: Session = Depends(get_session)):
    asset = get_or_404(session, Asset, asset_id, name="Asset")
    work_id, story_world_id = asset.work_id, asset.story_world_id
    storage = get_storage()
    for version in asset.versions:
        storage.delete(version.storage_key)
    session.delete(asset)
    brain.emit(
        session, event_type=brain.BrainEventType.ASSET_DELETED,
        aggregate_type="asset", aggregate_id=asset_id,
        work_id=work_id, story_world_id=story_world_id,
    )
    session.commit()


# --- versions --------------------------------------------------------------


def _get_version(session: Session, asset_id: str, version_id: str) -> AssetVersion:
    version = get_or_404(session, AssetVersion, version_id, name="AssetVersion")
    if version.asset_id != asset_id:
        raise HTTPException(status_code=404, detail="Version not found on this asset")
    return version


@router.get("/{asset_id}/versions", response_model=list[AssetVersionRead])
def list_versions(
    asset_id: str, session: Session = Depends(get_session)
) -> list[AssetVersionRead]:
    asset = get_or_404(session, Asset, asset_id, name="Asset")
    versions = sorted(asset.versions, key=lambda v: v.version_number)
    return [_version_read(v, current_id=asset.current_version_id) for v in versions]


@router.post(
    "/{asset_id}/versions",
    response_model=AssetVersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a metadata-only (placeholder) version",
)
def create_placeholder_version(
    asset_id: str,
    payload: AssetVersionCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AssetVersionRead:
    asset = get_or_404(session, Asset, asset_id, name="Asset")
    version = AssetVersion(
        asset_id=asset.id,
        version_number=asset_service.next_version_number(session, asset.id),
        storage_key=f"placeholder:{uuid4()}",
        mime_type=payload.mime_type,
        width=payload.width,
        height=payload.height,
        duration_seconds=payload.duration_seconds,
        technical_metadata=payload.technical_metadata,
        notes=payload.notes,
        creator_id=user.id,
    )
    session.add(version)
    session.flush()
    if asset.current_version_id is None:
        asset.current_version_id = version.id
        session.add(asset)
    session.commit()
    session.refresh(version)
    session.refresh(asset)
    return _version_read(version, current_id=asset.current_version_id)


@router.post(
    "/{asset_id}/versions/upload",
    response_model=AssetVersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload bytes as a new version (checksum-deduped within the asset)",
)
def upload_version(
    asset_id: str,
    file: UploadFile = File(...),
    width: Optional[int] = Form(default=None),
    height: Optional[int] = Form(default=None),
    duration_seconds: Optional[float] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    make_current: bool = Form(default=False),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AssetVersionRead:
    asset = get_or_404(session, Asset, asset_id, name="Asset")
    storage = get_storage()
    key = f"assets/{asset_id}/{uuid4()}_{safe_filename(file.filename)}"
    stored = storage.write(key, file.file)

    # Checksum-based duplicate detection within this asset.
    dupes = asset_service.find_versions_by_checksum(
        session, stored.sha256, asset_id=asset_id
    )
    if dupes:
        storage.delete(key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Identical bytes already stored as version "
                f"{dupes[0].version_number} (checksum {stored.sha256[:12]}…)."
            ),
        )

    version = AssetVersion(
        asset_id=asset.id,
        version_number=asset_service.next_version_number(session, asset.id),
        storage_key=stored.storage_key,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=stored.size_bytes,
        checksum=stored.sha256,
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        notes=notes,
        creator_id=user.id,
    )
    session.add(version)
    session.flush()
    if make_current or asset.current_version_id is None:
        asset_service.set_current_version(session, asset, version)
    session.commit()
    session.refresh(version)
    session.refresh(asset)
    return _version_read(version, current_id=asset.current_version_id)


@router.post(
    "/{asset_id}/versions/{version_id}/promote", response_model=AssetDetail
)
def promote_version(
    asset_id: str, version_id: str, session: Session = Depends(get_session)
) -> AssetDetail:
    asset = get_or_404(session, Asset, asset_id, name="Asset")
    version = _get_version(session, asset_id, version_id)
    asset_service.set_current_version(session, asset, version)
    brain.emit(
        session, event_type=brain.BrainEventType.ASSET_VERSION_PROMOTED,
        aggregate_type="asset", aggregate_id=asset.id,
        work_id=asset.work_id, story_world_id=asset.story_world_id,
        changes={"version_id": version.id,
                 "version_number": version.version_number},
    )
    session.commit()
    session.refresh(asset)
    return _asset_detail(session, asset)


@router.post(
    "/{asset_id}/versions/{version_id}/rollback", response_model=AssetDetail
)
def rollback_version(
    asset_id: str, version_id: str, session: Session = Depends(get_session)
) -> AssetDetail:
    asset = get_or_404(session, Asset, asset_id, name="Asset")
    version = _get_version(session, asset_id, version_id)
    current = (
        session.get(AssetVersion, asset.current_version_id)
        if asset.current_version_id
        else None
    )
    if current is not None and version.version_number >= current.version_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rollback target must be an earlier version than the current one.",
        )
    asset_service.set_current_version(session, asset, version)
    session.commit()
    session.refresh(asset)
    return _asset_detail(session, asset)


@router.post(
    "/{asset_id}/versions/{version_id}/approve", response_model=AssetVersionRead
)
def set_version_approval(
    asset_id: str,
    version_id: str,
    payload: AssetApprovalUpdate,
    session: Session = Depends(get_session),
) -> AssetVersionRead:
    """Human approval gate for a version (DRAFT → IN_REVIEW → APPROVED/REJECTED)."""
    asset = get_or_404(session, Asset, asset_id, name="Asset")
    version = _get_version(session, asset_id, version_id)
    version.approval_status = payload.approval_status
    session.add(version)
    session.commit()
    session.refresh(version)
    return _version_read(version, current_id=asset.current_version_id)


def _serve(version: AssetVersion, *, inline: bool):
    if version.is_placeholder:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Placeholder version — no file bytes on record.",
        )
    storage = get_storage()
    if not storage.exists(version.storage_key):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="File is no longer available on the storage backend.",
        )
    filename = version.storage_key.rsplit("/", 1)[-1]
    local = storage.local_path(version.storage_key)
    if local is not None:
        return FileResponse(
            path=local,
            media_type=version.mime_type,
            filename=filename,
            content_disposition_type="inline" if inline else "attachment",
        )
    return StreamingResponse(
        storage.open_stream(version.storage_key), media_type=version.mime_type
    )


@router.get(
    "/{asset_id}/versions/{version_id}/download",
    summary="Stream a version's bytes (private; 410 for placeholders)",
)
def download_version(
    asset_id: str, version_id: str, session: Session = Depends(get_session)
):
    version = _get_version(session, asset_id, version_id)
    return _serve(version, inline=False)


@router.get(
    "/{asset_id}/versions/{version_id}/preview",
    summary="Inline preview of a version's bytes (private)",
)
def preview_version(
    asset_id: str, version_id: str, session: Session = Depends(get_session)
):
    version = _get_version(session, asset_id, version_id)
    return _serve(version, inline=True)


# --- provenance ------------------------------------------------------------


@router.get(
    "/{asset_id}/versions/{version_id}/provenance",
    response_model=Optional[ProvenanceRead],
)
def get_provenance(
    asset_id: str, version_id: str, session: Session = Depends(get_session)
) -> Optional[ProvenanceRead]:
    version = _get_version(session, asset_id, version_id)
    return (
        ProvenanceRead.model_validate(version.provenance)
        if version.provenance is not None
        else None
    )


@router.put(
    "/{asset_id}/versions/{version_id}/provenance", response_model=ProvenanceRead
)
def upsert_provenance(
    asset_id: str,
    version_id: str,
    payload: ProvenanceWrite,
    session: Session = Depends(get_session),
) -> ProvenanceRead:
    version = _get_version(session, asset_id, version_id)
    if payload.responsible_user_id is not None:
        ensure_exists(session, User, payload.responsible_user_id, name="User")
    prov = version.provenance
    if prov is None:
        prov = ProvenanceRecord(asset_version_id=version.id, **payload.model_dump())
    else:
        for key, value in payload.model_dump().items():
            setattr(prov, key, value)
    session.add(prov)
    asset = session.get(Asset, version.asset_id)
    brain.emit(
        session, event_type=brain.BrainEventType.PROVENANCE_RECORDED,
        aggregate_type="provenance", aggregate_id=prov.id,
        work_id=asset.work_id if asset else None,
        story_world_id=asset.story_world_id if asset else None,
        changes={"asset_version_id": version.id},
    )
    session.commit()
    session.refresh(prov)
    return ProvenanceRead.model_validate(prov)


@router.get(
    "/{asset_id}/versions/{version_id}/provenance/completeness",
    response_model=ProvenanceCompletenessRead,
)
def provenance_completeness(
    asset_id: str, version_id: str, session: Session = Depends(get_session)
) -> ProvenanceCompletenessRead:
    version = _get_version(session, asset_id, version_id)
    if version.provenance is None:
        return ProvenanceCompletenessRead(
            complete=False, missing=["provenance"], recommended=[]
        )
    report = asset_service.provenance_completeness(version.provenance)
    return ProvenanceCompletenessRead(
        complete=report.complete, missing=report.missing, recommended=report.recommended
    )


# --- links -----------------------------------------------------------------


@router.get("/{asset_id}/links", response_model=list[AssetLinkRead])
def list_links(
    asset_id: str,
    session: Session = Depends(get_session),
    target_type: Optional[AssetLinkTargetType] = Query(default=None),
) -> list[AssetLinkRead]:
    get_or_404(session, Asset, asset_id, name="Asset")
    stmt = select(AssetLink).where(AssetLink.asset_id == asset_id)
    if target_type is not None:
        stmt = stmt.where(AssetLink.target_type == target_type)
    stmt = stmt.order_by(AssetLink.created_at.asc())
    return [AssetLinkRead.model_validate(link) for link in session.exec(stmt).all()]


@router.post(
    "/{asset_id}/links",
    response_model=AssetLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def add_link(
    asset_id: str,
    payload: AssetLinkCreate,
    session: Session = Depends(get_session),
) -> AssetLinkRead:
    get_or_404(session, Asset, asset_id, name="Asset")
    if payload.asset_version_id is not None:
        _get_version(session, asset_id, payload.asset_version_id)
    link = AssetLink(asset_id=asset_id, **payload.model_dump())
    session.add(link)
    session.commit()
    session.refresh(link)
    return AssetLinkRead.model_validate(link)


@router.delete(
    "/{asset_id}/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_link(
    asset_id: str, link_id: str, session: Session = Depends(get_session)
):
    link = get_or_404(session, AssetLink, link_id, name="AssetLink")
    if link.asset_id != asset_id:
        raise HTTPException(status_code=404, detail="Link not found on this asset")
    session.delete(link)
    session.commit()


# --- licences --------------------------------------------------------------


@router.get("/{asset_id}/licences", response_model=list[LicenceRead])
def list_licences(
    asset_id: str, session: Session = Depends(get_session)
) -> list[LicenceRead]:
    get_or_404(session, Asset, asset_id, name="Asset")
    stmt = (
        select(LicenceRecord)
        .where(LicenceRecord.asset_id == asset_id)
        .order_by(LicenceRecord.created_at.asc())
    )
    return [LicenceRead.model_validate(lic) for lic in session.exec(stmt).all()]


@router.post(
    "/{asset_id}/licences",
    response_model=LicenceRead,
    status_code=status.HTTP_201_CREATED,
)
def add_licence(
    asset_id: str,
    payload: LicenceCreate,
    session: Session = Depends(get_session),
) -> LicenceRead:
    asset = get_or_404(session, Asset, asset_id, name="Asset")
    licence = LicenceRecord(asset_id=asset_id, **payload.model_dump())
    session.add(licence)
    brain.emit(
        session, event_type=brain.BrainEventType.LICENCE_CREATED,
        aggregate_type="licence", aggregate_id=licence.id,
        work_id=asset.work_id, story_world_id=asset.story_world_id,
        changes={"asset_id": asset_id},
    )
    session.commit()
    session.refresh(licence)
    return LicenceRead.model_validate(licence)


@router.patch(
    "/{asset_id}/licences/{licence_id}", response_model=LicenceRead
)
def update_licence(
    asset_id: str,
    licence_id: str,
    payload: LicenceUpdate,
    session: Session = Depends(get_session),
) -> LicenceRead:
    licence = get_or_404(session, LicenceRecord, licence_id, name="LicenceRecord")
    if licence.asset_id != asset_id:
        raise HTTPException(status_code=404, detail="Licence not found on this asset")
    apply_patch(licence, payload)
    session.add(licence)
    asset = session.get(Asset, asset_id)
    brain.emit(
        session, event_type=brain.BrainEventType.LICENCE_UPDATED,
        aggregate_type="licence", aggregate_id=licence.id,
        work_id=asset.work_id if asset else None,
        story_world_id=asset.story_world_id if asset else None,
        changes=payload.model_dump(exclude_unset=True),
    )
    session.commit()
    session.refresh(licence)
    return LicenceRead.model_validate(licence)


@router.delete(
    "/{asset_id}/licences/{licence_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_licence(
    asset_id: str, licence_id: str, session: Session = Depends(get_session)
):
    licence = get_or_404(session, LicenceRecord, licence_id, name="LicenceRecord")
    if licence.asset_id != asset_id:
        raise HTTPException(status_code=404, detail="Licence not found on this asset")
    asset = session.get(Asset, asset_id)
    session.delete(licence)
    brain.emit(
        session, event_type=brain.BrainEventType.LICENCE_DELETED,
        aggregate_type="licence", aggregate_id=licence_id,
        work_id=asset.work_id if asset else None,
        story_world_id=asset.story_world_id if asset else None,
    )
    session.commit()
