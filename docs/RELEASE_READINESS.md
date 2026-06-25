# Release-Readiness Checklist — SUPERVOID Publishing

A pre-flight checklist to run before tagging a release or deploying. It is
deliberately conservative and local-first: the goal is a system that is correct,
honest about what it does, and recoverable. Commands assume the `backend/`
virtualenv (`.venv`) and `frontend/` toolchain.

Status legend used throughout the docs: see [`ROADMAP.md`](ROADMAP.md) for the
**completed / production-ready / experimental / adapter-only / future-extraction**
tiers. Do not promote anything across a tier in release notes without evidence.

---

## 1. Code & schema integrity

- [ ] **Backend tests green** — `cd backend && .venv/bin/python -m pytest -q`.
- [ ] **Migrations match models (CI gate)** — `python scripts/manage_db.py check`
      prints `migrations match the models ✓`.
- [ ] **Round-trip clean** — `upgrade head` → `downgrade base` → `upgrade head`
      with no errors (covered by `tests/test_migrations.py`).
- [ ] **No autogenerate drift** — a fresh autogenerate against head yields no
      table/column/index diffs.
- [ ] **Frontend type-checks & builds** — `cd frontend && npx tsc --noEmit && npm run build`.
- [ ] **Lint** — backend `ruff check` and frontend lint pass (or known-waived).

## 2. Data & migrations

- [ ] Target database reachable; `DATABASE_URL` set for the environment (SQLite
      default for local; Postgres for production-shaped deploys).
- [ ] `db_init_strategy` chosen deliberately: `migrate` for managed deploys,
      `create_all` only for throwaway dev.
- [ ] Existing/legacy databases adopt non-destructively (`ensure` stamps a
      pre-Alembic DB at baseline; never recreates tables).
- [ ] New high-use queries are indexed (migration `0012`); no obvious unindexed
      hot path introduced since.

## 3. Security & configuration

- [ ] `SECRET_KEY` / JWT signing secret set from the environment (not a default).
- [ ] Integration **credentials are env-var references only**; the API returns
      presence booleans / masked config, never secret values or env-var names.
- [ ] `INTEGRATIONS_ALLOW_NETWORK` is **off** unless an external dispatch is
      genuinely intended and tested; with it off, outbound effects are recorded,
      not sent.
- [ ] CORS origins restricted appropriately for the deployment.
- [ ] Admin accounts use strong passwords; demo seed password is **not** used in
      any non-demo environment.

## 4. Access control & isolation

- [ ] Global roles and project memberships behave as expected (spot-check an
      `editor` and a project-scoped collaborator).
- [ ] **Public/private isolation holds** — unpublished/draft/private records are
      invisible through `/public` (covered by `tests/test_curation.py`,
      `tests/test_public_reader.py`, `tests/test_e2e_workflows.py`). No private
      file is exposed automatically; only explicit derivatives are public.
- [ ] Publishing, rights changes, and external integration runs are admin-gated.

## 5. Approval boundaries (no surprise side effects)

- [ ] Agent proposals are human-gated; destructive/publishing/rights/external
      proposals require admin approval; nothing auto-executes.
- [ ] Integration runs: read-only/dry-run execute immediately; mutating/external
      runs are `PENDING_APPROVAL` → `APPROVED` → `execute`, external needs admin.
- [ ] Request/`correlation_id` traceability verified on at least one agent run and
      one integration run.

## 6. Honest integration labelling

Confirm nothing mocked, dry-run, or package-export is described as a fully
operational external integration:

- [ ] Desktop **file-exchange** adapters (Affinity/InDesign/Clip Studio/DaVinci/
      Blender/C4D/Houdini) labelled **package generators**, not remote control.
- [ ] **LOGOSFORGE** labelled **adapter-only / local-first bundle import**; the
      outbound notes path is recorded-only.
- [ ] Distribution **export packages** (ONIX/KDP/Ingram/web/press-kit/ARC)
      labelled **validated packages & checklists**, not uploads.
- [ ] **ComfyUI/n8n/GitHub** adapters: outbound effects recorded unless network
      is explicitly enabled.

## 7. Backup & recovery

- [ ] **Backup runs** — `python scripts/backup_restore.py backup --out <dir>`
      reports a non-zero row count and copies the asset storage tree.
- [ ] **Restore verified** — restore into a scratch database + storage path and
      confirm records and asset bytes survive (covered by
      `tests/test_backup_restore.py`); for a real cutover, restore into an empty,
      migrated target.
- [ ] Backups are stored **off-box** (hosted containers are ephemeral; commit and
      push anything that must persist).

## 8. Observability

- [ ] Structured logging on; every request/response carries `X-Request-ID`.
- [ ] Error responses use the `{detail, request_id}` envelope (validation adds
      `errors`); 500s are logged with the request id.

## 9. Documentation & artefacts

- [ ] [`API.md`](API.md), [`ARCHITECTURE.md`](ARCHITECTURE.md),
      [`ROADMAP.md`](ROADMAP.md), and both workflow guides reflect this release.
- [ ] `GET /docs` / `/openapi.json` load and match the shipped routes.
- [ ] Test report regenerated (see `INTEGRATION_TEST_REPORT.md`) and matches the
      tag.
- [ ] Seed produces the demonstrable corpus (covered by `tests/test_seed.py`) if
      shipping a demo.

---

## Quick command block

```bash
# Backend
cd backend
.venv/bin/python -m pytest -q
.venv/bin/python scripts/manage_db.py check
.venv/bin/python scripts/backup_restore.py backup --out ../backups/pre-release

# Frontend
cd ../frontend
npx tsc --noEmit
npm run build
```

If every box above is ticked and the four commands are clean, the release is
ready. If any integration's status is ambiguous, ship it at the **lower** tier —
honesty about capability is a release requirement, not a nicety.
