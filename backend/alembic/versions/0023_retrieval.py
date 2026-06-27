"""cold-detail retrieval index (pgvector evidence system)

Revision ID: 0023_retrieval
Revises: 0022_memory_review
Create Date: 2026-06-27 14:00:00.000000

Prompt 14. Creates the five retrieval tables — knowledge_documents,
knowledge_chunks, embedding_records, retrieval_runs, retrieval_hits — with a
PORTABLE schema (the embedding vector is a JSON ``list[float]``) so the suite's
SQLite and production PostgreSQL share one definition.

On PostgreSQL only (dialect-gated), this additionally:
  * enables the ``vector`` extension,
  * adds a parallel ``embedding_vec vector(N)`` column + an IVFFlat ANN index on
    embedding_records (N = settings.embedding_dim),
  * adds a GIN full-text index on knowledge_chunks.content.
These are accelerators; the JSON vector remains the canonical store, and the
in-process cosine + keyword fallback keeps SQLite fully functional.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings


revision: str = "0023_retrieval"
down_revision: Union[str, None] = "0022_memory_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base_cols() -> list:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        *_base_cols(),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=200), nullable=False),
        sa.Column("work_id", sa.String(), nullable=True),
        sa.Column("story_world_id", sa.String(), nullable=True),
        sa.Column("permission_scope", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False),
    )
    op.create_index("ix_knowledge_documents_source", "knowledge_documents",
                    ["source_type", "source_id"], unique=True)
    op.create_index("ix_knowledge_documents_scope", "knowledge_documents",
                    ["work_id", "story_world_id"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_source_type"), "knowledge_documents",
                    ["source_type"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_source_id"), "knowledge_documents",
                    ["source_id"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_work_id"), "knowledge_documents",
                    ["work_id"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_story_world_id"), "knowledge_documents",
                    ["story_world_id"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_status"), "knowledge_documents",
                    ["status"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_content_hash"), "knowledge_documents",
                    ["content_hash"], unique=False)
    op.create_index(op.f("ix_knowledge_documents_indexed_at"), "knowledge_documents",
                    ["indexed_at"], unique=False)

    op.create_table(
        "knowledge_chunks",
        *_base_cols(),
        sa.Column("document_id", sa.String(), sa.ForeignKey("knowledge_documents.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("section_ref", sa.String(length=200), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_knowledge_chunks_document", "knowledge_chunks",
                    ["document_id", "chunk_index"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_document_id"), "knowledge_chunks",
                    ["document_id"], unique=False)
    op.create_index(op.f("ix_knowledge_chunks_content_hash"), "knowledge_chunks",
                    ["content_hash"], unique=False)

    op.create_table(
        "embedding_records",
        *_base_cols(),
        sa.Column("chunk_id", sa.String(), sa.ForeignKey("knowledge_chunks.id"), nullable=False),
        sa.Column("document_id", sa.String(), sa.ForeignKey("knowledge_documents.id"), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_embedding_records_chunk", "embedding_records",
                    ["chunk_id"], unique=True)
    op.create_index("ix_embedding_records_document", "embedding_records",
                    ["document_id"], unique=False)
    op.create_index(op.f("ix_embedding_records_chunk_id"), "embedding_records",
                    ["chunk_id"], unique=False)
    op.create_index(op.f("ix_embedding_records_document_id"), "embedding_records",
                    ["document_id"], unique=False)
    op.create_index(op.f("ix_embedding_records_content_hash"), "embedding_records",
                    ["content_hash"], unique=False)

    op.create_table(
        "retrieval_runs",
        *_base_cols(),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("conversation_id", sa.String(), nullable=True),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("work_id", sa.String(), nullable=True),
        sa.Column("story_world_id", sa.String(), nullable=True),
        sa.Column("source_types", sa.JSON(), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("returned_count", sa.Integer(), nullable=False),
        sa.Column("reranked", sa.Boolean(), nullable=False),
        sa.Column("exclude_in_state", sa.Boolean(), nullable=False),
        sa.Column("embedding_model", sa.String(length=160), nullable=True),
        sa.Column("vector_backend", sa.String(length=20), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("sources_used", sa.JSON(), nullable=False),
    )
    op.create_index("ix_retrieval_runs_user_created", "retrieval_runs",
                    ["user_id", "created_at"], unique=False)
    op.create_index(op.f("ix_retrieval_runs_user_id"), "retrieval_runs",
                    ["user_id"], unique=False)
    op.create_index(op.f("ix_retrieval_runs_conversation_id"), "retrieval_runs",
                    ["conversation_id"], unique=False)
    op.create_index(op.f("ix_retrieval_runs_trigger"), "retrieval_runs",
                    ["trigger"], unique=False)
    op.create_index(op.f("ix_retrieval_runs_work_id"), "retrieval_runs",
                    ["work_id"], unique=False)
    op.create_index(op.f("ix_retrieval_runs_story_world_id"), "retrieval_runs",
                    ["story_world_id"], unique=False)

    op.create_table(
        "retrieval_hits",
        *_base_cols(),
        sa.Column("run_id", sa.String(), sa.ForeignKey("retrieval_runs.id"), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("chunk_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=200), nullable=True),
        sa.Column("section_ref", sa.String(length=200), nullable=True),
        sa.Column("citation", sa.String(length=300), nullable=True),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("vector_score", sa.Float(), nullable=True),
        sa.Column("text_score", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rerank_score", sa.Float(), nullable=True),
        sa.Column("returned", sa.Boolean(), nullable=False),
        sa.Column("snippet", sa.String(), nullable=True),
    )
    op.create_index("ix_retrieval_hits_run", "retrieval_hits",
                    ["run_id", "rank"], unique=False)
    op.create_index(op.f("ix_retrieval_hits_run_id"), "retrieval_hits",
                    ["run_id"], unique=False)
    op.create_index(op.f("ix_retrieval_hits_document_id"), "retrieval_hits",
                    ["document_id"], unique=False)
    op.create_index(op.f("ix_retrieval_hits_chunk_id"), "retrieval_hits",
                    ["chunk_id"], unique=False)
    op.create_index(op.f("ix_retrieval_hits_stage"), "retrieval_hits",
                    ["stage"], unique=False)
    op.create_index(op.f("ix_retrieval_hits_returned"), "retrieval_hits",
                    ["returned"], unique=False)

    # --- PostgreSQL-only accelerators: pgvector ANN + full-text GIN -----------
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        dim = int(settings.embedding_dim)
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute(f"ALTER TABLE embedding_records ADD COLUMN embedding_vec vector({dim})")
        # IVFFlat cosine index (lists tuned for small/medium corpora).
        op.execute(
            "CREATE INDEX ix_embedding_records_vec ON embedding_records "
            "USING ivfflat (embedding_vec vector_cosine_ops) WITH (lists = 100)"
        )
        # Full-text search over chunk content (expression index, no stored tsv).
        op.execute(
            "CREATE INDEX ix_knowledge_chunks_fts ON knowledge_chunks "
            "USING gin (to_tsvector('english', content))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_fts")
        op.execute("DROP INDEX IF EXISTS ix_embedding_records_vec")
        op.execute("ALTER TABLE embedding_records DROP COLUMN IF EXISTS embedding_vec")

    op.drop_table("retrieval_hits")
    op.drop_table("retrieval_runs")
    op.drop_table("embedding_records")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
