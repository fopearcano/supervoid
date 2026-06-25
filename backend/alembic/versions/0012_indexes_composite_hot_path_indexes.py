"""composite hot-path indexes

Revision ID: 0012_indexes
Revises: 0011_curation
Create Date: 2026-06-25 18:10:00.000000

Adds composite indexes for the command-centre / "my work" / agent-inbox hot
paths, whose queries filter on two columns together. These are pure additive
``CREATE INDEX`` statements (no table rebuild) and so apply identically on
SQLite and PostgreSQL. The matching ``Index`` definitions live on the models'
``__table_args__`` so a fresh ``create_all`` and the migration agree.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0012_indexes'
down_revision: Union[str, None] = '0011_curation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index name, table, [columns]) — order is upgrade order; downgrade reverses.
_INDEXES = [
    ("ix_production_items_assignee_status", "production_items", ["assignee_id", "status"]),
    ("ix_production_items_status_due_date", "production_items", ["status", "due_date"]),
    ("ix_production_items_work_status", "production_items", ["work_id", "status"]),
    ("ix_agent_findings_resolved_severity", "agent_findings", ["resolved", "severity"]),
    ("ix_agent_runs_target", "agent_runs", ["target_type", "target_id"]),
    ("ix_agent_runs_status_created_at", "agent_runs", ["status", "created_at"]),
    (
        "ix_agent_action_proposals_status_created_at",
        "agent_action_proposals",
        ["status", "created_at"],
    ),
    ("ix_integration_runs_point_status", "integration_runs", ["integration_point_id", "status"]),
]


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns, unique=False)


def downgrade() -> None:
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
