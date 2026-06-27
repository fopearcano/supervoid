"""The supervised studio-agent framework: code-registered definitions and
tools, plus the runner that persists runs, findings and gated proposals."""

from app.services.agents import definitions, output, runner, tool_service, tools
from app.services.agents.definitions import (
    AgentContext,
    AgentDefinition,
    AgentOutput,
    FindingSpec,
    ProposalSpec,
    get_agent,
    list_agents,
)
from app.services.agents.output import (
    AgentOutputError,
    AgentOutputModel,
    ModelToolCall,
    build_response_format,
    parse_output,
)
from app.services.agents.runner import (
    AgentRejection,
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
    "AgentOutputError",
    "AgentOutputModel",
    "AgentRejection",
    "FindingSpec",
    "ModelToolCall",
    "ProposalSpec",
    "Tool",
    "build_response_format",
    "build_snapshot",
    "definitions",
    "execute_proposal",
    "get_agent",
    "get_tool",
    "list_agents",
    "list_tools",
    "output",
    "parse_output",
    "redact",
    "retry_run",
    "run_agent",
    "runner",
    "tool_service",
    "tools",
]
