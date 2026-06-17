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

- ✅ Authors, manuscripts, reviews, contracts, editorial notes, attachments.
- ✅ Workflow engine with validated transitions and an audit trail.
- ✅ Production pipeline (records + items), publishing calendar, search/archive.
- ✅ Work types — **Books** and **Graphic novels** as first-class formats.
- 🟡 Dashboard analytics — expand indicators and deadline tracking.

## Phase 2 — Rights & contracts depth ⚪

- ⚪ Promote rights from `Contract` fields to a dedicated **Rights** module
  (territory, language, format, term windows, reversion, sub-licensing).
- ⚪ Royalty statements and advance reconciliation.
- ⚪ Contract templates and signature status timeline.

## Phase 3 — Visual production for graphic novels ⚪

- ⚪ Page/panel/spread tracking distinct from prose layout stages.
- ⚪ Art-status streams (pencils, inks, colours, letters) on `ProductionRecord`.
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

## Phase 6 — Platform hardening ⚪

- ⚪ Database migrations (Alembic) for non-destructive schema evolution.
- ⚪ Postgres as a first-class deployment target with CI coverage.
- ⚪ PDF export (currently a reserved placeholder).
- ⚪ Real AI providers behind the existing provider interface (opt-in).

---

### Non-goals (for now)

- No SaaS multi-tenancy, billing, or mandatory cloud services.
- No microservice split — the modular monolith stays until a division genuinely
  needs its own deployment.
