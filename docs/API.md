# API Reference — SUPERVOID Publishing

The backend is a FastAPI service. This document is a hand-maintained map of the
HTTP surface and its cross-cutting conventions; the **authoritative, always
up-to-date** reference is the generated OpenAPI schema:

- Swagger UI — `GET /docs`
- ReDoc — `GET /redoc`
- Raw schema — `GET /openapi.json`

There are two surfaces:

- **Private admin API** under `/api` — the studio system (authenticated writes).
- **Public Graphic Novel Webviewer** under `/public` — read-only, unauthenticated,
  and deliberately outside `/api`. It only ever serves *published* projections.

---

## Conventions

### Authentication & roles

JWT bearer tokens. Obtain one with `POST /api/auth/login`; send it as
`Authorization: Bearer <token>`. `GET /api/auth/me` returns the current user.

The global `UserRole` is one of `admin`, `editor`, `reviewer`,
`production_manager`, `marketing`, `archive_reader`. Writes and privileged routes
are guarded (`AUTHED`, `ADMIN_ONLY`); most reads are open for the local archive
experience. Some actions are additionally **admin-gated** (e.g. publishing,
external integration runs). Project-scoped access (story worlds / works) is
enforced on top of the global role — see *Collaboration*.

### Pagination & filtering

List endpoints that can grow return a **`Page`** envelope:

```json
{ "items": [ … ], "total": 123, "skip": 0, "limit": 50 }
```

Controlled by `?skip=` and `?limit=` query params. Most list endpoints also
accept resource-specific filters (documented inline / in OpenAPI), e.g.
`/api/assets?asset_type=cover&work_id=…`, `/api/agent-findings?resolved=false`,
`/api/curation/works/{id}/events?action=published`.

Naturally bounded structural collections (a work's volumes, a page's panels)
return a plain JSON array.

### Error envelope

**Every** error response uses one shape, with the correlation id both in the
body and on the `X-Request-ID` header:

```json
{ "detail": "Human-readable message.", "request_id": "…" }
```

Request-validation failures (422) add a structured list:

```json
{ "detail": "Request validation failed.", "errors": [ … ], "request_id": "…" }
```

Status codes follow HTTP conventions: `400` invalid input, `401` unauthenticated,
`403` forbidden / needs admin, `404` not found, `409` conflict / illegal state
transition, `422` schema validation, `500` unexpected.

### Request correlation

The request-id middleware mints an `X-Request-ID` (or honours an inbound one) and
stamps it on every log line and response. Agent runs and integration runs persist
it as their `correlation_id`, so a run traces back to the originating request.

### Health & meta

- `GET /api/health` — liveness.
- `GET /api/meta` — service metadata.
- `GET /` — service identity + docs link.

---

## Domain map

Resource groups (tag → base path). Counts are endpoint totals; see OpenAPI for
the per-route request/response schemas.

### Identity & core catalogue
- **auth** — `POST /api/auth/login`, `GET /api/auth/me`.
- **users** *(admin)* — `/api/users` CRUD + `activate` / `deactivate` /
  `rotate-password`.
- **authors** — `/api/authors` CRUD.
- **works** — `/api/works` CRUD + `GET /api/works/{id}/transmedia`.
- **manuscripts** — `/api/manuscripts` CRUD.

### IP / transmedia
- **story_worlds** — `/api/story-worlds` CRUD (slugged, hierarchical).
- **story_series** — `/api/story-series` CRUD.
- **adaptation_dossiers** — `/api/adaptation-dossiers` CRUD (the publishing →
  other-medium bridge).

### Editorial workflow
- **workflow** — `POST /api/manuscripts/{id}/transition`, workflow events,
  `GET /api/workflow/transitions`.
- **reviews**, **editorial_notes**, **contracts**, **workflow_events** — CRUD.
- **approvals** — generic approval requests (`/api/approvals`, `decide`,
  `cancel`).

### Production
- **production_tasks** — `/api/production-tasks` CRUD + saved views
  (`my-assignments`, `overdue`, `blocked`, `awaiting-approval`), `transition`,
  `dependencies`, `subtasks`, `activity`, `approvals`.
- **production_items** — the original (legacy-compatible) stage checklist.
- **milestones**, **production_records**, **production_templates** — supporting.

### Asset Library
- **assets** — `/api/assets` CRUD + search; **versions** (`/versions`,
  `/versions/upload`, `promote`, `rollback`, `approve`, `download`, `preview`);
  **provenance** (`GET`/`PUT …/provenance`, `…/completeness`); **licences**
  (`/licences` CRUD, `GET /api/assets/licence-warnings`); **links**.

### Graphic-novel production hierarchy
- **graphic_novel_productions** — `/api/graphic-novel-productions` CRUD +
  `tree`, `progress`, `readiness`, `validate`, `recalculate`,
  `curation-handoff`.
- **graphic_novel_hierarchy** — volumes → chapters → sequences → pages → panels
  → elements (each with CRUD + `reorder`), page `validate` / `comparison` /
  `duplicate`, and knowledge-entity links.

### SUPERVOID Pictures (screen)
- **screen** — `/api/screen/projects` (incl. `from-dossier/{id}`,
  `dossiers/promote`); units → sequences → scenes → shots → panels/assets;
  scene characters; project `breakdown`, `shot-list`, `storyboard`,
  `references`, `export`.

### Supervised agent framework
- **agents** — registry (`/api/agents`, `/api/agents/tools`),
  `POST /api/agents/{key}/run`; **runs** (`/api/agent-runs`, detail, `retry`);
  **findings** (`/api/agent-findings`, `resolve`); **proposals**
  (`/api/agent-proposals`, `approve` / `reject` / `execute`); **prompt
  templates** (versioned). The runner is **model-driven** (Prompt 9): the model
  returns a validated structured `AgentOutput` (result / findings / proposed tool
  calls / evidence references / confidence / unanswered questions); read-only
  tools run in a bounded, governed loop while mutation/external intentions become
  the same gated proposals (approval can never be bypassed). Invalid tool
  intentions (unknown / not-allowed / unpermitted / unsupported target / direct
  mutation) are rejected and fail the run with nothing executed; an unavailable /
  refusing / malformed model degrades to the deterministic validators
  (`result.model_driven=false`). The run detail includes safe `traces` (tool
  requested, tool result, validated output summary — never chain-of-thought). See
  [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervised-studio-agent-framework).

### Private navigation / Brain hand-off
- **brain hand-off** — context-aware "Ask the Brain" (Prompt 12). `POST
  /api/brain/handoff {entity_type, entity_id}` resolves the entity's project
  scope (Work / StoryWorld / manuscript / GN page+panel / screen project+scene+
  shot / asset / production task / rights), enforces `VIEW_PROJECT`, binds a
  `BrainConversation`, and returns a `handoff_url` carrying ONLY a signed,
  short-lived, single-use token (no project content). The root-mounted landing
  `GET /brain-handoff?token=…` consumes the token (once) and 303-redirects to the
  Brain UI. `GET /api/brain/status` powers the private-nav hub: active project,
  state version, model status, compiler status, and pending-proposals count. Deep
  links into a specific LibreChat conversation are intentionally not done (no
  fork); context is surfaced via the MCP `select_active_project` tool. See
  [`LIBRECHAT_INTEGRATION.md`](./LIBRECHAT_INTEGRATION.md#private-navigation--ask-the-brain-hand-off).

### SUPERVOID MCP server (LibreChat tools)
- **mcp** — the governed tool layer over Model Context Protocol (Streamable
  HTTP), mounted at `/mcp` (NOT under `/api`): `GET /mcp/health`
  (unauthenticated liveness) and `POST /mcp` (JSON-RPC: `initialize`,
  `tools/list`, `tools/call`, `ping`). Auth = internal service token +
  HMAC-signed user-context headers, mapped to a SUPERVOID user; every tool
  re-runs the policy service. ~36 tools (context / production / narrative /
  assets / publishing-rights / agent-ops): read tools return only authorised
  records, write-like tools create gated proposals, approval tools verify the
  user's approval scope. No raw CRUD. See
  [`MCP_SERVER.md`](./MCP_SERVER.md) and
  [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervoid-mcp-server).

### Conversation memory & decision extraction
- **memory analysis (Prompt 13)** — after every completed Brain response the
  gateway enqueues a `conversation.turn_completed` job (the outbox); the consumer
  routes it to the analyzer, which *proposes* durable items: project fact, member
  preference, procedural lesson, decision, commitment, unresolved question, task
  suggestion. Casual chat is archived (the messages persist) but never promoted.
  **Canon / rights / production claims never become inferred memory** — they
  become a PROPOSED `DecisionRecord` that needs approval. A member preference is
  auto-accepted (verified without review) ONLY when it concerns the same user, is
  low-risk, clears `brain_memory_auto_accept_min_confidence`, and neither grants
  permissions nor alters canon; everything else lands UNVERIFIED in the inbox.
  Contradictions with verified state are detected, and nothing is ever
  overwritten — corrections supersede and keep provenance.
- **memory review inbox** — `GET /api/brain/memory/inbox` (pending items you may
  review, scoped to your access). Actions, all scope-gated (studio = admin;
  project = `APPROVE`; member/conversation = owner): `POST /api/brain/memory/{id}/`
  `accept` · `reject` · `edit` · `supersede` · `merge` · `expire`. `edit` /
  `supersede` / `merge` return a NEW row that supersedes the original (never an
  overwrite). Approved decisions + verified memories flow into compiled state via
  the deterministic builders. Decisions carry an explicit status —
  proposed / approved / rejected / superseded (`/api/brain/decisions`). See
  [`CONVERSATION_MEMORY.md`](./CONVERSATION_MEMORY.md).

### Cold-detail retrieval (pgvector evidence)
- **retrieval (Prompt 14)** — an exceptional, permission-filtered evidence layer
  over studio detail that does NOT belong in the hot compiled state.
  `POST /api/brain/retrieval/search {query, trigger, work_id?, story_world_id?,
  source_types?, exclude_in_state?}` runs HYBRID retrieval (structured filters +
  full-text + vector similarity + optional rerank), filters every candidate by
  permission BEFORE returning content (rights/contract extracts need
  `manage_rights`), and returns stable internal citations
  (`[source_type:source_id · section]`) + a fenced evidence block. `trigger` is
  mandatory (historical justification / detailed source / insufficient evidence /
  agent request) — retrieval is never a per-turn reconstruction. Diagnostics:
  `GET /runs` + `/runs/{id}` (query, filters, candidates, reranked results,
  sources used); `GET /documents` and `POST /reindex` (admin; re-embeds only
  changed content). Eligible material — manuscripts, editorial notes, decision
  rationale, reviews, knowledge entities, asset **metadata** (never binary),
  panel + scene descriptions, **approved** conversation summaries, rights +
  contract extracts — is indexed asynchronously off the outbox. Embeddings use a
  configurable, separately-served small model (`embedding_provider`). pgvector
  ANN + `ts_rank` accelerate PostgreSQL; an in-process cosine + keyword fallback
  keeps SQLite working. The MCP `retrieve_evidence` tool exposes the same,
  permission-filtered, to agents. See [`RETRIEVAL.md`](./RETRIEVAL.md).

### Identity linking & member administration
- **identity (Prompt 15)** — the operational SUPERVOID ↔ LibreChat identity
  bridge (the simpler, robust first version — NOT a custom OAuth/OIDC provider).
  Admin linking workflow: `/api/identity-links` (list / create / verify /
  disable / edit, admin-only) ties a SUPERVOID user to a LibreChat identity
  (user id + email, status, linked_at, verified_at). Member self-service:
  `GET /api/identity-links/me`. The MCP server now resolves a LibreChat identity
  to a SUPERVOID user THROUGH an active link, rejecting **unlinked** identities
  and **disabled** members (`mcp_require_identity_link`). Brain access tokens
  (`/api/brain-tokens`) already support create / reveal-once / rotate / revoke /
  expiry / project-restrictions / last-use, now with an **audit trail**.
  Security events: `GET /api/security-events` (admin) records failed mapping,
  revoked/expired-token use, disabled-member access, project-denied tool calls,
  and suspicious repeated failures. LibreChat self-registration stays disabled.
  See [`IDENTITY.md`](./IDENTITY.md) (incl. the future-OIDC migration path).

### Observability & operational controls
- **brain ops (Prompt 16)** — the INTERNAL Brain Operations surface (admin-only):
  `GET /api/brain/ops/status` aggregates vLLM/model health, the gateway runtime
  gauge (active requests / queue depth), compiler lag, unprocessed/failed
  BrainEvents, state versions, stale projects, sessions (warmth + prefix hashes),
  prompt/completion token usage, TTFT + total latency, agent failures, MCP
  failures, pending proposals and LibreChat health, plus derived **health states**
  (healthy / degraded / unavailable / stale / maintenance). `GET /api/brain/ops/`
  `metrics` is a Prometheus-compatible exposition. Operator controls (admin):
  `controls/model-requests`, `controls/drain`, `controls/mcp`,
  `controls/maintenance`, `projects/{id}/rebuild|cold|prewarm`, `events/replay`,
  `tokens/{id}/revoke`. A correlation id flows across LibreChat → Gateway → model
  → MCP → agent → proposal (structured `log_event` lines), with redaction of
  tokens / auth headers / passwords / private prompts / contract content. GPU and
  internal topology are never exposed publicly. See
  [`OBSERVABILITY.md`](./OBSERVABILITY.md).

### Integration hub
- **integrations** — static contracts (`/api/integrations`, `/ecosystem`,
  `/{key}`); persisted **points** (`/api/integrations/points` CRUD +
  `health`, `config`, `operations`); **runs** (`/runs` + `approve` / `reject` /
  `execute`); **adapters** (`/adapters`); **links**. Adapters: `n8n_webhook`,
  `comfyui`, `github_project`, `file_exchange.*` (desktop apps), and
  `logosforge` (local-first bundle import — adapter-only, no live API).

### Operational business layer
- **rights** — `/api/rights` CRUD + `warnings`, and depth sub-resources
  (`windows`, `options`, `chain-of-title`, `evidence`, `status-history`).
- **crm** — `organizations`, `contacts` (+ roles / tags), `contact-tags`,
  `interactions`, `opportunities`.
- **editions** — `/api/editions` CRUD + `detail`, `packages`,
  `packages/{channel}` (ONIX / KDP / Ingram / web / press-kit / ARC export
  packages — generated & validated locally, not uploaded), `distribution/channels`.

### Public reader & private curation
- **public-reader** *(unauthenticated, `/public`)* — `works`, `works/{slug}`
  (+ `volumes`), `volumes/{id}/chapters`, `chapters/{id}/pages`, `pages/{id}`
  (+ `hotspots`), `media/{id}`. Only published / unlisted projections.
- **curation** *(private CMS, `/api/curation`)* — `works` (+ `from-work`),
  volumes / chapters / pages / panels / hotspots / media CRUD; lifecycle
  (`validate`, `preview`, `schedule`, `visibility`, `request-approval`,
  `approvals/{id}/approve|reject`, `publish`, `unpublish`); paginated `events`
  history; `handoff/page` (controlled private → public derivative hand-off).

### Command centre (read-only aggregation)
- **command-centre** — `overview`, `my-work`, `agent-inbox`, `asset-health`,
  `business-alerts`, `divisions`, `works/{id}/command`. Pure cross-domain
  roll-ups; no new tables.

### Knowledge graph, calendar, search, AI, exports, attachments
- **knowledge** — entities + relationships (+ manuscript entity-links,
  `neighborhood`).
- **calendar_events**, **search** (`/api/search`), **dashboard** (manuscript
  metrics), **attachments** (upload/download), **exports**
  (`/api/manuscripts/{id}/export`, `/api/exports/formats`).
- **ai** — manuscript AI features (summarize, consistency, style, tags,
  editorial suggestions) + `providers` + `health`. Dry-run by default; see
  ROADMAP. `GET /api/ai/health` probes the configured backend (reachable,
  active model, declared capabilities, latency) and never returns the API key.
  Provider `vllm` selects the dedicated self-hosted vLLM client (async pool,
  streaming, tools, structured JSON-schema output, reasoning, top_k, request-id
  propagation, bounded transient-only retries); `openai_compatible` stays the
  generic catch-all with conservative, declared capabilities. No
  OpenAI-compatible SUPERVOID endpoint is exposed yet.
- **brain** — SUPERVOID Brain persistence (`/api/brain`, private). Conversations
  + messages (owner-scoped); memory items and decision records (scope-gated via
  the policy service: studio = admin, project = project scopes, member =
  self); read-only compiled state (`/state/studio`, `/works/{id}/state`,
  `/story-worlds/{id}/state`); and read-only, admin-only `events` (append-only)
  and `revisions` (immutable). Storage only — no state is compiled yet.
- **brain outbox** — admin-only operations for the transactional domain-event
  outbox (`/api/brain/outbox`): `GET /` (monitoring: unprocessed/failed counts,
  current cursor, compiler lag, stale-project count), `GET /failed` (the
  dead-letter list), `POST /process` (deterministic one-shot drain),
  `POST /reconcile` (re-queue failures + mark stale anything missed), and
  `POST /replay` (requeue named or all `FAILED` events). Events are emitted in
  the same transaction as the domain mutation they describe; the consumer marks
  the affected project/studio state stale (it does not compile it). See
  [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervoid-brain--domain-event-outbox).
- **brain state compiler** — admin-only deterministic state APIs on `/api/brain`:
  `GET /state/studio`, `GET /works/{id}/state`, `GET /story-worlds/{id}/state`
  (current compiled facts + summary + version + cursor + checksum; reads are
  permission-scoped), `GET /revisions` (immutable history),
  `GET /revisions/{a}/delta/{b}` (section-level diff between versions),
  `GET /health` (head sequence, per-state version/staleness/lag), `GET /stale`
  (states needing recompilation), and `POST …/state/rebuild` (`{full}` —
  incremental, or a full rebuild for validation / disaster recovery). State is
  built deterministically from SQL; the LLM never computes facts. See
  [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervoid-brain--deterministic-state-compiler).
- **brain instruction layer** — the stable, versioned instruction records on
  `/api/brain`: `GET /constitution`, `GET /profiles` + `GET /profiles/{key}`,
  `GET /context-templates/{key}`, `GET /policies/{key}`, `GET /glossary` (authed
  reads), and admin-only `POST …/versions` to append a new immutable version
  (the `current_version` pointer bumps in the same transaction). `POST
  /conversations/{id}/assemble` returns the ordered, permission-filtered,
  ChatRequest-ready context (messages + model + temperature + max_tokens + tools
  + prefix_hash + state versions) and persists the prefix-cache checkpoint;
  scoped conversations require `VIEW_PROJECT`. `GET
  /conversations/{id}/debug/context` (admin-only) shows per-segment sizes +
  redacted previews and never echoes a key. See
  [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervoid-brain--stable-instruction-layer--contextassembler).
- **brain gateway** — the **OpenAI-compatible** surface LibreChat (and any
  OpenAI client) connects to. Mounted at `/brain` (NOT under `/api`):
  `GET /brain/health` (unauthenticated liveness), `GET /brain/v1/models`,
  `POST /brain/v1/chat/completions` (ordinary **and** streaming, `data:` SSE
  ending in `data: [DONE]`), and `POST /brain/v1/responses` (returns `501` —
  deferred). Authenticated by a dedicated **Brain access token**
  (`Authorization: Bearer sk-brain-…`), never the browser JWT and never the
  upstream vLLM key. Optional SUPERVOID extension metadata rides in a top-level
  `supervoid` object (project/story-world id, assistant profile, LibreChat
  conversation id, state-version hint) that strict clients ignore; responses
  echo a `supervoid` object carrying state versions, machine-readable evidence
  citations, and the request id. Each turn is persisted (user message, assembled
  state versions, model response, usage, request id, tool calls, retrieval
  refs, latency) via the `ContextAssembler`. Per-user rate + concurrency limits
  apply; provider-unavailable maps to graceful `502/503/504`. See
  [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervoid-brain--openai-compatible-gateway).
- **brain tokens** — private, JWT-authenticated management of Brain access
  tokens (`/api/brain-tokens`): `GET` (list own; never returns the secret),
  `POST` (create — returns the plaintext secret **exactly once**),
  `POST /{id}/rotate` (new secret, old one dies immediately), and
  `DELETE /{id}` (revoke; effective on the next gateway request). Only a
  SHA-256 hash is stored; tokens carry a name, optional expiry, last-used time,
  and optional project restrictions, and are strictly per-user.
- **brain sessions** — the stateful-session / prefix-cache layer (Prompt 8). The
  gateway maintains one `BrainSession` per conversation (live prefix signature,
  event cursor, hot/warm/cold) and stamps each completion's `supervoid.session`
  with `{warmth, prefix_cache_eligible, invalidation_reasons}`. Owner-or-admin:
  `GET /api/brain/conversations/{id}/session` (the session row),
  `GET …/session/metrics` (per-turn token / TTFT / latency / eligibility),
  `POST …/session/compact` (deterministic decision/task digest; messages
  retained, approved decisions never dropped); admin diagnostic
  `GET …/session/invalidation` (which rule would fire next). Admin ops:
  `GET /api/brain/sessions`, `POST /api/brain/sessions/sweep` (reclassify +
  archive aged-out; never deletes messages), `POST /api/brain/sessions/prewarm`
  (best-effort vLLM prefix-cache priming for ACTIVE projects; a no-op under
  dry-run, never claims vLLM durably remembers a conversation). See
  [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervoid-brain--stateful-sessions--prefix-cache-strategy).

---

## What is *not* a live external integration

In keeping with the project's local-first stance, several "integrations" are
**package generators or local-first adapters**, not live external clients. They
are clearly labelled as such and never dispatch over the network unless
`INTEGRATIONS_ALLOW_NETWORK` is explicitly set:

- Desktop **file-exchange** adapters (Affinity, InDesign, Clip Studio, DaVinci,
  Blender, Cinema 4D, Houdini) — generate/ingest structured packages.
- **LOGOSFORGE** — local-first **bundle import** (adapter-only).
- Distribution **export packages** (ONIX / KDP / Ingram / web / press-kit / ARC)
  — validated packages and checklists, not uploads.
- **ComfyUI** / **n8n** / **GitHub** adapters — outbound effects are *recorded*
  unless network access is enabled; all mutations pass the approval boundary.

See [`ROADMAP.md`](ROADMAP.md) for the per-feature status tiers.
