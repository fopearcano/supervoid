# SUPERVOID Brain — Implementation Plan (Audit)

**Status:** Audit only. No functional code is introduced by this document.
**Scope:** Plan the additive evolution of the working SUPERVOID Studio System to add
the **SUPERVOID Brain** (persistent, governed conversational orchestration),
**vLLM** (dedicated inference) and **LibreChat** (conversational UI + MCP client),
without rewriting the existing system.

This plan is written against the repository as audited on **2026-06-26** (migration
head `0013_catalogue`, 78 ORM tables, 374 backend tests passing). Every claim below
was checked against source; file paths and symbol names are cited so the plan can be
re-verified.

---

## Guiding constraints (non-negotiable, carried from ARCHITECTURE.md)

The Brain initiative is an **additive evolution**, not a rewrite. The following remain
the final authority and must not be weakened:

- **SUPERVOID database** — verified facts. Canonical state lives in Postgres/SQLite tables, never in a chat history.
- **SUPERVOID policy service** (`app/services/policy.py`) — permissions. `can()` / `ensure_can()` is the sole authority for scoped access.
- **SUPERVOID approval system** (`AgentActionProposal`, `ApprovalRequest`, `PublicationApproval`, `IntegrationRun`) — consequential actions stay human-gated.
- **SUPERVOID Brain** — orchestration only (it does not own facts or permissions).
- **vLLM** — inference only.
- **LibreChat** — conversational interface and MCP client only.

And the load-bearing invariants:

- Modular monolith, **local-first** (SQLite + `dry_run` provider + no network by default).
- **Strict public/private separation**: `/public` is GET-only, unauthenticated, and serves only the published projection; `/api` is authenticated.
- **Human approval** for publishing, rights, destructive and external actions.
- **Never** give the LLM direct SQL, shell, unrestricted filesystem or unrestricted HTTP.
- **Secrets** out of DB snapshots, prompts, logs and API responses (existing `redact()` / `credential_refs` patterns).
- One Alembic migration per schema change; backend tests + frontend build stay green; docs updated; **one focused commit per phase**.

---

## 1. Current AI inventory

### 1.1 OpenAI-compatible provider (client)
- `app/services/ai/providers/openai_compat.py` — `OpenAICompatibleProvider` (lines 14–78). Synchronous `httpx` **client** that POSTs `{base_url}/v1/chat/completions` with `Authorization: Bearer {api_key}`, parses `choices[0].message.content` and `usage`. Default timeout 60s. **No streaming.**
- `app/services/ai/providers/registry.py` — `get_provider()` (LRU-cached), `_build_provider()`, `PROVIDER_DEFAULTS` (openai → `https://api.openai.com/v1`, openrouter → `https://openrouter.ai/api/v1`, lm_studio → `http://localhost:1234/v1`), `KNOWN_PROVIDERS = (dry_run, openai, openrouter, lm_studio, openai_compatible)`.
- `app/services/ai/providers/base.py` — `LLMProvider` protocol (`name`, `chat(messages, model?, temperature?, max_tokens?) -> CompletionResult`), `ChatMessage`, `CompletionResult`.
- Config (`app/config.py`): `ai_provider` (default `dry_run`), `ai_base_url`, `ai_api_key`, `ai_model` (default `gpt-4o-mini`), `ai_request_timeout` (60.0).
- **Key fact:** SUPERVOID is a *client* to OpenAI-compatible upstreams. It does **not** expose an OpenAI-compatible *server* (`POST /v1/chat/completions`).

### 1.2 Dry-run provider
- `app/services/ai/providers/dry_run.py` — `DryRunProvider` (lines 72–101). Default provider. Pattern-matches `FEATURE:*` tags in the prompt and returns deterministic canned JSON; never touches the network. Makes the whole AI surface work offline and is the basis of the test suite.

### 1.3 Manuscript AI features
- `app/services/ai/features/` — five editorial features: `summarize.py`, `style_analysis.py`, `editorial_suggestions.py`, `semantic_tags.py`, `consistency.py`. Each builds a prompt, calls `provider.chat()`, parses JSON, persists an `AIInsight`.
- `app/services/ai/prompts.py` — `manuscript_excerpt()` (compact, truncated manuscript snapshot: title/author/status/synopsis/≤5 reviews/≤5 notes) and `parse_json_object()` (permissive JSON extraction).
- `app/models/ai_insight.py` — `AIInsight` table (`ai_insights`): `manuscript_id`, `feature` (`AIFeature` enum), `provider`, `model`, `payload` (JSON). Append-only; latest per `(manuscript, feature)` is canonical.
- `app/routers/ai.py` — 8 endpoints (`POST /api/ai/manuscripts/{id}/{summarize|style-analysis|editorial-suggestions|semantic-tags|consistency-check}`, `GET …/insights`, `GET /api/ai/providers`, `DELETE /api/ai/insights/{id}`). All `AUTHED`.
- **Key fact:** stateless, single-turn, manuscript-scoped. No conversation, no tool calls, no side effects, no citations.

### 1.4 Supervised agent framework
- `app/services/agents/runner.py` — `run_agent()` (101–202), `execute_proposal()` (248–280), `build_snapshot()`, `redact()`.
- **Key fact (runner semantics):** the runner calls `provider.chat()` only for **instrumentation and cost accounting**. The actual findings/proposals come from **deterministic Python handlers**, *not* from parsing the model's output. There is no LLM-output parser, no schema-validated tool-calling, no semantic consumption of the completion. This is a deliberate safety choice and the single biggest gap for a conversational Brain.
- `READ_ONLY` agents may not emit proposals (runtime invariant). Every proposal is `requires_approval=True`; nothing auto-executes.

### 1.5 Agent definitions and handlers
- `app/services/agents/definitions.py` — `AgentDefinition`, `AgentContext`, `AgentOutput`, `FindingSpec`, `ProposalSpec`; 4 code-registered agents (`manuscript_consistency`, `work_metadata_advisor`, `rights_risk_scanner`, `publishing_readiness`).
- `app/services/agents/tools.py` — `Tool`; 9 code-registered tools: 2 `READ_ONLY` (`read_entity`, `search_knowledge`), 5 `MUTATION` (`update_work_metadata`, `add_editorial_note`, `publish_to_public_reader`, `update_rights`, `delete_entity`), 2 `EXTERNAL` (`logosforge_export`, `movies_handoff`). Only `update_work_metadata` has a real executor; `EXTERNAL`/destructive tools are **recorded only** (dry-run, no secrets).
- Tables: `agent_runs`, `agent_findings`, `agent_action_proposals` (`app/models/agent.py`).

### 1.6 Action proposals and approval
- `AgentActionProposal` (`app/models/agent.py:116–156`): `PENDING → APPROVED → EXECUTED/FAILED` or `REJECTED`, moved only by explicit endpoints (`/api/agent-proposals/{id}/approve|reject|execute`). HIGH/CRITICAL and `always_requires_approval` tools require **ADMIN**.
- Sibling gates: `ApprovalRequest` (`app/models/approval_request.py`, production tasks), `PublicationApproval` (`app/models/publication_approval.py`, curation publish — ADMIN-only, double validation via `validate_for_publication()`), `IntegrationRun` (`PENDING_APPROVAL → APPROVED → execute`). `HUMAN_ONLY_STATUSES = {APPROVED, DONE}` in production (`app/services/production.py:52`) are never set by automation.

### 1.7 Existing integration adapters
- `app/services/integrations/` — `IntegrationAdapter` protocol (`health`, `capabilities`, `dry_run`, `inbound`, `outbound`, `execute`), `AdapterOperation`, `AdapterContext` (per-call `secret()` resolver from env). Service: `request_operation()` / `approve_run()` / `reject_run()` / `execute_run()`.
- Adapters: `logosforge` (package bundle exchange), `github`, `comfyui`, `n8n` (webhook), `file_exchange` (7 desktop profiles).
- Tables: `integration_points`, `integration_runs`, `integration_links`. `integrations_allow_network` defaults **False**; secrets stored only as env-var *names* (`credential_refs`).
- **This is the precedent for how the future MCP server must gate governed actions.**

### 1.8 Current authentication and project permissions
- Auth (`app/auth/`): JWT **HS256** (`create_access_token`/`decode_token`), bcrypt passwords, `OAuth2PasswordBearer` at `/api/auth/login`, `get_current_user`, `require_role`, reusable `AUTHED` / `ADMIN_ONLY`. `User` (email, hashed_password, `UserRole`, is_active). Token expiry 60 min. **No external IdP (OAuth/OIDC/SAML/LDAP)** → no external-identity mapping.
- Policy (`app/services/policy.py`): the **single authority** for scoped access. `can()`, `ensure_can()`, `effective_role()`, `require_scope()`, `role_scopes()`, `ROLE_SCOPES`, `ROLE_RANK`. `ProjectMembership` (user × Work/StoryWorld × `ProjectRole` [14 roles] × `MembershipStatus` [5]); `PermissionScope` [11 scopes incl. `PUBLISH`, `MANAGE_RIGHTS`, `APPROVE`, `MANAGE_COLLABORATORS`]. ADMIN bypasses; StoryWorld membership cascades to child Works; strongest role wins by `ROLE_RANK`. Audit via `membership_audits` (append-only).

### Supporting facts (deployment & wiring)
- `app/main.py`: `create_app()` mounts `ALL_ROUTERS` under `settings.api_prefix` (`/api`) and `public_reader` unprefixed at `/public`; middleware order CORS → `RequestIdMiddleware`; uniform error envelope `{detail, request_id}`.
- `app/db.py`: SQLite `PRAGMA foreign_keys=ON` listener; Postgres via `psycopg`. `db_init_strategy` = `create_all` (dev) | `migrate` | `skip`.
- Migrations: `alembic/versions/0001…0013`, `NAMING` convention + `batch_alter_table` (SQLite/Postgres-safe). `manage_db.py check` is the CI gate (schema-vs-models by table+column names).
- Deployment: `docker-compose.yml` = `postgres:16-alpine` (5432) + backend FastAPI (8000) + frontend nginx (`8080:80`). `frontend/nginx.conf` proxies `/api/*` and `/public/*` to `backend:8000`, SPA fallback. **No vLLM, no LibreChat, no MCP, no pgvector.**
- PromptTemplate system (`app/models/agent.py`): `PromptTemplate` + `PromptTemplateVersion` (versioned, append-only) with CRUD at `/api/prompt-templates`. Plain-text bodies; **no interpolation/templating engine** yet.

---

## 2. Current limitations (gaps for the Brain)

All confirmed absent in the audited tree (grep across repo for `librechat|vllm|pgvector|brain|embedding` returns **zero** hits):

1. **No persistent conversation domain** — no `Conversation` / `ConversationTurn` / message models. `ChatMessage`/`CompletionResult` exist only as transient provider DTOs; every AI call is single-turn and stateless.
2. **No `StudioState` / `ProjectBrainState`** — no persisted, queryable per-studio/per-work conversational or working state. State is scattered across 78 tables with no compiled view.
3. **No incremental state compiler** — nothing materializes Work/Manuscript/Assets/Tasks/Knowledge into a bounded, ranked context for a chat turn. Features rebuild a full static excerpt each call.
4. **No domain-event stream for the Brain** — no `EventOutbox`/`DomainEvent` table. Audit logs (`WorkflowEvent`, `ProductionActivity`, `PublicationEvent`, `MembershipAudit`) record history but are not a subscribable outbox.
5. **No OpenAI-compatible Brain Gateway** — SUPERVOID is only a *client*; it exposes no governed `POST /v1/chat/completions` / `GET /v1/models` server for LibreChat or other tools to call.
6. **No LibreChat deployment** — no container, no UI, no model routing, no account linking. The only SPA is the graphic-novel reader.
7. **No SUPERVOID MCP server** — no Model Context Protocol server exposing governed tools/resources (works, manuscripts, knowledge, approvals) to an MCP client.
8. **Agent runner does not semantically consume model output** — handlers are deterministic Python; the completion is recorded but never parsed into findings/proposals or validated tool calls.
9. **No state-version-aware context assembly** — no notion of a context built against a specific state version, so the Brain cannot detect staleness or attribute answers to a snapshot.
10. **No persistent member-to-chat identity mapping** — `User`/`ProjectMembership` are not linked to any chat principal; no `UserChatIdentity`/`ConversationParticipant`. No external-IdP federation.
11. **No retrieval citations in assistant answers** — `AIInsight.payload` is ungrounded; no `Citation`/`SourceReference` mapping a statement to a manuscript passage, note, or entity.
12. **No evaluation corpus** — no `EvalDataset`/`EvalCase`/`EvalResult` to measure Brain correctness/tone/style over time.

Adjacent enabling gaps (also absent, needed by the above): **no pgvector / embeddings / RAG**, **no streaming or async** (sync request/response only), **no multi-model orchestration / fallback**, **no per-Work/per-IP conversation namespace**, **no structured-output (schema) tool-calling**.

---

## 3. Proposed topology

```
Browser
  -> nginx                         (the ONLY internet-facing component)
       -> SUPERVOID frontend       (React/Vite SPA, served by nginx)
       -> LibreChat                (conversational UI)

LibreChat
  -> SUPERVOID Brain Gateway       (OpenAI-compatible; auth, policy, model allowlist, logging, redaction)
       -> vLLM                     (inference only; private network / LAN)
  -> SUPERVOID MCP server          (governed tools/resources)
       -> governed internal services  (policy service, approval system, DB — never raw SQL/shell/HTTP)

SUPERVOID backend (FastAPI)
  -> PostgreSQL / pgvector         (verified facts + embeddings)
  -> event outbox                  (domain events table)
  -> state compiler                (materializes ProjectBrainState / StudioState)
```

> **Production rule (load-bearing):** **LibreChat must connect to the SUPERVOID Brain
> Gateway, never directly to vLLM.** vLLM is raw, ungoverned inference. The Brain
> Gateway is where authentication, the policy service, the model allowlist, request-id
> correlation, prompt/secret redaction, citations and logging are enforced. A direct
> LibreChat→vLLM path would bypass every SUPERVOID governance control and is forbidden
> in production. (For isolated *infrastructure* smoke tests, vLLM may be hit directly on
> the private network — see §7 Phase 1 — but never from the user-facing UI.)

---

## 4. Trust boundaries and ports

**Trust boundaries (high → low exposure):**

1. **Internet-facing edge** — nginx only. Terminates TLS, serves the SPA, and reverse-proxies a curated set of paths (`/api`, `/public`, the LibreChat UI). Nothing else is reachable from the internet.
2. **Private application network** (Docker network / LAN) — SUPERVOID backend, Brain Gateway, MCP server, LibreChat backend, Postgres/pgvector. Reachable only between services.
3. **Inference tier** — vLLM, on the dedicated AI workstation's private LAN. Reachable only by the Brain Gateway (and, on the private net, by smoke-test scripts). **Never** bound to a public interface and **never** added to the internet-facing reverse proxy.

**Indicative ports** (all overridable via env; only nginx is published to the host/internet):

| Component | Port (container/host) | Exposure | Notes |
|---|---|---|---|
| nginx (frontend) | `80` → `${FRONTEND_PORT:-8080}` (and `443` in prod) | **public** | only internet-facing surface |
| SUPERVOID backend (FastAPI) | `8000` | private | proxied by nginx at `/api`, `/public` |
| PostgreSQL / pgvector | `5432` | private | swap base image to a pgvector build when RAG lands |
| SUPERVOID Brain Gateway | `8100` (proposed) | private | OpenAI-compatible; the only caller of vLLM |
| SUPERVOID MCP server | `8200` (proposed) | private | governed tools/resources; LibreChat is the MCP client |
| LibreChat | `3080` (its default) | private→nginx | UI proxied by nginx; talks to Gateway + MCP |
| vLLM | `${VLLM_PORT:-8000}` on the AI workstation | private LAN only | **bound to private/LAN, never the public proxy** |

> vLLM's default `8000` collides with the backend's `8000`; they live on different hosts/networks. When co-located, override `VLLM_PORT` (e.g. `8001`). The Gateway reaches vLLM by its private address, not via nginx.

---

## 5. Models, tables, endpoints, services and deployment files to add

Planned across the whole initiative (not implemented by this audit). Each schema change ships its own Alembic migration; each phase is one commit.

**New tables / models (additive, nullable FKs, NAMING + batch mode):**
- `conversations`, `conversation_turns` — persistent multi-turn history, scoped to Work/StoryWorld/global.
- `conversation_participants` + `user_chat_identities` — member-to-chat identity mapping bound to `User`/`ProjectMembership`.
- `project_brain_state` (and/or `studio_state`) — compiled, versioned working state per scope.
- `domain_events` — transactional event outbox (event_type, aggregate_type/id, payload, occurred_at, published_at).
- `retrieval_chunks` + vector embeddings (pgvector column) and `citations` (turn/finding → source entity + span).
- `eval_datasets`, `eval_cases`, `eval_results` — evaluation corpus + runs.
- (optional) `brain_request_log` — per-request token/cost/model accounting for quotas.

**New endpoints / services:**
- **Brain Gateway** (OpenAI-compatible server): `GET /v1/models`, `POST /v1/chat/completions` (streaming), enforcing auth + policy + model allowlist + request-id + redaction. New service module; mounts behind nginx, private.
- **Brain conversation API** (`/api/brain/*`): create/list conversations, post turns, fetch compiled state + citations. Private, `AUTHED`, policy-gated.
- **State compiler service** — builds `ProjectBrainState` from domain events; subscribes to the outbox.
- **Event outbox dispatcher** — reliable publish of `domain_events`.
- **Embedding/retrieval service** — index + rank corpus for RAG (Postgres/pgvector only; SQLite degrades gracefully).
- **SUPERVOID MCP server** — concrete boundary: (a) **read resources** — Works, Manuscripts, Knowledge entities and the published projection, every read first passing `policy.can(...)` (and `/public`-equivalent published-only filtering for any unauthenticated context); (b) **tools** — only governed actions, each routed through the existing `AgentActionProposal` / `IntegrationRun` approval gates (nothing auto-executes; HIGH/CRITICAL stay ADMIN-gated); (c) **never** — raw SQL, shell, unrestricted filesystem or unrestricted HTTP. The MCP server is a thin, governed bridge, not a new authority.

**New deployment / config files:**
- `deploy/brain/docker-compose.vllm.yml` (**Phase 1**) + `.env.brain.example` + start/stop/logs/test/benchmark scripts + `docs/VLLM_DEPLOYMENT.md`.
- `deploy/brain/docker-compose.gateway.yml`, `…librechat.yml`, `…mcp.yml` (later phases), composable as profiles.
- Postgres image swap to a pinned `pgvector`-enabled build (RAG phase).
- nginx route additions for the LibreChat UI; **no** route to vLLM.
- New `Settings` fields (env-driven), e.g. `brain_enabled`, `brain_gateway_url`, model allowlist, mirroring the existing `ai_*` and `integrations_allow_network` conventions.

---

## 6. Migration risks

- **pgvector is Postgres-only.** SQLite (local-first default) has no vector type. RAG features must be **capability-gated** (Postgres-only; SQLite path keeps working with retrieval disabled or a non-vector fallback). `manage_db check` must pass on **both** backends, so vector columns/migrations need a dialect-aware guard.
- **Base-image change.** Moving `postgres:16-alpine` → a pinned `pgvector/pgvector:pg16` image is an ops change; volume data must be preserved and the extension `CREATE EXTENSION vector` added idempotently in a migration.
- **Additive-only discipline.** New tables/columns must be nullable, NAMING-convention-compliant, batch-mode, and must not alter or rename existing columns — otherwise `manage_db check` and backward-compatibility tests fail.
- **Sync vs streaming/async.** The app is synchronous (`httpx`, sync SQLModel sessions). Streaming chat completions and an event-outbox dispatcher introduce async/background concerns that must not destabilize existing request/response paths.
- **Secrets surface grows.** `VLLM_API_KEY`, Gateway keys and LibreChat secrets must follow the existing rules: env-only, `credential_refs`-style names, `redact()` on snapshots/logs, never in API responses or DB snapshots.
- **Public/private wall.** Brain, Gateway and MCP are strictly `/api`-private; none may read or echo draft/editorial data into `/public`. The MCP server must never expose a path that bypasses `public_reader`'s published-only projection.
- **Authority creep.** The Brain must not become a second source of truth. Facts stay in the DB, permissions in the policy service, approvals in the approval system. No raw SQL/shell/filesystem/HTTP for the LLM.
- **No competing agent framework.** Brain orchestration must reuse `AgentRun`/`AgentFinding`/`AgentActionProposal`/`PromptTemplate`/`IntegrationRun`, not fork a parallel one.
- **Test/CI weight.** vLLM/LibreChat are heavy and GPU-bound; their smoke tests must be **opt-in and env-gated**, never required by the default backend suite (which stays hermetic and offline). Concretely: gate them behind a pytest marker (e.g. `@pytest.mark.vllm_smoke`) skipped unless `VLLM_SMOKE_TESTS=1`; CI and the default `pytest` run keep `VLLM_SMOKE_TESTS=0`, so the §9 baseline stays reproducible with no GPU or network.

---

## 7. Implementation order (matching the prompts)

The initiative is sequenced so each phase is independently shippable, testable, and a single commit. **Phase 0 = this audit.**

- **Phase 1 — Dedicated vLLM inference deployment (Prompt 1).** ✅ *Delivered — see [`VLLM_DEPLOYMENT.md`](./VLLM_DEPLOYMENT.md).*
  `deploy/brain/docker-compose.vllm.yml` (pinned vLLM OpenAI image, all settings env-driven), `.env.brain.example`, `docs/VLLM_DEPLOYMENT.md`, and start/stop/logs/test/benchmark scripts incl. health, model-list, chat/structured/tool/streaming smoke tests + concurrency & prefix-reuse benchmarks. vLLM bound to the **private** network; documented validation procedure for any AWQ/GPTQ checkpoint before it becomes a default. **No app code, no LibreChat, no Gateway yet.** Complete when the server starts standalone and passes the OpenAI-compatible smoke tests.
- **Phase 2 — SUPERVOID Brain Gateway (Prompt 2).** OpenAI-compatible server in front of vLLM: auth (reuse JWT), policy checks, model allowlist, request-id correlation, prompt/secret redaction, logging, streaming passthrough. This is the component LibreChat will target. *Done when:* the Gateway serves `GET /v1/models` + `POST /v1/chat/completions` (incl. streaming) on the private net, rejects unauthenticated/off-allowlist requests, redacts secrets from logs, stamps `request_id`, and the existing backend suite still passes with no regression.
- **Phase 3 — Conversation domain + identity + event outbox + state compiler (Prompt 3).** 🟡 *Persistence layer delivered (migration `0014`: studio/project state, immutable revisions, append-only events, conversations/messages/checkpoints, memory, decisions — see [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervoid-brain--persistence-layer)). The **transactional domain-event outbox** is delivered too (migration `0015`): a single `brain.emit` emitter wired into all 13 principal mutation domains, a cursor/idempotent/retry/dead-letter/replay consumer that performs project-scoped recompilation scheduling (marks state `stale`), a worker + one-shot CLI + reconciliation command, and admin monitoring endpoints under `/api/brain/outbox` — see [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervoid-brain--domain-event-outbox). The **deterministic state compiler is delivered** (`compiler.py` + `state_builders.py`): it builds the studio + per-project structured state purely from SQL/services, renders a budgeted compact summary (templates first, optional guarded LLM prose), compiles incrementally (only event-affected sections, incremental==full checksum) with full rebuild for DR, and exposes state/health/stale/delta/rebuild APIs plus a worker, CLI and an admin Brain State Inspector — see [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervoid-brain--deterministic-state-compiler). The **stable instruction layer + ContextAssembler is delivered** (migration `0016`): versioned Studio Constitution, 8 assistant profiles, context templates, safety/approval policy and terminology glossary, plus a permission-filtered, injection-delimited, prefix-hashed ContextAssembler with an admin debug endpoint — see [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervoid-brain--stable-instruction-layer--contextassembler).* **State-version-aware:** the compiler will stamp each `project_brain_state` with a monotonic version; every `conversation_turn` records the state version it consumed, so the Brain can detect staleness (turn version < current version) and recompile context. *Done when:* migrations apply on SQLite + Postgres, `manage_db check` passes, turns persist with their state version, and citations can reference a state version.
- **Phase 4 — SUPERVOID MCP server (Prompt 4).** Governed tools/resources delegating to the policy service + approval system (the integration-hub approval boundary is the template; see §5 for the resource/tool boundary). *Done when:* an MCP client can list resources/tools, every read is policy-gated, every mutating tool produces an approval-gated proposal/run, and no tool exposes raw SQL/shell/HTTP/filesystem.
- **Phase 5 — LibreChat deployment (Prompt 5).** Containerized UI wired to the **Brain Gateway** (not vLLM) and to the MCP server as MCP client; account linking to SUPERVOID members; nginx route for the UI. *Done when:* a SUPERVOID member signs in, holds a multi-turn conversation through the Gateway, and MCP tool calls are governed — with no network path from the UI to vLLM.
- **Phase 6 — pgvector + RAG + citations (Prompt 6).** pgvector image, embedding/retrieval service, `retrieval_chunks` + `citations`; capability-gated for Postgres. *Done when:* retrieval is enabled on Postgres and cleanly disabled on SQLite, assistant turns carry citations to source entities/spans, and `manage_db check` passes on both backends.
- **Phase 7 — Evaluation corpus (Prompt 7).** `eval_datasets`/`eval_cases`/`eval_results` + a bench runner to measure and regress Brain quality. *Done when:* a corpus can be loaded, a bench run scores Brain outputs, and results persist for regression tracking.

> The Prompt 2–7 mapping is the expected sequence implied by the topology; later prompts may refine names/scope, but the ordering (inference → gateway → state/identity → MCP → UI → retrieval → eval) is load-bearing because each phase depends on the one before it.

---

## 8. Production rule restated

**LibreChat connects to the SUPERVOID Brain Gateway, not directly to vLLM, in
production.** The Gateway is the governance choke point (auth, policy, model
allowlist, correlation, redaction, citations, logging). vLLM remains private,
inference-only, and is never placed behind the internet-facing reverse proxy.

---

## 9. Baseline test & build results (pre-change, 2026-06-26)

Captured on the audited tree before any Brain work, as the regression baseline:

| Check | Command | Result |
|---|---|---|
| Backend test suite | `python -m pytest -q` (37 files, `tests/`) | **374 passed, 1 warning** (exit 0, ~206 s) |
| Migration verification | `python scripts/manage_db.py check` | **migrations match the models ✓** (chain `0001 → 0013`, exit 0) |
| Frontend typecheck | `npx tsc -b --noEmit` | **clean** (exit 0) |
| Frontend production build | `npm run build` | **159 modules transformed, built ✓** (exit 0) |

Notes:
- The single warning is pre-existing and unrelated to this work: pydantic flags `StyleAnalysisResult.register` as shadowing a `BaseModel` attribute (`app/services/ai/features/style_analysis.py`).
- Backend tests run hermetically (in-memory SQLite, `dry_run` provider, no network). Any vLLM/LibreChat smoke tests added later must stay opt-in so this baseline remains reproducible offline.
