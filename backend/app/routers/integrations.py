"""Ecosystem integration endpoints.

Two complementary surfaces live here:

* The static, code-defined ecosystem descriptors (read-only): the SUPERVOID
  ENTANGLED map and the declared integration *contracts* to sibling systems
  (LOGOSFORGE, SUPERVOID Movies). These describe the seams; they call out to
  nothing.
* A persisted ``IntegrationPoint`` registry (CRUD) under ``/points`` — editable
  operational records of planned or active integrations, each with an endpoint
  placeholder.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY, AUTHED
from app.db import get_session
from app.integrations import (
    ECOSYSTEM,
    Ecosystem,
    Integration,
    all_integrations,
    get_integration,
)
from app.models import IntegrationPoint
from app.models.enums import IntegrationPointStatus, IntegrationPointType
from app.schemas import (
    IntegrationPointCreate,
    IntegrationPointRead,
    IntegrationPointUpdate,
)
from app.utils import (
    Page,
    PageParams,
    apply_patch,
    get_or_404,
    page_params,
    paginate,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


# --- Static, code-defined ecosystem descriptors (read-only) ----------------


@router.get(
    "", response_model=list[Integration], summary="Ecosystem integration points"
)
def list_integrations() -> list[Integration]:
    return all_integrations()


@router.get(
    "/ecosystem",
    response_model=Ecosystem,
    summary="SUPERVOID ENTANGLED ecosystem map",
)
def ecosystem() -> Ecosystem:
    return ECOSYSTEM


# --- Persisted IntegrationPoint registry (CRUD) ----------------------------
# Declared before the catch-all ``/{key}`` route so ``/points`` is not
# swallowed by it.


@router.get(
    "/points",
    response_model=Page[IntegrationPointRead],
    summary="List persisted integration points",
)
def list_integration_points(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    type_: Optional[IntegrationPointType] = Query(default=None, alias="type"),
    status_: Optional[IntegrationPointStatus] = Query(default=None, alias="status"),
) -> Page[IntegrationPointRead]:
    stmt = select(IntegrationPoint)
    if type_ is not None:
        stmt = stmt.where(IntegrationPoint.type == type_)
    if status_ is not None:
        stmt = stmt.where(IntegrationPoint.status == status_)
    stmt = stmt.order_by(IntegrationPoint.created_at.desc())

    items, total = paginate(session, stmt, params)
    return Page[IntegrationPointRead](
        items=[IntegrationPointRead.model_validate(i) for i in items],
        total=total,
        skip=params.skip,
        limit=params.limit,
    )


@router.post(
    "/points",
    response_model=IntegrationPointRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=AUTHED,
    summary="Create an integration point",
)
def create_integration_point(
    payload: IntegrationPointCreate, session: Session = Depends(get_session)
) -> IntegrationPoint:
    point = IntegrationPoint(**payload.model_dump())
    session.add(point)
    session.commit()
    session.refresh(point)
    return point


@router.get(
    "/points/{point_id}",
    response_model=IntegrationPointRead,
    summary="Fetch an integration point",
)
def get_integration_point(
    point_id: str, session: Session = Depends(get_session)
) -> IntegrationPoint:
    return get_or_404(session, IntegrationPoint, point_id, name="IntegrationPoint")


@router.patch(
    "/points/{point_id}",
    response_model=IntegrationPointRead,
    dependencies=AUTHED,
    summary="Update an integration point",
)
def update_integration_point(
    point_id: str,
    payload: IntegrationPointUpdate,
    session: Session = Depends(get_session),
) -> IntegrationPoint:
    point = get_or_404(session, IntegrationPoint, point_id, name="IntegrationPoint")
    apply_patch(point, payload)
    session.add(point)
    session.commit()
    session.refresh(point)
    return point


@router.delete(
    "/points/{point_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=ADMIN_ONLY,
    summary="Delete an integration point",
)
def delete_integration_point(
    point_id: str, session: Session = Depends(get_session)
):
    point = get_or_404(session, IntegrationPoint, point_id, name="IntegrationPoint")
    session.delete(point)
    session.commit()


# --- Single static descriptor (catch-all, declared last) -------------------


@router.get(
    "/{key}",
    response_model=Integration,
    summary="A single integration descriptor",
)
def get_one(key: str) -> Integration:
    integration = get_integration(key)
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found.")
    return integration
