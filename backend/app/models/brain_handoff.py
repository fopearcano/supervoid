"""A short-lived, single-use hand-off from a SUPERVOID entity into the Brain UI.

When a member clicks "Ask the Brain" on a Work / StoryWorld / page / panel /
scene / shot / asset / task / rights record, the backend resolves the project
scope, ensures/creates the bound :class:`BrainConversation`, and mints a SIGNED,
short-lived token. The landing endpoint consumes the token (once) and redirects
to LibreChat. No sensitive project content is ever placed in the URL — only the
opaque token, which references this row.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field

from app.models.base import BaseEntity


class BrainHandoff(BaseEntity, table=True):
    __tablename__ = "brain_handoffs"

    __table_args__ = (
        Index("ix_brain_handoffs_user_created", "user_id", "created_at"),
    )

    user_id: str = Field(foreign_key="users.id", index=True)
    conversation_id: Optional[str] = Field(
        default=None, foreign_key="brain_conversations.id", index=True
    )
    # The originating entity (for audit + the landing "active context").
    entity_type: str = Field(max_length=60, index=True)
    entity_id: str = Field(max_length=64, index=True)
    label: Optional[str] = Field(default=None, max_length=300)
    # The resolved project scope the conversation is bound to.
    work_id: Optional[str] = Field(default=None, index=True)
    story_world_id: Optional[str] = Field(default=None, index=True)
    profile: Optional[str] = Field(default=None, max_length=80)

    expires_at: datetime = Field(index=True)
    consumed_at: Optional[datetime] = Field(default=None, index=True)
