# Migration Notes — LOGOSFORGE Publishing → SUPERVOID Publishing

This document records the controlled migration of the earlier
**LOGOSFORGE Publishing** project into this **SUPERVOID Publishing**
repository.

- **Source:** `https://github.com/fopearcano/logosforge-pub` (single commit:
  *"Add PSYKE-inspired editorial knowledge graph"*)
- **Target:** `https://github.com/fopearcano/supervoid` (this repository)
- **Approach:** copy the working architecture, rebrand the publishing product,
  introduce explicit integration seams for sibling systems, and add docs —
  *not* a rewrite from zero.

---

## 1. What existed in the source project

The source was already a complete, well-structured, local-first editorial
management platform that closely matched the desired target architecture.

**Backend** — Python 3.11, FastAPI, SQLModel, Uvicorn; SQLite-first with a
Postgres-ready Docker Compose stack:

- `app/main.py` (application factory, CORS + request-id middleware, error
  handlers), `app/db.py`, `app/config.py` (env-driven settings), `app/seed.py`
  (idempotent demo corpus)
- `app/auth/` — bcrypt password hashing, JWT, role-based dependencies
- `app/models/` — 17 SQLModel entities + enums: `User`, `Author`,
  `Manuscript`, `Review`, `Contract`, `ProductionItem`, `ProductionRecord`,
  `EditorialNote`, `WorkflowEvent`, `Attachment`, `AIInsight`,
  `KnowledgeEntity`, `KnowledgeRelationship`, `ManuscriptEntityLink`
- `app/routers/` — auth, health, meta, dashboard, search, authors,
  manuscripts, reviews, workflow, workflow_events, contracts,
  production_items, production_records, editorial_notes, attachments,
  exports, ai, knowledge
- `app/services/` — workflow engine, knowledge graph, storage, AI (providers:
  `dry_run`, `openai_compat`; features: summarize, style analysis, editorial
  suggestions, semantic tags, consistency), exports (markdown, json, bundle)
- `app/utils/` — crud, logging, request-id middleware, pagination
- `tests/` — 19 pytest modules

**Frontend** — React 18, Vite 5, TypeScript, TailwindCSS 3, dark editorial
theme (ink/parchment/brass palette; EB Garamond / Inter / JetBrains Mono):

- pages: Dashboard, ManuscriptView, SearchPage, ArchivePage, ProductionBoard,
  ReleaseCalendar, ProductionItemView
- ~30 components, `AppShell` layout, `AuthContext`, typed API client, types

**Config / ops** — `docker-compose.yml`, backend/frontend `Dockerfile`s,
`.env.example` files, `scripts/backup.sh` + `scripts/restore.sh`, and a large
(~55 KB) README.

### Core-module coverage at intake

| Required module                       | In source? | Notes                                        |
| ------------------------------------- | ---------- | -------------------------------------------- |
| Dashboard                             | ✅         | `pages/Dashboard.tsx`, `/api/dashboard`      |
| Authors                               | ✅         | `Author` model, `AuthorPanel`, `/api/authors`|
| Manuscripts                           | ✅         | central content model                        |
| Graphic novels                        | ⚠️→✅      | added `work_type` to distinguish formats     |
| Books                                 | ⚠️→✅      | added `work_type` (default `book`)           |
| Editorial workflow                    | ✅         | workflow engine + `WorkflowEvent`            |
| Reviews                               | ✅         | `Review` model + router                       |
| Contracts                             | ✅         | `Contract` model + router                     |
| Rights management                     | ✅*        | on `Contract` (territory, royalty, advance)  |
| Production pipeline                    | ✅         | `ProductionItem` / `ProductionRecord`        |
| Publishing calendar                   | ✅         | `ReleaseCalendar`, upcoming releases         |
| Archive / search                      | ✅         | `SearchPage`, `ArchivePage`, `/api/search`   |
| Notes                                 | ✅         | `EditorialNote` + panel                       |
| File metadata / attachments           | ✅         | `Attachment` + storage service               |
| Integration layer for LOGOSFORGE      | ❌→✅      | newly implemented                            |
| Integration layer for SUPERVOID Movies| ❌→✅      | newly implemented                            |

\* Rights are currently modelled as fields on `Contract`. A dedicated rights
module is on the roadmap.

---

## 2. What was copied

The entire working architecture was copied verbatim, then rebranded — backend,
frontend, tests, Docker stack, scripts, and README. No reusable code was
rewritten from scratch. The source `.git` history was **not** carried over; the
migration begins this repository's history fresh.

---

## 3. What was renamed (rebranding)

All existing `LOGOSFORGE` references in the source referred to the *old
publishing product*, so they were rebranded wholesale. The separate LOGOSFORGE
*writing subsystem* is introduced fresh (see §5) and is the **only** place the
name is preserved.

| From                              | To                                  | Scope                              |
| --------------------------------- | ----------------------------------- | ---------------------------------- |
| `LOGOSFORGE` (display name)       | `SUPERVOID Publishing`              | app name, README, docstrings, copy |
| `LOGOSFORGE` (UI wordmark)        | `SUPERVOID` + `Publishing` tag      | `AppShell` header                  |
| `logosforge` (identifiers)        | `supervoid`                         | db file, token key, secret, env    |
| `logosforge-frontend`             | `supervoid-publishing-frontend`     | `package.json` / lockfile          |
| `@logosforge.local`               | `@supervoid.local`                  | seed demo users                    |
| `@logosforge.test`                | `@supervoid.test`                   | test fixtures                      |
| demo password `logosforge`        | `supervoid`                         | seed + login panel default         |
| Postgres `logosforge`             | `supervoid`                         | docker-compose, `.env.example`     |

The UI wordmark now reads **SUPERVOID · Publishing**, with an eyebrow of
**SUPERVOID ENTANGLED · Editio MMXXVI** establishing the parent ecosystem.

---

## 4. What needed repair

Nothing was broken at intake. The migrated-and-rebranded code passed its full
test suite (162 tests) and built cleanly before any new features were added,
so this was a healthy base rather than a salvage. The one benign warning
(Pydantic: `StyleAnalysisResult.register` shadows a `BaseModel` attribute) was
carried over unchanged and is non-fatal.

---

## 5. What was newly implemented

1. **Work types (Books vs Graphic novels).** A `WorkType` enum
   (`book`, `graphic_novel`, `novella`, `anthology`, `art_book`, `other`) and a
   `work_type` field on `Manuscript`, threaded through schemas, the list
   filter/sort, the seed corpus, and a `WorkTypeTag` UI component. This makes
   the *Books* and *Graphic novels* product lines first-class and filterable
   while keeping one shared workflow and production pipeline.

2. **Ecosystem integration layer.** `backend/app/integrations/` declares
   typed, local-first contracts for the sibling systems — `LOGOSFORGE` (the
   writing/narrative subsystem) and `SUPERVOID Movies` (future film division) —
   plus the `SUPERVOID ENTANGLED` ecosystem map. Exposed read-only under
   `/api/integrations`. These are descriptors, not live clients: the seams are
   explicit and ready to implement without committing to any external service.

3. **Documentation.** `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
   `docs/SUPERVOID_BRANDING.md`, and this file; plus a new ecosystem section in
   the README.

4. **Tests.** `tests/test_integrations.py` covers the integration endpoints and
   the new `work_type` behaviour.

---

## 6. Verification

| Check                     | Result                                             |
| ------------------------- | -------------------------------------------------- |
| Backend test suite        | **169 passed** (162 migrated + 7 new), 1 warning   |
| Database seed             | OK — 10 users, 5 authors, mixed work types         |
| App boot                  | OK — title `SUPERVOID Publishing`, 96 routes        |
| Frontend production build | OK — `tsc -b && vite build`, 90 modules            |
| Stray `logosforge` refs   | none remain except the intentional subsystem name  |

---

## 7. Preserved for the future

- **Local-first** remains the default (SQLite, dry-run AI, no required external
  services); Postgres stays a drop-in via `DATABASE_URL`.
- **Modularity** is preserved so **SUPERVOID Movies** can reuse the domain,
  workflow, and production patterns; the integration layer marks where it plugs
  in.
- **LOGOSFORGE** is documented and wired as a *separate* writing subsystem that
  can later feed drafts and narrative structure into this pipeline.
