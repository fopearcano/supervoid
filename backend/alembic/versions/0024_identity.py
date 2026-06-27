"""identity bridge: librechat identity links + security events

Revision ID: 0024_identity
Revises: 0023_retrieval
Create Date: 2026-06-27 16:00:00.000000

Prompt 15. The simpler, robust first version of the SUPERVOID ↔ LibreChat
identity bridge: an admin-managed link table and an append-only security-event
log. Both are additive new tables; no existing schema changes.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0024_identity"
down_revision: Union[str, None] = "0023_retrieval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base() -> list:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "librechat_identity_links",
        *_base(),
        sa.Column("supervoid_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("librechat_user_id", sa.String(length=120), nullable=True),
        sa.Column("librechat_email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("linked_at", sa.DateTime(), nullable=False),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
        sa.Column("linked_by_id", sa.String(), nullable=True),
        sa.Column("disabled_by_id", sa.String(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_librechat_identity_links_user", "librechat_identity_links",
                    ["supervoid_user_id"], unique=True)
    op.create_index("ix_librechat_identity_links_email", "librechat_identity_links",
                    ["librechat_email"], unique=False)
    op.create_index("ix_librechat_identity_links_lc_user", "librechat_identity_links",
                    ["librechat_user_id"], unique=False)
    op.create_index(op.f("ix_librechat_identity_links_supervoid_user_id"),
                    "librechat_identity_links", ["supervoid_user_id"], unique=False)
    op.create_index(op.f("ix_librechat_identity_links_status"),
                    "librechat_identity_links", ["status"], unique=False)
    op.create_index(op.f("ix_librechat_identity_links_linked_by_id"),
                    "librechat_identity_links", ["linked_by_id"], unique=False)

    op.create_table(
        "security_events",
        *_base(),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("supervoid_user_id", sa.String(), nullable=True),
        sa.Column("librechat_user_id", sa.String(length=120), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.Column("work_id", sa.String(), nullable=True),
        sa.Column("story_world_id", sa.String(), nullable=True),
        sa.Column("token_id", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(length=80), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
    )
    op.create_index("ix_security_events_type_created", "security_events",
                    ["event_type", "created_at"], unique=False)
    op.create_index("ix_security_events_email_created", "security_events",
                    ["email", "created_at"], unique=False)
    op.create_index("ix_security_events_user_created", "security_events",
                    ["supervoid_user_id", "created_at"], unique=False)
    op.create_index(op.f("ix_security_events_event_type"), "security_events",
                    ["event_type"], unique=False)
    op.create_index(op.f("ix_security_events_severity"), "security_events",
                    ["severity"], unique=False)
    op.create_index(op.f("ix_security_events_source"), "security_events",
                    ["source"], unique=False)
    op.create_index(op.f("ix_security_events_supervoid_user_id"), "security_events",
                    ["supervoid_user_id"], unique=False)
    op.create_index(op.f("ix_security_events_email"), "security_events",
                    ["email"], unique=False)
    op.create_index(op.f("ix_security_events_work_id"), "security_events",
                    ["work_id"], unique=False)
    op.create_index(op.f("ix_security_events_token_id"), "security_events",
                    ["token_id"], unique=False)


def downgrade() -> None:
    op.drop_table("security_events")
    op.drop_table("librechat_identity_links")
