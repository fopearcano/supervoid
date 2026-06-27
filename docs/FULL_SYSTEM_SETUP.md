# Full system setup & run (Docker)

End-to-end guide to run **all of SUPERVOID** with Docker: the app (Postgres +
backend + frontend), the self-hosted **vLLM** model server, and **LibreChat**
(with the bundled MCP signing shim) — wired together so LibreChat and the Brain
depend on, and talk to, the SUPERVOID backend.

If you only want the app + the **native in-app chat** (no LibreChat, no Docker),
the much shorter path is the repo `README` + `docs/LIBRECHAT_QUICKSTART.md`. This
document is the *whole* system.

---

## 1. Architecture & dependency order

Three independently-versioned stacks share one **private Docker network**,
`supervoid-brain`:

```
            ┌────────────────────────── host ──────────────────────────┐
            │                                                            │
 browser ─▶ │  frontend (nginx SPA) :8080                               │
            │     │  /api/  /public/  /brain-handoff  ──▶ backend        │
            │     │  /brain/            ──────────────▶ LibreChat        │
            │     ▼                                                      │
            │  backend (FastAPI) :8000 ◀── Brain Gateway /brain/v1       │
            │     │                    ◀── MCP /mcp (via sign-proxy)     │
            │     ├──▶ postgres :5432                                    │
            │     └──▶ vllm :8000  (OpenAI-compatible, PRIVATE)          │
            │                                                            │
            │  LibreChat :3080 (PRIVATE) ──▶ mongo, meilisearch          │
            │     └─ mcp-sign-proxy :8092 ──▶ backend /mcp               │
            └────────────────────────────────────────────────────────────┘
            shared private network: supervoid-brain
```

**Who depends on whom (so: bring-up order):**

1. `supervoid-brain` **network** must exist first.
2. **vLLM** (the model) — optional but recommended; everything that generates text needs it.
3. **SUPERVOID app** (Postgres → backend → frontend) — the system of record; LibreChat is useless without it. Seed it once.
4. **LibreChat** stack — depends on the backend (Brain Gateway + MCP) being up on the network.

| Stack | Compose file | Publishes | Private |
|---|---|---|---|
| App | `docker-compose.yml` **+** `deploy/brain/docker-compose.supervoid.brain.yml` | frontend `:8080`, backend `:8000`, postgres `:5432` | — |
| Model | `deploy/brain/docker-compose.vllm.yml` | — | vLLM `:8001`→loopback |
| Chat | `deploy/brain/docker-compose.librechat.yml` | — | LibreChat `:3080`→loopback, Mongo, Meili, sign-proxy `:8092` |

The **overlay** `docker-compose.supervoid.brain.yml` is the glue: it joins the
backend + frontend to `supervoid-brain` and points the backend at vLLM + the MCP
service token. Without it the app runs standalone (no model, no LibreChat link).

---

## 2. Prerequisites

- **Docker Engine + Compose v2** (`docker compose version`).
- **For vLLM:** an NVIDIA GPU + driver + the **NVIDIA Container Toolkit**. A 24 GB
  card (e.g. RTX 3090) fits a quantized ~7–14B model — see
  [`VLLM_DEPLOYMENT.md`](./VLLM_DEPLOYMENT.md) for sizing/quantization.
- Disk for images + the Hugging Face model cache (a persisted volume).
- Free host ports `8080` and `8000`. Everything else stays private (loopback).

No GPU? See **§8 No-GPU modes** — the system runs fully on `dry_run` or an
external OpenAI-compatible endpoint.

---

## 3. Get the code and create the three env files

```bash
git clone <your-fork> supervoid && cd supervoid

cp .env.example                        .env            # the app (root compose + overlay)
cp .env.brain.example                  .env.brain      # vLLM (example lives at the repo root)
cp deploy/brain/.env.librechat.example .env.librechat  # LibreChat + sign-proxy
```

Each compose reads its own file: the app/overlay use `.env` (auto-loaded), vLLM
uses `.env.brain`, LibreChat uses `.env.librechat` (passed with `--env-file`).

---

## 4. Generate secrets

```bash
openssl rand -hex 32     # SECRET_KEY, MCP_SERVICE_TOKEN, VLLM_API_KEY,
                         # JWT_SECRET, JWT_REFRESH_SECRET, CREDS_KEY, MEILI_MASTER_KEY
openssl rand -hex 16     # CREDS_IV
```

### Shared-secret matrix (the thing people get wrong)

Some secrets **must be identical across files** or the stacks reject each other:

| Secret | Set in | Must equal | Why |
|---|---|---|---|
| `MCP_SERVICE_TOKEN` | `.env` **and** `.env.librechat` | each other | MCP auth + the shim's HMAC key |
| `VLLM_API_KEY` (= `AI_API_KEY`) | `.env.brain` (as `VLLM_API_KEY`) **and** `.env` (the overlay forwards `VLLM_API_KEY`→`AI_API_KEY`) | each other | backend authenticating to vLLM |
| `MEILI_MASTER_KEY` | `.env.librechat` | itself (LibreChat + Meili) | search index auth |

Single-stack secrets (no cross-file match needed): `SECRET_KEY` (backend JWT);
`JWT_SECRET`, `JWT_REFRESH_SECRET`, `CREDS_KEY`, `CREDS_IV` (LibreChat).

---

## 5. Configure the env files

### `.env` (the app)
```ini
# Postgres
POSTGRES_USER=supervoid
POSTGRES_PASSWORD=<choose-a-strong-one>
POSTGRES_DB=supervoid

# Backend
SECRET_KEY=<openssl rand -hex 32>
ENVIRONMENT=production
DB_INIT_STRATEGY=migrate            # run Alembic on boot (overlay default)

# Model (used by the overlay) — in-network vLLM is `vllm` on its internal port
AI_PROVIDER=vllm
AI_BASE_URL=http://vllm:8000/v1
AI_MODEL=supervoid-brain
VLLM_API_KEY=<same value you put in .env.brain>   # overlay maps this to AI_API_KEY

# MCP (used by the overlay) — MUST match .env.librechat
MCP_SERVICE_TOKEN=<openssl rand -hex 32>
LIBRECHAT_PUBLIC_URL=/brain/        # the in-app "Open in LibreChat" link

# Host ports (optional)
FRONTEND_PORT=8080
BACKEND_PORT=8000
```

### `.env.brain` (vLLM)
Set at least the model; tune the rest per your GPU (see `VLLM_DEPLOYMENT.md`):
```ini
VLLM_MODEL=<a-HF-model-id-that-fits-your-GPU>
VLLM_SERVED_MODEL_NAME=supervoid-brain   # must match AI_MODEL in .env
VLLM_API_KEY=<same value as .env VLLM_API_KEY>
VLLM_PORT=8000                            # in-network port (keep 8000 → AI_BASE_URL)
VLLM_PUBLISH_PORT=8001                    # loopback host port (private)
VLLM_MAX_MODEL_LEN=8192                   # lower it if you OOM on 24 GB
# VLLM_QUANTIZATION=awq                   # e.g. for a quantized checkpoint
```

### `.env.librechat` (LibreChat + sign-proxy)
```ini
# Reach the SUPERVOID backend by its service name on the brain network:
SUPERVOID_BACKEND_HOST=backend
SUPERVOID_BACKEND_PORT=8000
# Tools: shipped shim is bundled; default SUPERVOID_MCP_URL works as-is.
MCP_SERVICE_TOKEN=<the SAME value as .env>
# LibreChat secrets
JWT_SECRET=<hex32>
JWT_REFRESH_SECRET=<hex32>
CREDS_KEY=<hex32>
CREDS_IV=<hex16>
MEILI_MASTER_KEY=<hex32>
```
> `SUPERVOID_BACKEND_HOST=backend` works because the overlay puts the backend on
> `supervoid-brain`, where its service name resolves. (Outside Docker you'd use a
> host/IP instead.)

---

## 6. Bring it up (in order)

### Step 1 — the shared network
- **If you will run vLLM:** skip this — vLLM's compose creates `supervoid-brain`.
- **If you will NOT run vLLM:** create it yourself:
  ```bash
  docker network create supervoid-brain
  ```

### Step 2 — vLLM (optional, recommended)
```bash
cd deploy/brain && ./scripts/vllm-start.sh        # uses ../../.env.brain
./scripts/vllm-smoke.sh                            # OpenAI-compatible smoke test
cd ../..
```
First boot downloads the model into the `supervoid-vllm-hf-cache` volume — give it
time (the healthcheck allows up to 10 min). vLLM stays on **loopback only**.

### Step 3 — the SUPERVOID app (joined to the brain)
```bash
docker compose \
  -f docker-compose.yml \
  -f deploy/brain/docker-compose.supervoid.brain.yml \
  up -d --build
```
Migrations run automatically on boot (`DB_INIT_STRATEGY=migrate`).

### Step 4 — seed demo data (one-time) *or* create your own admin
```bash
# Demo dataset (idempotent). Seeds users with password "supervoid",
# e.g. admin helena.pryce@supervoid.local
docker compose -f docker-compose.yml \
  -f deploy/brain/docker-compose.supervoid.brain.yml \
  exec backend python -m app.seed
```
For a clean deployment instead, create your own admin and skip the demo seed.

### Step 5 — LibreChat (+ Mongo + Meili + sign-proxy)
```bash
docker compose -f deploy/brain/docker-compose.librechat.yml \
  --env-file .env.librechat up -d --build
```
**First boot only**, to create the LibreChat admin account: set
`LIBRECHAT_ALLOW_REGISTRATION=true` in `.env.librechat`, `up -d`, register in the
browser, then set it back to `false` and `up -d` again.

---

## 7. Per-member wiring (per-role access)

Each person who uses LibreChat needs two things:

1. **Admin links their identity:** sign in to SUPERVOID → **System ▸ Identity &
   Access** → link the member's LibreChat email to their SUPERVOID account.
   *Unlinked identities are rejected by MCP.*
2. **Member pastes a Brain token:** **System ▸ Brain Tokens** → create a
   `sk-brain-…` token → paste it into LibreChat's *SUPERVOID Brain* endpoint as the
   API key.

Capability is enforced by the **mapped SUPERVOID user** (admin = studio-wide,
members = project-scoped). LibreChat's own role label is ignored. Details:
[`LIBRECHAT_INTEGRATION.md`](./LIBRECHAT_INTEGRATION.md).

---

## 8. Verify (health ladder)

Published (from the host):
```bash
curl -fsS http://localhost:8000/api/health            # backend
curl -fsS http://localhost:8000/api/ai/health         # model wiring (no secrets leaked)
curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:8080/   # frontend → 200
```
Private (from inside the network):
```bash
docker compose -f deploy/brain/docker-compose.librechat.yml exec mcp-sign-proxy \
  python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8092/healthz').read())"
docker compose -f deploy/brain/docker-compose.librechat.yml exec librechat \
  curl -fsS http://localhost:3080/api/health
```
End-to-end:
- **Native chat:** open `http://localhost:8080`, sign in (`helena.pryce@supervoid.local` / `supervoid`), go to **System ▸ SUPERVOID Brain**, ask a question → grounded answer + tool/citation chips.
- **LibreChat:** open `http://localhost:8080/brain/`, sign in, pick *SUPERVOID Brain*, ask → answer; a tool call exercises the shim → `/mcp`.

### Access points
| URL | What |
|---|---|
| `http://localhost:8080` | SUPERVOID app (public home + members) |
| `http://localhost:8080/brain/` | LibreChat (proxied; members only) |
| `http://localhost:8000/docs` | Backend OpenAPI |
| `http://localhost:8080/public/…` | Public reader (the only internet-safe surface) |
| vLLM, `/mcp`, Mongo, Meili, sign-proxy | **private — never publish** |

---

## 9. No-GPU / lightweight modes

- **dry_run (no model server):** omit the vLLM step and set `AI_PROVIDER=dry_run`
  in `.env` (or run the app without the overlay). The native chat returns canned,
  deterministic answers; every non-generative feature works. Good for kicking the
  tires.
- **External OpenAI-compatible endpoint:** set `AI_PROVIDER=openai_compatible`,
  `AI_BASE_URL=<https://…/v1>`, `AI_API_KEY=<key>` in `.env`; skip vLLM. (Note:
  sending studio data to a third-party endpoint defeats the self-hosted privacy
  posture — keep it internal for real use.)

You still get the overlay's MCP wiring; just point the model elsewhere.

---

## 10. Day-2 operations

```bash
# status / logs
docker compose -f docker-compose.yml -f deploy/brain/docker-compose.supervoid.brain.yml ps
docker compose -f docker-compose.yml -f deploy/brain/docker-compose.supervoid.brain.yml logs -f backend

# stop / start (data persists in named volumes)
docker compose -f docker-compose.yml -f deploy/brain/docker-compose.supervoid.brain.yml down
# add -v to ALSO delete volumes (DESTRUCTIVE: wipes Postgres + storage)

# update after a git pull
git pull && docker compose -f docker-compose.yml \
  -f deploy/brain/docker-compose.supervoid.brain.yml up -d --build
```

- **Persistent data:** `postgres_data` (DB), `storage` (uploads),
  `supervoid-vllm-hf-cache` (models), `supervoid-librechat-*` (chat/mongo/meili).
- **Backup / restore & disaster recovery:** [`SUPERVOID_BRAIN_RECOVERY.md`](./SUPERVOID_BRAIN_RECOVERY.md).
- **Operations / health states:** [`SUPERVOID_BRAIN_OPERATIONS.md`](./SUPERVOID_BRAIN_OPERATIONS.md).

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `network supervoid-brain not found` | network not created | start vLLM first, or `docker network create supervoid-brain` |
| Backend up, `ai/health` degraded | vLLM down / wrong URL / key mismatch | check vLLM healthy; `AI_BASE_URL=http://vllm:8000/v1`; `AI_API_KEY`==`VLLM_API_KEY` |
| `/brain/` returns **502** | LibreChat not up, or frontend/LibreChat not on the brain net | start the LibreChat stack; confirm the overlay is in your `up` command |
| MCP tools error / **401** | `MCP_SERVICE_TOKEN` differs between `.env` and `.env.librechat`, or no identity link | make the tokens identical; link the member in *Identity & Access* |
| Login fails for everyone | demo data not seeded | run Step 4 (`python -m app.seed`) |
| vLLM won't load / **OOM** | model too big for the GPU | lower `VLLM_MAX_MODEL_LEN`, use a quantized model — see `VLLM_DEPLOYMENT.md` |
| Backend can't reach Postgres | started before DB healthy | it retries; otherwise check the `postgres` healthcheck/logs |

Validate any compose file before `up`:
```bash
docker compose -f docker-compose.yml -f deploy/brain/docker-compose.supervoid.brain.yml config >/dev/null && echo OK
```

---

## 12. Security checklist (before LAN / internet)

- **vLLM stays private** — loopback only; only the SUPERVOID backend talks to it.
  Never publish it and never put it behind the public proxy.
- **Only `/public`** (the reader) is meant to be internet-facing. The Brain
  Gateway (`/brain/v1`), `/mcp`, Mongo, Meili and the sign-proxy are private.
- Front the app + LibreChat with a **TLS reverse proxy** (see `deploy/brain/nginx`).
- Set a strong `SECRET_KEY`; rotate `MCP_SERVICE_TOKEN` / `VLLM_API_KEY` periodically.
- Keep `LIBRECHAT_ALLOW_REGISTRATION=false` after creating the admin.
- Pin upstream images by digest in production (LibreChat, Mongo, Meili, vLLM).

---

### Related docs
- [`LIBRECHAT_QUICKSTART.md`](./LIBRECHAT_QUICKSTART.md) — shorter LibreChat-only paths (incl. no-Docker)
- [`LIBRECHAT_INTEGRATION.md`](./LIBRECHAT_INTEGRATION.md) — the full integration reference
- [`MCP_SERVER.md`](./MCP_SERVER.md) — the tool layer + signing shim
- [`VLLM_DEPLOYMENT.md`](./VLLM_DEPLOYMENT.md) — model serving, sizing, quantization
- [`MIGRATIONS.md`](./MIGRATIONS.md) — schema strategies (`create_all` / `migrate` / `skip`)
