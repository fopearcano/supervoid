# Database migrations — SUPERVOID Publishing

Safe, non-destructive schema migrations with **Alembic**, layered onto the
existing SQLModel schema. Works for **SQLite** (local-first default) and
**PostgreSQL**. The application keeps `init_db()` (direct `create_all`) for fast
fresh-dev databases; managed environments use Alembic.

- Tooling: `alembic==1.13.3` (pinned in `backend/requirements.txt`).
- Config: `backend/alembic.ini` + `backend/alembic/env.py`.
- Baseline migration: `backend/alembic/versions/0001_baseline_baseline_schema.py`
  (creates the full current schema — all 25 tables).
- Helpers: `backend/app/migrations.py` (shared by app, CLI, tests).
- CLI: `backend/scripts/manage_db.py`.

## How the URL is resolved

There is **no hardcoded URL or credentials**. `alembic/env.py` resolves the
database URL from, in order:

1. a URL explicitly set on the Alembic `Config` (used by `app.migrations` and
   tests), then
2. `settings.database_url` (i.e. the `DATABASE_URL` environment variable / the
   app's normal configuration).

So `alembic` on the command line and the app share one source of truth.

## Startup strategies (`DB_INIT_STRATEGY`)

`prepare_database()` runs at app startup and branches on
`settings.db_init_strategy`:

| Value | Behaviour | Use for |
| --- | --- | --- |
| `create_all` *(default)* | `init_db()` → `SQLModel.metadata.create_all` | fresh **dev** databases (fast, no migration step) |
| `migrate` | `ensure_migrated()` — adopt a legacy DB (stamp), else upgrade/create | managed / shared / production databases |
| `skip` | do nothing | when migrations are run out-of-band (deploy/CI) before boot |

`init_db()` is retained unchanged for backward compatibility; it is **not**
removed.

`ensure_migrated()` is non-destructive:
- `alembic_version` present → `upgrade head`;
- core tables present but no `alembic_version` → **`stamp head`** (a pre-Alembic
  database is adopted at the baseline — tables are never recreated);
- empty database → `upgrade head` (creates the full schema).

## Commands

Run from `backend/` with the virtualenv active. The CLI wraps Alembic +
`app.migrations`; raw `alembic` also works.

```bash
python scripts/manage_db.py current        # show current revision
python scripts/manage_db.py upgrade        # upgrade to head
python scripts/manage_db.py upgrade <rev>  # upgrade to a specific revision
python scripts/manage_db.py downgrade -1   # step back one revision
python scripts/manage_db.py downgrade base # remove all migrations
python scripts/manage_db.py stamp head     # mark a DB at head WITHOUT running DDL
python scripts/manage_db.py ensure         # non-destructive adopt/upgrade/create
python scripts/manage_db.py verify         # structural check: configured DB vs models
python scripts/manage_db.py check          # CI: migrations build a schema matching models
python scripts/manage_db.py history        # migration history

# Equivalent raw Alembic (URL still resolved from DATABASE_URL):
alembic upgrade head
alembic downgrade -1
alembic stamp head
alembic revision --autogenerate -m "describe change"
```

## Procedures

### Fresh install (dev, SQLite)
Nothing to do — the default `create_all` strategy builds the schema on first
boot, and `python -m app.seed` loads demo data. To use the managed path instead:

```bash
DB_INIT_STRATEGY=migrate uvicorn app.main:app   # migrations create the schema
# or, explicitly:
python scripts/manage_db.py upgrade
```

### Existing / populated database (the important one)
A database created by the old `init_db()`/`create_all` has tables but **no**
`alembic_version`. Adopt it **without recreating anything**:

```bash
python scripts/manage_db.py ensure      # detects legacy schema -> stamps baseline
# or explicitly:
python scripts/manage_db.py stamp head
```

After stamping, `current` reports `0001_baseline`, data is untouched, and future
`upgrade`s apply only new migrations. (Verified by `tests/test_migrations.py`
and an end-to-end stamp of a seeded database — row counts unchanged.)

### Upgrade
```bash
python scripts/manage_db.py upgrade     # to head
```
In a managed deployment, either set `DB_INIT_STRATEGY=migrate` (upgrade on boot)
or run the command in your release step and boot with `DB_INIT_STRATEGY=skip`.

### Downgrade
```bash
python scripts/manage_db.py downgrade -1     # one step
python scripts/manage_db.py downgrade base   # everything (drops all tables)
```
Downgrade is supported and round-trip tested on SQLite. Treat production
downgrades as destructive — back up first.

### Authoring a new migration (later phases)
```bash
# 1. change/add SQLModel models
# 2. autogenerate against a throwaway DB so the diff is the new change only:
DATABASE_URL="sqlite:////tmp/gen.db" alembic revision --autogenerate -m "add X"
# 3. review the generated file (esp. SQLite uses batch mode for ALTERs)
# 4. confirm models and migrations agree:
python scripts/manage_db.py check
```

### CI schema verification
`python scripts/manage_db.py check` builds the schema **from migrations** on a
throwaway SQLite database and asserts it matches `SQLModel.metadata` (tables and
columns). It needs no configured database and exits non-zero on drift — wire it
into CI to catch "a model changed but no migration was added". The same guard is
asserted by `tests/test_migrations.py::test_baseline_upgrade_creates_full_schema`.

## SQLite vs PostgreSQL

- **SQLite** (default, fully tested here): `env.py` enables `render_as_batch`
  so future `ALTER`s work despite SQLite's limitations.
- **PostgreSQL**: install the driver (`pip install -r requirements-postgres.txt`,
  `psycopg[binary]`) and set
  `DATABASE_URL=postgresql+psycopg://user:pass@host/dbname`. The same `env.py`
  and baseline apply; constructs are portable. Postgres is **not** exercised in
  this repo's test run, so validate against a real instance before relying on
  it. Note one known Alembic/Postgres wart: `downgrade` of tables that use
  native `ENUM` types may leave the enum types behind (forward `upgrade` is
  unaffected).

## What is intentionally not changed
- `init_db()` stays (back-compat; default dev path).
- The test suite builds its schema via `create_all` (in `conftest.py`) — Alembic
  does not interfere with tests; the migration tests use isolated temp SQLite
  files.
- No domain/model changes were made in this phase — only the migration
  foundation.
