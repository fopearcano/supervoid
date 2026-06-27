# Identity linking & member administration (Prompt 15)

The operational identity bridge between SUPERVOID and LibreChat. This is the
**simpler, robust first version** — an admin-managed link table, hardened token
and MCP mapping, and a security-event trail. It is deliberately **not** a custom
OAuth/OIDC provider; see "Future: OIDC migration" below for the safe upgrade path.

## Components

### Identity links (`LibreChatIdentityLink`)
An admin links a SUPERVOID user to a LibreChat identity:

* SUPERVOID user, LibreChat user id, LibreChat email,
* `status` (`pending → active → disabled / revoked`), `linked_at`, `verified_at`,
* who linked / disabled it, and a note.

One link per SUPERVOID user (re-linking upserts). **Only an `active` (verified)
link may authenticate the Brain via MCP.** Admin workflow: `/api/identity-links`
(list / create / verify / disable / edit). Member self-service: a member sees
their own link status at `/api/identity-links/me` (and in the **Brain Account**
page).

### Brain access tokens (`BrainAccessToken`)
Per-user Gateway tokens: **create**, name, **reveal once** (the plaintext secret
is shown only at create/rotate), **revoke**, **rotate**, **expiry**, **project
restrictions**, **last use**, and an **audit trail** (`token_created` /
`token_rotated` / `token_revoked` security events). Only the SHA-256 hash is
stored; the gateway looks a token up by hash and rejects revoked/expired tokens
and disabled owners.

### MCP identity mapping
Every MCP request must present the internal **service credential** AND a
**signed user-context**. The server then:

1. resolves the LibreChat identity to a SUPERVOID user **through an active
   identity link** (no implicit provisioning),
2. **rejects unlinked** LibreChat identities,
3. **rejects disabled** SUPERVOID users (`is_active = false`),
4. re-runs the policy service for every tool (the LibreChat-declared role is
   never trusted for access).

Set `mcp_require_identity_link = false` only for a controlled migration window.

### LibreChat registration
Self-registration is **disabled** for arbitrary visitors:
`ALLOW_REGISTRATION` defaults to `false` and `ALLOW_SOCIAL_LOGIN` /
`ALLOW_SOCIAL_REGISTRATION` are hard-`false`
(`deploy/brain/docker-compose.librechat.yml`). Members are provisioned by an
admin and then linked.

## Security events (`SecurityEvent`)
Append-only log (`/api/security-events`, admin) of:

| Event | When |
|---|---|
| `service_auth_failed` | bad/missing MCP service credential |
| `invalid_signature` | bad user-context HMAC |
| `mapping_failed` | no SUPERVOID user for the email |
| `unlinked_user` | no active identity link |
| `disabled_member` | a deactivated SUPERVOID user attempted access |
| `revoked_token_use` / `expired_token_use` | a dead Gateway token was presented |
| `project_denied` | a tool call denied by the policy service |
| `repeated_failures` | ≥ threshold failures from one principal within the window (CRITICAL) |
| `token_*` / `identity_*` | benign audit lifecycle |

Failure events are committed even when the request 401s or its tool call rolls
back, so the trail is never lost. Repeated-failure detection
(`security_repeated_failure_threshold` / `_window_seconds`) raises a single
CRITICAL alert per principal per window.

## UI
* **Identity & Access** (admin): link members, verify/disable links, and review
  recent security events.
* **Brain Account** (member): self-service link status + the Gateway endpoint +
  a pointer to **Brain Tokens**.

## Future: OIDC migration (not implemented now)

Hand-rolling an OAuth/OIDC provider or custom SSO is a security liability, so we
do **not** build one here. When a real IdP is warranted, migrate like this —
without changing the authorization model:

1. **Add an external IdP** (Keycloak / Auth0 / Authentik / Google Workspace …).
   LibreChat already supports OpenID Connect; point it at the IdP and keep
   `ALLOW_REGISTRATION=false` (provisioning stays admin-gated, now via the IdP).
2. **Keep the link table as the bridge.** Store the IdP `sub` (subject) on
   `LibreChatIdentityLink` alongside the email; resolution becomes
   `IdP sub → identity link → SUPERVOID user`, removing reliance on email.
3. **Validate IdP-issued tokens** at the Gateway/MCP boundary using the IdP's
   published JWKS (standard, audited libraries) instead of the signed-header
   shim — the shim is the interim bridge, not a bespoke token format to keep.
4. **Map IdP groups → SUPERVOID roles/memberships** explicitly (never trust IdP
   claims for authorization directly; the policy service stays authoritative).
5. **Cut over per environment** behind `mcp_require_identity_link`, retire the
   service-token + HMAC shim once OIDC validation is proven, and keep the
   security-event log throughout.

The current design intentionally minimises what must change: the policy service,
the identity-link bridge, the token model and the security-event log all carry
forward unchanged.
