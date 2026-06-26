# Architecture — SUPERVOID Publishing

SUPERVOID Publishing is a **local-first** production and publishing management
system for books, graphic novels, manuscripts, and editorial projects. It is
the publishing division of **SUPERVOID ENTANGLED**, built so that the future
**SUPERVOID Movies** division can reuse its patterns and so the separate
**LOGOSFORGE** writing subsystem can feed into it.

## Stack

| Layer    | Choice                                          |
| -------- | ----------------------------------------------- |
| Backend  | Python 3.11+, FastAPI, SQLModel, Uvicorn        |
| Database | SQLite (local-first), PostgreSQL-ready          |
| Frontend | React 18, Vite 5, TypeScript, TailwindCSS 3     |
| Auth     | JWT (PyJWT) + bcrypt, role-based access control  |
| AI       | Provider-pluggable (`dry_run` default; `vllm`, OpenAI-compatible); async + streaming + tools + structured output |
| Theme    | Dark, editorial, archival                       |

## Repository layout

```
backend/
  app/
    main.py          FastAPI application factory + middleware + error handlers
    db.py            Engine, session, init_db + prepare_database (startup)
    migrations.py    Alembic helpers (config, upgrade/stamp/ensure/verify)
    config.py        Env-driven settings (app name, db url, db_init_strategy, AI)
    seed.py          Idempotent demo corpus
    auth/            Password hashing, JWT, DI dependencies (roles)
    models/          SQLModel domain entities + enums
    schemas/         Pydantic request/response payloads
    routers/         HTTP routers (one per resource) + public_reader (/public)
    services/        Business logic (workflow, knowledge, AI, exports, storage,
                     public_reader_service)
    integrations/    Ecosystem integration contracts (LOGOSFORGE, Movies)
    services/integrations/adapters/   Hub adapters (n8n, comfyui, github,
                     file_exchange.*, logosforge) + effects
    static/demo/     Local placeholder media for the public reader
    utils/           crud, logging, request-id middleware, pagination
  alembic/           Migration environment + versions/ (baseline … 0012)
  alembic.ini        Alembic config (URL resolved from settings in env.py)
  scripts/manage_db.py       Migration CLI (upgrade/stamp/ensure/verify/check)
  scripts/backup_restore.py  Logical dump/restore (records + asset storage)
  tests/             Pytest suite (incl. test_e2e_workflows, test_backup_restore)
frontend/
  src/
    main.tsx         Entry — admin App, or PublicViewerApp for /reader*
    App.tsx          Private admin root + view routing
    pages/ components/ layouts/ api/ types/ auth/   Private admin app
    styles/          Shared SUPERVOID design tokens (supervoid-tokens.css)
    public-viewer/   Public Graphic Novel Webviewer (own pages/player/api/types)
docs/                Architecture, roadmap, branding, migration, public viewer
scripts/             Local backup / restore helpers
```

## Domain model

`Work` is the **central catalogue entity** — the publishing *project* (a book,
graphic novel, art book, essay, or future adaptation candidate). `Manuscript`
is a **text draft/version** of a Work; work-level concerns attach to the Work,
while editorial concerns attach to the manuscript.

```
          Author 1──* Work 1──* Manuscript *──1 ProductionRecord
                       │             │
   ┌─────────┬─────────┼─────────┬───────────────┬───────────────┐
   *         *         *         *               1                *
 Rights   Contract  Review  ProductionItem  GraphicNovel     EditorialNote
                       │                     Production
                 WorkflowEvent (audit trail of manuscript status)
 PublishingCalendarEvent *──1 Work           Attachment, AIInsight
 Manuscript *──* KnowledgeEntity *──* KnowledgeRelationship
```

- **Work** (`works`) — title, subtitle, `work_type`, `genre`, `WorkStatus`
  lifecycle (concept → in_development → in_production → published → archived…),
  synopsis, internal pitch, target audience, language, word/page counts, author.
- **Manuscript** (`manuscripts`) — a text draft of a Work (`work_id`): `version`,
  `DraftStatus`, submission date, file-metadata placeholder, and the editorial
  `WorkflowStatus`. Remains the operational unit for the review / workflow /
  production / knowledge / AI subsystems carried over from the foundation.
- **Work type** — shared `WorkType` (`book`, `graphic_novel`, `novella`,
  `anthology`, `art_book`, `essay`, `adaptation_candidate`, `other`)
  distinguishes product lines over one shared workflow and production pipeline.
- **Author** — name, pen name, email, phone, website, bio, notes; linked works
  and manuscripts.
- **Review** — recommendation (`accept`/`reject`/`revise`/`hold`) plus a rubric
  (literary quality, visual potential, market potential, originality, editorial
  effort) and a written report.
- **Contract** — author + work/manuscript, status, advance, royalty rate,
  territory, signed and expiration dates.
- **Rights** (`rights`) — a per-work, per territory/language profile; each right
  (print, ebook, audiobook, film, adaptation, merchandising) carries a
  `RightStatus` (available / reserved / optioned / licensed / sold / n-a).
- **GraphicNovelProduction** (`graphic_novel_productions`) — the high-level
  visual-production summary for illustrated works (script → storyboard →
  character/environment design → page layout → lettering → colouring → final
  files, each a `StreamStatus`). Detailed statuses roll up into it from the
  production hierarchy below (see *Graphic-novel production hierarchy*).
- **Production** — `ProductionRecord` is a 1:1 edition roll-up (ISBN, release
  date, per-format and per-stage `StreamStatus`); `ProductionItem` has evolved
  into a general cross-medium production **task** (see *Production task system*
  below) while staying backward compatible.
- **PublishingCalendarEvent** (`calendar_events`) — dated catalogue events
  (release, cover reveal, preorder…), optionally tied to a Work; date-range
  filterable.
- **EditorialNote** — typed notes against a manuscript, optionally also a Work
  and/or subject author.
- **WorkflowEvent** — audit trail of manuscript status transitions.
- **IntegrationPoint** (`integration_points`) — a persisted, CRUD-able registry
  of planned/active ecosystem integrations (complements the static descriptors).
- **Knowledge graph** — typed `KnowledgeEntity` nodes and
  `KnowledgeRelationship` edges, linked to manuscripts; the natural seam for
  LOGOSFORGE narrative structure.
- **ProjectMembership / MembershipAudit** (`project_memberships`,
  `membership_audits`) — project-scoped collaboration on a Work and/or
  StoryWorld, plus an append-only audit trail. See *Collaboration &
  project-scoped access control* below.

> Back-compat: `work_id` is nullable on carried-over entities, so the editorial
> subsystems and their tests keep working while the Work hub is layered on top.

## IP / transmedia layer (a bounded context above Work)

A studio context sits *above* the catalogue. `Work` remains the central
production/catalogue entity; the IP layer groups Works into universes and tracks
adaptations across divisions. It is a **bounded context inside the modular
monolith** — its own models, schemas and routers, related to `Work` only by
nullable foreign keys — so a future SUPERVOID Pictures/Interactive/Audio surface
can be extracted along the `AdaptationDossier` / `Work.source_work_id` seams
without a rewrite (no separate service is introduced now).

```
            StoryWorld 1──* StorySeries
                │  (parent_id self-ref for meta-universes)
                *                 *
              Work  ◀── story_series_id / story_world_id (nullable)
                │
   source_work_id (self-ref)        AdaptationDossier
   Work ◀───────────────────  source_work_id ──┐
   Work ◀── target_work_id (optional) ──────────┘  (medium + division + lifecycle)
```

- **StoryWorld** (`story_worlds`) — an IP / narrative universe: name, slug,
  description, canon summary, `StoryWorldStatus`, visual-identity notes, default
  language, owner (Author), optional parent world. Owns identity and canon.
- **StorySeries** (`story_series`) — an ordered series within a world (title,
  description, `sequence_order`, `StorySeriesStatus`).
- **Work placement** — Works gain nullable `story_world_id` / `story_series_id` /
  `series_order`, a `primary_division` (`StudioDivision`), `primary_medium`
  (`Medium`), `canon_status` (`CanonState`), and a self-referential
  `source_work_id` (the originating Work, when derived/adapted).
- **AdaptationDossier** (`adaptation_dossiers`) — a development dossier adapting a
  source Work into a `target_medium` / `target_division`: `AdaptationStatus`
  lifecycle, logline, format, intended scope, `RightsClearanceState`, creative
  notes, source revision, and an optional `target_work_id` once a concrete Work
  is created. `GET /api/works/{id}/transmedia` composes a Work's world, series,
  source, derived works and dossiers into one overview.

All enums (`StudioDivision`, `Medium`, `CanonState`, `AdaptationStatus`,
`RightsClearanceState`, `StoryWorldStatus`, `StorySeriesStatus`) live in
`models/enums.py`. Frontend sections: **Story Worlds** (list + detail, with the
**Series** panel and the world's Works), **Adaptation Dossiers**, and a
**Work-level transmedia overview**.

## Request flow

```
React (api/*.ts) ──HTTP──> FastAPI router ──> service / crud util ──> SQLModel ──> SQLite/Postgres
                              │
                         schema validation (Pydantic)         RequestId + structured logging
```

The app factory (`create_app`) mounts every router in `routers.ALL_ROUTERS`
under the `/api` prefix, installs CORS and a request-id middleware, and
registers a consistent set of error handlers.

**Structured error envelope.** Every error response — `HTTPException` (404 /
400 / 401 / 403 / 409 …), request-validation (422), `IntegrityError` (409) and
the catch-all 500 — returns the same JSON shape: `{"detail": <string>,
"request_id": <id>}` (validation errors add a structured `"errors"` list), with
the `X-Request-ID` header set on every response (errors included). Any
exception-supplied headers (e.g. `WWW-Authenticate` on 401) are preserved.

**Request correlation.** The request-id middleware mints (or honours an inbound)
`X-Request-ID` and stamps it on `request.state`, every log record, and the
response. Agent runs and integration runs carry that id as their
`correlation_id` (falling back to a fresh id off-request), so a run is traceable
back to the HTTP request — and, for integration runs, across its whole
approve/execute lifecycle.

## Authentication & roles

JWT bearer tokens; the **global** `UserRole` is one of `admin`, `editor`,
`reviewer`, `production_manager`, `marketing`, `archive_reader`. Dependency
helpers (`AUTHED`, `ADMIN_ONLY`, …) guard write and privileged routes; reads are
generally public for the local archive experience.

User accounts are managed at `/api/users` (admin-only): list/create/get/patch,
`activate`/`deactivate`, and `rotate-password` (admin-or-self). `/api/auth`
remains responsible only for issuing tokens and reporting the current user.

## Collaboration & project-scoped access control

The global `UserRole` governs studio-wide actions; it is **not** replaced.
Layered on top is **project-scoped** access control so collaborators can be
given access to a specific Work or StoryWorld without becoming studio admins.

- **`ProjectMembership`** — a user's membership on a project (a `work_id`
  and/or `story_world_id`), carrying a project `role`, a lifecycle `status`
  (`invited` → `active`, plus `suspended`/`declined`/`revoked`), `invited_at`,
  `accepted_at`, `created_by`, and optional `notes`. A membership scoped to a
  StoryWorld **cascades** to every Work in that world.
- **Project roles** (14): `owner`, `director`, `editor`, `writer`, `artist`,
  `letterer`, `colourist`, `animator`, `sound_designer`, `technician`,
  `production_manager`, `marketing`, `reviewer`, `viewer`.
- **Permission scopes** (11): `view_project`, `edit_narrative`,
  `edit_visual_assets`, `manage_production`, `upload_assets`, `review`,
  `approve`, `manage_collaborators`, `publish`, `manage_rights`,
  `manage_marketing`.

**Policy service** (`app/services/policy.py`) is the single source of truth.
`can(session, user, scope, work_id=…, story_world_id=…)` combines, in order:
the global role (an `admin` is a super-user — this is how existing admin
behaviour stays valid), project **membership** (active memberships on the Work
or its world), **ownership** (the `owner` project role grants every scope), and
the requested **operation**. The role → scope matrix lives in `ROLE_SCOPES`;
when several memberships apply, the strongest role wins (`ROLE_RANK`).

Routers never hand-roll checks. They use the reusable helpers:
`require_scope(scope)` (a FastAPI dependency that reads the project id from the
path) for path-scoped routes, and `ensure_can(...)` for membership-id routes
that load the record first. Membership changes append an immutable
**`MembershipAudit`** row (decoupled, no FKs, so the trail survives revocation).

Endpoints (`routers/collaborators.py`, mounted unprefixed under `/api`):

- `GET|POST /works/{work_id}/members`, `GET|POST /story-worlds/{world_id}/members`
  — list (needs `view_project`) and invite (needs `manage_collaborators`).
- `PATCH /memberships/{id}` (role), `…/suspend`, `…/reactivate`,
  `DELETE /memberships/{id}` (soft-revoke) — all need `manage_collaborators`.
- `POST /memberships/{id}/accept` · `…/decline` — restricted to the invited user.
- `GET /memberships/{id}/audits` — the change history (needs `manage_collaborators`).
- `GET /me/projects` — the caller's memberships with resolved scopes.
- `GET /collaboration/roles` — the role → scope matrix, for the UI.

The private UI surfaces a **Collaborators panel** inside each StoryWorld and
each Work (`components/CollaboratorsPanel.tsx`): invite, change role, suspend /
reactivate / revoke, accept / decline your own invitations, and per-member
history. It self-gates manage controls from `/me/projects` (or global admin).

## Production task system

`ProductionItem` (the `production_items` table) has grown from a publishing-stage
checklist item into a general production **task** spanning publishing, graphic
novels, film, audio and interactive work — without breaking the original
`/production-items` endpoints or records.

- **Backward compatibility** — the original columns (`manuscript_id`, `stage`,
  `status`, `due_date`, `notes`, `assignee_id`) and routes are untouched.
  `manuscript_id` and `stage` became nullable; `work_id` is now the primary
  project link. `ProductionItemStatus` was *extended* (the original
  `pending/in_progress/blocked/done` plus `todo/in_review/changes_requested/
  approved/cancelled`), so existing rows remain valid (migration `0004` rebuilds
  the table on SQLite via a naming convention, defaulting new NOT NULL columns).
- **New fields** — title, description, story_world_id, division, track,
  task_type, priority, creator, reviewer, parent (subtasks), milestone,
  start/due/completed dates, estimated/actual effort, blocked reason, acceptance
  criteria, deliverable asset, revision number.
- **Related entities** — `ProductionDependency` (a directed dependency edge),
  `ProductionMilestone` (checkpoints tasks group under), `ApprovalRequest`
  (human approval gate), and the append-only `ProductionActivity` log.
- **Workflow engine** (`app/services/production.py`) — `ALLOWED_TRANSITIONS`
  defines a validated state machine; completion/review transitions are blocked
  while finish-to-start dependencies are unmet; `would_create_cycle` guards the
  dependency graph; every change appends a `ProductionActivity`.
- **AI safety** — `HUMAN_ONLY_STATUSES = {APPROVED, DONE}`: completion and
  approval are reachable only through authenticated endpoints, never AI/service
  code. Deciding an `ApprovalRequest` requires the assigned human approver (or
  an admin), and approving does **not** auto-complete the task.

Surfaces (private API, mounted under `/api`):

- `/production-items` — the **legacy** CRUD, unchanged.
- `/production-tasks` — the rich surface: CRUD + detail (with derived
  `is_blocked` / unmet-dependency / subtask data), `/transition`, `/subtasks`,
  `/dependencies`, `/activity`, `/approvals`, and the queries `/my-assignments`,
  `/overdue`, `/blocked`, `/awaiting-approval`.
- `/milestones` — milestone CRUD + `/{id}/tasks`.
- `/approvals` — list/get/create, `/decide` (human-gated), `/cancel`.
- `/production-templates` + `POST /works/{id}/production-template` — list the
  starter templates and instantiate one onto a Work. Starter templates
  (`app/services/production_templates.py`): graphic novel volume, book
  publication, short film, feature film, animated sequence, promotional launch.

The private UI adds a **Production tasks** board (`ProductionTasksPage`) with
Kanban / list / timeline views, inline task creation, template application, and
a per-task panel for validated transitions, dependencies and activity.

## Asset Library

The central, work-centred home for reusable creative material. Distinct from
`Attachment` (a manuscript-scoped file record, unchanged for backward
compatibility): assets are durable identities whose bytes live in versioned
rows, carrying provenance and licensing. **Assets are private and never served
through the public reader** — public media uses the curated public projection.

- **`Asset`** (`assets`) — title, asset type, work / story-world association,
  canonical status (`CanonState`), visibility, owner, tags (JSON), description,
  and a pointer to the current version.
- **`AssetVersion`** (`asset_versions`) — one revision's bytes: storage key,
  MIME type, dimensions, duration, checksum, size, creator, approval status,
  `superseded_by` link, and free-form technical metadata (JSON).
- **`AssetLink`** (`asset_links`) — connects an asset (optionally a specific
  version) to a character, location, page, panel, scene, shot, production task,
  public-reader record, work or story world. Generic (`target_type` + id) so it
  can reference entities that are not first-class tables.
- **`ProvenanceRecord`** (`provenance_records`) — per-version disclosure:
  human-created / AI-assisted / AI-generated / mixed, provider, base model and
  version, LoRA/adapter ids, prompt + negative prompt, seed, sampler/settings,
  source references, ControlNet inputs, generating workflow, human
  modifications, generation date, responsible user, and commercial-use review.
- **`LicenceRecord`** (`licence_records`) — rights holder, licence type, source,
  territory, permitted uses, attribution, expiration, evidence file, review state.

Storage is abstracted behind `StorageBackend` (`app/services/storage.py`): a
local filesystem adapter ships today; a remote/object-storage adapter implements
the same interface later. The asset service (`app/services/assets.py`) owns
versioning, **checksum-based duplicate detection**, version **promotion /
rollback** (`set_current_version` supersedes the previous head), **provenance
completeness** checks (the AI-disclosure gate, by provenance kind), and
**licence-expiry warnings**.

Surface (`/assets`, fully private — every route requires auth):

- Asset CRUD with search/filters (title, type, work, story world, canon,
  visibility, owner, tag).
- `/{id}/versions` (+ `/upload` with in-asset checksum dedupe, `/promote`,
  `/rollback`, `/approve`), and private `/download` + inline `/preview`.
- `/{id}/versions/{vid}/provenance` (+ `/completeness`),
  `/{id}/links`, `/{id}/licences`, plus library-wide `/licence-warnings` and
  duplicate discovery `/versions/by-checksum/{checksum}`.

Approval of a version and commercial-use review are human actions; nothing here
auto-approves. The private UI adds an **Asset Library** browser with version
history, preview/download, provenance and licence panels.

## Graphic-novel production hierarchy

`GraphicNovelProduction` stays the high-level summary; beneath it sits a detailed
breakdown so a graphic novel can be planned and tracked panel by panel::

    GraphicNovelProduction → Volume → Chapter → Sequence → Page → Panel → element

- Every level (`gn_volumes`, `gn_chapters`, `gn_sequences`, `gn_pages`,
  `gn_panels`) has a stable `position` (for reorder) and a `GNStatus`.
- **`GraphicNovelPage`** — page number, spread membership + page side, script,
  visual brief, dialogue summary, lettering/colour/final `StreamStatus`, print
  geometry (width/height/bleed/safe-area mm), linked **master asset** (Asset
  Library), and a deliberate `curation_status` + `published_page_id` mapping.
- **`GraphicNovelPanel`** — panel number, normalised x/y/width/height, script
  beat, dialogue, captions, sound effects, camera framing & angle, lens
  metadata, continuity notes, storyboard & final asset-version links (for
  comparison), and an approval status.
- **`GraphicNovelPanelElement`** — characters, props, locations and text within
  a panel. Characters/props/locations reference a `KnowledgeEntity` (and
  `GraphicNovelPageEntityLink` does the same at page level) — characters and
  locations are linked, never duplicated, into the production hierarchy.

The service (`app/services/graphic_novel.py`) provides the **roll-up** of
detailed statuses into the summary, **completion percentages**, **page/spread
validation** (panel bounds, page-number uniqueness, spread integrity),
**print/digital readiness** checks, **duplication** (page & panel, deep-copying
panels/elements), **reordering**, and **storyboard↔final comparison**.

Surfaces (private API): CRUD for each level (`/graphic-novel-productions/{id}/
volumes`, `/gn-volumes/{id}/chapters`, … `/gn-pages/{id}/panels`,
`/gn-panels/{id}/elements`), `…/reorder`, `…/duplicate`, page/panel
`…/validate`, `…/comparison`, and production-level `/progress`, `/validate`,
`/readiness`, `/recalculate`, `/tree`, and `/curation-handoff`.

**Curation hand-off, not publish.** `/curation-handoff` proposes which pages are
ready for the public reader and (with `?commit=true`) marks them
`READY_FOR_CURATION` — it **never writes the public reader**. Publishing remains
the separate, deliberate public-projection step. The private UI adds a
**Graphic-novel studio**: a volume/chapter/page/panel navigator, a visual
page-board, a panel coordinate editor, and progress/readiness views.

## SUPERVOID Pictures (screen bounded context)

The first operational sibling division, living **inside this repository** but
kept extractable into its own service later (its own status vocabulary; all
cross-context references held by id). Entered via `AdaptationDossier` — the
publishing → screen seam — and structured::

    ScreenProject → ScreenUnit (Episode/Reel) → ScreenSequence → Scene → Shot

Supports films, shorts, series and animation (`ScreenFormat`, `ScreenUnitType`).

- **Scene** — heading, location, interior/exterior, time of day, synopsis,
  script text, characters (via `SceneCharacterLink` → `KnowledgeEntity`),
  estimated duration, production status, continuity notes.
- **Shot** — shot number, framing, camera angle, movement, lens, duration,
  blocking, lighting, dialogue, sound, music, VFX, a source storyboard panel
  (`gn_panels`), linked asset versions (`ScreenShotAssetLink`), status and
  approval. Panels map to one or more shots via `ScreenShotPanelLink`.

Operations (`app/services/screen.py`, surfaced under `/api/screen`):

1. **Promote** a Work / graphic novel into an `AdaptationDossier`
   (`POST /screen/dossiers/promote`, `target_division = pictures`).
2. **Create a ScreenProject** from an *approved* dossier
   (`POST /screen/projects/from-dossier/{id}` — rejects proposed/abandoned).
3. **Reuse graphic-novel pages/panels** as storyboard references
   (`GET /screen/projects/{id}/storyboard`).
4. **Map panels to shots** (`POST /screen/shots/{id}/panels`, many-to-many).
5. **Carry references** — knowledge entities (scene characters), rights (from
   the source Work) and provenance (via shot asset versions):
   `GET /screen/projects/{id}/references`.
6. **Shot lists & breakdowns** (`/shot-list`, `/breakdown`).
7. **Export the adaptation package** as JSON or Markdown (`/export?format=`).

This makes the SUPERVOID Movies integration descriptor **operational**
(`status = available`) rather than a future plan — without another deployment or
repository. The private UI adds a **Screen studio** (dossiers, scenes, shots,
export).

## Supervised studio-agent framework

The manuscript AI layer (`/api/ai`, `AIInsight`) is preserved unchanged; on top
of it sits a governed agent framework where every run, finding and proposed
action is persisted.

**Model-provider client** (`app/services/ai/providers`): a pluggable
chat-completion abstraction. The legacy synchronous `chat()` contract is kept
for the editorial features; alongside it the providers expose an async client
over a reusable connection pool with streaming, tool definitions / tool choice /
returned tool calls, structured JSON-schema output, reasoning fields, stop / top_p
/ top_k / presence + frequency penalties, request-id propagation, cancellation +
timeout, model listing and health checks. `CompletionResult` additively carries
finish reason, tool calls, reasoning, request id, latency, usage and provider
metadata. A dedicated **`vllm`** provider declares the full capability set;
**`openai_compatible`** stays the generic catch-all with conservative, *declared*
capabilities (we never assume a backend supports a feature). Retries apply only
to safe transient failures (connection error, timeout, selected 5xx) and never
re-issue a completed call. `GET /api/ai/health` reports the configured provider,
reachability, active model, capabilities and latency — never the API key. No
OpenAI-compatible SUPERVOID endpoint is exposed yet (that is a later phase).

- **Code-registered** (`app/services/agents`): `AgentDefinition`s (key, name,
  supported entity types, required permissions, allowed tools, mutability,
  default provider/model, enabled) and a **tool registry** of read-only,
  proposal-only mutation, and external tools — each with a risk level and
  permission declarations.
- **Persisted**: `AgentRun` (agent, requester, target, provider/model, input
  snapshot, status, timestamps, result, error, token/cost metadata, correlation
  id), `AgentFinding` (severity, category, target, message, evidence,
  confidence, resolved), `AgentActionProposal` (tool, payload, reason, risk,
  approval status + actors, execution result), and `PromptTemplate` +
  `PromptTemplateVersion` (append-only version tracking).

Rules enforced by the runner (`app/services/agents/runner.py`):

- read-only analysis executes immediately (findings persisted);
- mutations become **proposals** — handlers never touch the database;
- destructive / publishing / rights / external tools are
  `always_requires_approval` and need an **admin** sign-off; execution is
  refused unless the proposal is APPROVED;
- every run preserves its input snapshot and output;
- providers keep dry-run support (the default `DryRunProvider`);
- no secrets in prompts, snapshots, payloads or results (recursive `redact`);
- retry creates a **new** run (`retry_of_id`) — history is never overwritten.

Surface (`/api`, private — the whole router is `AUTHED`): `/agents` +
`/agents/tools` (registry), `POST /agents/{key}/run`, `/agent-runs` (+ detail,
`/retry`), `/agent-findings` (inbox, `/resolve`), `/agent-proposals`
(`/approve`, `/reject`, `/execute`), and `/prompt-templates` (+ `/versions`).
Declared agent permissions are checked through the policy service (admin
bypasses; project scopes resolve against the target work). The private UI adds
an **Agent Centre** (registry, run, history, findings inbox, proposals).

## SUPERVOID Brain — persistence layer

The durable storage for the persistent, governed conversational Brain
(`backend/app/models/brain.py`, migration `0014`). **Storage only — no state is
compiled here** (the compiler is a later phase). Nine tables:

- **StudioBrainState / ProjectBrainState** — the single current compiled state
  for the studio, and one per Work / StoryWorld (version, status, source-event
  cursor, structured state, digests, checksum, stale flag). Upserted in place.
- **BrainStateRevision** — the immutable snapshot of every compiled version
  (deterministic payload + optional LLM summary + source-event range + approval
  status where semantic content could affect canon). Never edited.
- **BrainEvent** — the append-only domain-event log with a monotonic, unique
  `sequence` (assigned by the service); processing fields advanced only by the
  future processor.
- **BrainConversation / BrainMessage / BrainCheckpoint** — persistent
  conversations, their turns (model/provider/tokens/request-id/state-version/
  retrieval + tool-call ids), and prompt-prefix cache checkpoints.
- **BrainMemoryItem** — scoped durable memory (studio / project / member /
  conversation) with kind, confidence, verification state and supersede chain.
- **DecisionRecord** — recorded decisions with a proposed → approved / rejected
  / superseded lifecycle.

Invariants live in `backend/app/services/brain` (revisions/events never edited;
sequences monotonic; current-state upsert + revision snapshot). The private API
(`/api/brain`) applies user/project permissions via the policy service:
conversations are owner-scoped; memory/decisions are scope-gated (studio =
admin, project = project scopes, member = self); compiled state is read-only;
events and revisions are read-only and admin-only. No field stores a model
secret or credential.

The Brain is a **strictly downstream observer**: its references to domain rows
(`work_id` / `story_world_id`) and users (`actor_id`, …) are deliberately
FK-less (migration `0015`), so recording an event or compiled state can never
block — or be blocked by — an upstream domain mutation (deleting a Work,
StoryWorld or User). Internal Brain references (conversation → message → event →
memory → decision) keep their foreign keys.

## SUPERVOID Brain — domain-event outbox

The mechanism that keeps the Brain current without re-reading the whole database
after every question (`backend/app/services/brain/events.py` +
`consumer.py`, migration `0015`). A **transactional outbox**: `BrainEvent` rows
are the outbox table, written in the *same* DB transaction as the mutation they
describe — so the change and its event commit (or roll back) together. No second
datastore, no Redis/Kafka/cloud requirement; PostgreSQL (or SQLite) + the
existing app is enough.

- **Single emitter** — `brain.emit(session, *, event_type, aggregate_type,
  aggregate_id, work_id?, story_world_id?, actor_id?, changes?, …)` appends one
  event inside the caller's transaction. Stable, dotted event names
  (`work.updated`, `page.approved`, `asset.version_promoted`,
  `decision.approved`, `task.completed`, `rights.updated`,
  `publication.approved`, …) live on `BrainEventType` and are never renamed.
  Payloads carry **identifiers + a changed-field summary only** — secret-like
  keys are redacted and structured/oversized values are elided, never a full
  secret-bearing record. `correlation_id` defaults to the current request id.
- **Wired into the 13 principal mutation domains** — Work; StoryWorld /
  StorySeries; Manuscript (incl. workflow transitions); knowledge
  entities/relationships; production tasks + approvals; assets / versions /
  provenance / licences; graphic-novel pages + panels; screen projects / scenes
  / shots; rights + contracts; adaptations; collaborators; publishing / public
  curation; agent findings + approved/executed proposals.
- **Consumer** (`consumer.py`) — selects `PENDING` events in `sequence` order,
  processes each inside its own `SAVEPOINT` (a failure isolates to that event),
  advances `attempts` and dead-letters to `FAILED` after `max_attempts`. The
  cursor is derived as `max(sequence WHERE status = PROCESSED)`; `compiler_lag =
  head_sequence − cursor`. Processing is **project-scoped recompilation
  scheduling only** — it marks the studio state and the affected Work/StoryWorld
  `ProjectBrainState` `stale` (creating a placeholder STALE row if none exists).
  *It does not compile state* (the compiler is a later phase). Duplicate
  consumption is therefore idempotent.
- **Operations** — a background worker, a deterministic one-shot `drain()`, a
  `reconcile()` that re-queues `FAILED` events and marks stale any scope whose
  state cursor trails the latest event (catching anything missed), and manual
  `replay_failed()`. Driven by `backend/scripts/brain_outbox.py`
  (`status` / `run-once` / `worker` / `reconcile` / `replay`) and by admin-only
  endpoints under `/api/brain/outbox` (`/`, `/failed`, `/replay`, `/process`,
  `/reconcile`). Monitoring surfaces unprocessed/failed counts, the current
  cursor and the compiler lag.

## SUPERVOID Brain — deterministic state compiler

The compiler keeps a ready-to-use, compact mental state *before* a user asks a
question (`backend/app/services/brain/compiler.py` +
`state_builders.py`). It turns the raw domain + outbox data into the current
`StudioBrainState` and per-`ProjectBrainState`, plus an immutable
`BrainStateRevision` per version, advancing each state's event cursor.

- **Deterministic by construction.** Every section is built purely from SQL +
  existing read services (`command_centre`-style aggregates, `production`,
  `rights`, `assets`, `graphic_novel`, `screen`). The LLM is **never** asked to
  compute counts, statuses, deadlines, rights ownership or permissions. The
  checksum is `sha256` over a *canonical* JSON encoding (sorted keys, enums →
  `.value`, dates → ISO, sets sorted, percentages rounded), so re-running over
  the same data at the same pinned `compile_date` yields a byte-identical state.
- **Studio state** carries studio identity + divisions, active StoryWorlds,
  active Works, releases, major blockers, pending approvals, rights warnings,
  asset health, collaborator load, integration health and strategic priorities.
- **Project state** (per Work or StoryWorld) carries identity, Work/StoryWorld,
  medium + division, canonical synopsis, canon facts, characters & locations,
  current creative phase, production hierarchy, progress, blocked tasks, assets
  & approved versions, continuity findings, rights constraints, adaptations,
  pending approvals, recent decisions, unresolved questions, recent changes and
  next priorities.
- **Compact summary, facts authoritative.** A deterministic template renders the
  summary from the structured facts (strict per-section + total character
  budgets, deterministic truncation). An *optional* LLM step may compress the
  prose only — and only if a guard proves every numeric fact survived; otherwise
  it falls back to the template. The LLM never touches the structured state or
  the checksum (`assist_version` records the prose model separately from the
  deterministic `compiler_version`).
- **Incremental == full.** `EVENT_SECTION_MAP` maps each domain-event prefix to
  the sections it invalidates. An incremental compile consumes only events past
  the cursor, rebuilds just the affected sections, carries the rest forward, and
  emits a revision — and produces the *same* checksum a full rebuild would at the
  same high-water mark (asserted in tests). A no-op compile (no new events,
  unchanged checksum) writes no new revision. Full rebuild stays available for
  validation and disaster recovery.
- **Downstream-observer.** Like the outbox, the compiler marks state stale but is
  never on the critical path of a domain mutation; it runs in a worker / CLI.

Operated by `backend/scripts/brain_compiler.py`
(`compile-studio` / `compile-project` / `compile-stale` / `rebuild-all` /
`verify` / `health` / `worker`) and admin-only endpoints under `/api/brain`:
`GET /health`, `GET /stale`, `GET /revisions/{a}/delta/{b}`, and
`POST …/state/rebuild`. The private Brain State Inspector (frontend, admin-gated)
shows the compiled facts, summary, version, event cursor, recent deltas and the
rebuild controls.

## Integration layer (ecosystem seams)

`backend/app/integrations/` declares **typed contracts** — not live clients —
for sibling systems under SUPERVOID ENTANGLED:

- `logosforge.py` — the LOGOSFORGE writing subsystem bridge (status
  `available`). The inbound seam is now backed by a **local-first, package-based
  hub adapter** (`logosforge`): it ingests an exported draft *bundle* as a
  manuscript and seeds the knowledge graph through the approval boundary.
  Outbound editorial notes are *recorded only* — there is no live LOGOSFORGE API.
- `movies.py` — the SUPERVOID Pictures bridge, now **operational** (status
  `available`): it points at the in-repo screen context at `/api/screen` (see
  *SUPERVOID Pictures*), not a future external system.
- `ecosystem.py` — the holding map (parent + member systems).

Exposed read-only at `/api/integrations`, `/api/integrations/ecosystem`, and
`/api/integrations/{key}`. Keeping these as descriptors preserves the
local-first principle (no required external services) while making the
extension points explicit and inspectable.

Alongside the static contracts, a persisted **`IntegrationPoint`** registry is
CRUD-able at `/api/integrations/points` (filterable by `type` and `status`).
The `/points` routes are declared before the `/{key}` catch-all so they are not
shadowed by it.

### Operational integration hub

`IntegrationPoint` has grown from a descriptive record into the binding for an
**operational but local-first** hub. Each point may bind a code-registered
**adapter** (`app/services/integrations`) and carries non-secret `config`, a
`credential_refs` map (logical name → ENV-VAR name), and an `enabled` flag.

- **Adapter interface** (`base.py`): health check, capabilities, dry-run,
  inbound operation, outbound operation, status reporting. Each
  `AdapterOperation` declares `mutating` / `external` / `touches_network`, which
  drive the approval boundary.
- **Adapters**: `n8n_webhook` (generic outbound webhook), `comfyui` (queue
  workflows, read status/history, attach outputs to assets with AI provenance,
  import workflow provenance — never assumes ComfyUI is running), `github_project`
  (link commits/issues/PRs to production tasks; dry-run fixtures for remote
  sync), and a `file_exchange.*` profile per desktop app (Affinity, InDesign,
  Clip Studio Paint, DaVinci Resolve, Blender, Cinema 4D, Houdini) that
  generates/ingests **structured packages** rather than pretending to remote-
  control the app, plus `logosforge` (sibling writing subsystem): a local-first
  **bundle import** — `import_manuscript` (draft bundle → manuscript) and
  `sync_knowledge_graph` (entities/relationships → knowledge graph) inbound, with
  `return_editorial_notes` recorded-only. Adapter-only: no live LOGOSFORGE API.
- **Secure configuration** (`config.py`): secrets live only in the environment
  and are resolved by reference at call time; the API never returns secret
  values or env-var names — only presence booleans and masked config.
  `credential_refs` values are validated as env-var names so a raw secret can
  never be stored.
- **Approval boundary** (`service.py`): `IntegrationRun` carries its own
  lifecycle (the equivalent of an `AgentActionProposal`). Read-only operations
  and dry-runs run immediately; mutating/external operations are created
  `PENDING_APPROVAL` and can only ever execute once `APPROVED` — external
  actions additionally require an **admin**. Local-first: outbound network
  effects are *recorded*, not dispatched, unless `INTEGRATIONS_ALLOW_NETWORK` is
  set; internal mutations (asset/provenance/link/package) run for real after
  approval. Inputs and outputs are persisted with secret-like keys redacted.
- **`IntegrationLink`** records external objects (commit/issue/PR) attached to a
  production task.

Surface (declared before `/{key}`, mostly `AUTHED`): `/integrations/adapters`,
`/integrations/points/{id}/health`, `/integrations/points/{id}/config`,
`POST /integrations/points/{id}/operations`, `/integrations/runs`
(+ detail, `/approve`, `/reject`, `/execute`), and `/integrations/links`. The
private UI adds an **Integration Hub** (adapters, points + health/config, run
history, links).

## Operational business layer (rights, CRM, editions)

The studio's commercial spine, in three parts.

**Rights depth.** `Rights` and `Contract` gain term windows, rights holder,
exclusivity, sublicensing, reversion, option periods, territory/language
coverage and adaptation/merchandising constraints. The dynamic detail lives in
child tables of `Rights`: `RightsWindow` (per-scope term windows), `RightsOption`
(option periods + exercise deadlines), `ChainOfTitleEntry` (how the right moved
between parties), `RightsEvidence` (documents, optionally a stored asset) and
`RightsStatusHistory` (append-only; a scope change also applies to the matching
profile column). `app/services/rights.py` derives **reminders and expiry
warnings** from profile expirations, term ends, window ends, option deadlines,
reversion and reminder dates, and contract term/option ends — sorted by urgency
at `GET /api/rights/warnings`. Child resources are nested under
`/api/rights/{id}/…`; `/warnings` is declared before `/{rights_id}`.

**Relationship memory (CRM).** A private, manual-only CRM: `Organization`,
`Contact` (with `ContactRole` and `ContactTag` via a link table), `Interaction`
(a logged touchpoint) and `Opportunity` (a light pipeline). Contacts carry
source of introduction, interests, relevant works, follow-up date, consent /
preferences and notes. It only *records* relationships — there is no endpoint
that sends communication or imports contacts; `do_not_contact` and
`consent_status` are recorded, never assumed.

**Editions & distribution.** `Edition` is a concrete format/language/territory
of a Work — identifier (+ type), dimensions, page count, price, publication
date, files, metadata and distribution status — connected to (not replacing)
`ProductionRecord`. `app/services/distribution` generates **validated packages**
for six channels (ONIX, KDP, Ingram, GlobalComix, press kit, ARC): each
generator builds a JSON-safe manifest and a checklist of pass/warn/fail/na
items, persisted as a `DistributionPackage` (status `validated`/`invalid`).
Generators prepare and validate — they never upload; real uploads would need a
tested adapter (the integration hub). Surface: `/api/rights` (+ children,
`/warnings`), `/api/organizations`, `/api/contacts` (+ roles/tags),
`/api/interactions`, `/api/opportunities`, `/api/editions` (+ `/detail`,
`/packages/{channel}`) and `/api/distribution/channels`. The private UI adds
**Rights**, **Contacts** and **Editions** views.

## Public Graphic Novel Webviewer (public layer)

A public, read-only reader for published graphic novels sits on top of the
private system through a narrow, public-safe surface — same identity, none of
the private data. Full detail in [`PUBLIC_VIEWER.md`](PUBLIC_VIEWER.md).

- **Separate projection.** `PublishedWork → PublishedVolume → PublishedChapter →
  PublishedPage → PublicHotspot`, plus `PublicMediaAsset` (image/audio/video).
  These tables carry only public fields — no contracts, rights, notes, workflow,
  production, or private files exist on them. The link back to the private
  `Work` (`source_work_id`) is stored but never serialised.
- **Publication bridge.** `publish_work_to_public_reader(work_id)` copies only
  public metadata from a private `Work`; everything else is curated by hand.
- **URL separation.** Private API stays under `/api`; the public API is a
  separate, unauthenticated, GET-only router at `/public` (writes → 405), with
  demo media under `/public/demo`. The reader UI is a separate, code-split
  frontend tree at `/reader/*`.
- **Visibility.** Only `PUBLISHED` works are listed; `UNLISTED` is by-slug only;
  `DRAFT`/`ARCHIVED` and their deep ids return 404.
- **Media discipline.** Audio is gated behind an Enter overlay (user gesture);
  ambient video is muted-autoplay only; missing/blocked media degrades quietly.

The `player/` module (cinematic viewer, audio/video players, hotspots, gated
playback) is content-agnostic by design — the seam SUPERVOID Movies can reuse.

### Private curation CMS & controlled hand-off

A private admin CMS (`/api/curation`, authenticated) is the *only* writer of the
public projection — the public router stays read-only. It manages
`PublishedWork` / volumes / chapters / pages / media / hotspots / panels, with
visibility, scheduling and an exact-public **preview** (`preview_*` build the
public schema regardless of status, reached only through the private API).

- **Gated publication.** `validate → request approval → approve (admin) →
  publish`. `validate_for_publication` checks credits and, for asset-derived
  pages, provenance + a cleared, current licence. Publishing requires an
  APPROVED `PublicationApproval` and passing validation; every step appends a
  `PublicationEvent` (history is never deleted). Unpublish flips visibility only
  — the projection rows and the private source are preserved.
- **Controlled hand-off.** `hand_off_page` turns a private `GraphicNovelPage`
  into a public page using an **explicitly selected public derivative**
  (`PublicMediaAsset`) — a private file is never used or exposed. It copies the
  normalised `GraphicNovelPanel` coordinates into public `PublishedPanel` rows
  and records soft source references (`source_gn_page_id`,
  `source_asset_version_id`, never serialised) for licence/provenance validation.
- **Cinematic panels.** `PublishedPanel` carries normalised geometry, reading
  order, transition + duration, optional focus crop, panel-level audio/video and
  panel-scoped hotspots. The public page read exposes these; the reader's
  cinematic mode frames each panel in order and falls back to full-page display
  when a page has no panels.

## Operational command centre

A private, read-only aggregation surface (`/api/command-centre`, authenticated)
that unifies every domain into one archival dashboard — built one-person-first,
team-ready. `app/services/command_centre.py` rolls up the existing services
rather than re-deriving logic (rights / licence warnings, provenance
completeness, production blocked-detection).

- **Seven sections, one endpoint each** so the overview loads cheaply and the
  rest disclose progressively: *studio overview* (story worlds, active works,
  divisions, graphic-novel and screen progress, releases, adaptation dossiers);
  *my work* (assignments, overdue, blocked, requested reviews, approval queue —
  scoped to the current user, with unassigned work folded in for the solo
  operator); *agent inbox* (findings by severity, pending proposals, failed
  runs, recent analyses); *asset health* (missing files, incomplete provenance,
  expiring licences, unapproved versions, public assets missing credits);
  *business alerts* (rights expiries, contract deadlines, distribution
  readiness, contact follow-ups, upcoming releases); *division views*
  (Publishing / Pictures / Interactive / cross-media); and a per-Work *command
  page* gathering narrative, production, assets, collaborators, rights, editions,
  adaptations, public release and agent history.
- **Generic, small shapes** (`Metric`, `AlertItem`, `TaskBrief`) keep payloads
  light and the UI uniform.
- The frontend is the studio landing: an archival hero with key indicators plus
  collapsible, lazily-loaded sections (progressive disclosure) — not a generic
  SaaS dashboard. Items deep-link into the Work command page.

## Local-first & Postgres

Defaults require nothing external: SQLite on disk, `dry_run` AI, no network.
Switching to Postgres is a single `DATABASE_URL` change (plus the `psycopg`
driver); the ORM layer is engine-agnostic and `docker-compose.yml` provides a
production-shaped stack.

## Schema migrations (Alembic)

Alembic manages non-destructive schema evolution for both SQLite and Postgres
(see [`MIGRATIONS.md`](MIGRATIONS.md)). The URL is resolved from
`settings.database_url` in `alembic/env.py` (no hardcoded URL/credentials);
SQLite runs in batch mode for portable `ALTER`s.

Startup is strategy-driven (`settings.db_init_strategy`):

- `create_all` *(default)* — `init_db()` builds the schema directly; the fast
  path for fresh dev databases. `init_db()` is retained for back-compat.
- `migrate` — `prepare_database()` → `ensure_migrated()`: a pre-Alembic
  database (tables but no `alembic_version`) is **stamped** at the baseline
  (never recreated); otherwise it is upgraded/created.
- `skip` — migrations run out-of-band (deploy/CI).

Shared helpers live in `app/migrations.py`; the CLI is `scripts/manage_db.py`
(`upgrade`/`downgrade`/`stamp`/`ensure`/`verify`/`check`). `manage_db.py check`
is a CI-safe guard that builds the schema from migrations on a throwaway DB and
asserts it matches `SQLModel.metadata`.

Migration **0012** adds composite indexes for the hot read paths (the command
centre / "my work" / agent inbox): `production_items(assignee_id,status)`,
`(status,due_date)`, `(work_id,status)`; `agent_findings(resolved,severity)`;
`agent_runs(target_type,target_id)` and `(status,created_at)`;
`agent_action_proposals(status,created_at)`; and
`integration_runs(integration_point_id,status)`. They are declared on the
models' `__table_args__` so a fresh `create_all` and the migration agree.

**Backup / restore.** `scripts/backup_restore.py` performs a logical,
dialect-agnostic dump of every table (driven by `SQLModel.metadata`, so it
covers new record types automatically) plus a copy of the asset storage tree,
and restores both into a freshly migrated target. See the *Release readiness*
checklist for operational use.

## Extending the system

- **New resource:** add a model in `models/`, schemas in `schemas/`, a router
  in `routers/`, register it in `routers.ALL_ROUTERS`, then add a typed client
  and types on the frontend.
- **New enum value:** extend the enum in `models/enums.py` and mirror the
  label map in the corresponding `frontend/src/types/*.ts`.
- **New integration capability:** add an `IntegrationCapability` to the
  relevant descriptor; implement an adapter behind it when ready.
- **SUPERVOID Movies:** reuse the model/workflow/production patterns; the
  `movies` integration descriptor marks the publishing → film boundary.
