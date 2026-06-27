# Observability & operational controls (Prompt 16)

An internal **Brain Operations** surface: a live view of the Brain's health, a
Prometheus exposition, correlated structured logs, and operator controls.
Everything here is **admin-only** — GPU and internal topology are never exposed on
a public endpoint.

## What it shows (`GET /api/brain/ops/status`)

| Group | Metrics |
|---|---|
| vLLM / model | reachability, loaded model, context limit, latency; GPU utilisation *when available* (the provider `/health` does not expose it) |
| Gateway | active requests, queue depth, capacity, request/rejected totals, control flags |
| Compiler / outbox | head sequence, compiler lag, unprocessed BrainEvents, failed events, stale projects, studio state version |
| State versions | studio + per-project versions / lag / stale |
| Sessions | total, warmth distribution, distinct prefix hashes; active conversations |
| Usage / latency | prompt-token + completion-token totals, TTFT (avg/p95), total latency (avg/p95) |
| Agents / MCP / proposals | agent failures, MCP failures, pending action proposals |
| LibreChat | health (probed when `librechat_health_url` is set, else "unknown") |

Sources are existing data — `compiler_health` / `outbox_status`, `BrainSession`,
`BrainMessage` (tokens + `session_metrics`), `AgentRun`, `AgentActionProposal`,
`SecurityEvent`, the provider `health()`, and the in-process runtime gauge.

## Prometheus (`GET /api/brain/ops/metrics`)

A Prometheus text-exposition of the numeric metrics
(`brain_gateway_active_requests`, `brain_compiler_lag`, `brain_events_unprocessed`,
`brain_prompt_tokens_total`, `brain_ttft_ms_avg`, `brain_agent_failures_total`,
`brain_mcp_failures_total`, `brain_pending_proposals`, …). Admin-only — scrape it
over the internal network, not the public ingress.

## Health states

`healthy` · `degraded` · `unavailable` · `stale` · `maintenance`, computed per
component (vLLM, gateway, MCP, compiler) and rolled up to an overall state.
Precedence for the overall: **unavailable → maintenance → degraded → stale →
healthy**. A live provider that is unreachable is `unavailable`; an operator flag
makes a component `maintenance`; dead-lettered events make the compiler
`degraded`; lag / stale projects make it `stale`.

## Correlated structured logs

A single correlation id (the `X-Request-ID`, honoured or minted by the request-id
middleware) flows across the chain and is stamped on every log line (`rid=…`):

```
LibreChat request → Brain Gateway → model request → MCP tool call → agent run → proposal execution
```

It is persisted as `BrainEvent.correlation_id`, `BrainMessage.request_id` and
`AgentRun.correlation_id`, and emitted as structured boundary events via
`log_event(...)`: `model.request`, `mcp.tool_call`, `agent.run`,
`proposal.execute`. Boundary logs carry only ids, counts and timings — never
prompt or response bodies.

## Redaction

`redact_log()` strips any field keyed as a token, authorization header, password,
credential/api-key, **private prompt**, or **contract/terms** content, and caps
long strings. Boundary logs never include prompt/response text in the first place;
the redactor is defence-in-depth for any structured field.

## Operator controls (admin)

| Control | Endpoint | Effect |
|---|---|---|
| Disable new model requests | `POST /api/brain/ops/controls/model-requests {enabled}` | Gateway returns 503 for NEW requests; in-flight unaffected |
| Drain | `POST /api/brain/ops/controls/drain {draining}` | Reject new requests while in-flight finish |
| Disable MCP | `POST /api/brain/ops/controls/mcp {enabled}` | MCP rejects all requests (maintenance) |
| Maintenance note | `POST /api/brain/ops/controls/maintenance {note}` | Shown in the Ops view |
| Rebuild project state | `POST /api/brain/ops/projects/{work_id}/rebuild` | Re-compile a Work's state |
| Replay failed events | `POST /api/brain/ops/events/replay {event_ids?}` | Re-queue dead-lettered BrainEvents |
| Mark project cold | `POST /api/brain/ops/projects/{work_id}/cold` | Set the project's sessions COLD (cache evicted) |
| Prewarm project | `POST /api/brain/ops/projects/{work_id}/prewarm` | Best-effort prefix prewarm (no-op under dry-run) |
| Revoke a Brain token | `POST /api/brain/ops/tokens/{token_id}/revoke` | Admin revoke of ANY token (immediate) |

Control flags are **per process** (per uvicorn worker), like the gateway's
rate/concurrency limiters; a shared control plane is a later concern. Each control
is logged as an `ops.control` audit line; token revoke also records a
`token_revoked` security event.

## Not public

The Ops router (`/api/brain/ops/*`) is gated to admins. The Brain Gateway
(`/brain/v1`, `/brain/health`) and MCP (`/mcp`) are not reverse-proxied to the
internet (see `LIBRECHAT_INTEGRATION.md`), and the public reverse proxy returns
404 for them. GPU / internal topology is never serialized to any public endpoint.
