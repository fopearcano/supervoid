# SUPERVOID Brain — Security model

How the Brain stays private, authenticated, authorised and auditable. Every
control listed here is **implemented and tested** (not mocked) — see the
release-readiness section of [`ROADMAP.md`](./ROADMAP.md).

Related: [`IDENTITY.md`](./IDENTITY.md), [`MCP_SERVER.md`](./MCP_SERVER.md),
[`OBSERVABILITY.md`](./OBSERVABILITY.md), [`SUPERVOID_BRAIN_OPERATIONS.md`](./SUPERVOID_BRAIN_OPERATIONS.md).

## Trust boundaries

```
public internet ──▶ public reader only (read-only projection; NO Brain/MCP/private data)
member browser  ──▶ LibreChat ──▶ Brain Gateway (/brain/v1)  ──▶ vLLM (private)
                                  └▶ MCP server (/mcp) ──▶ governed SUPERVOID tools
vLLM is bound to loopback / the private network — never the public proxy.
```

The public surface (`/public`) is a curated, read-only projection. It can reach
**no** Brain, MCP, token, ops, tuning, or private API. This separation is enforced
at the router/auth layer and covered by tests (anonymous requests to every Brain
surface return `401/403`).

## 1. Identity mapping (real, not mocked)

A LibreChat identity is mapped to a SUPERVOID user **through an admin-managed,
active `LibreChatIdentityLink`** — there is no implicit/auto-provisioning.
Unlinked, pending, disabled or revoked identities are rejected. This is the
deliberate *simpler, robust first version* of the bridge; a future OIDC migration
is documented but not implemented (no insecure custom SSO). See `IDENTITY.md`.

## 2. Gateway authentication (Brain access tokens)

LibreChat authenticates to the Gateway with a **Brain access token**
(`Authorization: Bearer sk-brain-…`). Tokens are:

- generated with high entropy and **stored only as a SHA-256 hash** (the plaintext
  is shown once, at creation);
- **per-user and isolated** (one member cannot see/rotate/revoke another's);
- optionally project-restricted and time-limited;
- **revocable immediately** — a revoked or expired token is rejected (`401`) and the
  attempt is recorded as a `SecurityEvent`.

## 3. MCP authentication

The MCP server requires an internal **service token** plus a **signed user
context** (HMAC-SHA256 over the user id/email/role, keyed by the service token).
The declared LibreChat role is informational only — authorisation always re-runs
against the *mapped SUPERVOID user*. Missing/invalid credentials → `401`.

## 4. Permission enforcement (real, not mocked)

Every governed read/write re-runs the **policy service**: global role + active
project **membership** + ownership + the requested `PermissionScope`. Read tools
return only authorised records; an unauthorised call raises a `forbidden`
`MCPToolError` and records a `PROJECT_DENIED` security event. Admins are
studio-wide super-users; all other access is membership-scoped.

## 5. Action approval (real, not mocked)

The model never mutates the studio directly. A write-like MCP tool creates a
**gated `AgentActionProposal` (PENDING)**; a human with the `APPROVE` scope (admin
for critical/publishing/rights actions) approves it; execution is **audited**
(status → `EXECUTED`, `execution_result` recorded, structured `log_event`). Brain
agents are bounded (tool rounds/calls/time) and read-only unless explicitly
propose-capable.

## 6. Prompt-injection defence

Retrieved cold evidence and any untrusted document are wrapped in
`<<<UNTRUSTED_EVIDENCE … trust="unverified">>> … <<<END_UNTRUSTED_EVIDENCE>>>`
fences, with inner fence markers neutralised. The constitution instructs the model
to treat fenced content as DATA, never instructions. A malicious document cannot
escalate privileges, call forbidden tools, or exfiltrate secrets — verified by the
evaluation corpus's injection case.

## 7. Secret handling

Secrets (vLLM API key, service token, HF token, passwords) live in environment
variables, never in the database, prompts, responses, logs or backups. Structured
logs run through `redact_log` (token/secret/password/authorization/contract keys
redacted, long values capped). The fine-tuning sanitiser additionally strips
chain-of-thought and redacts any secret-shaped content before an example is stored.

## 8. Auditability

- `BrainEvent` — append-only, monotonic-sequence domain event log.
- `SecurityEvent` — append-only security/audit log (auth failures, denials, token
  & identity lifecycle, repeated-failure bursts → CRITICAL).
- `AgentActionProposal` / `AgentRun` / `AgentTrace` — every proposed/executed
  action and the reasoning trace behind it.
- Correlated `X-Request-ID` flows LibreChat → Gateway → model → MCP → agent →
  proposal across structured log lines.

## Threat model — covered vs out of scope

**Covered:** stolen/leaked Brain token (revoke), unauthorised project access
(membership/scope), privilege escalation via LibreChat-declared role (ignored),
prompt injection (fencing), secret leakage (redaction + env-only), public access to
private data (surface separation), runaway agents (bounds), tampered MCP user
context (HMAC).

**Out of scope (documented future work):** a full custom OIDC/OAuth provider;
network-level isolation beyond the loopback/private binding; HSM-backed key
storage; per-field encryption at rest. None of these are required for the intended
private small-team deployment, but they are the next hardening steps if the
deployment broadens.
