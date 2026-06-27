"""Vector storage backend — dialect-aware.

The embedding vector is always stored as portable JSON on ``EmbeddingRecord``.
On PostgreSQL we ALSO mirror it into a ``vector(N)`` column (pgvector) and use the
ANN index to pre-rank candidates; on SQLite (and any non-pg dialect) we score
candidates with in-process cosine over the JSON vectors. Behaviour is identical;
only the candidate-ranking acceleration differs.

The pgvector path is lazily imported so SQLite/air-gapped installs never need the
``pgvector`` / ``psycopg`` packages.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from app.config import settings


def active_backend(session: Session) -> str:
    """'pgvector' on PostgreSQL when enabled, else 'memory'."""
    mode = (settings.retrieval_vector_backend or "auto").lower()
    if mode == "memory":
        return "memory"
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql" and mode in ("auto", "pgvector"):
        return "pgvector"
    return "memory"


def on_embedding_written(session: Session, record) -> None:
    """Sync the JSON vector into the pgvector column (Postgres only; no-op else)."""
    if active_backend(session) != "pgvector":
        return
    try:  # pragma: no cover - exercised only against PostgreSQL
        from sqlalchemy import text

        vec_literal = "[" + ",".join(repr(float(x)) for x in record.embedding) + "]"
        session.execute(
            text("UPDATE embedding_records SET embedding_vec = :vec WHERE id = :id"),
            {"vec": vec_literal, "id": record.id},
        )
    except Exception:  # noqa: BLE001 - acceleration only; JSON store remains canonical
        pass


def ann_candidate_ids(
    session: Session, query_vector: list[float], *, limit: int,
    document_ids: Optional[list[str]] = None,
) -> Optional[list[str]]:
    """Return chunk ids ranked by ANN cosine distance, or None when pgvector is
    unavailable (caller then falls back to in-process cosine). Optionally
    restricted to a candidate document set."""
    if active_backend(session) != "pgvector":
        return None
    try:  # pragma: no cover - PostgreSQL only
        from sqlalchemy import text

        vec_literal = "[" + ",".join(repr(float(x)) for x in query_vector) + "]"
        sql = (
            "SELECT chunk_id FROM embedding_records "
            "WHERE embedding_vec IS NOT NULL "
        )
        params: dict = {"vec": vec_literal, "k": int(limit)}
        if document_ids:
            sql += "AND document_id = ANY(:docs) "
            params["docs"] = document_ids
        sql += "ORDER BY embedding_vec <=> CAST(:vec AS vector) LIMIT :k"
        rows = session.execute(text(sql), params).all()
        return [r[0] for r in rows]
    except Exception:  # noqa: BLE001
        return None
