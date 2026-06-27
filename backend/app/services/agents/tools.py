"""The agent tool registry (code-registered).

Tools are declared with their *kind* — read-only, mutation, or external — and a
risk level + permission declarations. Read-only tools may run during analysis;
mutation and external tools can only ever produce **proposals** that require
explicit human approval before execution. Destructive / publishing / rights /
credential / external tools are flagged ``always_requires_approval`` so the gate
can never be downgraded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.models.enums import AgentRiskLevel, AgentToolKind


@dataclass(frozen=True)
class Tool:
    key: str
    name: str
    description: str
    kind: AgentToolKind
    risk_level: AgentRiskLevel
    required_permissions: tuple[str, ...] = field(default_factory=tuple)
    always_requires_approval: bool = False

    @property
    def proposal_only(self) -> bool:
        """Any non-read-only tool can only ever yield a proposal."""
        return self.kind != AgentToolKind.READ_ONLY


_TOOLS: dict[str, Tool] = {}


def _register(tool: Tool) -> Tool:
    _TOOLS[tool.key] = tool
    return tool


# --- read-only internal tools (may execute during analysis) ---------------

_register(Tool(
    key="read_entity",
    name="Read entity",
    description="Read a manuscript / work / asset / scene snapshot for analysis.",
    kind=AgentToolKind.READ_ONLY,
    risk_level=AgentRiskLevel.LOW,
    required_permissions=("view_project",),
))
_register(Tool(
    key="search_knowledge",
    name="Search knowledge graph",
    description="Read characters, places and themes from the knowledge graph.",
    kind=AgentToolKind.READ_ONLY,
    risk_level=AgentRiskLevel.LOW,
))

# --- proposal-only mutation tools (approval required) ----------------------

_register(Tool(
    key="update_work_metadata",
    name="Update work metadata",
    description="Propose edits to a Work's catalogue metadata (synopsis, pitch…).",
    kind=AgentToolKind.MUTATION,
    risk_level=AgentRiskLevel.MEDIUM,
    required_permissions=("edit_narrative",),
))
_register(Tool(
    key="add_editorial_note",
    name="Add editorial note",
    description="Propose adding an editorial note to a manuscript.",
    kind=AgentToolKind.MUTATION,
    risk_level=AgentRiskLevel.LOW,
    required_permissions=("review",),
))

# --- always-gated: destructive / publishing / rights / external -----------

_register(Tool(
    key="publish_to_public_reader",
    name="Publish to public reader",
    description="Propose publishing curated content to the public reader.",
    kind=AgentToolKind.MUTATION,
    risk_level=AgentRiskLevel.CRITICAL,
    required_permissions=("publish",),
    always_requires_approval=True,
))
_register(Tool(
    key="update_rights",
    name="Update rights",
    description="Propose a change to a Work's rights record.",
    kind=AgentToolKind.MUTATION,
    risk_level=AgentRiskLevel.HIGH,
    required_permissions=("manage_rights",),
    always_requires_approval=True,
))
_register(Tool(
    key="delete_entity",
    name="Delete entity",
    description="Propose deleting an entity (destructive).",
    kind=AgentToolKind.MUTATION,
    risk_level=AgentRiskLevel.CRITICAL,
    required_permissions=("manage_production",),
    always_requires_approval=True,
))
_register(Tool(
    key="logosforge_export",
    name="LOGOSFORGE export (external)",
    description="Propose pushing editorial notes to the external LOGOSFORGE system.",
    kind=AgentToolKind.EXTERNAL,
    risk_level=AgentRiskLevel.HIGH,
    always_requires_approval=True,
))
_register(Tool(
    key="movies_handoff",
    name="SUPERVOID Pictures hand-off (external)",
    description="Propose handing an adaptation off to the screen division.",
    kind=AgentToolKind.EXTERNAL,
    risk_level=AgentRiskLevel.MEDIUM,
    always_requires_approval=True,
))


# --- MCP proposal tools (created by the MCP server, never by an agent) ------
# Registered so the proposal/approval governance reads consistent risk +
# permission metadata. They have no executor, so execution is *recorded* (a
# deliberate manual follow-up through the dedicated audited endpoint).

_register(Tool(
    key="create_production_task",
    name="Create production task",
    description="Propose creating a production task.",
    kind=AgentToolKind.MUTATION,
    risk_level=AgentRiskLevel.MEDIUM,
    required_permissions=("manage_production",),
))
_register(Tool(
    key="update_production_task",
    name="Update production task",
    description="Propose an update to a production task.",
    kind=AgentToolKind.MUTATION,
    risk_level=AgentRiskLevel.LOW,
    required_permissions=("manage_production",),
))
_register(Tool(
    key="link_asset",
    name="Link asset",
    description="Propose linking an asset to a character / location / page.",
    kind=AgentToolKind.MUTATION,
    risk_level=AgentRiskLevel.LOW,
    required_permissions=("upload_assets",),
))


def get_tool(key: str) -> Optional[Tool]:
    return _TOOLS.get(key)


def list_tools() -> list[Tool]:
    return list(_TOOLS.values())


def proposal_requires_approval(tool: Tool) -> bool:
    """In this framework every proposal needs approval before execution; the
    flag simply marks the categories that can never be downgraded."""
    return True
