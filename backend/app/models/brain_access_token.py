"""A dedicated bearer token for the SUPERVOID Brain Gateway.

LibreChat (and any OpenAI-compatible client) authenticates to the gateway with
one of these — NOT the browser JWT. The model stores only a deterministic
SHA-256 hash of the high-entropy secret (the plaintext is shown to the owner
once, at creation/rotation, and is never recoverable). A token belongs to a
``User`` and may optionally be restricted to a set of project scopes.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship

from app.models.base import BaseEntity


class BrainAccessToken(BaseEntity, table=True):
    __tablename__ = "brain_access_tokens"

    user_id: str = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=200)
    # SHA-256 hexdigest of the secret — deterministic so it is indexable/lookup-able.
    token_hash: str = Field(max_length=64, unique=True, index=True)
    # First few chars of the plaintext, kept only to disambiguate in the UI list.
    token_prefix: str = Field(default="", max_length=16)

    last_used_at: Optional[datetime] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None, index=True)
    revoked_at: Optional[datetime] = Field(default=None, index=True)

    # Optional further restriction: a list of {"work_id":..|null, "story_world_id":..|null}
    # scope objects. Empty list = no restriction beyond the user's own policy.
    project_restrictions: list = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )

    user: "User" = Relationship(back_populates="brain_tokens")  # noqa: F821
