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

from app.auth import ADMIN_ONLY, AUTHED, get_current_user
from app.db import get_session
from app.integrations import (
    ECOSYSTEM,
    Ecosystem,
    Integration,
    all_integrations,
    get_integration,
)
from app.models import (
    IntegrationLink,
    IntegrationPoint,
    IntegrationRun,
    IntegrationRunStatus,
    User,
)
from app.models.enums import IntegrationPointStatus, IntegrationPointType
from app.schemas import (
    AdapterOperationRead,
    AdapterRead,
    ConfigStatusRead,
    HealthRead,
    IntegrationLinkRead,
    IntegrationPointCreate,
    IntegrationPointRead,
    IntegrationPointUpdate,
    IntegrationRunRead,
    OperationRequest,
    RunRejectRequest,
)
from app.services import integrations as integration_hub
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


# --- Operational hub: adapters, health, operations, runs, links ------------
# Declared before the catch-all ``/{key}`` so these segments are not swallowed.


def _adapter_read(adapter) -> AdapterRead:
    return AdapterRead(
        key=adapter.key,
        kind=adapter.kind.value,
        name=adapter.name,
        description=adapter.description,
        required_config=list(adapter.required_config),
        credential_names=list(adapter.credential_names),
        operations=[
            AdapterOperationRead(
                key=op.key, name=op.name, summary=op.summary,
                direction=op.direction.value, mutating=op.mutating,
                external=op.external, touches_network=op.touches_network,
                requires_approval=op.requires_approval, admin_gated=op.admin_gated,
                read_only=op.read_only, risk=op.risk,
            )
            for op in adapter.capabilities()
        ],
    )


@router.get(
    "/adapters",
    response_model=list[AdapterRead],
    dependencies=AUTHED,
    summary="List code-registered integration adapters",
)
def list_integration_adapters() -> list[AdapterRead]:
    return [_adapter_read(a) for a in integration_hub.list_adapters()]


@router.get(
    "/points/{point_id}/health",
    response_model=HealthRead,
    dependencies=AUTHED,
    summary="Adapter health for an integration point",
)
def integration_point_health(
    point_id: str, session: Session = Depends(get_session)
) -> HealthRead:
    point = get_or_404(session, IntegrationPoint, point_id, name="IntegrationPoint")
    report = integration_hub.adapter_health(session, point)
    return HealthRead(
        status=report.status, detail=report.detail, configured=report.configured,
        checked_live=report.checked_live, credentials=report.credentials,
        missing_config=report.missing_config,
    )


@router.get(
    "/points/{point_id}/config",
    response_model=ConfigStatusRead,
    dependencies=AUTHED,
    summary="Masked configuration status (never secrets)",
)
def integration_point_config(
    point_id: str, session: Session = Depends(get_session)
) -> ConfigStatusRead:
    point = get_or_404(session, IntegrationPoint, point_id, name="IntegrationPoint")
    return ConfigStatusRead(**integration_hub.config_status(point))


@router.post(
    "/points/{point_id}/operations",
    response_model=IntegrationRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Request an adapter operation (read-only runs now; mutations await approval)",
)
def request_integration_operation(
    point_id: str,
    payload: OperationRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> IntegrationRunRead:
    point = get_or_404(session, IntegrationPoint, point_id, name="IntegrationPoint")
    run = integration_hub.request_operation(
        session, point, payload.operation, payload.payload,
        user=user, dry_run=payload.dry_run,
    )
    session.commit()
    session.refresh(run)
    return IntegrationRunRead.model_validate(run)


@router.get(
    "/runs",
    response_model=Page[IntegrationRunRead],
    dependencies=AUTHED,
    summary="Integration run history",
)
def list_integration_runs(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    point_id: Optional[str] = Query(default=None),
    adapter_key: Optional[str] = Query(default=None),
    operation: Optional[str] = Query(default=None),
    status_: Optional[IntegrationRunStatus] = Query(default=None, alias="status"),
) -> Page[IntegrationRunRead]:
    stmt = select(IntegrationRun)
    if point_id is not None:
        stmt = stmt.where(IntegrationRun.integration_point_id == point_id)
    if adapter_key is not None:
        stmt = stmt.where(IntegrationRun.adapter_key == adapter_key)
    if operation is not None:
        stmt = stmt.where(IntegrationRun.operation == operation)
    if status_ is not None:
        stmt = stmt.where(IntegrationRun.status == status_)
    stmt = stmt.order_by(IntegrationRun.created_at.desc())
    items, total = paginate(session, stmt, params)
    return Page[IntegrationRunRead](
        items=[IntegrationRunRead.model_validate(r) for r in items],
        total=total, skip=params.skip, limit=params.limit,
    )


@router.get(
    "/runs/{run_id}",
    response_model=IntegrationRunRead,
    dependencies=AUTHED,
    summary="Fetch an integration run",
)
def get_integration_run(
    run_id: str, session: Session = Depends(get_session)
) -> IntegrationRunRead:
    run = get_or_404(session, IntegrationRun, run_id, name="IntegrationRun")
    return IntegrationRunRead.model_validate(run)


@router.post(
    "/runs/{run_id}/approve",
    response_model=IntegrationRunRead,
    summary="Approve a pending integration run",
)
def approve_integration_run(
    run_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> IntegrationRunRead:
    run = get_or_404(session, IntegrationRun, run_id, name="IntegrationRun")
    integration_hub.approve_run(session, run, user=user)
    session.commit()
    session.refresh(run)
    return IntegrationRunRead.model_validate(run)


@router.post(
    "/runs/{run_id}/reject",
    response_model=IntegrationRunRead,
    summary="Reject a pending integration run",
)
def reject_integration_run(
    run_id: str,
    payload: RunRejectRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> IntegrationRunRead:
    run = get_or_404(session, IntegrationRun, run_id, name="IntegrationRun")
    integration_hub.reject_run(session, run, user=user, reason=payload.reason)
    session.commit()
    session.refresh(run)
    return IntegrationRunRead.model_validate(run)


@router.post(
    "/runs/{run_id}/execute",
    response_model=IntegrationRunRead,
    summary="Execute an approved integration run",
)
def execute_integration_run(
    run_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> IntegrationRunRead:
    run = get_or_404(session, IntegrationRun, run_id, name="IntegrationRun")
    integration_hub.execute_run(session, run, user=user)
    session.commit()
    session.refresh(run)
    return IntegrationRunRead.model_validate(run)


@router.get(
    "/links",
    response_model=Page[IntegrationLinkRead],
    dependencies=AUTHED,
    summary="External objects linked to production tasks",
)
def list_integration_links(
    session: Session = Depends(get_session),
    params: PageParams = Depends(page_params),
    point_id: Optional[str] = Query(default=None),
    target_id: Optional[str] = Query(default=None),
) -> Page[IntegrationLinkRead]:
    stmt = select(IntegrationLink)
    if point_id is not None:
        stmt = stmt.where(IntegrationLink.integration_point_id == point_id)
    if target_id is not None:
        stmt = stmt.where(IntegrationLink.target_id == target_id)
    stmt = stmt.order_by(IntegrationLink.created_at.desc())
    items, total = paginate(session, stmt, params)
    return Page[IntegrationLinkRead](
        items=[IntegrationLinkRead.model_validate(link) for link in items],
        total=total, skip=params.skip, limit=params.limit,
    )


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
