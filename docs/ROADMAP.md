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
- ⚪ Real panel-by-panel cinematic mode (coords per panel), guided reading.
- ⚪ A small curation UI in the admin app for building published works.
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
  colouring → final files, each a `StreamStatus`, with volume/issue numbers.
- ⚪ Page/panel/spread tracking distinct from prose layout stages.
- ⚪ Cover and interior asset versioning via the attachments layer.

## Phase 4 — LOGOSFORGE integration (writing subsystem) ⚪

The contract already exists at `/api/integrations/logosforge`. Implementation:

- ⚪ `import_manuscript` — pull a finished LOGOSFORGE draft into a manuscript.
- ⚪ `sync_knowledge_graph` — seed editorial entities/relationships from
  LOGOSFORGE narrative structure.
- ⚪ `return_editorial_notes` — push editorial notes/revisions back to the author.
- ⚪ Adapter + auth model for a locally running LOGOSFORGE instance (local-first).

## Phase 5 — SUPERVOID Movies bridge (future division) ⚪

The contract already exists at `/api/integrations/supervoid_movies`:

- ⚪ `promote_to_adaptation` — open a film-adaptation dossier from a published
  title.
- ⚪ `share_rights` / `share_knowledge_graph` — carry rights and narrative
  structure across the publishing → film boundary.
- ⚪ Extract reusable domain/workflow packages so SUPERVOID Movies can build on
  them without forking.

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
