"""Turn a write-like MCP intention into a gated ``AgentActionProposal``.

MCP write tools NEVER mutate directly. Each creates a synthetic ``AgentRun``
(``agent_key="mcp"``, requester = the mapped SUPERVOID user) plus a PENDING,
approval-required proposal — reusing the agent framework's existing
approve / reject / execute governance. Execution of an MCP proposal is *recorded*
(no executor), so even an approved proposal performs no side effect on its own.
"""
from __future__ import annotations

from typing import Optional
from uuid import uuid4

from sqlmodel import Session

from app.models import (
    AgentActionProposal,
    AgentRiskLevel,
    AgentRun,
    AgentRunStatus,
    AgentToolKind,
    ProposalStatus,
)
from app.models.base import utcnow
from app.services.agents import get_tool as get_agent_tool
from app.services.agents import redact


def create_action_proposal(
    session: Session,
    principal,
    *,
    tool_key: str,
    target_type: Optional[str],
    target_id: Optional[str],
    payload: dict,
    reason: str,
    risk_level: Optional[AgentRiskLevel] = None,
) -> AgentActionProposal:
    """Create the synthetic run + PENDING proposal. Caller commits."""
    tool = get_agent_tool(tool_key)
    run = AgentRun(
        agent_key="mcp",
        requested_by_id=principal.user.id,
        target_type=target_type,
        target_id=target_id,
        provider="mcp",
        model=None,
        input_snapshot=redact({"source": "mcp", "tool": tool_key, "payload": payload or {}}),
        status=AgentRunStatus.SUCCEEDED,
        started_at=utcnow(),
        completed_at=utcnow(),
        correlation_id=principal.request_id or uuid4().hex,
    )
    session.add(run)
    session.flush()

    action_type = "external" if (tool and tool.kind == AgentToolKind.EXTERNAL) else "mutation"
    proposal = AgentActionProposal(
        run_id=run.id,
        agent_key="mcp",
        tool_key=tool_key,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        payload=redact(payload or {}),
        reason=reason,
        risk_level=risk_level or (tool.risk_level if tool else AgentRiskLevel.MEDIUM),
        requires_approval=True,  # always human-gated
        status=ProposalStatus.PENDING,
    )
    session.add(proposal)
    session.flush()
    return proposal
