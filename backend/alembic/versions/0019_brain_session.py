"""brain stateful sessions (prefix-cache strategy)

Revision ID: 0019_brain_session
Revises: 0018_brain_token
Create Date: 2026-06-26 22:10:00.000000

The live, per-conversation Brain session (Prompt 8). One row per conversation;
the source of truth for prefix-cache eligibility and the hot/warm/cold
lifecycle. vLLM prefix caching is an optimisation we make eligible — this row
never asserts vLLM durably remembers anything.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (SQLModel column types)


revision: str = "0019_brain_session"
down_revision: Union[str, None] = "0018_brain_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brain_sessions",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("conversation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("work_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("story_world_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("active_profile", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=True),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString(length=160), nullable=True),
        sa.Column("last_prefix_hash", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
        sa.Column("constitution_version", sa.Integer(), nullable=True),
        sa.Column("profile_version", sa.Integer(), nullable=True),
        sa.Column("studio_state_version", sa.Integer(), nullable=True),
        sa.Column("project_state_version", sa.Integer(), nullable=True),
        sa.Column("studio_state_checksum", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
        sa.Column("project_state_checksum", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
        sa.Column("permissions_fingerprint", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("last_event_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_message_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(), nullable=True),
        sa.Column("warmth", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="hot"),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalidation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_invalidation_reason", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("last_prewarmed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["brain_conversations.id"]),
        sa.ForeignKeyConstraint(["last_message_id"], ["brain_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_brain_sessions_conversation_id"), "brain_sessions", ["conversation_id"], unique=True
    )
    op.create_index(op.f("ix_brain_sessions_work_id"), "brain_sessions", ["work_id"], unique=False)
    op.create_index(
        op.f("ix_brain_sessions_story_world_id"), "brain_sessions", ["story_world_id"], unique=False
    )
    op.create_index(
        op.f("ix_brain_sessions_last_prefix_hash"), "brain_sessions", ["last_prefix_hash"], unique=False
    )
    op.create_index(
        op.f("ix_brain_sessions_last_message_id"), "brain_sessions", ["last_message_id"], unique=False
    )
    op.create_index(
        op.f("ix_brain_sessions_last_activity_at"), "brain_sessions", ["last_activity_at"], unique=False
    )
    op.create_index(op.f("ix_brain_sessions_warmth"), "brain_sessions", ["warmth"], unique=False)
    op.create_index(
        op.f("ix_brain_sessions_last_prewarmed_at"), "brain_sessions", ["last_prewarmed_at"], unique=False
    )
    op.create_index(
        "ix_brain_sessions_warmth_activity", "brain_sessions", ["warmth", "last_activity_at"], unique=False
    )
    op.create_index(
        "ix_brain_sessions_scope", "brain_sessions", ["work_id", "story_world_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_brain_sessions_scope", table_name="brain_sessions")
    op.drop_index("ix_brain_sessions_warmth_activity", table_name="brain_sessions")
    op.drop_index(op.f("ix_brain_sessions_last_prewarmed_at"), table_name="brain_sessions")
    op.drop_index(op.f("ix_brain_sessions_warmth"), table_name="brain_sessions")
    op.drop_index(op.f("ix_brain_sessions_last_activity_at"), table_name="brain_sessions")
    op.drop_index(op.f("ix_brain_sessions_last_message_id"), table_name="brain_sessions")
    op.drop_index(op.f("ix_brain_sessions_last_prefix_hash"), table_name="brain_sessions")
    op.drop_index(op.f("ix_brain_sessions_story_world_id"), table_name="brain_sessions")
    op.drop_index(op.f("ix_brain_sessions_work_id"), table_name="brain_sessions")
    op.drop_index(op.f("ix_brain_sessions_conversation_id"), table_name="brain_sessions")
    op.drop_table("brain_sessions")
