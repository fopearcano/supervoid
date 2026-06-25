"""Persisted records for the supervised studio-agent framework.

``AgentDefinition`` and the tool registry are *code-registered* (see
``app/services/agents``); what lives here is the durable history: every run, its
findings, the actions it proposed, and the prompt templates (with version
tracking). Nothing here auto-mutates the system — proposals require human
approval before execution, and retries create new runs rather than overwrite.
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity
from app.models.enums import (
    AgentRiskLevel,
    AgentRunStatus,
    FindingSeverity,
    ProposalStatus,
)

if TYPE_CHECKING:
    from app.models.user import User


class AgentRun(BaseEntity, table=True):
    """One execution of an agent against a target entity.

    The input snapshot and the result are both preserved; a retry creates a new
    run (history is append-only). ``provider``/``model`` and token metadata are
    recorded for cost accounting; never any secret material.
    """

    __tablename__ = "agent_runs"

    agent_key: str = Field(max_length=120, index=True)
    requested_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )

    target_type: Optional[str] = Field(default=None, max_length=60, index=True)
    target_id: Optional[str] = Field(default=None, index=True)

    provider: str = Field(default="dry_run", max_length=80)
    model: Optional[str] = Field(default=None, max_length=160)

    input_snapshot: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    status: AgentRunStatus = Field(default=AgentRunStatus.PENDING, index=True)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    result: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    error: Optional[str] = Field(default=None)

    prompt_tokens: Optional[int] = Field(default=None, ge=0)
    completion_tokens: Optional[int] = Field(default=None, ge=0)
    total_tokens: Optional[int] = Field(default=None, ge=0)
    cost_usd: Optional[float] = Field(default=None, ge=0)

    correlation_id: Optional[str] = Field(default=None, max_length=80, index=True)
    # When this run is a retry of an earlier one (history is never overwritten).
    retry_of_id: Optional[str] = Field(
        default=None, foreign_key="agent_runs.id", index=True
    )

    requested_by: Optional["User"] = Relationship()
    findings: list["AgentFinding"] = Relationship(
        back_populates="run",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    proposals: list["AgentActionProposal"] = Relationship(
        back_populates="run",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class AgentFinding(BaseEntity, table=True):
    """An observation produced by a read-only analysis run."""

    __tablename__ = "agent_findings"

    run_id: str = Field(foreign_key="agent_runs.id", index=True)
    agent_key: str = Field(max_length=120, index=True)

    severity: FindingSeverity = Field(default=FindingSeverity.INFO, index=True)
    category: Optional[str] = Field(default=None, max_length=120, index=True)
    target_type: Optional[str] = Field(default=None, max_length=60, index=True)
    target_id: Optional[str] = Field(default=None, index=True)

    message: str = Field(default="")
    evidence: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    confidence: Optional[float] = Field(default=None, ge=0, le=1)

    resolved: bool = Field(default=False, index=True)
    resolved_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    resolved_at: Optional[datetime] = Field(default=None)

    run: "AgentRun" = Relationship(back_populates="findings")


class AgentActionProposal(BaseEntity, table=True):
    """A mutation or external action an agent proposes. Never executed without
    explicit human approval; destructive / publishing / rights / credential /
    external actions always require it."""

    __tablename__ = "agent_action_proposals"

    run_id: str = Field(foreign_key="agent_runs.id", index=True)
    agent_key: str = Field(max_length=120, index=True)
    tool_key: str = Field(max_length=120, index=True)
    action_type: str = Field(default="mutation", max_length=40, index=True)

    target_type: Optional[str] = Field(default=None, max_length=60, index=True)
    target_id: Optional[str] = Field(default=None, index=True)

    payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    reason: Optional[str] = Field(default=None)
    risk_level: AgentRiskLevel = Field(default=AgentRiskLevel.LOW, index=True)
    requires_approval: bool = Field(default=True, index=True)

    status: ProposalStatus = Field(default=ProposalStatus.PENDING, index=True)
    approved_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    approved_at: Optional[datetime] = Field(default=None)
    rejected_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )
    rejected_at: Optional[datetime] = Field(default=None)

    execution_result: dict = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    error: Optional[str] = Field(default=None)

    run: "AgentRun" = Relationship(back_populates="proposals")


class PromptTemplate(BaseEntity, table=True):
    """A named prompt with version tracking (versions are append-only)."""

    __tablename__ = "prompt_templates"

    key: str = Field(max_length=120, unique=True, index=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None)
    current_version: int = Field(default=1)
    enabled: bool = Field(default=True, index=True)

    versions: list["PromptTemplateVersion"] = Relationship(
        back_populates="template",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class PromptTemplateVersion(BaseEntity, table=True):
    __tablename__ = "prompt_template_versions"

    template_id: str = Field(foreign_key="prompt_templates.id", index=True)
    version: int = Field(default=1, index=True)
    body: str = Field(default="")
    notes: Optional[str] = Field(default=None)
    created_by_id: Optional[str] = Field(
        default=None, foreign_key="users.id", index=True
    )

    template: "PromptTemplate" = Relationship(back_populates="versions")
