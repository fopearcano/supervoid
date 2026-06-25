# Roadmap — SUPERVOID Publishing

A phased plan. The guiding constraints are unchanged from the migration:
**local-first**, **modular**, no unnecessary services, working system first.

Status legend: ✅ done · 🟡 in place / partial · ⚪ planned

---

## Phase 0 — Migration & rebrand ✅

- ✅ Migrate the working architecture from `logosforge-pub`.
- ✅ Rebrand the publishing product to **SUPERVOID Publishing**; preserve
  **LOGOSFORGE** strictly as the separate writing subsystem.
- ✅ Establish the **SUPERVOID ENTANGLED** ecosystem model in code and docs.
- ✅ Green test suite + clean frontend build.

## Phase 1 — Editorial core (carried over) 🟡

- ✅ **Work** as the central catalogue entity; manuscripts are its text drafts
  (`work_id`, version, draft status, submission date, file-metadata placeholder).
- ✅ Authors (pen name, phone, website, notes), manuscripts, contracts,
  editorial notes (now also link a Work / subject author), attachments.
- ✅ Reviews extended with a scoring rubric (literary quality, visual potential,
  market potential, originality, editorial effort) + a `hold` recommendation.
- ✅ Workflow engine with validated transitions and an audit trail.
- ✅ Production pipeline (records + items), publishing calendar, search/archive.
- ✅ Work types — **Books**, **Graphic novels**, art books, essays and
  adaptation candidates as first-class formats.
- 🟡 Dashboard analytics — expand indicators and deadline tracking.

## Public Graphic Novel Webviewer 🟡

A public, read-only reader layered on the private system through a public-safe
API. See [`PUBLIC_VIEWER.md`](PUBLIC_VIEWER.md).

- ✅ Public projection models (`PublishedWork/Volume/Chapter/Page`,
  `PublicHotspot`, `PublicMediaAsset`) — no private fields by construction.
- ✅ Read-only `/public` API (separate from `/api`, unauthenticated, GET-only)
  with visibility rules (published / unlisted / hidden).
- ✅ Publication bridge `publish_work_to_public_reader` (public metadata only).
- ✅ Immersive reader: single / double / scroll / cinematic modes, zoom & fit,
  fullscreen, keyboard + touch, progress, volume/chapter selectors.
- ✅ Gated background music (page→chapter→volume→work) and HTML5 video
  (intro / page overlay / hotspot / ambient), with graceful degradation.
- ✅ Curated public hotspots (info / character / location / lore / link / audio
  / video) and a dark, cinematic SUPERVOID identity + shared design tokens.
- ✅ **Real panel-by-panel cinematic mode** from normalised `PublishedPanel`
  coordinates: guided navigation, configurable transition + duration, reading
  order, optional focus crop, panel-level audio/video/hotspots, accessibility
  fallback, keyboard + touch, and graceful fallback to full-page display.
- ✅ **Private curation CMS** (`/api/curation`): create/edit published works,
  volumes, chapters, pages, media, hotspots, panels and credits; visibility and
  scheduling; gated publication (validate → request approval → approve →
  publish) with preserved history; unpublish without deleting the private
  source; validate credits/licences/provenance; exact-public preview; and a
  controlled hand-off from `GraphicNovelPage`/`AssetVersion` using an explicit
  public derivative. Tests prove unpublished/private data stays out of `/public`.
  Alembic `0011`, seed (cinematic panels + approval/history), private UI.
- ⚪ Image/asset pipeline (derivatives, CDN) beyond local placeholders.

## IP & transmedia studio layer 🟡

The bounded context above `Work` that turns the catalogue into an IP-centred
transmedia studio. `Work` stays central; this sits above it. See
[`STUDIO_SYSTEM_IMPLEMENTATION_PLAN.md`](STUDIO_SYSTEM_IMPLEMENTATION_PLAN.md)
phases A–B.

- ✅ **StoryWorld** (IP/universe: canon, status, visual identity, owner, optional
  parent) and **StorySeries** (ordered series within a world).
- ✅ **Work** extended (additive, nullable): `story_world_id`, `story_series_id`,
  `series_order`, `primary_division`, `primary_medium`, `canon_status`,
  self-referential `source_work_id`.
- ✅ **AdaptationDossier** — source Work → target medium/division, lifecycle,
  logline, format, scope, rights-clearance, notes, source revision, optional
  linked target Work.
- ✅ Enums: `StudioDivision` (publishing/pictures/interactive/audio/cross-media),
  `Medium`, `CanonState`, `AdaptationStatus`, `RightsClearanceState`,
  `StoryWorldStatus`, `StorySeriesStatus`.
- ✅ CRUD + filtering APIs, Alembic migration `0002_transmedia`, seed examples,
  backend tests, and private frontend sections (Story Worlds, Series, Adaptation
  Dossiers, Work-level transmedia overview).
- ✅ Kept as a bounded context in the monolith with extraction seams
  (`AdaptationDossier`, `Work.source_work_id`) — no separate Movies service.
- ⚪ Per-medium production trees (page/panel/scene/shot), assets + provenance,
  supervised agents (later studio-plan phases C+).

## Collaboration & project-scoped access control 🟡

Project-scoped collaboration layered on top of (never replacing) the global
`UserRole`. See *Collaboration & project-scoped access control* in
[`ARCHITECTURE.md`](ARCHITECTURE.md).

- ✅ **ProjectMembership** — user ↔ Work and/or StoryWorld, with a project role,
  lifecycle status (invited/active/suspended/declined/revoked), invited/accepted
  timestamps, created-by and notes; world memberships cascade to their Works.
- ✅ 14 project roles and 11 permission scopes; the role → scope matrix and
  strongest-role resolution live in the **policy service**.
- ✅ **Policy service** (`app/services/policy.py`) combines global role +
  membership + ownership + operation; reusable `require_scope` dependency and
  `ensure_can` helper — no permission checks scattered across routers.
- ✅ **User management** (`/api/users`, admin): create/list/get/patch,
  activate/deactivate, password rotation (admin-or-self).
- ✅ **Collaboration API**: invitations, accept/decline, role change,
  suspend/reactivate/revoke, `/me/projects`, and `/collaboration/roles`.
- ✅ **MembershipAudit** — append-only, decoupled audit trail of every change.
- ✅ Alembic migration `0003_collaboration`, seed memberships, backend tests
  (policy truth-table + API + cross-project isolation), and a private
  **Collaborators panel** inside each Work and StoryWorld.
- ⚪ Email/notification on invite; bulk invite; per-scope custom role overrides.

## Phase 2 — Rights & contracts depth 🟡

- ✅ Dedicated **Rights** module (`/api/rights`): per-work, per territory/language
  profiles with a `RightStatus` for each right (print, ebook, audiobook, film,
  adaptation, merchandising), holder and expiration; contracts gained an
  `expiration_date` and a `work_id` link.
- ⚪ Term windows, reversion and sub-licensing chains.
- ⚪ Royalty statements and advance reconciliation.
- ⚪ Contract templates and signature status timeline.

## Phase 3 — Visual production for graphic novels 🟡

- ✅ **GraphicNovelProduction** board (`/api/graphic-novel-productions`): script
  → storyboard → character/environment design → page layout → lettering →
  colouring → final files, each a `StreamStatus`, with volume/issue numbers —
  now the **high-level summary** over the detailed hierarchy below.
- ✅ **Production hierarchy** (Volume → Chapter → Sequence → Page → Panel →
  element) with stable ordering and status at every level. See *Graphic-novel
  production hierarchy* in [`ARCHITECTURE.md`](ARCHITECTURE.md).
  - ✅ Rich page fields (spread/side, script, visual brief, dialogue summary,
    lettering/colour/final, print geometry, master asset, public mapping) and
    panel fields (normalised x/y/w/h, beats, dialogue/captions/SFX, camera
    framing/angle/lens, continuity, storyboard & final asset versions, approval).
  - ✅ Panel elements (characters/props/locations/text); knowledge-entity links
    on pages and panels — characters/locations linked, never duplicated.
  - ✅ Page/spread validation, automatic roll-up into the summary, completion
    percentages, drag/reorder, page & panel duplication, storyboard↔final
    comparison, and print/digital readiness checks.
  - ✅ Frontend studio: navigator, visual page-board, panel coordinate editor,
    progress & readiness views. Alembic `0006`, seed and tests.
  - ✅ **Curation hand-off, not publish**: a deliberate hand-off proposes/marks
    pages ready for the public reader but never writes it directly.
- ⚪ Cover and interior asset versioning is now handled by the Asset Library.

## Production task system (cross-medium) 🟡

`ProductionItem` evolved into a general production task for publishing, graphic
novels, film, audio and interactive work. See *Production task system* in
[`ARCHITECTURE.md`](ARCHITECTURE.md). Backward compatible: the legacy
`/production-items` endpoints and records are unchanged.

- ✅ Extended task fields (title, description, division, track, task type,
  priority, creator, reviewer, parent, milestone, start/due/completed dates,
  estimated/actual effort, blocked reason, acceptance criteria, deliverable
  asset, revision number); `work_id` primary, `manuscript_id` optional.
- ✅ **Dependencies** (`ProductionDependency`, with cycle guard), **subtasks**
  (self-referential parent), **milestones** (`ProductionMilestone`).
- ✅ **ApprovalRequest** human gate; append-only **ProductionActivity** log.
- ✅ **Validated state transitions** + detection of blocked tasks / unmet
  dependencies in the policy-like `production` service.
- ✅ Query endpoints: my-assignments, overdue, blocked, awaiting-approval.
- ✅ Kanban / list / timeline frontend board.
- ✅ Work-level production templates + 6 starter templates (graphic novel
  volume, book publication, short film, feature film, animated sequence,
  promotional launch); Alembic `0004`, seed and tests.
- ✅ **AI safety**: completion and approval are human-only; no auto-approval.
- ⚪ Effort burndown, capacity/scheduling, and Gantt-style dependency bars.

## Asset Library (central, work-centred) 🟡

A reusable, versioned asset domain with provenance and licensing. See *Asset
Library* in [`ARCHITECTURE.md`](ARCHITECTURE.md). `Attachment` is preserved for
backward compatibility; assets are a separate, durable layer.

- ✅ **Asset / AssetVersion / AssetLink / ProvenanceRecord / LicenceRecord**
  with work / story-world association, canonical status, visibility, owner,
  tags; per-version checksum, dimensions, duration, technical metadata.
- ✅ Local filesystem storage behind a `StorageBackend` adapter interface
  (remote/object storage drops in later).
- ✅ Checksum-based duplicate detection; version promotion & rollback;
  asset search & filters; provenance completeness checks; licence-expiry
  warnings; private preview/download endpoints.
- ✅ Asset browser + version history frontend; Alembic `0005`, seed and tests.
- ✅ **Privacy**: assets are never exposed via the public reader — public media
  stays on the curated public projection.
- ⚪ Image-dimension/duration auto-extraction; thumbnail generation; S3 adapter.

## Supervised studio-agent framework 🟡

The manuscript AI layer evolved into governed agents. The existing `/api/ai`
endpoints and `AIInsight` records are preserved. See *Supervised studio-agent
framework* in [`ARCHITECTURE.md`](ARCHITECTURE.md).

- ✅ Code-registered `AgentDefinition`s and a tool registry (read-only /
  proposal-only mutation / external, with risk + permission declarations).
- ✅ Persisted `AgentRun`, `AgentFinding`, `AgentActionProposal`, and
  `PromptTemplate` + versions.
- ✅ Read-only analysis runs immediately; mutations become gated proposals;
  destructive / publishing / rights / external actions require admin approval;
  snapshots + outputs preserved; dry-run kept; no secrets; retry = new run.
- ✅ Registry, run, history, findings inbox, proposal approve/reject/execute
  endpoints; Alembic `0008`, seed, tests, and a private Agent Centre UI.
- ⚪ Streaming runs, scheduled/triggered agents, and per-tool real executors.

## Operational integration hub 🟡

`IntegrationPoint` became an operational but local-first hub without breaking the
existing integration endpoints. See *Operational integration hub* in
[`ARCHITECTURE.md`](ARCHITECTURE.md).

- ✅ `IntegrationAdapter` interface (health, capabilities, dry-run, inbound,
  outbound, status) with code-registered adapters and persisted `IntegrationRun`.
- ✅ Secure configuration: env-referenced secrets, credential references only in
  the DB, no raw secret retrieval through the API, masked config status.
- ✅ Generic **n8n** webhook adapter; **ComfyUI** adapter (queue, status/history,
  attach outputs to assets, import workflow provenance, full dry-run, no
  always-on assumption); **GitHub** adapter (link commits/issues/PRs to tasks,
  dry-run fixtures, no embedded credentials).
- ✅ **File-exchange** adapters for Affinity, InDesign, Clip Studio Paint,
  DaVinci Resolve and Blender/Cinema 4D/Houdini — structured export/import
  packages, not fake remote control.
- ✅ Every external mutation passes an approval boundary (`IntegrationRun`
  PENDING_APPROVAL → APPROVED → execute; external actions admin-gated); network
  effects recorded unless enabled; Alembic `0009`, seed, tests, and a private
  **Integration Hub** UI (adapter health/status + run history).
- ⚪ Live network dispatch by default, richer GitHub sync, and remote/object
  storage for ingested outputs.

## Operational business layer 🟡

The studio's commercial spine — rights depth, a CRM, and editions/distribution.
See *Operational business layer* in [`ARCHITECTURE.md`](ARCHITECTURE.md).

- ✅ **Rights depth**: `Rights`/`Contract` extended with term windows, rights
  holder, exclusivity, sublicensing, reversion, option periods, chain of title,
  evidence, territory/language coverage, adaptation/merchandising constraints,
  status history, and reminders/expiry warnings.
- ✅ **Relationship memory**: `Organization`, `Contact`, `ContactRole`,
  `Interaction`, `Opportunity`, `ContactTag` — covering publishers, distributors,
  printers, journalists, reviewers, festivals, translators, artists, agents and
  collaborators; consent/preferences recorded; no scraping or auto-send.
- ✅ **Editions & distribution**: an `Edition` model connected to
  `ProductionRecord`, plus validated package generators for ONIX, KDP, Ingram,
  GlobalComix, press kit and reviewer/ARC — packages + checklists, never direct
  uploads.
- ✅ Alembic `0010`, seed, tests, and private Rights / Contacts / Editions UIs.
- ⚪ Real tested upload adapters per channel, royalty statements, and a sales
  dashboard.

## Operational command centre ✅

The unifying dashboard over the whole studio — one-person-first, team-ready. See
*Operational command centre* in [`ARCHITECTURE.md`](ARCHITECTURE.md).

- ✅ Studio overview, my work, agent inbox, asset health, business alerts,
  division views, and a per-Work command page — each a read-only endpoint under
  `/api/command-centre`, reusing existing services rather than re-deriving them.
- ✅ Archival, cinematic UI as the studio landing, with progressive disclosure
  (collapsible, lazily-loaded sections) so the solo workflow isn't overwhelmed,
  and deep links into the Work command page.
- ✅ 10 tests, including per-user scoping for *my work*. No new tables — pure
  aggregation over the existing domains.

## Phase 4 — LOGOSFORGE integration (writing subsystem) ⚪

The contract already exists at `/api/integrations/logosforge`. Implementation:

- ⚪ `import_manuscript` — pull a finished LOGOSFORGE draft into a manuscript.
- ⚪ `sync_knowledge_graph` — seed editorial entities/relationships from
  LOGOSFORGE narrative structure.
- ⚪ `return_editorial_notes` — push editorial notes/revisions back to the author.
- ⚪ Adapter + auth model for a locally running LOGOSFORGE instance (local-first).

## Phase 5 — SUPERVOID Pictures (screen division) 🟡

Now an **operational** bounded context inside the repo (`/api/screen`), not a
future plan. See *SUPERVOID Pictures* in [`ARCHITECTURE.md`](ARCHITECTURE.md).
The SUPERVOID Movies integration descriptor is `available`.

- ✅ **ScreenProject → Unit (Episode/Reel) → Sequence → Scene → Shot** for
  films, shorts, series and animation, with full scene and shot fields.
- ✅ `promote_to_adaptation` — promote a Work / graphic novel into an
  `AdaptationDossier` (the entry seam).
- ✅ Create a ScreenProject from an *approved* dossier (unapproved rejected).
- ✅ Reuse graphic-novel pages/panels as storyboards; map panels to one or more
  shots; carry knowledge entities, rights and provenance by reference.
- ✅ Shot lists, production breakdowns, and an adaptation-package **export**
  (JSON + Markdown). Alembic `0007`, seed, tests, and a private Screen studio.
- ✅ Kept **extractable** (own vocabulary, id-only cross-references) — no extra
  deployment or repository.
- ⚪ Scheduling/stripboard, call sheets, and a true extraction to its own service.

## Phase 6 — Platform hardening 🟡

- ✅ **Database migrations (Alembic)** — baseline of the current schema,
  non-destructive adoption of existing DBs (stamp), strategy-driven startup
  (`create_all` / `migrate` / `skip`), a migration CLI, a CI-safe schema
  verification (`manage_db.py check`), and migration tests. SQLite tested;
  Postgres supported via the same env. See [`MIGRATIONS.md`](MIGRATIONS.md).
- ⚪ Postgres as a first-class deployment target with CI coverage (validate the
  baseline against a real Postgres instance).
- ⚪ PDF export (currently a reserved placeholder).
- ⚪ Real AI providers behind the existing provider interface (opt-in).

---

### Non-goals (for now)

- No SaaS multi-tenancy, billing, or mandatory cloud services.
- No microservice split — the modular monolith stays until a division genuinely
  needs its own deployment.
