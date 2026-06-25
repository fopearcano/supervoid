# Integration & Hardening — Test Report

Scope: a complete integration and hardening pass across the SUPERVOID studio
system. No unrelated features were introduced. Run from a clean checkout of the
working tree on branch `claude/confident-albattani-fujtxk`.

## Summary

| Check | Result |
| --- | --- |
| Backend test suite (`pytest`) | ✅ **373 passed**, 1 warning, ~2m52s |
| Migrations match models (`manage_db.py check`) | ✅ `migrations match the models ✓` |
| Migration round-trip (head ↔ base, incl. `0012`) | ✅ clean |
| Autogenerate drift (indexes) | ✅ none |
| Frontend type-check (`tsc --noEmit`) | ✅ clean |
| Frontend production build (`vite build`) | ✅ 156 modules, built in ~2.8s |
| Lint (ruff) — files changed in this pass | ✅ all checks passed |

The one pytest warning is a pre-existing Pydantic field-shadow notice
(`StyleAnalysisResult.register`), unrelated to this work. Ruff reports 4
unused-import notices in two test files (`test_routers.py`, `test_search.py`)
that **predate this pass** (original migration commit) and were left untouched.

Backend tests grew from **358 → 373** (+15) with no regressions.

## Backend test suite

```
cd backend && .venv/bin/python -m pytest -q
→ 373 passed, 1 warning in ~172s
```

New tests added this pass (+15):

- `test_request_id.py` (+3) — the structured error envelope on 404 / 422 and the
  preserved `WWW-Authenticate` header on 401, each carrying `request_id`.
- `test_agents.py` (+1) — an agent run's `correlation_id` equals the inbound
  `X-Request-ID`.
- `test_integration_hub.py` (+5) — integration-run correlation; LOGOSFORGE
  adapter registration, dry-run→create import, idempotent knowledge-graph sync,
  and admin-gated recorded-only editorial notes.
- `test_integrations.py` (±1) — LOGOSFORGE descriptor now `available`
  (adapter-backed).
- `test_curation.py` (modified) — events/approvals now paginated; added an
  `action` filter assertion.
- `test_e2e_workflows.py` (+3, new) — the three principal cross-domain flows.
- `test_seed.py` (+1, new) — the demo seed demonstrates all eight artefacts.
- `test_backup_restore.py` (+2, new) — records + asset bytes survive a
  backup→restore round-trip; restore refuses a non-empty target without `--reset`.

## Migrations (SQLite)

```
.venv/bin/python scripts/manage_db.py check        → migrations match the models ✓
upgrade head → downgrade 0011 → upgrade head        → clean
upgrade head → downgrade base                       → clean (all tables dropped)
tests/test_migrations.py                            → 9 passed
```

Migration **0012** (composite hot-path indexes) applies as additive
`CREATE INDEX` (no table rebuild), is reversible, and produces **no** autogenerate
drift against the models.

## Migrations (PostgreSQL)

The ORM and Alembic environment are engine-agnostic (URL resolved from settings;
SQLite uses batch mode, Postgres uses native `ALTER`). Migration `0012` uses only
portable `CREATE INDEX` / `DROP INDEX`. **A live PostgreSQL run was not exercised
here** (no Postgres service in this environment); validating the baseline against
a real Postgres instance in CI remains the tracked Phase-6 item. This is stated
plainly rather than claimed.

## Frontend

```
cd frontend && npx tsc --noEmit   → clean
npm run build                      → ✓ 156 modules transformed; built in ~2.8s
```

The only frontend change was unwrapping the now-paginated curation endpoints
(`events`, `approvals`, `media`) in `src/api/curation.ts`; the page components are
unchanged.

## Verification matrix

Each item from the brief and where it is exercised:

| Verify item | Covered by |
| --- | --- |
| Migrations from original schema | `test_migrations.py` (baseline→head, legacy adopt) |
| Clean database installation | `test_migrations.py::test_ensure_migrated_creates_fresh_db` |
| SQLite operation | entire suite (default engine) |
| PostgreSQL operation (where CI permits) | engine-agnostic; **not run here** (see above) |
| Authentication | `test_auth.py`, `test_request_id.py` (401 + header) |
| Project-scoped permissions | `test_collaboration.py`, agent `_check_permissions` |
| Public/private isolation | `test_curation.py`, `test_public_reader.py`, `test_e2e_workflows.py` |
| Asset storage & versioning | `test_assets.py`, e2e upload step |
| Provenance & licence validation | `test_assets.py`, curation publish validator |
| Production dependencies | `test_production_tasks.py` |
| Approval workflows | `test_production_tasks.py`, `test_agents.py`, `test_integration_hub.py` |
| Graphic-novel hierarchy | `test_graphic_novel_hierarchy.py` |
| Audiovisual hierarchy | `test_screen.py` |
| Adaptation hand-offs | `test_e2e_workflows.py` (publishing→pictures), `test_transmedia.py` |
| Agent runs & proposals | `test_agents.py` |
| Integration dry-run modes | `test_integration_hub.py` |
| LOGOSFORGE bundle import | `test_integration_hub.py` (dry-run + create + idempotent sync) |
| Public-reader curation | `test_curation.py`, `test_e2e_workflows.py` |
| Panel cinematic mode | `test_curation.py` (panels), public viewer |
| Dashboard queries | `test_command_centre.py`, `test_dashboard.py`, e2e |

## Additions delivered

| # | Addition | Status |
| --- | --- | --- |
| 1 | End-to-end integration tests | ✅ `test_e2e_workflows.py` (3 flows) |
| 2 | DB indexes for new high-use queries | ✅ migration `0012`, 8 composite indexes |
| 3 | Pagination & filtering for large collections | ✅ curation events/approvals/media + audit |
| 4 | Consistent structured error responses | ✅ `{detail, request_id}` envelope everywhere |
| 5 | Request correlation across agent & integration runs | ✅ `correlation_id` = request id |
| 6 | Backup/restore for new records & assets | ✅ `scripts/backup_restore.py` + tests |
| 7 | Seed demonstrating the 8 artefacts | ✅ verified by `test_seed.py` |
| 8 | Updated API documentation | ✅ `docs/API.md` |
| 9 | Updated ASCII architecture maps | ✅ `docs/ARCHITECTURE.md` |
| 10 | One-person studio workflow | ✅ `docs/ONE_PERSON_STUDIO_WORKFLOW.md` |
| 11 | Collaborative studio workflow | ✅ `docs/COLLABORATIVE_STUDIO_WORKFLOW.md` |
| 12 | Release-readiness checklist | ✅ `docs/RELEASE_READINESS.md` |
| 13 | Frontend build + backend test report | ✅ this document |

Plus: ROADMAP restructured into the five status tiers (completed /
production-ready / experimental / adapter-only / future extraction), and a
minimal **LOGOSFORGE bundle-import adapter** added to complete the declared seam.

## Honest labelling

No mocked, dry-run, or package-export integration is described as a fully
operational external integration. Specifically: the LOGOSFORGE adapter is
**local-first bundle import** (outbound notes recorded-only); desktop adapters are
**package generators**; distribution outputs are **validated packages**, not
uploads; and ComfyUI/n8n/GitHub outbound effects are **recorded** unless network
access is explicitly enabled. See [`ROADMAP.md`](ROADMAP.md) status tiers.

## Reproduce

```bash
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python scripts/manage_db.py check
cd ../frontend
npx tsc --noEmit && npm run build
```
