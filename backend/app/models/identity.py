"""Identity bridge between SUPERVOID and LibreChat (Prompt 15).

The **simpler, robust first version** of the identity bridge — an admin-managed
link table plus an append-only security-event log. This is deliberately NOT a
custom OAuth/OIDC provider (see docs/IDENTITY.md for the future-OIDC path).

* ``LibreChatIdentityLink`` — an admin links a SUPERVOID user to a LibreChat
  identity (user id + email). Only an ACTIVE (verified) link may authenticate an
  MCP request; unlinked or disabled identities are rejected.
* ``SecurityEvent`` — append-only record of security-relevant events (failed
  mapping, revoked-token use, disabled member, project-denied tool call,
  suspicious repeated failures) and benign audit lifecycle (token/link changes).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field

from app.models.base import BaseEntity, utcnow
from app.models.enums import (
    IdentityLinkStatus,
    SecurityEventSeverity,
    SecurityEventType,
)


class LibreChatIdentityLink(BaseEntity, table=True):
    """An admin-managed link from a SUPERVOID user to a LibreChat identity.

    One link per SUPERVOID user (unique). Re-linking upserts this row. The MCP
    server resolves the LibreChat identity to a SUPERVOID user THROUGH an ACTIVE
    link — there is no implicit/auto provisioning."""

    __tablename__ = "librechat_identity_links"
    __table_args__ = (
        Index("ix_librechat_identity_links_user", "supervoid_user_id", unique=True),
        Index("ix_librechat_identity_links_email", "librechat_email"),
        Index("ix_librechat_identity_links_lc_user", "librechat_user_id"),
    )

    supervoid_user_id: str = Field(foreign_key="users.id", index=True)
    librechat_user_id: Optional[str] = Field(default=None, max_length=120)
    librechat_email: str = Field(default="", max_length=255)

    status: IdentityLinkStatus = Field(default=IdentityLinkStatus.PENDING, index=True)
    linked_at: datetime = Field(default_factory=utcnow)
    verified_at: Optional[datetime] = Field(default=None)
    disabled_at: Optional[datetime] = Field(default=None)

    linked_by_id: Optional[str] = Field(default=None, index=True)
    disabled_by_id: Optional[str] = Field(default=None)
    note: Optional[str] = Field(default=None, max_length=500)


class SecurityEvent(BaseEntity, table=True):
    """Append-only security / audit event. Never edited or deleted.

    Decoupled (plain id columns, no FKs) so the log survives even when the
    referenced user / token / link is later removed."""

    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_type_created", "event_type", "created_at"),
        Index("ix_security_events_email_created", "email", "created_at"),
        Index("ix_security_events_user_created", "supervoid_user_id", "created_at"),
    )

    event_type: SecurityEventType = Field(index=True)
    severity: SecurityEventSeverity = Field(default=SecurityEventSeverity.WARNING, index=True)
    source: str = Field(default="", max_length=20, index=True)  # mcp | gateway | api

    supervoid_user_id: Optional[str] = Field(default=None, index=True)
    librechat_user_id: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=255, index=True)

    reason: Optional[str] = Field(default=None, max_length=300)
    work_id: Optional[str] = Field(default=None, index=True)
    story_world_id: Optional[str] = Field(default=None)
    token_id: Optional[str] = Field(default=None, index=True)
    request_id: Optional[str] = Field(default=None, max_length=80)
    detail: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
