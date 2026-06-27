"""The SUPERVOID MCP server — the governed tool layer exposed to LibreChat over
Model Context Protocol (Streamable HTTP).

It exposes a curated set of read / proposal / approval tools that all run through
the SUPERVOID policy service. It NEVER exposes raw CRUD or unrestricted database
access: read tools return only authorised records, write-like tools create gated
proposals (never direct mutations), and approval tools verify the mapped
SUPERVOID user's approval scope.
"""

from app.services.mcp import auth, proposals, registry, server, tools  # noqa: F401
from app.services.mcp.auth import MCPAuthError, MCPPrincipal, authenticate
from app.services.mcp.registry import (
    MCPToolError,
    ToolKind,
    ToolSpec,
    get_tool,
    list_tools,
)
from app.services.mcp.server import SERVER_INSTRUCTIONS, handle_rpc

__all__ = [
    "MCPAuthError",
    "MCPPrincipal",
    "MCPToolError",
    "SERVER_INSTRUCTIONS",
    "ToolKind",
    "ToolSpec",
    "authenticate",
    "auth",
    "get_tool",
    "handle_rpc",
    "list_tools",
    "proposals",
    "registry",
    "server",
    "tools",
]
