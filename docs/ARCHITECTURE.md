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
| AI       | Provider-pluggable; `dry_run` default (offline) |
| Theme    | Dark, editorial, archival                       |

## Repository layout

```
backend/
  app/
    main.py          FastAPI application factory + middleware + error handlers
    db.py            Engine, session, init_db (SQLite FK pragma)
    config.py        Env-driven settings (app name, db url, secret, AI)
    seed.py          Idempotent demo corpus
    auth/            Password hashing, JWT, DI dependencies (roles)
    models/          SQLModel domain entities + enums
    schemas/         Pydantic request/response payloads
    routers/         HTTP routers (one per resource) + public_reader (/public)
    services/        Business logic (workflow, knowledge, AI, exports, storage,
                     public_reader_service)
    integrations/    Ecosystem integration contracts (LOGOSFORGE, Movies)
    static/demo/     Local placeholder media for the public reader
    utils/           crud, logging, request-id middleware, pagination
  tests/             Pytest suite
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
- **GraphicNovelProduction** (`graphic_novel_productions`) — visual-production
  board for illustrated works: script → storyboard → character/environment
  design → page layout → lettering → colouring → final files, each a
  `StreamStatus`.
- **Production** — `ProductionRecord` is a 1:1 edition roll-up (ISBN, release
  date, per-format and per-stage `StreamStatus`); `ProductionItem`s are granular
  tasks (now linkable to a Work, with deadline/status filters).
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

> Back-compat: `work_id` is nullable on carried-over entities, so the editorial
> subsystems and their tests keep working while the Work hub is layered on top.

## Request flow

```
React (api/*.ts) ──HTTP──> FastAPI router ──> service / crud util ──> SQLModel ──> SQLite/Postgres
                              │
                         schema validation (Pydantic)         RequestId + structured logging
```

The app factory (`create_app`) mounts every router in `routers.ALL_ROUTERS`
under the `/api` prefix, installs CORS and a request-id middleware, and
registers integrity/`Exception` handlers that return correlation-tagged JSON.

## Authentication & roles

JWT bearer tokens; roles are `admin`, `editor`, `reviewer`,
`production_manager`, `marketing`, `archive_reader`. Dependency helpers
(`AUTHED`, `ADMIN_ONLY`, …) guard write and privileged routes; reads are
generally public for the local archive experience.

## Integration layer (ecosystem seams)

`backend/app/integrations/` declares **typed contracts** — not live clients —
for sibling systems under SUPERVOID ENTANGLED:

- `logosforge.py` — the LOGOSFORGE writing subsystem bridge (import drafts,
  seed the knowledge graph, return editorial notes).
- `movies.py` — the SUPERVOID Movies film-adaptation bridge (promote a
  published title, share rights and knowledge graph).
- `ecosystem.py` — the holding map (parent + member systems).

Exposed read-only at `/api/integrations`, `/api/integrations/ecosystem`, and
`/api/integrations/{key}`. Keeping these as descriptors preserves the
local-first principle (no required external services) while making the
extension points explicit and inspectable.

Alongside the static contracts, a persisted **`IntegrationPoint`** registry is
CRUD-able at `/api/integrations/points` (filterable by `type` and `status`).
These are operational records — a specific LOGOSFORGE bridge, a SUPERVOID Movies
adaptation hand-off, an AI Lab or Archive/Knowledge-Graph seam — each with an
endpoint placeholder. The `/points` routes are declared before the `/{key}`
catch-all so they are not shadowed by it.

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

## Local-first & Postgres

Defaults require nothing external: SQLite on disk, `dry_run` AI, no network.
Switching to Postgres is a single `DATABASE_URL` change (plus a driver); the
ORM layer is engine-agnostic and `docker-compose.yml` provides a
production-shaped stack.

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
