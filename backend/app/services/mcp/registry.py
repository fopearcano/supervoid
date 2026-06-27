"""The MCP tool registry: declarative specs + governance annotations.

Each tool declares its *kind* (read-only / proposal-only / destructive / external
/ approval) and whether it requires human approval. The dispatcher turns these
into MCP tool annotations so a client can reason about side effects before
calling. Schemas are kept concise so tool descriptions don't consume excessive
context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class ToolKind(str, Enum):
    READ_ONLY = "read-only"
    PROPOSAL_ONLY = "proposal-only"
    DESTRUCTIVE = "destructive"
    EXTERNAL = "external"
    APPROVAL = "approval"


class MCPToolError(Exception):
    """A tool refused the call (bad args / not found / permission). Surfaces as a
    tool result with ``isError: true`` — distinct from a transport/auth error."""

    def __init__(self, message: str, *, code: str = "tool_error"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    kind: ToolKind
    input_schema: dict
    handler: Callable  # (session, principal, args) -> dict | list | str
    requires_approval: bool = False

    def annotations(self) -> dict:
        """MCP tool annotations (hints) + a SUPERVOID governance block."""
        read_only = self.kind == ToolKind.READ_ONLY
        destructive = self.kind == ToolKind.DESTRUCTIVE
        return {
            "title": self.title,
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": read_only,
            "openWorldHint": self.kind == ToolKind.EXTERNAL,
            "supervoid": {
                "kind": self.kind.value,
                "requiresApproval": self.requires_approval,
            },
        }

    def describe(self) -> dict:
        """The MCP ``tools/list`` entry for this tool."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": self.annotations(),
        }


_TOOLS: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.name in _TOOLS:
        raise ValueError(f"Duplicate MCP tool '{spec.name}'.")
    _TOOLS[spec.name] = spec
    return spec


def tool(
    name: str,
    *,
    title: str,
    description: str,
    kind: ToolKind,
    input_schema: Optional[dict] = None,
    requires_approval: bool = False,
):
    """Decorator: register a handler as an MCP tool."""
    def _wrap(fn: Callable) -> Callable:
        register(ToolSpec(
            name=name, title=title, description=description, kind=kind,
            input_schema=input_schema or {"type": "object", "properties": {}},
            handler=fn, requires_approval=requires_approval,
        ))
        return fn
    return _wrap


def get_tool(name: str) -> Optional[ToolSpec]:
    return _TOOLS.get(name)


def list_tools() -> list[ToolSpec]:
    return list(_TOOLS.values())


# Small concise-schema helpers (keep descriptions cheap on context).
def obj(props: dict, *, required: Optional[list] = None) -> dict:
    schema = {"type": "object", "properties": props, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}


def opt_str(desc: str) -> dict:
    return {"type": "string", "description": desc}
