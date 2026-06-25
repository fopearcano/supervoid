"""Editions and distribution-package generation.

An Edition is a concrete format/language/territory of a Work. Distribution
packages (ONIX, KDP, Ingram, GlobalComix, press kit, ARC) are *generated and
validated* here — manifests and checklists — never uploaded.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED, get_current_user
from app.db import get_session
from app.models import (
    DistributionPackage,
    Edition,
    Manuscript,
    ProductionRecord,
    User,
    Work,
)
from app.models.enums import DistributionChannel, DistributionStatus, EditionFormat
from app.schemas import (
    DistributionPackageRead,
    EditionCreate,
    EditionDetail,
    EditionRead,
    EditionUpdate,
    GeneratePackageRequest,
)
from app.services import distribution
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(tags=["editions"])


# --- distribution channel catalogue ----------------------------------------
# Declared before ``/editions/{edition_id}`` is irrelevant (different prefix),
# but grouped here for clarity.


@router.get("/distribution/channels", response_model=list[str])
def list_distribution_channels() -> list[str]:
    return distribution.available_channels()


# --- editions --------------------------------------------------------------


@router.get("/editions", response_model=Page[EditionRead])
def list_editions(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    work_id: Optional[str] = Query(default=None),
    format_: Optional[EditionFormat] = Query(default=None, alias="format"),
    distribution_status: Optional[DistributionStatus] = Query(default=None),
) -> Page[EditionRead]:
    stmt = select(Edition)
    if work_id is not None:
        stmt = stmt.where(Edition.work_id == work_id)
    if format_ is not None:
        stmt = stmt.where(Edition.format == format_)
    if distribution_status is not None:
        stmt = stmt.where(Edition.distribution_status == distribution_status)
    stmt = stmt.order_by(Edition.created_at.desc())
    items, total = paginate(session, stmt, params)
    return Page[EditionRead](
        items=[EditionRead.model_validate(e) for e in items],
        total=total, skip=params.skip, limit=params.limit,
    )


@router.get("/editions/{edition_id}", response_model=EditionRead)
def get_edition(edition_id: str, session: Session = Depends(get_session)) -> Edition:
    return get_or_404(session, Edition, edition_id, name="Edition")


@router.get("/editions/{edition_id}/detail", response_model=EditionDetail)
def get_edition_detail(
    edition_id: str, session: Session = Depends(get_session)
) -> EditionDetail:
    edition = get_or_404(session, Edition, edition_id, name="Edition")
    detail = EditionDetail.model_validate(edition)
    detail.packages = [
        DistributionPackageRead.model_validate(p)
        for p in sorted(edition.distribution_packages, key=lambda p: p.created_at, reverse=True)
    ]
    return detail


@router.post(
    "/editions", response_model=EditionRead,
    status_code=status.HTTP_201_CREATED, dependencies=AUTHED,
)
def create_edition(
    payload: EditionCreate, session: Session = Depends(get_session)
) -> Edition:
    ensure_exists(session, Work, payload.work_id, name="Work")
    if payload.manuscript_id is not None:
        ensure_exists(session, Manuscript, payload.manuscript_id, name="Manuscript")
    if payload.production_record_id is not None:
        ensure_exists(
            session, ProductionRecord, payload.production_record_id,
            name="ProductionRecord",
        )
    edition = Edition(**payload.model_dump())
    session.add(edition)
    session.commit()
    session.refresh(edition)
    return edition


@router.patch("/editions/{edition_id}", response_model=EditionRead, dependencies=AUTHED)
def update_edition(
    edition_id: str, payload: EditionUpdate, session: Session = Depends(get_session)
) -> Edition:
    edition = get_or_404(session, Edition, edition_id, name="Edition")
    apply_patch(edition, payload)
    session.add(edition)
    session.commit()
    session.refresh(edition)
    return edition


@router.delete(
    "/editions/{edition_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY
)
def delete_edition(edition_id: str, session: Session = Depends(get_session)):
    edition = get_or_404(session, Edition, edition_id, name="Edition")
    session.delete(edition)
    session.commit()


# --- distribution packages -------------------------------------------------


@router.get("/editions/{edition_id}/packages", response_model=list[DistributionPackageRead])
def list_packages(
    edition_id: str,
    session: Session = Depends(get_session),
    channel: Optional[DistributionChannel] = Query(default=None),
) -> list[DistributionPackageRead]:
    ensure_exists(session, Edition, edition_id, name="Edition")
    stmt = select(DistributionPackage).where(
        DistributionPackage.edition_id == edition_id
    )
    if channel is not None:
        stmt = stmt.where(DistributionPackage.channel == channel)
    stmt = stmt.order_by(DistributionPackage.created_at.desc())
    return [DistributionPackageRead.model_validate(p) for p in session.exec(stmt).all()]


@router.post(
    "/editions/{edition_id}/packages/{channel}",
    response_model=DistributionPackageRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_package(
    edition_id: str,
    channel: DistributionChannel,
    payload: GeneratePackageRequest | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DistributionPackage:
    edition = get_or_404(session, Edition, edition_id, name="Edition")
    package = distribution.generate_package(session, edition, channel, user=user)
    if payload is not None and payload.notes:
        package.notes = payload.notes
    session.commit()
    session.refresh(package)
    return package
