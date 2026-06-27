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
| `nginx/librechat.conf` | reverse-proxy location block (`/brain/`) |
| `scripts/validate_librechat_config.py` | automated configuration validation |
| `scripts/librechat-validate.sh` | validator + `docker compose config` wrapper |

---

## Topology & security boundary

```
Member browser ──HTTPS──> SUPERVOID reverse proxy ──/brain/──> LibreChat (loopback)
                                                                  │  (private supervoid-brain network)
                                                                  ├─> SUPERVOID Brain Gateway   /brain/v1   (OpenAI-compatible)
                                                                  └─> SUPERVOID MCP (via signing shim)  /mcp  (governed tools)
LibreChat ──internal only──> MongoDB + Meilisearch  (no host ports)
SUPERVOID Brain Gateway ──> vLLM  (private; never reached by LibreChat directly)
```

- **Only LibreChat is exposed**, under `/brain/`, and **only behind the SUPERVOID
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
2. Open `/brain/`, register the administrator account (email login).
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
The **signing shim** (shipped at `deploy/brain/sign-proxy/`, bundled in the
LibreChat compose as service `mcp-sign-proxy`) adds the internal service token
and an HMAC signature over that context; the SUPERVOID backend:

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

## Private navigation & "Ask the Brain" hand-off

The SUPERVOID studio shows a prominent **SUPERVOID Brain** nav item (System group)
opening a hub with the current **active project, state version, model status,
compiler status, and pending-proposals count**, plus an **Open the Brain** button.

Every entity view also carries a context-aware **Ask the Brain** action — on a
Work, Story World, graphic-novel page or panel, screen project, scene, shot,
asset, production task, and rights record. Clicking it:

1. calls `POST /api/brain/handoff {entity_type, entity_id}`; the backend resolves
   the entity's **project scope**, enforces `VIEW_PROJECT`, and **creates/resolves
   a bound `BrainConversation`**;
2. mints a **signed, short-lived, single-use** hand-off token (HMAC over
   `handoff_id:exp`, ~120 s TTL);
3. redirects the browser to `/brain-handoff?token=…` — which carries **only the
   opaque token; never any project content**;
4. the landing endpoint **consumes** the token (once), then 303-redirects to the
   Brain UI.

### Deep-link limitation (no fork)

Deep-linking into a *specific* LibreChat conversation would require modifying
upstream LibreChat, so we **do not**. Instead:

- the hand-off opens the **normal Brain UI**;
- the selected context is the member's most-recent hand-off, made available
  through the MCP **`select_active_project`** / **`list_my_projects`** tools (and
  surfaced in the hub's *active project*);
- the member (or the model) selects it on the first turn.

This keeps LibreChat unforked. If a future LibreChat version supports inbound deep
links, the landing endpoint can pass the bound conversation through without any
other change.

### Independent authentication boundaries

Three independent credentials, never mixed: the SUPERVOID **browser JWT** (studio
+ `/api`), the member's **BrainAccessToken** (Brain Gateway), and **LibreChat's
own** session. The hand-off token is the *only* bridge — single-purpose,
short-lived, signed, and single-use — and is the sole credential on the redirect
(which carries no JWT).

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
6. Verify `GET /brain/api/health` and a SUPERVOID Brain round-trip + one MCP tool
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

- Public ingress is **only** `/brain/` via the SUPERVOID reverse proxy.
- `/brain` and `/mcp` are private — never internet-exposed.
- Mongo + Meilisearch have no host ports.
- Two-layer MCP auth (service token + signed user-context); SUPERVOID maps the
  email to a user and re-runs the policy service on every tool.
- Each member uses their own Brain token; secrets live only in `.env.librechat`
  / a secret manager and are validated (strength + non-placeholder) before deploy.
---

## End-to-end hardening (Prompt 19)

The SUPERVOID Brain has completed its final integration + hardening pass. A
full-path end-to-end test exercises the complete governed flow against the offline
provider: a member creates a Brain token → LibreChat calls the OpenAI-compatible
Gateway → the Gateway authenticates the member → a project is selected → the
`ProjectBrainState` is loaded → a stable prefix + state delta are assembled → the
provider streams → internal evidence is cited (UNTRUSTED-fenced) → an MCP read tool
is permission-checked → a write proposes a production task → a PENDING
`AgentActionProposal` appears → a human approves it → execution is audited → a
`BrainEvent` is emitted → the project state recompiles incrementally → the next
turn carries only the new delta → public users cannot reach any Brain/MCP/private
surface.

Also hardened/verified: backup & restore across **every** Brain record,
migration-chain verification, vLLM- and LibreChat-unavailable fallbacks, the
stale-compiler warning, token revocation, model-change and prompt-template-change
invalidation, multi-user isolation, two simultaneous project conversations, and a
small-team load/isolation check.

See the Brain operations docs:
[`SUPERVOID_BRAIN_OPERATIONS.md`](./SUPERVOID_BRAIN_OPERATIONS.md) ·
[`SUPERVOID_BRAIN_SECURITY.md`](./SUPERVOID_BRAIN_SECURITY.md) ·
[`SUPERVOID_BRAIN_RECOVERY.md`](./SUPERVOID_BRAIN_RECOVERY.md) ·
[`SUPERVOID_BRAIN_MODEL_EVALUATION.md`](./SUPERVOID_BRAIN_MODEL_EVALUATION.md),
and the **release-readiness report** in [`ROADMAP.md`](./ROADMAP.md).
