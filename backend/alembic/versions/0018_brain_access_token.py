"""brain access tokens (gateway bearer tokens)

Revision ID: 0018_brain_token
Revises: 0017_ckpt_profile
Create Date: 2026-06-26 20:20:00.000000

A dedicated, hashed bearer token for the Brain Gateway (LibreChat authenticates
with this, not the browser JWT). Stores only a SHA-256 hash of the secret.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (SQLModel column types)


revision: str = "0018_brain_token"
down_revision: Union[str, None] = "0017_ckpt_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brain_access_tokens",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("token_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("token_prefix", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("project_restrictions", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_brain_access_tokens_user_id"), "brain_access_tokens", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_brain_access_tokens_token_hash"), "brain_access_tokens", ["token_hash"], unique=True
    )
    op.create_index(
        op.f("ix_brain_access_tokens_expires_at"), "brain_access_tokens", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_brain_access_tokens_revoked_at"), "brain_access_tokens", ["revoked_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_brain_access_tokens_revoked_at"), table_name="brain_access_tokens")
    op.drop_index(op.f("ix_brain_access_tokens_expires_at"), table_name="brain_access_tokens")
    op.drop_index(op.f("ix_brain_access_tokens_token_hash"), table_name="brain_access_tokens")
    op.drop_index(op.f("ix_brain_access_tokens_user_id"), table_name="brain_access_tokens")
    op.drop_table("brain_access_tokens")
