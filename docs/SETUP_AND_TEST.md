# Setup & Test — Mini-Guide

A fast path to running SUPERVOID Publishing locally and verifying it works. For
the full reference see [`ARCHITECTURE.md`](ARCHITECTURE.md), [`API.md`](API.md),
and the [release checklist](RELEASE_READINESS.md).

## Prerequisites

- Python **3.11+**
- Node **18+** (npm)
- No external services required — it is local-first (SQLite + local file storage).

---

## 1. Backend — set up & run

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt     # test/lint tools

python -m app.seed                       # idempotent demo corpus
uvicorn app.main:app --reload --port 8000
```

Now reachable:

- `http://127.0.0.1:8000/` — service identity
- `http://127.0.0.1:8000/api/health` — liveness
- `http://127.0.0.1:8000/docs` — interactive OpenAPI (try every endpoint here)

The seed loads a full demo studio (story world, graphic novel, film adaptation,
collaborators, assets + provenance, tasks + approvals, agent findings, a
published public work). Re-running prints `Seed skipped`.

## 2. Frontend — set up & run

In a second terminal:

```bash
cd frontend
npm install
npm run dev                              # http://127.0.0.1:5173
```

Vite proxies `/api/*` to `http://127.0.0.1:8000`, so just open
`http://127.0.0.1:5173/`. The public reader is at `/reader`.

## 3. Log in & explore

Every seeded user has the password `supervoid`. Start as the admin:

| Email | Role |
| --- | --- |
| `helena.pryce@supervoid.local` | `admin` |
| `kazu.fujita@supervoid.local` | `production_manager` |
| `olesya.kestral@supervoid.local` | `archive_reader` |

In the UI: **Studio** (command centre) → open a work's command page → wander into
GN Studio, Assets, Agents, Curation, Rights, Editions.

API login (OAuth2 password form):

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -d 'username=helena.pryce@supervoid.local&password=supervoid' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -s http://127.0.0.1:8000/api/command-centre/overview \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

---

## 4. Test it

### Backend test suite (373 tests)

```bash
cd backend
.venv/bin/python -m pytest -q
```

Run a focused slice:

```bash
.venv/bin/python -m pytest tests/test_e2e_workflows.py tests/test_seed.py -q
```

### Migrations match the models (CI gate)

```bash
.venv/bin/python scripts/manage_db.py check      # → migrations match the models ✓
```

### Frontend type-check & build

```bash
cd frontend
npx tsc --noEmit
npm run build
```

---

## 5. Verify the hardening features by hand

With the backend running:

```bash
# Structured error envelope + X-Request-ID header (404)
curl -i http://127.0.0.1:8000/api/manuscripts/nope
#   → 404  {"detail":"Manuscript not found","request_id":"…"}  + X-Request-ID

# Validation error envelope (422 with a structured errors list)
curl -i 'http://127.0.0.1:8000/api/authors?limit=0'

# Request correlation — your id is echoed back on the header
curl -i -H 'X-Request-ID: my-trace-1' http://127.0.0.1:8000/api/health

# Pagination envelope on a large collection
curl -s -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8000/api/curation/works?limit=5' | python3 -m json.tool
#   → {"items":[…],"total":…,"skip":0,"limit":5}

# Public reader only shows published works (private stays invisible)
curl -s http://127.0.0.1:8000/public/works | python3 -m json.tool
```

## 6. Backup & restore (records + assets)

```bash
cd backend
.venv/bin/python scripts/backup_restore.py backup --out ../backups/demo
# → backed up N rows and M files to ../backups/demo

# restore into a scratch database to confirm it round-trips
.venv/bin/python scripts/backup_restore.py restore \
  --in ../backups/demo --url "sqlite:///./restored.db"
```

---

## Troubleshooting

- **`No module named pytest`** — activate the venv (`source .venv/bin/activate`)
  or call `.venv/bin/python -m pytest`.
- **Frontend 401s** — log in; the dev server proxies to the backend on `:8000`,
  so the backend must be running too.
- **Reset the demo** — delete `backend/supervoid.db` (and `backend/storage/`),
  then re-run `python -m app.seed`.
- **Postgres** — set `DATABASE_URL` and `pip install -r requirements-postgres.txt`;
  the ORM and migrations are engine-agnostic (no code changes).
