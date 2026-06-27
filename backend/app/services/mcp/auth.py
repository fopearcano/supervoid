"""MCP request authentication: the internal service credential + signed
user-context headers, mapped to a SUPERVOID user.

LibreChat must present BOTH:
  * ``X-SUPERVOID-Service-Token`` — the shared internal service credential; and
  * signed user-context headers (id / email / role / request-id) plus an
    ``X-SUPERVOID-User-Sig`` HMAC over them, keyed by the same service token.

The user-context is NEVER trusted without a valid service credential AND a valid
signature. The SUPERVOID user is resolved from the email (the authorisation
subject for every subsequent policy check) — the LibreChat-supplied role is
informational only and never used to grant access.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Mapping, Optional

from sqlmodel import Session, select

from app.config import settings
from app.models import User
from app.models.enums import SecurityEventType


class MCPAuthError(Exception):
    """Authentication / authorisation failure at the MCP boundary."""

    def __init__(self, message: str, *, code: int = -32001):
        super().__init__(message)
        self.message = message
        self.code = code  # JSON-RPC error code


@dataclass
class MCPPrincipal:
    """The authenticated principal behind an MCP request."""

    user: User                       # the resolved SUPERVOID user (authz subject)
    librechat_user_id: Optional[str]
    email: str
    declared_role: Optional[str]     # LibreChat-supplied; informational ONLY
    request_id: Optional[str]


# Header names (Starlette Headers lookups are case-insensitive).
H_SERVICE = "x-supervoid-service-token"
H_USER_ID = "x-supervoid-user-id"
H_EMAIL = "x-supervoid-user-email"
H_ROLE = "x-supervoid-user-role"
H_REQUEST_ID = "x-supervoid-request-id"
H_SIG = "x-supervoid-user-sig"


def canonical_user_context(
    *, user_id: str, email: str, role: str, request_id: str
) -> str:
    """The exact string both sides HMAC. Order + separators are fixed."""
    return "\n".join([user_id or "", email or "", role or "", request_id or ""])


def sign_user_context(token: str, *, user_id: str, email: str, role: str, request_id: str) -> str:
    """Helper (also used by tests / a LibreChat shim) to produce the signature."""
    msg = canonical_user_context(user_id=user_id, email=email, role=role, request_id=request_id)
    return hmac.new(token.encode(), msg.encode(), hashlib.sha256).hexdigest()


def authenticate(session: Session, headers: Mapping[str, str]) -> MCPPrincipal:
    """Validate the service credential + signed user-context, resolve the
    LibreChat identity to a SUPERVOID user THROUGH an active identity link, and
    reject unlinked or disabled members. Every failure is recorded as a security
    event (committed even though the request will 401). Fails closed."""
    if not settings.mcp_enabled:
        raise MCPAuthError("MCP server is disabled.", code=-32001)
    # Operator switch (Prompt 16): MCP can be disabled for maintenance at runtime.
    from app.services.brain import runtime as brain_runtime

    if not brain_runtime.mcp_allowed():
        raise MCPAuthError("MCP integration is in maintenance.", code=-32001)
    token = settings.mcp_service_token
    if not token:
        # No configured credential => refuse everything (never run open).
        raise MCPAuthError("MCP server is not configured (no service token).", code=-32001)

    from app.services import identity as identity_svc
    from app.services import security_events as sec

    user_id = headers.get(H_USER_ID) or ""
    email = (headers.get(H_EMAIL) or "").strip().lower()
    role = headers.get(H_ROLE) or ""
    request_id = headers.get(H_REQUEST_ID) or ""
    sig = headers.get(H_SIG) or ""

    def _fail(event_type, reason, *, supervoid_user_id=None):
        sec.record_security_event(
            session, event_type=event_type, source="mcp", email=email or None,
            librechat_user_id=user_id or None, supervoid_user_id=supervoid_user_id,
            request_id=request_id or None, reason=reason, commit=True,
        )

    presented = headers.get(H_SERVICE)
    if not presented or not hmac.compare_digest(presented, token):
        _fail(SecurityEventType.SERVICE_AUTH_FAILED, "invalid or missing service credential")
        raise MCPAuthError("Invalid or missing service credential.", code=-32001)

    if not email:
        _fail(SecurityEventType.MAPPING_FAILED, "missing user-context email")
        raise MCPAuthError("Missing user-context (email).", code=-32001)

    # The user-context is only trusted when correctly signed with the service
    # credential — a service token alone cannot impersonate an arbitrary user
    # without also producing a valid signature over that exact context.
    expected = sign_user_context(
        token, user_id=user_id, email=email, role=role, request_id=request_id
    )
    if not sig or not hmac.compare_digest(sig, expected):
        _fail(SecurityEventType.INVALID_SIGNATURE, "invalid user-context signature")
        raise MCPAuthError("Invalid user-context signature.", code=-32001)

    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        _fail(SecurityEventType.MAPPING_FAILED, "no SUPERVOID user for email")
        raise MCPAuthError("No SUPERVOID user for the supplied email.", code=-32001)
    if not user.is_active:
        _fail(SecurityEventType.DISABLED_MEMBER, "SUPERVOID user is disabled",
              supervoid_user_id=user.id)
        raise MCPAuthError("SUPERVOID user is disabled.", code=-32001)

    # Resolve THROUGH an active identity link (no implicit provisioning).
    if settings.mcp_require_identity_link:
        link = identity_svc.resolve_active_link(
            session, supervoid_user_id=user.id, email=email,
            librechat_user_id=user_id or None,
        )
        if link is None:
            _fail(SecurityEventType.UNLINKED_USER, "no active identity link",
                  supervoid_user_id=user.id)
            raise MCPAuthError(
                "LibreChat identity is not linked to an active SUPERVOID account.",
                code=-32001,
            )

    return MCPPrincipal(
        user=user, librechat_user_id=user_id or None, email=email,
        declared_role=role or None, request_id=request_id or None,
    )
