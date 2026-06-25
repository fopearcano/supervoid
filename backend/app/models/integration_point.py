from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import (
    IntegrationLinkKind,
    IntegrationPointStatus,
    IntegrationPointType,
    IntegrationRunStatus,
)

if TYPE_CHECKING:
    from app.models.user import User


class IntegrationPoint(BaseEntity, table=True):
    """A persisted, editable record of an integration to a sibling SUPERVOID
    ENTANGLED system or external tool — now an *operational* hub entry.

    This complements the static, code-defined ecosystem descriptors under
    ``app.integrations`` (served read-only at ``/api/integrations``): those
    declare the *contracts*. An ``IntegrationPoint`` is the operational,
    CRUD-able record that binds a code-registered **adapter** (n8n webhook,
    ComfyUI, GitHub, a desktop file-exchange profile, …) to its configuration.

    Local-first and secure by construction: ``config`` holds only non-secret
    settings; secrets are never stored here. ``credential_refs`` maps a logical
    credential name to the **environment variable name** that supplies it at
    call time — never the secret value itself.
    """

    __tablename__ = "integration_points"

    name: str = Field(max_length=200, index=True)
    type: IntegrationPointType = Field(
        default=IntegrationPointType.OTHER, index=True
    )
    status: IntegrationPointStatus = Field(
        default=IntegrationPointStatus.PLANNED, index=True
    )
    endpoint: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None)

    # --- Operational hub fields (additive; existing rows stay valid) ---
    # The code-registered adapter that drives this point (e.g. ``comfyui``,
    # ``github_project``, ``file_exchange.affinity``). Null = descriptive only.
    adapter_key: Optional[str] = Field(default=None, max_length=120, index=True)
    enabled: bool = Field(default=True, index=True)

    # Non-secret configuration only (endpoints, owner/repo, profile, defaults).
    config: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    # Logical credential name -> ENV VAR NAME (never a secret value). Resolved
    # from the environment at call time; never returned through the API.
    credential_refs: dict = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )

    runs: list["IntegrationRun"] = Relationship(
        back_populates="integration_point",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    links: list["IntegrationLink"] = Relationship(
        back_populates="integration_point",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class IntegrationRun(BaseEntity, table=True):
    """One execution of an adapter operation, with its own approval lifecycle.

    The run **is** the approval boundary (the equivalent of an
    ``AgentActionProposal``): operations that mutate internal state or touch an
    external system are created ``PENDING_APPROVAL`` and can only run once
    ``APPROVED``. Read-only operations and dry-runs succeed immediately. The
    input and output are both preserved (and redacted of any secret-like keys);
    secrets never appear in either.
    """

    __tablename__ = "integration_runs"

    # Composite index for run history filtered by point + status.
    __table_args__ = (
        Index("ix_integration_runs_point_status", "integration_point_id", "status"),
    )

    integration_point_id: str = Field(
        foreign_key="integration_points.id", index=True
    )
    adapter_key: str = Field(max_length=120, index=True)
    operation: str = Field(max_length=120, index=True)
    direction: str = Field(default="outbound", max_length=20, index=True)

    status: IntegrationRunStatus = Field(
        default=IntegrationRunStatus.PENDING_APPROVAL, index=True
    )
    dry_run: bool = Field(default=False, index=True)
    # Whether this operation needed approval before it could execute (mutating
    # or external). Persisted so history is self-describing if adapters change.
    requires_approval: bool = Field(default=False, index=True)
    is_external: bool = Field(default=False, index=True)

    input: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    output: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    error: Optional[str] = Field(default=None)

    requested_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    approved_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    approved_at: Optional[datetime] = Field(default=None)
    rejected_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    rejected_at: Optional[datetime] = Field(default=None)
    # Optional bridge to an agent proposal, when an agent drove this action.
    approval_proposal_id: Optional[str] = Field(
        default=None, foreign_key="agent_action_proposals.id", index=True
    )

    correlation_id: Optional[str] = Field(default=None, max_length=80, index=True)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    integration_point: Optional["IntegrationPoint"] = Relationship(
        back_populates="runs"
    )
    requested_by: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[IntegrationRun.requested_by_id]"}
    )

    @property
    def requested_by_name(self) -> Optional[str]:
        return self.requested_by.full_name if self.requested_by is not None else None


class IntegrationLink(BaseEntity, table=True):
    """A connection from an external object (a commit, issue or pull request)
    to an internal production task, created by the GitHub project adapter.

    Generic by design: ``target_type`` / ``target_id`` reference the internal
    entity (a production task), while the external identifiers live alongside.
    No credentials are stored here.
    """

    __tablename__ = "integration_links"

    integration_point_id: str = Field(
        foreign_key="integration_points.id", index=True
    )
    external_kind: IntegrationLinkKind = Field(
        default=IntegrationLinkKind.OTHER, index=True
    )
    external_ref: str = Field(max_length=300, index=True)  # sha / number / slug
    external_url: Optional[str] = Field(default=None, max_length=600)
    title: Optional[str] = Field(default=None, max_length=400)

    target_type: str = Field(default="production_task", max_length=60, index=True)
    target_id: str = Field(index=True)

    extra: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    integration_point: Optional["IntegrationPoint"] = Relationship(
        back_populates="links"
    )
