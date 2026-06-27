# Cold-detail retrieval with pgvector (Prompt 14)

An **exceptional evidence system** for specific questions — not a second copy of
the hot compiled state, and never a per-turn reconstruction of the project. When
a turn genuinely needs a precise source, retrieval finds it, filters it by
permission, and returns it with an internal citation.

## Models

| Model | Purpose |
|---|---|
| `KnowledgeDocument` | One indexed source (`(source_type, source_id)` unique). Carries scope (`work_id`/`story_world_id`), the `permission_scope` required to read it, a stable `source_ref`, a content hash and `status`. |
| `KnowledgeChunk` | A retrievable slice with a stable `section_ref` (e.g. `"synopsis"`, `"panel 3 · dialogue"`) and char offsets. |
| `EmbeddingRecord` | The chunk's embedding (portable JSON vector) + its `content_hash` (so only changed content is re-embedded). |
| `RetrievalRun` | Diagnostics for one retrieval: query, filters, candidate/return counts, rerank flag, sources used, timing. |
| `RetrievalHit` | One scored candidate (stage = candidate / reranked / returned) — the audit trail and citation source. |

## Eligible material

Manuscripts, editorial notes, decision rationale, project documentation
(reviews), knowledge entities, asset **metadata** (title/description/tags/notes/
text specs — never pixels), graphic-novel **panel** descriptions, screen
**scene** descriptions, **approved** conversation summaries, and rights/contract
**extracts** (gated on `manage_rights`). Extractors live in
`app/services/brain/retrieval/extractors.py`; each pulls only text and resolves
the source's project scope + required permission.

**No binary image data is ever stored.** Storage keys, checksums, byte sizes and
geometry are explicitly excluded; only the text around an asset is indexed.

## Hybrid retrieval

`app/services/brain/retrieval/search.py::retrieve()`:

1. **Structured filter** — active documents in scope (work / story world / source
   types).
2. **Permission filter** — every candidate document is checked with the policy
   service for the calling user *before its content is scored or returned*.
   Rights/contract extracts require `manage_rights` (strict); everything else
   `view_project`.
3. **Vector similarity** — cosine over chunk embeddings.
4. **Full-text** — PostgreSQL `ts_rank` on Postgres; a portable keyword-overlap
   proxy elsewhere.
5. **Hybrid blend** (`retrieval_vector_weight` · vector + `retrieval_text_weight`
   · text) and an optional **rerank** pass (coverage-weighted; the hook where a
   cross-encoder can plug in).
6. **exclude-in-state** — skip sources already adequately present in the compiled
   state (so retrieval never re-fetches the hot state).

Results carry stable **internal citations** — `[source_type:source_id ·
section]` — and a fenced `evidence_block` the Brain treats strictly as DATA.

## Triggers (when retrieval runs)

`RetrievalTrigger` is mandatory on every call. Retrieval is invoked ONLY when:

* the user asks for historical justification (`historical_justification`),
* a detailed source is needed (`detailed_source`),
* the Brain reports insufficient evidence (`insufficient_evidence`),
* an agent explicitly requires supporting records (`agent_request` — the MCP
  `retrieve_evidence` tool).

It is never run to reconstruct the project on a normal turn.

## Indexing

* **Asynchronous, off the outbox.** When a domain event for an indexable
  aggregate is processed, the consumer runs a best-effort re-index in its own
  SAVEPOINT (`consumer._schedule_index`), so an indexing failure never blocks
  recompiles. `EVENT_SOURCE_MAP` maps aggregate types → source types.
* **Re-embed only changed content.** A chunk is re-embedded only when its content
  hash is new; unchanged chunks carry their existing vector forward
  (`indexer.reindex_source` → `embedded` / `reused` counts).
* **Backfill / admin.** `POST /api/brain/retrieval/reindex` (optionally one
  source type) rebuilds the index, re-embedding only what changed.

## Embeddings (configurable, served separately)

Embeddings are decoupled from the conversational model so a small local model can
run on its own endpoint (`app/services/ai/embeddings.py`):

| Setting | Default | Notes |
|---|---|---|
| `embedding_provider` | `dry_run` | Deterministic offline feature-hashing embedder (tests / air-gapped). Set `openai_compatible` for a real endpoint. |
| `embedding_base_url` / `embedding_api_key` | — | The **separate** embedding endpoint (TEI / llama.cpp / vLLM / OpenAI). |
| `embedding_model` / `embedding_dim` | `supervoid-embed-small` / 384 | Model id + vector dimension. |

## PostgreSQL / pgvector

The schema is portable (JSON vector), so SQLite and Postgres share one
definition. On PostgreSQL, migration `0023` additionally (dialect-gated):

* `CREATE EXTENSION vector`,
* adds `embedding_records.embedding_vec vector(N)` + an IVFFlat cosine ANN index,
* adds a GIN full-text index on `knowledge_chunks.content`.

`retrieval/vector_backend.py` selects the backend at runtime
(`retrieval_vector_backend = auto|pgvector|memory`): pgvector ANN pre-ranks
candidates and `ts_rank` powers full-text on Postgres; the in-process cosine +
keyword fallback keeps SQLite (and any non-pg dialect) fully functional. The JSON
vector is always the canonical store. `pgvector` / `psycopg` are imported lazily,
so SQLite installs never need them.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/brain/retrieval/search` | Trigger-gated, permission-filtered hybrid retrieval → hits + citations + evidence block. |
| `GET /api/brain/retrieval/runs` · `/runs/{id}` | Retrieval diagnostics (own runs; admins see all): query, filters, candidates, reranked results, sources used. |
| `GET /api/brain/retrieval/documents` | The indexed corpus (admin). |
| `POST /api/brain/retrieval/reindex` | (Re)index, re-embedding only changed content (admin). |
| MCP `retrieve_evidence` | Read-only, permission-filtered evidence for agents (`agent_request` trigger, `exclude_in_state=true`). |
