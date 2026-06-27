# LibreChat integration (SUPERVOID Brain)

LibreChat is the conversational UI for the SUPERVOID Brain. It is deployed as a
**separately versioned upstream application** — we run the official, pinned image
and configure it entirely through a mounted `librechat.yaml` + environment. We do
**not** vendor LibreChat source into the SUPERVOID frontend and do **not** fork
it, so upstream upgrades stay a one-line image bump.

Artefacts (under `deploy/brain/`):

| File | Purpose |
|---|---|
| `docker-compose.librechat.yml` | LibreChat + MongoDB + Meilisearch (pinned, private) |
| `librechat.yaml` | the SUPERVOID Brain custom endpoint + the MCP server config |
| `.env.librechat.example` | secrets + pinned image tags + networking |
| `nginx/librechat.conf` | reverse-proxy location block (`/chat/`) |
| `scripts/validate_librechat_config.py` | automated configuration validation |
| `scripts/librechat-validate.sh` | validator + `docker compose config` wrapper |

---

## Topology & security boundary

```
Member browser ──HTTPS──> SUPERVOID reverse proxy ──/chat/──> LibreChat (loopback)
                                                                  │  (private supervoid-brain network)
                                                                  ├─> SUPERVOID Brain Gateway   /brain/v1   (OpenAI-compatible)
                                                                  └─> SUPERVOID MCP (via signing shim)  /mcp  (governed tools)
LibreChat ──internal only──> MongoDB + Meilisearch  (no host ports)
SUPERVOID Brain Gateway ──> vLLM  (private; never reached by LibreChat directly)
```

- **Only LibreChat is exposed**, under `/chat/`, and **only behind the SUPERVOID
  reverse proxy** (`deploy/brain/nginx/librechat.conf`). LibreChat binds to
  loopback; Mongo and Meilisearch publish no host ports (`internal: true`).
- The **Brain Gateway (`/brain`) and MCP server (`/mcp`) are never proxied to the
  internet.** The proxy snippet explicitly `return 404`s them as defence in depth.
- vLLM is reached only by the Brain Gateway, never by LibreChat.
- The MCP server is reachable only via the **signing shim** on the private
  network (it adds the service token + HMAC over the user-context — see
  [`MCP_SERVER.md`](./MCP_SERVER.md)).

---

## First-time deployment

1. **Generate secrets and the env file.**
   ```bash
   cp deploy/brain/.env.librechat.example .env.librechat
   # fill in every CHANGE_ME with a strong value:
   openssl rand -hex 32   # JWT_SECRET, JWT_REFRESH_SECRET, MEILI_MASTER_KEY, CREDS_KEY, MCP_SERVICE_TOKEN
   openssl rand -hex 16   # CREDS_IV
   ```
   `MCP_SERVICE_TOKEN` **must exactly match** the SUPERVOID backend's
   `MCP_SERVICE_TOKEN`.

2. **Validate before bringing anything up.**
   ```bash
   ./deploy/brain/scripts/librechat-validate.sh --env-file .env.librechat
   ```

3. **Attach the SUPERVOID backend to the `supervoid-brain` network** (so LibreChat
   can reach `/brain/v1` and the MCP shim can reach `/mcp`). The vLLM compose
   creates that network; ensure the backend container joins it (add it to the
   backend service's `networks:` or `docker network connect supervoid-brain
   supervoid-backend`).

4. **Bring up the stack.**
   ```bash
   docker compose -f deploy/brain/docker-compose.librechat.yml --env-file .env.librechat up -d
   ```

---

## Account creation (registration disabled by default)

LibreChat registration is **disabled** in steady state. To create the first
administrator:

1. Set `LIBRECHAT_ALLOW_REGISTRATION=true` in `.env.librechat` and restart
   LibreChat.
2. Open `/chat/`, register the administrator account (email login).
3. Set `LIBRECHAT_ALLOW_REGISTRATION=false` again and restart.

Thereafter the administrator provisions members (LibreChat admin UI / CLI). Email
login is enabled; social login is disabled.

> A LibreChat account is **not** a SUPERVOID account. Authorisation for SUPERVOID
> data comes entirely from the SUPERVOID user the member's **email** maps to (see
> *MCP identity mapping*), never from their LibreChat role.

---

## Brain token linking (per member, once)

The SUPERVOID Brain endpoint uses `apiKey: user_provided`. Each member supplies
**their own** SUPERVOID `BrainAccessToken`:

1. In SUPERVOID (the private app), go to **System → Brain Tokens** and create a
   token (`POST /api/brain-tokens`). The plaintext `sk-brain-…` is shown **once**.
2. In LibreChat, choose the **SUPERVOID Brain** endpoint and paste the token when
   prompted for the API key. LibreChat encrypts it at rest with `CREDS_KEY`/
   `CREDS_IV` and reuses it for that member.
3. Rotate or revoke the token in SUPERVOID at any time; the member re-enters the
   new one once.

This binds each conversation to the member's own SUPERVOID identity, scopes and
rate limits at the Brain Gateway.

---

## MCP identity mapping

When the model calls a SUPERVOID tool, LibreChat sends the member's identity to
the MCP server as dynamic headers (`X-SUPERVOID-User-Id/Email/Role/Request-Id`).
The **signing shim** adds the internal service token and an HMAC signature over
that context; the SUPERVOID backend:

1. verifies the service credential **and** the signature (fails closed otherwise);
2. maps the **email** to a SUPERVOID user (the authorisation subject — the
   LibreChat-declared role is ignored);
3. re-runs every tool through the SUPERVOID **policy service**.

So a member only ever sees and proposes what their SUPERVOID permissions allow,
no matter what they type into LibreChat. See [`MCP_SERVER.md`](./MCP_SERVER.md).

---

## Model endpoint

- **SUPERVOID Brain** → `http://<backend>:8000/brain/v1` (internal). The model
  list is restricted to the served alias(es) (`supervoid-brain`); `fetch: true`
  also queries `/brain/v1/models`.
- **Conversation titles** are generated through the Brain (`titleConvo: true`,
  `titleModel: supervoid-brain`) — no extra provider.
- **`dropParams` is empty by default.** Only add unsupported sampling params after
  compatibility-testing them against the served model + Gateway (otherwise you
  silently change behaviour). Re-run `librechat-validate.sh` after any change.

---

## Studio Director agent (provisioning)

Provide a single starting agent; keep specialised profiles **in the Brain**, not
duplicated as LibreChat prompts.

Create a LibreChat **Agent** (Agents panel → *Create*):

- **Name:** `SUPERVOID Studio Director`
- **Endpoint / model:** `SUPERVOID Brain` → `supervoid-brain`
- **Tools:** the `supervoid` MCP server (enable deferred/lazy tool loading so the
  full ~36-tool catalogue is not always in context).
- **Instructions (thin — the Brain owns the rest):**
  > You are the SUPERVOID Studio Director's interface. The SUPERVOID Brain holds
  > the studio constitution, the compiled state, and the specialised assistant
  > profiles. Always ground answers with `get_studio_state` / `get_project_state`
  > / `get_project_delta` before acting. To work in a specialised capacity
  > (production, narrative, rights, …), ask the Brain to switch profile rather
  > than restating those rules here. All changes go through proposals you create
  > with the `propose_*` tools; never claim a change is applied until a human
  > approves it.

Because profile selection and state live in the Brain, switching specialities is
a Brain concern — the LibreChat agent prompt stays small and stable.

---

## Deferred MCP tools

The MCP catalogue is ~36 tools. Where the LibreChat version supports it, enable
**deferred / on-demand tool loading** so the whole catalogue is not injected into
every prompt (the schemas are deliberately concise to keep this cheap regardless).
This is a LibreChat-side setting on the agent / MCP server; the SUPERVOID MCP
server already advertises governance `serverInstructions` at `initialize`.

---

## Backups

Two stateful stores; back both up on a schedule:

```bash
# MongoDB (conversations, accounts, agents)
docker exec supervoid-librechat-mongo \
  mongodump --archive=/data/db/backup-$(date +%F).gz --gzip
docker cp supervoid-librechat-mongo:/data/db/backup-$(date +%F).gz ./backups/

# Meilisearch (search index — can be rebuilt, but a dump speeds recovery)
docker exec supervoid-librechat-meili \
  curl -fsS -X POST 'http://localhost:7700/dumps' \
  -H "Authorization: Bearer $MEILI_MASTER_KEY"
```

Also back up `.env.librechat` (the **only** copy of `CREDS_KEY`/`CREDS_IV` — lose
them and every member must re-enter their Brain token) to your secret manager.
The named volumes (`supervoid-librechat-*`) are the on-disk state.

---

## Upgrades

LibreChat is upstream and pinned:

1. Read the upstream release notes for the target tag.
2. Bump `LIBRECHAT_IMAGE` in `.env.librechat` to the new pinned tag (prefer a
   digest). Re-pin Mongo/Meilisearch only if the release requires it.
3. Back up Mongo (above).
4. `./deploy/brain/scripts/librechat-validate.sh --env-file .env.librechat`
5. `docker compose -f deploy/brain/docker-compose.librechat.yml --env-file .env.librechat up -d`
6. Verify `GET /chat/api/health` and a SUPERVOID Brain round-trip + one MCP tool
   call.

Because no SUPERVOID code lives inside LibreChat, upgrades carry no merge/fork
risk — only the `librechat.yaml` schema `version` may need a bump (re-validate).

---

## Recovery

- **Restore Mongo:** `mongorestore --gzip --archive=…` into a fresh
  `supervoid-librechat-mongo`, then start LibreChat.
- **Lost `CREDS_KEY`/`CREDS_IV`:** stored member API keys become undecryptable;
  rotate them — each member re-enters a fresh Brain token (their SUPERVOID data is
  untouched; only the cached key is lost).
- **Meilisearch loss:** restore a dump, or let LibreChat re-index from Mongo
  (`SEARCH=true`).
- **MCP/Brain unreachable:** LibreChat keeps working as a chat UI; tool calls and
  completions fail gracefully until the backend/shim is back. Check the
  `supervoid-brain` network attachment and `MCP_SERVICE_TOKEN` parity.

---

## Security boundary (summary)

- Public ingress is **only** `/chat/` via the SUPERVOID reverse proxy.
- `/brain` and `/mcp` are private — never internet-exposed.
- Mongo + Meilisearch have no host ports.
- Two-layer MCP auth (service token + signed user-context); SUPERVOID maps the
  email to a user and re-runs the policy service on every tool.
- Each member uses their own Brain token; secrets live only in `.env.librechat`
  / a secret manager and are validated (strength + non-placeholder) before deploy.
