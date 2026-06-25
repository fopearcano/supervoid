"""The integration hub service: the approval boundary and run lifecycle.

Read-only operations and dry-runs execute immediately. Operations that mutate
internal state or touch an external system are created ``PENDING_APPROVAL`` and
can only execute once ``APPROVED`` — external operations additionally require an
administrator. This is the boundary every external mutation must pass through.

The caller commits. Inputs and outputs are persisted with secret-like keys
redacted; secrets themselves are resolved from the environment at call time and
never stored.
"""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, status
from sqlmodel import Session

from app.config import settings
from app.models import (
    IntegrationPoint,
    IntegrationRun,
    IntegrationRunStatus,
    User,
    UserRole,
)
from app.models.base import utcnow
from app.services.agents import redact
from app.services.integrations import config as config_module
from app.services.integrations.adapters import get_adapter, list_adapters
from app.services.integrations.base import (
    AdapterContext,
    HealthReport,
    IntegrationAdapter,
)

__all__ = [
    "get_adapter",
    "list_adapters",
    "request_operation",
    "approve_run",
    "reject_run",
    "execute_run",
    "adapter_health",
    "config_status",
]


def _ctx(
    session: Session,
    adapter: IntegrationAdapter,
    point: IntegrationPoint,
    payload: Optional[dict],
    *,
    user: Optional[User],
    dry_run: bool,
) -> AdapterContext:
    merged = {**adapter.default_config(), **(point.config or {})}
    return AdapterContext(
        session=session,
        point=point,
        config=merged,
        payload=payload or {},
        dry_run=dry_run,
        allow_network=settings.integrations_allow_network,
        user=user,
        secret_resolver=lambda name: config_module.resolve_secret(point, name),
    )


def _require_adapter(point: IntegrationPoint) -> IntegrationAdapter:
    if not point.enabled:
        raise HTTPException(status_code=409, detail="Integration point is disabled.")
    if not point.adapter_key:
        raise HTTPException(
            status_code=409, detail="No operational adapter is bound to this point."
        )
    adapter = get_adapter(point.adapter_key)
    if adapter is None:
        raise HTTPException(
            status_code=409, detail=f"Unknown adapter '{point.adapter_key}'."
        )
    return adapter


def request_operation(
    session: Session,
    point: IntegrationPoint,
    operation: str,
    payload: Optional[dict],
    *,
    user: User,
    dry_run: bool = False,
    correlation_id: Optional[str] = None,
) -> IntegrationRun:
    """Request an adapter operation. Read-only ops and dry-runs run now;
    mutating/external ops are persisted PENDING_APPROVAL with no side effect.

    ``correlation_id`` ties the run to the originating HTTP request (the API
    layer passes ``request.state.request_id``) and stays fixed across the
    run's approve/execute lifecycle; it falls back to a fresh id when invoked
    outside a request."""
    adapter = _require_adapter(point)
    op = adapter.get_operation(operation)
    if op is None:
        raise HTTPException(
            status_code=404,
            detail=f"Operation '{operation}' is not supported by '{adapter.key}'.",
        )

    run = IntegrationRun(
        integration_point_id=point.id,
        adapter_key=adapter.key,
        operation=op.key,
        direction=op.direction.value,
        dry_run=dry_run,
        requires_approval=op.requires_approval and not dry_run,
        is_external=op.external,
        requested_by_id=user.id if user else None,
        input=redact(payload or {}),
        correlation_id=correlation_id or uuid4().hex,
    )

    if dry_run or op.read_only:
        ctx = _ctx(session, adapter, point, payload, user=user, dry_run=dry_run)
        run.status = IntegrationRunStatus.RUNNING
        run.started_at = utcnow()
        try:
            result = adapter.dry_run(op, ctx) if dry_run else adapter.execute(op, ctx)
            run.output = redact(result or {})
            run.status = IntegrationRunStatus.SUCCEEDED
        except Exception as exc:  # noqa: BLE001 - record any adapter failure
            run.status = IntegrationRunStatus.FAILED
            run.error = str(exc)
        run.completed_at = utcnow()
    else:
        # Mutating / external: awaits approval; nothing happens yet.
        run.status = IntegrationRunStatus.PENDING_APPROVAL

    session.add(run)
    return run


def _gated_for(run: IntegrationRun) -> bool:
    """Whether approving this run requires an administrator. Looked up from the
    adapter operation; falls back to the persisted external flag if the adapter
    has since changed."""
    adapter = get_adapter(run.adapter_key)
    op = adapter.get_operation(run.operation) if adapter else None
    return op.admin_gated if op else run.is_external


def approve_run(session: Session, run: IntegrationRun, *, user: User) -> IntegrationRun:
    if run.status != IntegrationRunStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400, detail=f"Run is already {run.status.value}."
        )
    if _gated_for(run) and user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This external action requires an administrator's approval.",
        )
    run.status = IntegrationRunStatus.APPROVED
    run.approved_by_id = user.id
    run.approved_at = utcnow()
    session.add(run)
    return run


def reject_run(
    session: Session, run: IntegrationRun, *, user: User, reason: Optional[str] = None
) -> IntegrationRun:
    if run.status != IntegrationRunStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400, detail=f"Run is already {run.status.value}."
        )
    run.status = IntegrationRunStatus.REJECTED
    run.rejected_by_id = user.id
    run.rejected_at = utcnow()
    if reason:
        run.error = reason
    session.add(run)
    return run


def execute_run(session: Session, run: IntegrationRun, *, user: User) -> IntegrationRun:
    """Execute an approved run. This is the only path that fires a real
    mutating/external effect, and only an APPROVED run can reach it."""
    if run.status != IntegrationRunStatus.APPROVED:
        raise HTTPException(
            status_code=409, detail="Only an approved run can be executed."
        )
    adapter = get_adapter(run.adapter_key)
    op = adapter.get_operation(run.operation) if adapter else None
    if adapter is None or op is None:
        raise HTTPException(
            status_code=409, detail="The adapter or operation is no longer available."
        )
    point = session.get(IntegrationPoint, run.integration_point_id)
    if point is None:
        raise HTTPException(status_code=409, detail="Integration point no longer exists.")

    ctx = _ctx(session, adapter, point, run.input, user=user, dry_run=False)
    run.status = IntegrationRunStatus.RUNNING
    run.started_at = run.started_at or utcnow()
    try:
        result = adapter.execute(op, ctx)
        run.output = redact(result or {})
        run.status = IntegrationRunStatus.SUCCEEDED
    except Exception as exc:  # noqa: BLE001 - record execution failure on the run
        run.status = IntegrationRunStatus.FAILED
        run.error = str(exc)
    run.completed_at = utcnow()
    session.add(run)
    return run


# --- health & configuration (never leak secrets) ---------------------------


def adapter_health(session: Session, point: IntegrationPoint) -> HealthReport:
    from app.models.enums import IntegrationHealthStatus

    adapter = get_adapter(point.adapter_key) if point.adapter_key else None
    if adapter is None:
        return HealthReport(
            status=IntegrationHealthStatus.NOT_CONFIGURED,
            detail="No operational adapter is bound to this point.",
            configured=False,
        )
    ctx = _ctx(session, adapter, point, {}, user=None, dry_run=True)
    return adapter.health_check(ctx)


def config_status(point: IntegrationPoint) -> dict:
    """Masked configuration status — booleans and non-secret config only."""
    adapter = get_adapter(point.adapter_key) if point.adapter_key else None
    required = list(adapter.required_config) if adapter else []
    return {
        "adapter_key": point.adapter_key,
        "enabled": point.enabled,
        "config": config_module.masked_config(point),
        "credentials": config_module.credential_status(point),
        "required_config": required,
        "missing_config": [k for k in required if not (point.config or {}).get(k)],
    }
