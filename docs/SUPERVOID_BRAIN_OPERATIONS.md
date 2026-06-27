# SUPERVOID Brain — Operations runbook

Day-2 operations for the SUPERVOID Brain (the governed AI layer: Gateway, MCP,
compiler, sessions, retrieval, memory, evaluation, fine-tuning). Everything here
is **admin-only and private** — GPU / internal topology is never exposed publicly.

See also: [`OBSERVABILITY.md`](./OBSERVABILITY.md) (the Ops surface in detail),
[`VLLM_DEPLOYMENT.md`](./VLLM_DEPLOYMENT.md), [`LIBRECHAT_INTEGRATION.md`](./LIBRECHAT_INTEGRATION.md),
[`SUPERVOID_BRAIN_RECOVERY.md`](./SUPERVOID_BRAIN_RECOVERY.md),
[`SUPERVOID_BRAIN_SECURITY.md`](./SUPERVOID_BRAIN_SECURITY.md).

## Components & processes

| Component | What it is | How it runs |
|---|---|---|
| **vLLM** | the inference server (OpenAI-compatible) | `deploy/brain/docker-compose.vllm.yml` on the GPU host, bound to loopback/private network |
| **Backend API** | gateway `/brain/v1`, MCP `/mcp`, ops `/api/brain/ops`, tuning `/api/brain/tuning` | the FastAPI app (uvicorn) |
| **Outbox worker** | drains `BrainEvent`s → incremental recompiles | `python scripts/brain_outbox.py worker` |
| **LibreChat** | the chat UI; the Brain's *client* | `deploy/brain/docker-compose.librechat.yml` |

The Brain does **not** depend on LibreChat being up (LibreChat calls the Gateway,
not the reverse). vLLM being down degrades the Gateway to `503` but never corrupts
state.

## The Operations surface

- `GET /api/brain/ops/status` — full snapshot (vLLM/model, gateway runtime gauge,
  compiler lag, unprocessed/failed events, state versions, sessions + warmth,
  token/latency, agent/MCP failures, pending proposals, LibreChat health).
- `GET /api/brain/ops/health` — derived health states (per component + overall):
  `healthy · degraded · unavailable · stale · maintenance` (precedence:
  unavailable → maintenance → degraded → stale → healthy).
- `GET /api/brain/ops/metrics` — Prometheus exposition (scrape over the private
  network only).

### Operator controls (admin)

| Control | Effect |
|---|---|
| `POST /controls/model-requests {enabled}` | disable / re-enable NEW model requests (in-flight unaffected) |
| `POST /controls/drain {draining}` | reject new requests while in-flight finish |
| `POST /controls/mcp {enabled}` | disable / re-enable the MCP integration |
| `POST /controls/maintenance {note}` | set/clear a maintenance banner |
| `POST /projects/{work_id}/rebuild?full=` | recompile a project's state (incremental or full) |
| `POST /projects/{work_id}/cold` | mark a project's sessions COLD (treat prefix cache as evicted) |
| `POST /projects/{work_id}/prewarm` | best-effort prefix prewarm (no-op under dry-run) |
| `POST /events/replay` | re-queue dead-lettered `BrainEvent`s |
| `POST /tokens/{token_id}/revoke` | revoke any Brain access token immediately |

## Routine operations

**Start a deployment**
1. Bring up vLLM on the GPU host: `cd deploy/brain && ./scripts/vllm-start.sh` then `./scripts/vllm-smoke.sh`.
2. Set `ai_provider=vllm`, `ai_base_url`, `ai_model`, `ai_api_key` in the backend env.
3. Start the API and the outbox worker (`brain_outbox.py worker`).
4. Confirm `GET /api/brain/ops/health` → `overall: healthy`.

**Issue a member a Brain token** — the member self-serves at `POST /api/brain-tokens`
(returns the secret ONCE). They paste it into LibreChat's custom-endpoint API key.

**Compile / recompile state**
- Incremental (normal): the outbox worker does this automatically as events arrive.
- Manual: `python scripts/brain_compiler.py` or the ops `rebuild` control.
- A full rebuild is always safe and deterministic (same checksum as incremental).

**Watch for backlog** — `outbox_status` / ops `compiler_lag` + `unprocessed_events`.
A non-zero `failed_events` means dead-lettered events: investigate, then
`events/replay`.

## Alerting (suggested Prometheus rules)

- `brain_gateway_active_requests` near capacity → scale or drain.
- `brain_compiler_lag` rising or `brain_events_unprocessed` > 0 sustained → worker stalled.
- `brain_events_failed_total` > 0 → dead-letters; page.
- vLLM `reachable == 0` while `ai_provider=vllm` → model host down (Gateway returns 503).
- `brain_mcp_failures_total` / `brain_agent_failures_total` climbing → investigate.

## Capacity (intended small team)

The system is sized for a **small studio team** (single-digit concurrent users).
The Gateway enforces a per-user token-bucket rate limit and a global concurrency
cap (excess → `429` with `Retry-After`), so a burst degrades gracefully rather
than overloading vLLM. For more headroom, raise the concurrency cap and vLLM
`--max-num-seqs`, and add GPU memory.

## Incidents — quick index

| Symptom | Action | Reference |
|---|---|---|
| vLLM down (`503`) | check the GPU host / restart vLLM; Gateway recovers automatically | RECOVERY |
| Compiler stale | `events/replay`, then `rebuild` the affected project | RECOVERY |
| Token compromised | `tokens/{id}/revoke` (immediate) | SECURITY |
| Bad data / corruption | restore from backup + full state rebuild | RECOVERY |
| Need to pause AI | `controls/drain` then `controls/model-requests {false}` | this doc |
