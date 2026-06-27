from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    AgentMutability,
    AgentRiskLevel,
    AgentRunStatus,
    AgentToolKind,
    FindingSeverity,
    ProposalStatus,
)
from app.schemas._common import TimestampedRead


# --- code-registered descriptors -------------------------------------------


class AgentDefinitionRead(BaseModel):
    key: str
    name: str
    description: str
    supported_entity_types: list[str]
    required_permissions: list[str]
    allowed_tools: list[str]
    mutability: AgentMutability
    default_provider: str
    default_model: Optional[str]
    enabled: bool


class ToolRead(BaseModel):
    key: str
    name: str
    description: str
    kind: AgentToolKind
    risk_level: AgentRiskLevel
    required_permissions: list[str]
    always_requires_approval: bool


# --- runs ------------------------------------------------------------------


class RunRequest(BaseModel):
    target_type: Optional[str] = Field(default=None, max_length=60)
    target_id: Optional[str] = None


class AgentRunRead(TimestampedRead):
    agent_key: str
    requested_by_id: Optional[str]
    target_type: Optional[str]
    target_id: Optional[str]
    provider: str
    model: Optional[str]
    status: AgentRunStatus
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error: Optional[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    cost_usd: Optional[float]
    correlation_id: Optional[str]
    retry_of_id: Optional[str]
    finding_count: int = 0
    proposal_count: int = 0


class AgentFindingRead(TimestampedRead):
    run_id: str
    agent_key: str
    severity: FindingSeverity
    category: Optional[str]
    target_type: Optional[str]
    target_id: Optional[str]
    message: str
    evidence: dict
    confidence: Optional[float]
    resolved: bool
    resolved_by_id: Optional[str]
    resolved_at: Optional[datetime]


class AgentProposalRead(TimestampedRead):
    run_id: str
    agent_key: str
    tool_key: str
    action_type: str
    target_type: Optional[str]
    target_id: Optional[str]
    payload: dict
    reason: Optional[str]
    risk_level: AgentRiskLevel
    requires_approval: bool
    status: ProposalStatus
    approved_by_id: Optional[str]
    approved_at: Optional[datetime]
    rejected_by_id: Optional[str]
    rejected_at: Optional[datetime]
    execution_result: dict
    error: Optional[str]


class AgentTraceRead(TimestampedRead):
    run_id: str
    agent_key: str
    sequence: int
    round: int
    kind: str
    tool_key: Optional[str]
    payload: dict


class AgentRunDetail(AgentRunRead):
    input_snapshot: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    findings: list[AgentFindingRead] = Field(default_factory=list)
    proposals: list[AgentProposalRead] = Field(default_factory=list)
    traces: list[AgentTraceRead] = Field(default_factory=list)


class ProposalRejectRequest(BaseModel):
    reason: Optional[str] = None


# --- prompt templates (versioned) ------------------------------------------


class PromptTemplateCreate(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    body: str = Field(default="")


class PromptVersionCreate(BaseModel):
    body: str
    notes: Optional[str] = None


class PromptVersionRead(TimestampedRead):
    template_id: str
    version: int
    body: str
    notes: Optional[str]
    created_by_id: Optional[str]


class PromptTemplateRead(TimestampedRead):
    key: str
    name: str
    description: Optional[str]
    current_version: int
    enabled: bool
