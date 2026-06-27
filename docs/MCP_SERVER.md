# SUPERVOID MCP server

The SUPERVOID **MCP server** exposes the *governed* SUPERVOID tool layer to
LibreChat over the **Model Context Protocol (Streamable HTTP)**. It is mounted in
the FastAPI backend at **`/mcp`** (outside the private `/api` prefix) and reuses
the same service layer — it **never** exposes raw CRUD or unrestricted database
access.

- Read tools return **only records the calling user is authorised to see**.
- Write-like tools create **gated proposals**, never direct mutations.
- Approval tools verify the **mapped SUPERVOID user's approval scope** (and
  require an administrator for always-gated destructive / publishing / rights /
  external actions).
- Every tool re-runs authorisation through the SUPERVOID **policy service**
  against the mapped user — never the LibreChat-declared role.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md#supervoid-mcp-server) for the design.

---

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/mcp/health` | none | Liveness + tool count (no governance data). |
| `POST` | `/mcp` | service token + signed user-context | MCP JSON-RPC (Streamable HTTP). |
| `GET` | `/mcp` | — | `405` (no server-initiated SSE stream). |

The `POST /mcp` endpoint speaks MCP JSON-RPC: `initialize`, `tools/list`,
`tools/call`, `ping`, and the `notifications/initialized` notification. A single
message returns `200 application/json`; a body containing only notifications
returns `202` with no body.

---

## Authentication (two layers)

1. **Internal service credential** — the `X-SUPERVOID-Service-Token` header must
   equal the configured `MCP_SERVICE_TOKEN`. If the token is unset the server
   **fails closed** (refuses every request).
2. **Signed user-context** — LibreChat's user identity is carried in headers and
   **HMAC-signed with the service token**. The user-context is *never trusted*
   without a valid service credential AND a valid signature.

| Header | Meaning |
|---|---|
| `X-SUPERVOID-Service-Token` | the shared internal credential |
| `X-SUPERVOID-User-Id` | LibreChat user id |
| `X-SUPERVOID-User-Email` | LibreChat user email (the mapping key) |
| `X-SUPERVOID-User-Role` | LibreChat role (informational only — never grants access) |
| `X-SUPERVOID-Request-Id` | correlation id |
| `X-SUPERVOID-User-Sig` | `HMAC-SHA256(token, canonical)` hex |

The canonical string is the four user fields joined by `\n` in this order:

```
user_id \n email \n role \n request_id
```

The server resolves the SUPERVOID **user from the email** (an explicit account
link can be layered on later); the LibreChat role is ignored for authorisation.

> Set `MCP_SERVICE_TOKEN` from a secret manager in deployment. Never commit a
> real value, and keep `/mcp` on the private network only (LibreChat is the only
> intended caller).

---

## Configuring LibreChat (Streamable HTTP)

Add a custom MCP server to LibreChat's `librechat.yaml`. LibreChat injects the
per-user fields via its dynamic placeholders; the **signature is produced by the
trusted integration edge** (LibreChat deployment / a tiny signing shim that holds
the service token), since the chat UI cannot compute an HMAC itself.

```yaml
mcpServers:
  supervoid:
    type: streamable-http
    url: "https://studio.example.internal/mcp"
    headers:
      X-SUPERVOID-Service-Token: "${MCP_SERVICE_TOKEN}"
      X-SUPERVOID-User-Id: "{{LIBRECHAT_USER_ID}}"
      X-SUPERVOID-User-Email: "{{LIBRECHAT_USER_EMAIL}}"
      X-SUPERVOID-User-Role: "{{LIBRECHAT_USER_ROLE}}"
      X-SUPERVOID-Request-Id: "{{LIBRECHAT_REQUEST_ID}}"
      # X-SUPERVOID-User-Sig is added by the signing shim (below).
```

### Signing shim (minimal, holds the service token)

Because the signature binds the exact user-context, compute it at a trusted hop
in front of `/mcp`. A ~15-line reverse proxy is enough:

```python
# sign_proxy.py — sits between LibreChat and SUPERVOID /mcp on the private net.
import hashlib, hmac, os, httpx
from fastapi import FastAPI, Request, Response

TOKEN = os.environ["MCP_SERVICE_TOKEN"]
UPSTREAM = os.environ["SUPERVOID_MCP_URL"]  # https://studio.internal/mcp
app = FastAPI()

def sign(uid, email, role, rid):
    msg = "\n".join([uid, email, role, rid]).encode()
    return hmac.new(TOKEN.encode(), msg, hashlib.sha256).hexdigest()

@app.post("/mcp")
async def proxy(request: Request):
    h = request.headers
    uid, email = h.get("x-supervoid-user-id", ""), h.get("x-supervoid-user-email", "")
    role, rid = h.get("x-supervoid-user-role", ""), h.get("x-supervoid-request-id", "")
    fwd = {
        "X-SUPERVOID-Service-Token": TOKEN,
        "X-SUPERVOID-User-Id": uid, "X-SUPERVOID-User-Email": email,
        "X-SUPERVOID-User-Role": role, "X-SUPERVOID-Request-Id": rid,
        "X-SUPERVOID-User-Sig": sign(uid, email, role, rid),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as c:
        r = await c.post(UPSTREAM, content=await request.body(), headers=fwd)
    return Response(r.content, status_code=r.status_code, media_type="application/json")
```

Point LibreChat's `url` at the shim (`http://sign-proxy:PORT/mcp`); the shim adds
the signature and forwards to SUPERVOID. (If LibreChat can compute the HMAC
itself, the shim is unnecessary — sign with the same canonical string.)

---

## Tools (grouped)

All tools carry MCP annotations describing their **kind** (`read-only`,
`proposal-only`, `destructive`, `external`, `approval`) and an `requiresApproval`
flag, with concise input schemas.

- **Context / navigation**: `get_studio_state`, `get_project_state`,
  `get_project_delta`, `list_my_projects`, `select_active_project`,
  `search_supervoid`, `get_entity_context`.
- **Production**: `get_my_assignments`, `get_blocked_tasks`,
  `get_pending_approvals`, `inspect_production_progress`, `propose_task`,
  `propose_task_update`.
- **Narrative**: `get_story_world`, `get_work_canon`, `get_character_context`,
  `get_location_context`, `get_recent_decisions`, `propose_decision`,
  `propose_canon_change`.
- **Assets**: `search_assets`, `inspect_asset_version`, `inspect_provenance`,
  `inspect_licence`, `propose_asset_link`.
- **Publishing & rights**: `inspect_publication_readiness`, `inspect_rights`,
  `prepare_distribution_checklist`, `propose_publication`,
  `propose_rights_action`.
- **Agent operations**: `run_supervoid_agent`, `list_agent_findings`,
  `list_action_proposals`, `approve_proposal`, `reject_proposal`,
  `execute_approved_proposal`.

Production / asset / publication / rights proposals surface in
`list_action_proposals` (and the Agent Centre); narrative `propose_decision` /
`propose_canon_change` are recorded as decisions surfaced by
`get_recent_decisions`. MCP proposals execute in *recorded* mode — even after
approval the underlying side effect is performed by a human through the audited
UI.

---

## Smoke test

```bash
# health (no auth)
curl -s http://localhost:8000/mcp/health | jq

# tools/list (through the signing shim, or with a hand-computed signature)
TOKEN=dev-token
EMAIL=admin@studio.test
SIG=$(python - <<PY
import hmac,hashlib
print(hmac.new(b"$TOKEN", "\n".join(["lc-1","$EMAIL","admin","req-1"]).encode(), hashlib.sha256).hexdigest())
PY
)
curl -s http://localhost:8000/mcp \
  -H "X-SUPERVOID-Service-Token: $TOKEN" \
  -H "X-SUPERVOID-User-Id: lc-1" -H "X-SUPERVOID-User-Email: $EMAIL" \
  -H "X-SUPERVOID-User-Role: admin" -H "X-SUPERVOID-Request-Id: req-1" \
  -H "X-SUPERVOID-User-Sig: $SIG" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | jq '.result.tools | length'
```
