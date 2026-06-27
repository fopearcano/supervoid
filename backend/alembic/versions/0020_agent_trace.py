"""agent reasoning traces (model-driven runner)

Revision ID: 0020_agent_trace
Revises: 0019_brain_session
Create Date: 2026-06-27 09:30:00.000000

A safe, structured record of each step in a model-driven agent reasoning cycle
(tool requested, tool result, validated output) — never the model's private
chain-of-thought.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (SQLModel column types)


revision: str = "0020_agent_trace"
down_revision: Union[str, None] = "0019_brain_session"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_traces",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("run_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("agent_key", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("round", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False, server_default="note"),
        sa.Column("tool_key", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_traces_run_id"), "agent_traces", ["run_id"], unique=False)
    op.create_index(op.f("ix_agent_traces_agent_key"), "agent_traces", ["agent_key"], unique=False)
    op.create_index(op.f("ix_agent_traces_kind"), "agent_traces", ["kind"], unique=False)
    op.create_index("ix_agent_traces_run_sequence", "agent_traces", ["run_id", "sequence"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_traces_run_sequence", table_name="agent_traces")
    op.drop_index(op.f("ix_agent_traces_kind"), table_name="agent_traces")
    op.drop_index(op.f("ix_agent_traces_agent_key"), table_name="agent_traces")
    op.drop_index(op.f("ix_agent_traces_run_id"), table_name="agent_traces")
    op.drop_table("agent_traces")
