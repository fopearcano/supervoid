"""brain checkpoint: record the assistant profile version

Revision ID: 0017_ckpt_profile
Revises: 0016_constitution
Create Date: 2026-06-26 19:40:00.000000

The ContextAssembler stamps the constitution / profile / studio / project state
versions into every request; this adds the missing ``profile_version`` column to
``brain_checkpoints`` so the active assistant-profile version is persisted next
to the prefix hash.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_ckpt_profile"
down_revision: Union[str, None] = "0016_constitution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("brain_checkpoints", schema=None) as batch_op:
        batch_op.add_column(sa.Column("profile_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("brain_checkpoints", schema=None) as batch_op:
        batch_op.drop_column("profile_version")
