from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED
from app.db import get_session
from app.models import AdaptationDossier, Work
from app.models.enums import (
    AdaptationStatus,
    Medium,
    RightsClearanceState,
    StudioDivision,
)
from app.schemas.adaptation_dossier import (
    AdaptationDossierCreate,
    AdaptationDossierRead,
    AdaptationDossierUpdate,
)
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    ensure_exists,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(prefix="/adaptation-dossiers", tags=["adaptation_dossiers"])


@router.get("", response_model=Page[AdaptationDossierRead])
def list_adaptation_dossiers(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    source_work_id: Optional[str] = Query(default=None),
    target_work_id: Optional[str] = Query(default=None),
    status_: Optional[AdaptationStatus] = Query(default=None, alias="status"),
    target_medium: Optional[Medium] = Query(default=None),
    target_division: Optional[StudioDivision] = Query(default=None),
    rights_clearance: Optional[RightsClearanceState] = Query(default=None),
) -> Page[AdaptationDossierRead]:
    stmt = select(AdaptationDossier)
    if source_work_id is not None:
        stmt = stmt.where(AdaptationDossier.source_work_id == source_work_id)
    if target_work_id is not None:
        stmt = stmt.where(AdaptationDossier.target_work_id == target_work_id)
    if status_ is not None:
        stmt = stmt.where(AdaptationDossier.status == status_)
    if target_medium is not None:
        stmt = stmt.where(AdaptationDossier.target_medium == target_medium)
    if target_division is not None:
        stmt = stmt.where(AdaptationDossier.target_division == target_division)
    if rights_clearance is not None:
        stmt = stmt.where(AdaptationDossier.rights_clearance == rights_clearance)
    stmt = stmt.order_by(AdaptationDossier.created_at.desc())

    items, total = paginate(session, stmt, params)
    return Page[AdaptationDossierRead](
        items=[AdaptationDossierRead.model_validate(i) for i in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.get("/{dossier_id}", response_model=AdaptationDossierRead)
def get_adaptation_dossier(
    dossier_id: str, session: Session = Depends(get_session)
) -> AdaptationDossier:
    return get_or_404(session, AdaptationDossier, dossier_id, name="AdaptationDossier")


@router.post("", response_model=AdaptationDossierRead, status_code=status.HTTP_201_CREATED, dependencies=AUTHED)
def create_adaptation_dossier(
    payload: AdaptationDossierCreate, session: Session = Depends(get_session)
) -> AdaptationDossier:
    ensure_exists(session, Work, payload.source_work_id, name="Work")
    if payload.target_work_id is not None:
        ensure_exists(session, Work, payload.target_work_id, name="Work")
    dossier = AdaptationDossier(**payload.model_dump())
    session.add(dossier)
    session.commit()
    session.refresh(dossier)
    return dossier


@router.patch("/{dossier_id}", response_model=AdaptationDossierRead, dependencies=AUTHED)
def update_adaptation_dossier(
    dossier_id: str,
    payload: AdaptationDossierUpdate,
    session: Session = Depends(get_session),
) -> AdaptationDossier:
    dossier = get_or_404(session, AdaptationDossier, dossier_id, name="AdaptationDossier")
    if payload.target_work_id is not None:
        ensure_exists(session, Work, payload.target_work_id, name="Work")
    apply_patch(dossier, payload)
    session.add(dossier)
    session.commit()
    session.refresh(dossier)
    return dossier


@router.delete("/{dossier_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=ADMIN_ONLY)
def delete_adaptation_dossier(dossier_id: str, session: Session = Depends(get_session)):
    dossier = get_or_404(session, AdaptationDossier, dossier_id, name="AdaptationDossier")
    session.delete(dossier)
    session.commit()
