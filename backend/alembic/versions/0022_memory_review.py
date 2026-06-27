"""brain memory: review/provenance + contradiction columns

Revision ID: 0022_memory_review
Revises: 0021_brain_handoff
Create Date: 2026-06-27 12:00:00.000000

Prompt 13 (conversation memory & decision extraction). The durable
``brain_memory_items`` table already existed; this adds the columns the
analysis job and the Memory Review inbox need:

* ``topic_key``   — normalised topic slug for contradiction / duplicate
                    detection within a scope (indexed).
* ``risk_level``  — coarse risk band gating preference auto-acceptance.
* ``auto_accepted`` — the rules engine promoted it without human review.
* ``reviewed_by_id`` / ``reviewed_at`` / ``review_note`` — review provenance.

All columns are nullable / defaulted, so the change is additive and safe. No
new table is created (the memory + decision models already exist), and the new
``BrainMemoryKind.TASK_SUGGESTION`` enum value needs no schema change (the
column stores enum *values* as plain strings).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0022_memory_review"
down_revision: Union[str, None] = "0021_brain_handoff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("brain_memory_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("topic_key", sa.String(length=200), nullable=True))
        batch_op.add_column(
            sa.Column(
                "risk_level", sa.String(length=20), nullable=False, server_default="low"
            )
        )
        batch_op.add_column(
            sa.Column(
                "auto_accepted", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch_op.add_column(sa.Column("reviewed_by_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("review_note", sa.String(), nullable=True))
        batch_op.create_index(
            "ix_brain_memory_items_topic_key", ["topic_key"], unique=False
        )
        batch_op.create_index(
            "ix_brain_memory_items_reviewed_by_id", ["reviewed_by_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("brain_memory_items", schema=None) as batch_op:
        batch_op.drop_index("ix_brain_memory_items_reviewed_by_id")
        batch_op.drop_index("ix_brain_memory_items_topic_key")
        batch_op.drop_column("review_note")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by_id")
        batch_op.drop_column("auto_accepted")
        batch_op.drop_column("risk_level")
        batch_op.drop_column("topic_key")
