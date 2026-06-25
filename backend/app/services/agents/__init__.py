"""The supervised studio-agent framework: code-registered definitions and
tools, plus the runner that persists runs, findings and gated proposals."""

from app.services.agents import definitions, runner, tools
from app.services.agents.definitions import (
    AgentContext,
    AgentDefinition,
    AgentOutput,
    FindingSpec,
    ProposalSpec,
    get_agent,
    list_agents,
)
from app.services.agents.runner import (
    build_snapshot,
    execute_proposal,
    redact,
    retry_run,
    run_agent,
)
from app.services.agents.tools import Tool, get_tool, list_tools

__all__ = [
    "AgentContext",
    "AgentDefinition",
    "AgentOutput",
    "FindingSpec",
    "ProposalSpec",
    "Tool",
    "build_snapshot",
    "definitions",
    "execute_proposal",
    "get_agent",
    "get_tool",
    "list_agents",
    "list_tools",
    "redact",
    "retry_run",
    "run_agent",
    "runner",
    "tools",
]
