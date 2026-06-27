# LibreChat quickstart (single machine)

> **You probably don't need this.** The **native in-app chat** (sign in → sidebar
> **System ▸ SUPERVOID Brain**) already gives every member a governed chat — it
> answers within their permissions, cites internal evidence, and calls the MCP
> read/proposal tools per role — with **no Docker, no MongoDB, no second app**.
> Use LibreChat only if you want its richer UI (multi-model presets, file uploads,
> plugins, conversation management).

LibreChat is a separate full-stack app that requires **MongoDB** (and optional
Meilisearch). There are two ways to run it on one machine. Full reference:
[`LIBRECHAT_INTEGRATION.md`](./LIBRECHAT_INTEGRATION.md). Pinned config:
`deploy/brain/librechat.yaml` (validate with
`python deploy/brain/scripts/validate_librechat_config.py`).

Assumes the SUPERVOID API is on `:8000` and vLLM on `:8001` (per the dev setup).

## What must line up (both paths)

| Where | Value |
|---|---|
| Backend env | `MCP_SERVICE_TOKEN=<a long random secret>` |
| LibreChat env | `MCP_SERVICE_TOKEN=<the SAME secret>` (service auth + HMAC signing) |
| LibreChat env | `SUPERVOID_BACKEND_HOST` + `SUPERVOID_BACKEND_PORT` → the API |
| Backend env | `LIBRECHAT_PUBLIC_URL=http://<host>:3080` (so the in-app "Open in LibreChat" link works) |
| Per member | an **active identity link** (admin) + a **Brain token** pasted into LibreChat |

The gateway baseURL LibreChat uses is `…/brain/v1`; each member's API key is their
own `sk-brain-…` token (`apiKey: user_provided`).

## Path B — no Docker (bare-metal; best fit if you're avoiding Docker)

Everything on `localhost`, so no container networking.

1. **MongoDB**: install + run locally (e.g. `mongod --dbpath ~/.supervoid-mongo`),
   listening on `127.0.0.1:27017`.
2. **LibreChat**: clone the pinned version (`v0.7.8`), `npm ci`.
   - Copy `deploy/brain/librechat.yaml` to LibreChat's config path.
   - In LibreChat's `.env`: `MONGO_URI=mongodb://127.0.0.1:27017/LibreChat`,
     `MCP_SERVICE_TOKEN=<secret>`, `SUPERVOID_BACKEND_HOST=127.0.0.1`,
     `SUPERVOID_BACKEND_PORT=8000`, `PORT=3080`. (Meilisearch optional — disable
     search if you skip it.)
   - Build + run: `npm run frontend && npm run backend`.
3. **Backend env** (where you run the SUPERVOID API): `MCP_SERVICE_TOKEN=<secret>`,
   `LIBRECHAT_PUBLIC_URL=http://localhost:3080`. Restart the API.

LibreChat talks to the gateway at `http://127.0.0.1:8000/brain/v1` and MCP at
`http://127.0.0.1:8000/mcp` — all loopback.

## Path A — Docker (simplest if you accept containers)

`deploy/brain/docker-compose.librechat.yml` bundles LibreChat + Mongo +
Meilisearch (Mongo/Meili are internal-only; LibreChat publishes `127.0.0.1:3080`).

```bash
cd deploy/brain
# set MCP_SERVICE_TOKEN, MEILI_MASTER_KEY, and how LibreChat reaches the API:
#   SUPERVOID_BACKEND_HOST / SUPERVOID_BACKEND_PORT
docker compose -f docker-compose.librechat.yml up -d
```

Reaching the API from the LibreChat container:
- **Cleanest:** run the SUPERVOID API as a container in the same compose network so
  LibreChat reaches it at the default `supervoid-backend:8000` (the backend then
  reaches host vLLM via `host.docker.internal:8001`).
- **API on the host:** set `SUPERVOID_BACKEND_HOST=host.docker.internal` and ensure
  the network allows it (the bundled network is private by design — attach a
  non-internal network or co-locate the backend container).

Then set `LIBRECHAT_PUBLIC_URL=http://<host>:3080` in the backend env.

## Per-member wiring (the per-role part)

1. **Admin** links each member's LibreChat identity: sign in → **System ▸ Identity
   & Access** (an active link is required; unlinked identities are rejected by MCP).
2. **Member** creates a **Brain Token** (**System ▸ Brain Tokens / Brain Account**)
   and pastes it into LibreChat's *SUPERVOID Brain* endpoint API key.
3. Capability is enforced **per the mapped SUPERVOID user** — admin is studio-wide,
   members are project-scoped. The LibreChat-declared role is ignored.

Registration is disabled for arbitrary visitors by design — the admin provisions
accounts.

## Security

- **Never expose vLLM** — keep it on loopback (`:8001`); only the SUPERVOID API
  talks to it.
- For LAN/internet, put LibreChat + the gateway + MCP behind a **reverse proxy with
  TLS** (see `deploy/brain/nginx` and Prompt 12); rotate `SECRET_KEY` and
  `MCP_SERVICE_TOKEN`. Only `/public` (the reader) is meant to be internet-facing.
