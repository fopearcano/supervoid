"""brain outbox: drop domain/user foreign keys

Revision ID: 0015_brain_outbox
Revises: 0014_brain
Create Date: 2026-06-26 17:10:00.000000

The Brain is a strictly *downstream* observer: it records domain events and
compiled state, and must never block an upstream domain mutation (deleting a
Work, a StoryWorld or a User must not fail because a Brain event/state/memory
row still references it). This migration drops the foreign-key constraints from
the Brain tables back to ``works`` / ``story_worlds`` / ``users``, keeping the
columns and their indexes. Internal Brain foreign keys (conversation/message/
event/memory/decision self-references) are deliberately retained.

The 0014 constraints are unnamed, so a ``naming_convention`` is supplied to
``batch_alter_table`` — SQLite rebuilds each table, reflecting the unnamed FKs
under deterministic names that ``drop_constraint`` can then address.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0015_brain_outbox'
down_revision: Union[str, None] = '0014_brain'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Deterministic names for the otherwise-unnamed reflected foreign keys.
_NAMING = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}

# (table, [(local_column, referred_table)]) — the domain/user FKs to drop.
_DOMAIN_FKS = [
    ("brain_state_revisions", [("approved_by_id", "users")]),
    (
        "brain_conversations",
        [
            ("owner_user_id", "users"),
            ("story_world_id", "story_worlds"),
            ("work_id", "works"),
        ],
    ),
    (
        "brain_events",
        [
            ("actor_id", "users"),
            ("story_world_id", "story_worlds"),
            ("work_id", "works"),
        ],
    ),
    (
        "project_brain_states",
        [
            ("story_world_id", "story_worlds"),
            ("work_id", "works"),
        ],
    ),
    (
        "decision_records",
        [
            ("approver_id", "users"),
            ("proposer_id", "users"),
            ("story_world_id", "story_worlds"),
            ("work_id", "works"),
        ],
    ),
    (
        "brain_memory_items",
        [
            ("approved_by_id", "users"),
            ("created_by_id", "users"),
            ("member_user_id", "users"),
            ("story_world_id", "story_worlds"),
            ("work_id", "works"),
        ],
    ),
]


def _fk_name(table: str, column: str, referred: str) -> str:
    return f"fk_{table}_{column}_{referred}"


def upgrade() -> None:
    for table, fks in _DOMAIN_FKS:
        with op.batch_alter_table(
            table, schema=None, naming_convention=_NAMING
        ) as batch_op:
            for column, referred in fks:
                batch_op.drop_constraint(
                    _fk_name(table, column, referred), type_="foreignkey"
                )


def downgrade() -> None:
    for table, fks in _DOMAIN_FKS:
        with op.batch_alter_table(
            table, schema=None, naming_convention=_NAMING
        ) as batch_op:
            for column, referred in fks:
                batch_op.create_foreign_key(
                    _fk_name(table, column, referred),
                    referred,
                    [column],
                    ["id"],
                )
