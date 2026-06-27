"""Cold-detail retrieval (Prompt 14): the pgvector-backed evidence system.

An exceptional, permission-filtered evidence layer over studio detail that does
NOT belong in the hot compiled state. Public surface:

* ``indexer`` — extract → chunk → embed (only changed content) eligible material.
* ``search`` — hybrid (structured + full-text + vector + optional rerank)
  retrieval, permission-filtered before any content is returned, with diagnostics
  and stable internal citations.
"""
from app.services.brain.retrieval import chunking, extractors, indexer, search  # noqa: F401
