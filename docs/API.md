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
  templates** (versioned).

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
