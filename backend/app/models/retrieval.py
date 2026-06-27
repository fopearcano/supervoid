"""Cold-detail retrieval index (Prompt 14: pgvector evidence system).

An *exceptional* evidence layer for specific questions — NOT a second copy of the
hot compiled state. Eligible studio material is chunked, embedded and stored here
so the Brain can cite a precise source when (and only when) a turn genuinely needs
historical justification or a detailed record.

Portability: the embedding vector is stored as a portable JSON ``list[float]`` so
the same schema works on SQLite (tests) and PostgreSQL (production). On Postgres
a parallel ``embedding_vec vector(N)`` column + ANN index and a full-text GIN
index are added by the migration (dialect-gated) and used as accelerators; the
JSON vector remains the canonical store. **No binary image data is ever stored
here** — only text and text metadata.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field

from app.models.base import BaseEntity
from app.models.enums import (
    KnowledgeDocStatus,
    KnowledgeSourceType,
    RetrievalStage,
    RetrievalTrigger,
)


class KnowledgeDocument(BaseEntity, table=True):
    """One indexed source (a manuscript, a decision, a rights extract, …).

    ``(source_type, source_id)`` is unique so re-indexing upserts in place.
    ``permission_scope`` is the PermissionScope *value* a user must hold on the
    document's project to be shown its content (``view_project`` by default;
    ``manage_rights`` for rights/contract extracts)."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index("ix_knowledge_documents_source", "source_type", "source_id", unique=True),
        Index("ix_knowledge_documents_scope", "work_id", "story_world_id"),
    )

    source_type: KnowledgeSourceType = Field(index=True)
    source_id: str = Field(max_length=64, index=True)
    source_ref: str = Field(default="", max_length=200)  # stable human/citation ref

    work_id: Optional[str] = Field(default=None, index=True)
    story_world_id: Optional[str] = Field(default=None, index=True)
    permission_scope: str = Field(default="view_project", max_length=40)

    title: Optional[str] = Field(default=None, max_length=300)
    status: KnowledgeDocStatus = Field(default=KnowledgeDocStatus.ACTIVE, index=True)
    content_hash: Optional[str] = Field(default=None, max_length=64, index=True)
    chunk_count: int = Field(default=0, ge=0)
    indexed_at: Optional[datetime] = Field(default=None, index=True)
    meta: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class KnowledgeChunk(BaseEntity, table=True):
    """A retrievable slice of a document, with a stable section/line reference."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_knowledge_chunks_document", "document_id", "chunk_index"),
    )

    document_id: str = Field(foreign_key="knowledge_documents.id", index=True)
    chunk_index: int = Field(default=0, ge=0)
    content: str = Field(default="")
    section_ref: Optional[str] = Field(default=None, max_length=200)  # e.g. "synopsis", "panel 3 · dialogue"
    char_start: int = Field(default=0, ge=0)
    char_end: int = Field(default=0, ge=0)
    token_estimate: int = Field(default=0, ge=0)
    content_hash: str = Field(default="", max_length=64, index=True)


class EmbeddingRecord(BaseEntity, table=True):
    """The embedding for one chunk. ``content_hash`` lets us re-embed ONLY changed
    content. The vector is JSON here (portable); Postgres mirrors it into a
    pgvector column for ANN search."""

    __tablename__ = "embedding_records"
    __table_args__ = (
        Index("ix_embedding_records_chunk", "chunk_id", unique=True),
        Index("ix_embedding_records_document", "document_id"),
    )

    chunk_id: str = Field(foreign_key="knowledge_chunks.id", index=True)
    document_id: str = Field(foreign_key="knowledge_documents.id", index=True)
    provider: str = Field(default="", max_length=40)
    model: str = Field(default="", max_length=160)
    dim: int = Field(default=0, ge=0)
    embedding: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    content_hash: str = Field(default="", max_length=64, index=True)


class RetrievalRun(BaseEntity, table=True):
    """Diagnostics for one retrieval: query, filters, candidate/return counts,
    whether reranking ran, the sources actually used, and timing."""

    __tablename__ = "retrieval_runs"
    __table_args__ = (
        Index("ix_retrieval_runs_user_created", "user_id", "created_at"),
    )

    user_id: Optional[str] = Field(default=None, index=True)
    conversation_id: Optional[str] = Field(default=None, index=True)
    query: str = Field(default="")
    trigger: RetrievalTrigger = Field(index=True)

    work_id: Optional[str] = Field(default=None, index=True)
    story_world_id: Optional[str] = Field(default=None, index=True)
    source_types: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    filters: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    candidate_count: int = Field(default=0, ge=0)
    returned_count: int = Field(default=0, ge=0)
    reranked: bool = Field(default=False)
    exclude_in_state: bool = Field(default=False)
    embedding_model: Optional[str] = Field(default=None, max_length=160)
    vector_backend: Optional[str] = Field(default=None, max_length=20)
    latency_ms: Optional[float] = Field(default=None)
    sources_used: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))


class RetrievalHit(BaseEntity, table=True):
    """One scored candidate in a retrieval run (diagnostics + citation source).

    ``stage`` distinguishes candidates from reranked/returned hits, so the full
    funnel (candidates → reranked → sources used) is auditable."""

    __tablename__ = "retrieval_hits"
    __table_args__ = (
        Index("ix_retrieval_hits_run", "run_id", "rank"),
    )

    run_id: str = Field(foreign_key="retrieval_runs.id", index=True)
    document_id: str = Field(max_length=64, index=True)
    chunk_id: str = Field(max_length=64, index=True)
    source_type: str = Field(default="", max_length=40)
    source_id: str = Field(default="", max_length=64)
    source_ref: Optional[str] = Field(default=None, max_length=200)
    section_ref: Optional[str] = Field(default=None, max_length=200)
    citation: Optional[str] = Field(default=None, max_length=300)

    stage: RetrievalStage = Field(default=RetrievalStage.CANDIDATE, index=True)
    rank: int = Field(default=0, ge=0)
    vector_score: Optional[float] = Field(default=None)
    text_score: Optional[float] = Field(default=None)
    score: float = Field(default=0.0)
    rerank_score: Optional[float] = Field(default=None)
    returned: bool = Field(default=False, index=True)
    snippet: Optional[str] = Field(default=None)
