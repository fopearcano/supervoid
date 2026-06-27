"""Schemas for cold-detail retrieval (Prompt 14)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.enums import (
    KnowledgeSourceType,
    RetrievalStage,
    RetrievalTrigger,
)


class RetrievalSearchRequest(BaseModel):
    """A trigger-gated retrieval request. ``trigger`` is mandatory — cold
    retrieval is exceptional and is invoked only under the defined conditions."""

    query: str = Field(min_length=1)
    trigger: RetrievalTrigger
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    source_types: Optional[list[KnowledgeSourceType]] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    rerank: Optional[bool] = None
    exclude_in_state: bool = True
    conversation_id: Optional[str] = None


class RetrievalHitRead(BaseModel):
    document_id: str
    chunk_id: str
    source_type: str
    source_id: str
    source_ref: str
    section_ref: Optional[str] = None
    citation: str
    snippet: str
    score: float
    vector_score: float
    text_score: float
    rerank_score: Optional[float] = None
    rank: int


class RetrievalResultRead(BaseModel):
    run_id: Optional[str] = None
    query: str
    trigger: RetrievalTrigger
    candidate_count: int
    returned_count: int
    reranked: bool
    backend: str
    embedding_model: Optional[str] = None
    sources_used: list[str] = []
    hits: list[RetrievalHitRead] = []
    evidence_block: str = ""


class RetrievalHitDiagnostic(BaseModel):
    chunk_id: str
    document_id: str
    source_type: str
    source_id: str
    source_ref: Optional[str] = None
    section_ref: Optional[str] = None
    citation: Optional[str] = None
    stage: RetrievalStage
    rank: int
    vector_score: Optional[float] = None
    text_score: Optional[float] = None
    score: float
    rerank_score: Optional[float] = None
    returned: bool
    snippet: Optional[str] = None


class RetrievalRunRead(BaseModel):
    id: str
    created_at: datetime
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    query: str
    trigger: RetrievalTrigger
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    source_types: list[Any] = []
    filters: dict[str, Any] = {}
    candidate_count: int
    returned_count: int
    reranked: bool
    exclude_in_state: bool
    embedding_model: Optional[str] = None
    vector_backend: Optional[str] = None
    latency_ms: Optional[float] = None
    sources_used: list[Any] = []


class RetrievalRunDetail(RetrievalRunRead):
    hits: list[RetrievalHitDiagnostic] = []


class KnowledgeDocumentRead(BaseModel):
    id: str
    source_type: KnowledgeSourceType
    source_id: str
    source_ref: str
    work_id: Optional[str] = None
    story_world_id: Optional[str] = None
    permission_scope: str
    title: Optional[str] = None
    status: str
    chunk_count: int
    indexed_at: Optional[datetime] = None


class ReindexRequest(BaseModel):
    source_type: Optional[KnowledgeSourceType] = None


class ReindexResult(BaseModel):
    indexed: int = 0
    unchanged: int = 0
    archived: int = 0
    skipped: int = 0
    documents: int = 0
