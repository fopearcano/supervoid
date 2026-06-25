"""The IntegrationAdapter interface and its supporting value types.

Adapters are *code-registered* (see ``app.services.integrations.adapters``).
Each declares its capabilities as :class:`AdapterOperation` records and
implements the six interface methods: health check, status, capabilities,
dry-run, inbound operation and outbound operation.

Local-first and secure by construction:

* the per-call :class:`AdapterContext` exposes non-secret ``config`` and a
  ``secret(name)`` resolver that reads the value from the environment **at call
  time only** — secrets are never passed in persisted payloads;
* operations that mutate internal state or touch an external system are gated
  behind an approval boundary by the service layer (see ``service.py``);
* outbound network effects are *recorded* rather than fired unless network
  access is explicitly enabled.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from app.models.enums import (
    IntegrationAdapterKind,
    IntegrationDirectionKind,
    IntegrationHealthStatus,
)

if TYPE_CHECKING:
    from sqlmodel import Session

    from app.models import IntegrationPoint, User


# Risk labels are display + gating hints (the approval boundary itself is driven
# by ``mutating`` / ``external``).
RiskLabel = str  # one of: "low" | "medium" | "high" | "critical"


@dataclass(frozen=True)
class AdapterOperation:
    """A single capability an adapter exposes."""

    key: str
    name: str
    summary: str
    direction: IntegrationDirectionKind
    mutating: bool = False  # writes internal SUPERVOID state
    external: bool = False  # causes a side effect on an external system
    touches_network: bool = False  # would reach over the network (display)
    risk: RiskLabel = "low"

    @property
    def requires_approval(self) -> bool:
        """Mutating or external operations must pass the approval boundary."""
        return self.mutating or self.external

    @property
    def read_only(self) -> bool:
        return not self.requires_approval

    @property
    def admin_gated(self) -> bool:
        """External side effects always need an administrator's sign-off."""
        return self.external


@dataclass
class AdapterContext:
    """Everything an adapter needs for one operation."""

    session: "Session"
    point: "IntegrationPoint"
    config: dict  # non-secret config (adapter defaults merged with the point)
    payload: dict  # caller-supplied operation payload (never secrets)
    dry_run: bool
    allow_network: bool
    user: Optional["User"] = None
    secret_resolver: Optional[Callable[[str], Optional[str]]] = None

    def secret(self, logical_name: str) -> Optional[str]:
        """Resolve a secret from the environment by its configured reference.

        Returns ``None`` when unconfigured. The value is used only to make a
        live call and must never be persisted, logged or returned.
        """
        if self.secret_resolver is None:
            return None
        return self.secret_resolver(logical_name)

    def has_secret(self, logical_name: str) -> bool:
        return bool(self.secret(logical_name))


@dataclass
class HealthReport:
    status: IntegrationHealthStatus
    detail: str
    configured: bool
    checked_live: bool = False
    # logical credential name -> present-in-environment (booleans only).
    credentials: dict = field(default_factory=dict)
    missing_config: list = field(default_factory=list)


def recorded_result(request: dict, note: str) -> dict:
    """A uniform 'prepared but not dispatched' result for external operations
    when network access is disabled (the local-first default)."""
    return {"mode": "recorded", "dispatched": False, "request": request, "note": note}


class IntegrationAdapter(abc.ABC):
    """Base class every adapter implements.

    Subclasses set the class attributes (``key``, ``kind``, ``name``,
    ``description``, ``operations``, ``required_config``, ``credential_names``)
    and implement the abstract methods.
    """

    key: str = ""
    kind: IntegrationAdapterKind = IntegrationAdapterKind.OTHER
    name: str = ""
    description: str = ""
    operations: tuple[AdapterOperation, ...] = ()
    required_config: tuple[str, ...] = ()
    credential_names: tuple[str, ...] = ()

    # --- capabilities ------------------------------------------------------

    def capabilities(self) -> list[AdapterOperation]:
        return list(self.operations)

    def get_operation(self, key: str) -> Optional[AdapterOperation]:
        return next((o for o in self.operations if o.key == key), None)

    def default_config(self) -> dict:
        """Adapter-supplied config defaults, overlaid by the point's config."""
        return {}

    # --- health / status ---------------------------------------------------

    def base_health(self, ctx: AdapterContext) -> HealthReport:
        """Config-driven health that makes no network assumptions (local-first).

        Adapters may call this and then optionally probe liveness when
        ``ctx.allow_network`` is set.
        """
        creds = {n: ctx.has_secret(n) for n in self.credential_names}
        missing = [k for k in self.required_config if not ctx.config.get(k)]
        if not ctx.point.enabled:
            return HealthReport(
                IntegrationHealthStatus.DISABLED,
                "Integration point is disabled.",
                configured=not missing,
                credentials=creds,
                missing_config=missing,
            )
        if missing:
            return HealthReport(
                IntegrationHealthStatus.NOT_CONFIGURED,
                f"Missing required configuration: {', '.join(missing)}.",
                configured=False,
                credentials=creds,
                missing_config=missing,
            )
        return HealthReport(
            IntegrationHealthStatus.UNKNOWN,
            "Configured; liveness not checked (local-first).",
            configured=True,
            credentials=creds,
        )

    @abc.abstractmethod
    def health_check(self, ctx: AdapterContext) -> HealthReport: ...

    @abc.abstractmethod
    def status(self, ctx: AdapterContext) -> dict: ...

    # --- operations --------------------------------------------------------

    @abc.abstractmethod
    def dry_run(self, op: AdapterOperation, ctx: AdapterContext) -> dict: ...

    @abc.abstractmethod
    def inbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict: ...

    @abc.abstractmethod
    def outbound(self, op: AdapterOperation, ctx: AdapterContext) -> dict: ...

    def execute(self, op: AdapterOperation, ctx: AdapterContext) -> dict:
        """Dispatch a real (non-dry-run) operation by its declared direction."""
        if op.direction == IntegrationDirectionKind.OUTBOUND:
            return self.outbound(op, ctx)
        return self.inbound(op, ctx)
