"""Cold-detail retrieval API (Prompt 14), under ``/api/brain/retrieval``.

* ``POST /search`` — trigger-gated, permission-filtered hybrid retrieval with
  internal citations and diagnostics. Any authenticated member may call it; the
  service returns only records they are authorised to see.
* ``GET /runs`` / ``GET /runs/{id}`` — retrieval diagnostics (own runs; admins
  see all): query, filters, candidates, reranked results, sources used.
* ``GET /documents`` — the indexed corpus (admin / ops).
* ``POST /reindex`` — (re)build the index, re-embedding only changed content
  (admin).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.auth import ADMIN_ONLY
from app.auth.dependencies import get_current_user
from app.db import get_session
from app.models import (
    KnowledgeDocument,
    RetrievalHit,
    RetrievalRun,
    User,
    UserRole,
)
from app.models.enums import KnowledgeSourceType
from app.schemas.retrieval import (
    KnowledgeDocumentRead,
    ReindexRequest,
    ReindexResult,
    RetrievalHitDiagnostic,
    RetrievalHitRead,
    RetrievalResultRead,
    RetrievalRunDetail,
    RetrievalRunRead,
    RetrievalSearchRequest,
)
from app.services.brain.retrieval import indexer, search

router = APIRouter(prefix="/brain/retrieval", tags=["retrieval"])


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _hit_read(h) -> RetrievalHitRead:
    """Adapt a search.Hit dataclass to the response schema."""
    return RetrievalHitRead(
        document_id=h.document_id, chunk_id=h.chunk_id, source_type=h.source_type,
        source_id=h.source_id, source_ref=h.source_ref, section_ref=h.section_ref,
        citation=h.citation, snippet=h.snippet, score=h.score,
        vector_score=h.vector_score, text_score=h.text_score,
        rerank_score=h.rerank_score, rank=h.rank,
    )


@router.post("/search", response_model=RetrievalResultRead)
def search_evidence(
    body: RetrievalSearchRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RetrievalResultRead:
    """Run a permission-filtered hybrid retrieval. The ``trigger`` field enforces
    that retrieval is invoked only as an exceptional evidence step."""
    result = search.retrieve(
        session, user, query=body.query, trigger=body.trigger,
        work_id=body.work_id, story_world_id=body.story_world_id,
        source_types=body.source_types, top_k=body.top_k, rerank=body.rerank,
        exclude_in_state=body.exclude_in_state, conversation_id=body.conversation_id,
    )
    session.commit()
    return RetrievalResultRead(
        run_id=result.run_id, query=result.query, trigger=result.trigger,
        candidate_count=result.candidate_count, returned_count=result.returned_count,
        reranked=result.reranked, backend=result.backend,
        embedding_model=result.embedding_model, sources_used=result.sources_used,
        evidence_block=result.evidence_block,
        hits=[_hit_read(h) for h in result.hits],
    )


@router.get("/runs", response_model=list[RetrievalRunRead])
def list_runs(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[RetrievalRunRead]:
    """Recent retrieval runs (your own; admins see all)."""
    stmt = select(RetrievalRun)
    if not _is_admin(user):
        stmt = stmt.where(RetrievalRun.user_id == user.id)
    stmt = stmt.order_by(RetrievalRun.created_at.desc()).offset(skip).limit(limit)
    return [RetrievalRunRead.model_validate(r, from_attributes=True) for r in session.exec(stmt).all()]


@router.get("/runs/{run_id}", response_model=RetrievalRunDetail)
def get_run(
    run_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> RetrievalRunDetail:
    """Full diagnostics for one run: query, filters, candidates, reranked
    results and sources used."""
    run = session.get(RetrievalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not _is_admin(user) and run.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your retrieval run")
    hits = session.exec(
        select(RetrievalHit).where(RetrievalHit.run_id == run_id).order_by(RetrievalHit.rank)
    ).all()
    detail = RetrievalRunDetail.model_validate(run, from_attributes=True)
    detail.hits = [RetrievalHitDiagnostic.model_validate(h, from_attributes=True) for h in hits]
    return detail


@router.get("/documents", response_model=list[KnowledgeDocumentRead], dependencies=ADMIN_ONLY)
def list_documents(
    session: Session = Depends(get_session),
    source_type: Optional[KnowledgeSourceType] = Query(default=None),
    work_id: Optional[str] = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[KnowledgeDocumentRead]:
    """The indexed corpus (admin / ops view)."""
    stmt = select(KnowledgeDocument)
    if source_type is not None:
        stmt = stmt.where(KnowledgeDocument.source_type == source_type)
    if work_id is not None:
        stmt = stmt.where(KnowledgeDocument.work_id == work_id)
    stmt = stmt.order_by(KnowledgeDocument.indexed_at.desc()).offset(skip).limit(limit)
    return [KnowledgeDocumentRead.model_validate(d, from_attributes=True) for d in session.exec(stmt).all()]


@router.post("/reindex", response_model=ReindexResult, dependencies=ADMIN_ONLY)
def reindex(
    body: ReindexRequest = ReindexRequest(),
    session: Session = Depends(get_session),
) -> ReindexResult:
    """(Re)index eligible material — re-embedding ONLY changed content (admin).
    Optionally scope to a single source type."""
    tally = indexer.reindex_all(session, source_type=body.source_type)
    session.commit()
    return ReindexResult(**{k: tally.get(k, 0) for k in
                            ("indexed", "unchanged", "archived", "skipped", "documents")})
