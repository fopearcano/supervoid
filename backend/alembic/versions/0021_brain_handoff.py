"""brain hand-off (private navigation into LibreChat)

Revision ID: 0021_brain_handoff
Revises: 0020_agent_trace
Create Date: 2026-06-27 11:30:00.000000

A short-lived, single-use hand-off from a SUPERVOID entity into the Brain UI.
The signed token references this row; no sensitive content lives in the URL.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401


revision: str = "0021_brain_handoff"
down_revision: Union[str, None] = "0020_agent_trace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brain_handoffs",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("conversation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("entity_type", sqlmodel.sql.sqltypes.AutoString(length=60), nullable=False),
        sa.Column("entity_id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
        sa.Column("work_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("story_world_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("profile", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["brain_conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_brain_handoffs_user_id"), "brain_handoffs", ["user_id"], unique=False)
    op.create_index(op.f("ix_brain_handoffs_conversation_id"), "brain_handoffs", ["conversation_id"], unique=False)
    op.create_index(op.f("ix_brain_handoffs_entity_type"), "brain_handoffs", ["entity_type"], unique=False)
    op.create_index(op.f("ix_brain_handoffs_entity_id"), "brain_handoffs", ["entity_id"], unique=False)
    op.create_index(op.f("ix_brain_handoffs_work_id"), "brain_handoffs", ["work_id"], unique=False)
    op.create_index(op.f("ix_brain_handoffs_story_world_id"), "brain_handoffs", ["story_world_id"], unique=False)
    op.create_index(op.f("ix_brain_handoffs_expires_at"), "brain_handoffs", ["expires_at"], unique=False)
    op.create_index(op.f("ix_brain_handoffs_consumed_at"), "brain_handoffs", ["consumed_at"], unique=False)
    op.create_index("ix_brain_handoffs_user_created", "brain_handoffs", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_brain_handoffs_user_created", table_name="brain_handoffs")
    op.drop_index(op.f("ix_brain_handoffs_consumed_at"), table_name="brain_handoffs")
    op.drop_index(op.f("ix_brain_handoffs_expires_at"), table_name="brain_handoffs")
    op.drop_index(op.f("ix_brain_handoffs_story_world_id"), table_name="brain_handoffs")
    op.drop_index(op.f("ix_brain_handoffs_work_id"), table_name="brain_handoffs")
    op.drop_index(op.f("ix_brain_handoffs_entity_id"), table_name="brain_handoffs")
    op.drop_index(op.f("ix_brain_handoffs_entity_type"), table_name="brain_handoffs")
    op.drop_index(op.f("ix_brain_handoffs_conversation_id"), table_name="brain_handoffs")
    op.drop_index(op.f("ix_brain_handoffs_user_id"), table_name="brain_handoffs")
    op.drop_table("brain_handoffs")
