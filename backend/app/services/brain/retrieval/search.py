"""Hybrid, permission-filtered cold retrieval (Prompt 14).

Pipeline:

1. **Structured filter** — active documents in scope (work / story world /
   source types).
2. **Permission filter** — drop any document the user may not view BEFORE its
   content is ever scored or returned (rights/contract extracts need
   ``manage_rights``).
3. **Vector similarity** — cosine over chunk embeddings (pgvector ANN on
   PostgreSQL pre-ranks candidates; in-process cosine otherwise).
4. **Full-text** — PostgreSQL ``ts_rank`` on Postgres; portable keyword overlap
   elsewhere.
5. **Hybrid blend** + **optional rerank** (coverage-weighted; the hook where a
   cross-encoder could plug in).
6. **exclude-in-state** — skip sources already adequately in the compiled state.

Every run records full diagnostics (query, filters, candidates, reranked
results, sources used) and returns stable internal citations.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session, select

from app.config import settings
from app.models import (
    EmbeddingRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    RetrievalHit,
    RetrievalRun,
    User,
)
from app.models.base import utcnow
from app.models.enums import (
    KnowledgeDocStatus,
    PermissionScope,
    RetrievalStage,
    RetrievalTrigger,
    UserRole,
)
from app.services import brain, policy
from app.services.ai.embeddings import cosine, embed_texts
from app.services.brain.retrieval import vector_backend

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class Hit:
    document_id: str
    chunk_id: str
    source_type: str
    source_id: str
    source_ref: str
    section_ref: Optional[str]
    citation: str
    snippet: str
    score: float
    vector_score: float
    text_score: float
    rerank_score: Optional[float] = None
    rank: int = 0


@dataclass
class RetrievalResult:
    run_id: Optional[str]
    query: str
    trigger: RetrievalTrigger
    hits: list[Hit] = field(default_factory=list)
    candidate_count: int = 0
    returned_count: int = 0
    reranked: bool = False
    backend: str = "memory"
    embedding_model: Optional[str] = None
    sources_used: list[str] = field(default_factory=list)
    evidence_block: str = ""


# --- helpers ---------------------------------------------------------------
def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _keyword_score(query_tokens: set[str], content: str) -> float:
    """Portable full-text proxy: fraction of distinct query terms present."""
    if not query_tokens:
        return 0.0
    body = set(_tokens(content))
    return len(query_tokens & body) / len(query_tokens)


def _is_admin(user: User) -> bool:
    return user.role == UserRole.ADMIN


def _can_view_doc(session: Session, user: User, doc: KnowledgeDocument) -> bool:
    if _is_admin(user):
        return True
    if not (doc.work_id or doc.story_world_id):
        return False  # unscoped docs are admin-only (none are produced today)
    try:
        scope = PermissionScope(doc.permission_scope)
    except ValueError:
        scope = PermissionScope.VIEW_PROJECT
    return policy.can(session, user, scope, work_id=doc.work_id, story_world_id=doc.story_world_id)


def in_state_source_ids(
    session: Session, *, work_id: Optional[str], story_world_id: Optional[str]
) -> set[str]:
    """Source ids already adequately represented in the compiled state — so cold
    retrieval doesn't re-surface what the hot state already carries."""
    ids: set[str] = set()
    state = brain.get_project_state(session, work_id=work_id, story_world_id=story_world_id)
    if state is None:
        return ids
    ss = state.structured_state or {}
    canon = ss.get("canon_facts", {}) if isinstance(ss.get("canon_facts"), dict) else {}
    for d in canon.get("decisions", []) or []:
        if isinstance(d, dict) and d.get("id"):
            ids.add(d["id"])
    for f in canon.get("facts", []) or []:
        if isinstance(f, dict) and f.get("id"):
            ids.add(f["id"])
    for d in ss.get("recent_decisions", []) or []:
        if isinstance(d, dict) and d.get("id"):
            ids.add(d["id"])
    return ids


def _pg_text_ranks(session: Session, query: str, chunk_ids: list[str]) -> dict[str, float]:
    """PostgreSQL ts_rank for the candidate chunks (empty dict if unavailable)."""
    if not chunk_ids or vector_backend.active_backend(session) != "pgvector":
        return {}
    try:  # pragma: no cover - PostgreSQL only
        from sqlalchemy import text

        rows = session.execute(
            text(
                "SELECT id, ts_rank(to_tsvector('english', content), "
                "plainto_tsquery('english', :q)) AS r "
                "FROM knowledge_chunks WHERE id = ANY(:ids)"
            ),
            {"q": query, "ids": chunk_ids},
        ).all()
        ranks = {r[0]: float(r[1] or 0.0) for r in rows}
        top = max(ranks.values(), default=0.0)
        return {k: (v / top if top > 0 else 0.0) for k, v in ranks.items()}
    except Exception:  # noqa: BLE001
        return {}


def _citation(source_type: str, source_id: str, section_ref: Optional[str]) -> str:
    ref = section_ref or "doc"
    return f"[{source_type}:{source_id} · {ref}]"


def _fence(hit: Hit) -> str:
    safe = (hit.snippet or "").replace(">>>", "> > >").replace("<<<", "< < <")
    return (
        f'<<<EVIDENCE cite="{hit.citation}" source="{hit.source_ref}">>>\n'
        f"{safe}\n"
        "<<<END_EVIDENCE>>>"
    )


def render_evidence_block(hits: list[Hit]) -> str:
    """Fenced, citable evidence the Brain treats strictly as DATA."""
    return "\n".join(_fence(h) for h in hits)


# --- the search ------------------------------------------------------------
def retrieve(
    session: Session,
    user: User,
    *,
    query: str,
    trigger: RetrievalTrigger,
    work_id: Optional[str] = None,
    story_world_id: Optional[str] = None,
    source_types: Optional[list] = None,
    top_k: Optional[int] = None,
    candidates: Optional[int] = None,
    rerank: Optional[bool] = None,
    exclude_in_state: bool = False,
    conversation_id: Optional[str] = None,
    record: bool = True,
) -> RetrievalResult:
    """Run a permission-filtered hybrid retrieval. ``trigger`` is mandatory: cold
    retrieval is exceptional, never a per-turn reconstruction."""
    started = time.perf_counter()
    top_k = top_k or settings.retrieval_top_k
    candidates = candidates or settings.retrieval_candidates
    rerank = settings.retrieval_rerank if rerank is None else rerank
    backend = vector_backend.active_backend(session)
    query = (query or "").strip()

    result = RetrievalResult(
        run_id=None, query=query, trigger=trigger, reranked=False, backend=backend
    )
    if not query or not settings.retrieval_enabled:
        if record:
            _record_run(session, user, result, work_id, story_world_id, source_types,
                        exclude_in_state, conversation_id, started, [])
        return result

    qvec = embed_texts([query]).vectors[0]
    result.embedding_model = settings.embedding_model
    query_tokens = set(_tokens(query))

    # 1. structured filter — candidate documents in scope.
    doc_stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.status == KnowledgeDocStatus.ACTIVE
    )
    if work_id:
        doc_stmt = doc_stmt.where(KnowledgeDocument.work_id == work_id)
    if story_world_id:
        doc_stmt = doc_stmt.where(KnowledgeDocument.story_world_id == story_world_id)
    if source_types:
        wanted = [getattr(s, "value", s) for s in source_types]
        doc_stmt = doc_stmt.where(KnowledgeDocument.source_type.in_(wanted))
    docs = list(session.exec(doc_stmt).all())

    # 2. permission filter — BEFORE any content is scored/returned.
    docs = [d for d in docs if _can_view_doc(session, user, d)]

    # exclude material already adequately present in the compiled state.
    if exclude_in_state:
        skip = in_state_source_ids(session, work_id=work_id, story_world_id=story_world_id)
        docs = [d for d in docs if d.source_id not in skip]

    doc_by_id = {d.id: d for d in docs}
    if not doc_by_id:
        if record:
            _record_run(session, user, result, work_id, story_world_id, source_types,
                        exclude_in_state, conversation_id, started, [])
        return result

    # 3. candidate embeddings (pgvector ANN pre-rank when available).
    emb_stmt = select(EmbeddingRecord).where(
        EmbeddingRecord.document_id.in_(list(doc_by_id.keys()))
    )
    ann_ids = vector_backend.ann_candidate_ids(session, qvec, limit=candidates * 5)
    if ann_ids:
        emb_stmt = emb_stmt.where(EmbeddingRecord.chunk_id.in_(ann_ids))
    embs = list(session.exec(emb_stmt.limit(max(candidates * 20, 200))).all())
    chunk_by_id = {
        c.id: c
        for c in session.exec(
            select(KnowledgeChunk).where(
                KnowledgeChunk.id.in_([e.chunk_id for e in embs])
            )
        ).all()
    }

    # 4. score (vector + full-text) and 5. blend.
    pg_ranks = _pg_text_ranks(session, query, [e.chunk_id for e in embs])
    tw, vw = settings.retrieval_text_weight, settings.retrieval_vector_weight
    scored: list[Hit] = []
    for er in embs:
        chunk = chunk_by_id.get(er.chunk_id)
        doc = doc_by_id.get(er.document_id)
        if chunk is None or doc is None:
            continue
        vscore = max(0.0, cosine(qvec, er.embedding))
        tscore = pg_ranks.get(er.chunk_id) if pg_ranks else _keyword_score(query_tokens, chunk.content)
        tscore = float(tscore or 0.0)
        blended = vw * vscore + tw * tscore
        snippet = (chunk.content or "")[:280]
        citation = _citation(doc.source_type.value, doc.source_id, chunk.section_ref)
        scored.append(Hit(
            document_id=doc.id, chunk_id=chunk.id,
            source_type=doc.source_type.value, source_id=doc.source_id,
            source_ref=doc.source_ref, section_ref=chunk.section_ref,
            citation=citation, snippet=snippet, score=blended,
            vector_score=vscore, text_score=tscore,
        ))
    scored.sort(key=lambda h: h.score, reverse=True)
    scored = scored[:candidates]
    result.candidate_count = len(scored)

    # 6. optional rerank (coverage-weighted; deterministic).
    reranked_set: set[str] = set()
    ordered = scored
    if rerank and scored:
        for h in scored:
            coverage = _keyword_score(query_tokens, h.snippet)
            h.rerank_score = round(h.score * (0.5 + 0.5 * coverage), 6)
            reranked_set.add(h.chunk_id)
        ordered = sorted(scored, key=lambda h: (h.rerank_score or 0.0), reverse=True)
        result.reranked = True

    # cutoff + min score.
    returned = [h for h in ordered if h.score >= settings.retrieval_min_score][:top_k]
    for i, h in enumerate(returned):
        h.rank = i + 1
    result.hits = returned
    result.returned_count = len(returned)
    result.sources_used = [h.citation for h in returned]
    result.evidence_block = render_evidence_block(returned)

    if record:
        _record_run(session, user, result, work_id, story_world_id, source_types,
                    exclude_in_state, conversation_id, started, ordered,
                    returned_ids={h.chunk_id for h in returned}, reranked_ids=reranked_set)
    return result


def _record_run(
    session: Session, user: User, result: RetrievalResult,
    work_id, story_world_id, source_types, exclude_in_state, conversation_id,
    started: float, ordered: list[Hit], *,
    returned_ids: Optional[set] = None, reranked_ids: Optional[set] = None,
) -> None:
    """Persist the diagnostics: the run + every scored candidate hit."""
    returned_ids = returned_ids or set()
    reranked_ids = reranked_ids or set()
    latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
    run = RetrievalRun(
        user_id=user.id, conversation_id=conversation_id, query=result.query,
        trigger=result.trigger, work_id=work_id, story_world_id=story_world_id,
        source_types=[getattr(s, "value", s) for s in (source_types or [])],
        filters={
            "work_id": work_id, "story_world_id": story_world_id,
            "source_types": [getattr(s, "value", s) for s in (source_types or [])],
            "exclude_in_state": exclude_in_state,
            "top_k": settings.retrieval_top_k,
        },
        candidate_count=result.candidate_count, returned_count=result.returned_count,
        reranked=result.reranked, exclude_in_state=exclude_in_state,
        embedding_model=result.embedding_model, vector_backend=result.backend,
        latency_ms=latency_ms, sources_used=result.sources_used,
    )
    session.add(run)
    session.flush()
    result.run_id = run.id
    for i, h in enumerate(ordered):
        if h.chunk_id in returned_ids:
            stage = RetrievalStage.RETURNED
        elif h.chunk_id in reranked_ids:
            stage = RetrievalStage.RERANKED
        else:
            stage = RetrievalStage.CANDIDATE
        session.add(RetrievalHit(
            run_id=run.id, document_id=h.document_id, chunk_id=h.chunk_id,
            source_type=h.source_type, source_id=h.source_id, source_ref=h.source_ref,
            section_ref=h.section_ref, citation=h.citation, stage=stage,
            rank=(h.rank or i + 1), vector_score=h.vector_score, text_score=h.text_score,
            score=h.score, rerank_score=h.rerank_score,
            returned=h.chunk_id in returned_ids, snippet=h.snippet,
        ))
    session.flush()
