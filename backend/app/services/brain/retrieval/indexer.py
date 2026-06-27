"""Indexing: extract → chunk → embed eligible material, re-embedding ONLY
changed content.

Idempotent per source: ``(source_type, source_id)`` upserts one
``KnowledgeDocument``. A chunk is re-embedded only when its content hash is new;
unchanged chunks carry their existing vector forward. A source that no longer
yields text (deleted / ineligible) has its document marked ARCHIVED so it drops
out of retrieval without losing the row.

Adds + flushes only — the caller (admin endpoint, consumer savepoint, or a test)
owns the commit.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from app.config import settings
from app.models import EmbeddingRecord, KnowledgeChunk, KnowledgeDocument
from app.models.base import utcnow
from app.models.enums import KnowledgeDocStatus, KnowledgeSourceType
from app.services.ai.embeddings import embed_texts
from app.services.brain.retrieval import vector_backend
from app.services.brain.retrieval.chunking import Chunk, chunk_text, content_hash
from app.services.brain.retrieval.extractors import EXTRACTORS, enumerate_sources, extract


def _get_doc(
    session: Session, source_type: KnowledgeSourceType, source_id: str
) -> Optional[KnowledgeDocument]:
    return session.exec(
        select(KnowledgeDocument).where(
            KnowledgeDocument.source_type == source_type,
            KnowledgeDocument.source_id == source_id,
        )
    ).first()


def _delete_doc_chunks(session: Session, document_id: str) -> None:
    for er in session.exec(
        select(EmbeddingRecord).where(EmbeddingRecord.document_id == document_id)
    ).all():
        session.delete(er)
    for ch in session.exec(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
    ).all():
        session.delete(ch)
    session.flush()


def _build_chunks(content) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    for seg in content.segments:
        seg_chunks = chunk_text(
            seg.text, label=seg.label, start_index=idx,
            chunk_chars=settings.retrieval_chunk_chars,
            overlap=settings.retrieval_chunk_overlap,
        )
        chunks.extend(seg_chunks)
        idx += len(seg_chunks)
    return chunks


def reindex_source(
    session: Session, source_type: KnowledgeSourceType, source_id: str
) -> dict:
    """(Re)index one source. Returns a small status dict."""
    if not settings.retrieval_enabled:
        return {"status": "disabled"}
    content = extract(session, source_type, source_id)
    doc = _get_doc(session, source_type, source_id)

    if content is None:
        if doc is not None and doc.status != KnowledgeDocStatus.ARCHIVED:
            doc.status = KnowledgeDocStatus.ARCHIVED
            session.add(doc)
            session.flush()
            return {"status": "archived", "document_id": doc.id}
        return {"status": "skipped"}

    chunks = _build_chunks(content)
    if not chunks:
        return {"status": "skipped"}
    doc_hash = content_hash("|".join(c.content_hash for c in chunks))

    existed = doc is not None
    if doc is None:
        doc = KnowledgeDocument(source_type=source_type, source_id=source_id)

    # Capture existing vectors (by content hash) so unchanged chunks are NOT
    # re-embedded. Copy the values out before any delete.
    old_vecs: dict[str, dict] = {}
    if existed:
        for er in session.exec(
            select(EmbeddingRecord).where(EmbeddingRecord.document_id == doc.id)
        ).all():
            old_vecs[er.content_hash] = {
                "embedding": list(er.embedding), "model": er.model,
                "provider": er.provider, "dim": er.dim,
            }

    unchanged = existed and doc.content_hash == doc_hash and doc.chunk_count == len(chunks)

    # Update document metadata (scope / permission / title may shift even when
    # the unchanged content fast-path applies).
    doc.source_ref = content.source_ref
    doc.permission_scope = content.permission_scope
    doc.title = content.title
    doc.work_id = content.work_id
    doc.story_world_id = content.story_world_id
    doc.status = KnowledgeDocStatus.ACTIVE
    doc.meta = content.meta or {}
    doc.indexed_at = utcnow()
    session.add(doc)
    session.flush()  # ensure doc.id

    if unchanged:
        return {"status": "unchanged", "document_id": doc.id, "chunks": len(chunks)}

    _delete_doc_chunks(session, doc.id)

    to_embed = [c for c in chunks if c.content_hash not in old_vecs]
    fresh: dict[str, dict] = {}
    if to_embed:
        result = embed_texts([c.content for c in to_embed])
        for c, vec in zip(to_embed, result.vectors):
            fresh[c.content_hash] = {
                "embedding": vec, "model": result.model,
                "provider": result.provider, "dim": result.dim,
            }

    for c in chunks:
        row = KnowledgeChunk(
            document_id=doc.id, chunk_index=c.chunk_index, content=c.content,
            section_ref=c.section_ref, char_start=c.char_start, char_end=c.char_end,
            token_estimate=c.token_estimate, content_hash=c.content_hash,
        )
        session.add(row)
        session.flush()
        v = old_vecs.get(c.content_hash) or fresh[c.content_hash]
        er = EmbeddingRecord(
            chunk_id=row.id, document_id=doc.id, provider=v["provider"],
            model=v["model"], dim=v["dim"], embedding=v["embedding"],
            content_hash=c.content_hash,
        )
        session.add(er)
        session.flush()
        vector_backend.on_embedding_written(session, er)

    doc.content_hash = doc_hash
    doc.chunk_count = len(chunks)
    session.add(doc)
    session.flush()
    return {
        "status": "indexed", "document_id": doc.id, "chunks": len(chunks),
        "embedded": len(to_embed), "reused": len(chunks) - len(to_embed),
    }


def reindex_all(
    session: Session, source_type: Optional[KnowledgeSourceType] = None
) -> dict:
    """Backfill: (re)index every eligible source (optionally one type)."""
    types = [source_type] if source_type else list(EXTRACTORS.keys())
    tally = {"indexed": 0, "unchanged": 0, "archived": 0, "skipped": 0, "documents": 0}
    for st in types:
        for sid in enumerate_sources(session, st):
            res = reindex_source(session, st, sid)
            status = res.get("status", "skipped")
            tally[status] = tally.get(status, 0) + 1
            if status in ("indexed", "unchanged"):
                tally["documents"] += 1
    return tally
