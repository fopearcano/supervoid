"""optional fine-tuning data pipeline: examples, datasets, adapters

Revision ID: 0025_tuning
Revises: 0024_identity
Create Date: 2026-06-27 18:00:00.000000

Prompt 18. The PREPARED (not auto-run) LoRA/PEFT fine-tuning data pipeline:
candidate examples (behaviour, not facts), versioned datasets, and an adapter
registry. All three are additive new tables; no existing schema changes.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0025_tuning"
down_revision: Union[str, None] = "0024_identity"
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
        "tuning_examples",
        *_base(),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("work_id", sa.String(), nullable=True),
        sa.Column("story_world_id", sa.String(), nullable=True),
        sa.Column("task_category", sa.String(length=60), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("target_output", sa.String(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=False),
        sa.Column("expected_tools", sa.JSON(), nullable=False),
        sa.Column("forbidden_tools", sa.JSON(), nullable=False),
        sa.Column("approval_behaviour", sa.String(length=30), nullable=False),
        sa.Column("retrieval_expectation", sa.String(length=20), nullable=False),
        sa.Column("refusal", sa.Boolean(), nullable=False),
        sa.Column("rationale", sa.String(length=1000), nullable=False),
        sa.Column("anonymised", sa.Boolean(), nullable=False),
        sa.Column("contains_sensitive", sa.Boolean(), nullable=False),
        sa.Column("redactions", sa.JSON(), nullable=False),
        sa.Column("sanitization_notes", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("created_by_id", sa.String(), nullable=True),
        sa.Column("reviewed_by_id", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_note", sa.String(length=500), nullable=True),
        sa.Column("dataset_version", sa.String(length=40), nullable=True),
        sa.Column("split", sa.String(length=10), nullable=True),
    )
    op.create_index("ix_tuning_examples_status_kind", "tuning_examples", ["status", "kind"])
    op.create_index("ix_tuning_examples_dataset", "tuning_examples", ["dataset_version", "split"])
    op.create_index("ix_tuning_examples_project_category", "tuning_examples", ["work_id", "task_category"])
    op.create_index(op.f("ix_tuning_examples_kind"), "tuning_examples", ["kind"])
    op.create_index(op.f("ix_tuning_examples_status"), "tuning_examples", ["status"])
    op.create_index(op.f("ix_tuning_examples_source_type"), "tuning_examples", ["source_type"])
    op.create_index(op.f("ix_tuning_examples_source_id"), "tuning_examples", ["source_id"])
    op.create_index(op.f("ix_tuning_examples_work_id"), "tuning_examples", ["work_id"])
    op.create_index(op.f("ix_tuning_examples_task_category"), "tuning_examples", ["task_category"])
    op.create_index(op.f("ix_tuning_examples_contains_sensitive"), "tuning_examples", ["contains_sensitive"])
    op.create_index(op.f("ix_tuning_examples_content_hash"), "tuning_examples", ["content_hash"])
    op.create_index(op.f("ix_tuning_examples_created_by_id"), "tuning_examples", ["created_by_id"])
    op.create_index(op.f("ix_tuning_examples_dataset_version"), "tuning_examples", ["dataset_version"])

    op.create_table(
        "tuning_datasets",
        *_base(),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("example_count", sa.Integer(), nullable=False),
        sa.Column("train_count", sa.Integer(), nullable=False),
        sa.Column("val_count", sa.Integer(), nullable=False),
        sa.Column("split_strategy", sa.String(length=40), nullable=False),
        sa.Column("val_fraction", sa.Float(), nullable=False),
        sa.Column("train_path", sa.String(length=300), nullable=True),
        sa.Column("val_path", sa.String(length=300), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.String(), nullable=True),
    )
    op.create_index("ix_tuning_datasets_version", "tuning_datasets", ["version"], unique=True)
    op.create_index(op.f("ix_tuning_datasets_status"), "tuning_datasets", ["status"])
    op.create_index(op.f("ix_tuning_datasets_created_by_id"), "tuning_datasets", ["created_by_id"])

    op.create_table(
        "tuning_adapters",
        *_base(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("base_model", sa.String(length=160), nullable=False),
        sa.Column("dataset_version", sa.String(length=40), nullable=True),
        sa.Column("training_parameters", sa.JSON(), nullable=False),
        sa.Column("licence", sa.String(length=80), nullable=False),
        sa.Column("artifact_ref", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("evaluation_results", sa.JSON(), nullable=False),
        sa.Column("beats_base", sa.Boolean(), nullable=True),
        sa.Column("permissions_preserved", sa.Boolean(), nullable=True),
        sa.Column("approval_preserved", sa.Boolean(), nullable=True),
        sa.Column("deploy_blocked_reason", sa.String(length=300), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("deployed_at", sa.DateTime(), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.String(), nullable=True),
        sa.Column("approved_by_id", sa.String(), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
    )
    op.create_index("ix_tuning_adapters_status", "tuning_adapters", ["status"])
    op.create_index("ix_tuning_adapters_name", "tuning_adapters", ["name"])
    op.create_index(op.f("ix_tuning_adapters_dataset_version"), "tuning_adapters", ["dataset_version"])
    op.create_index(op.f("ix_tuning_adapters_created_by_id"), "tuning_adapters", ["created_by_id"])


def downgrade() -> None:
    op.drop_table("tuning_adapters")
    op.drop_table("tuning_datasets")
    op.drop_table("tuning_examples")
