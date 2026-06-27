# The Collaborative Studio — Adding Collaborators Later

SUPERVOID runs as a [one-person studio](ONE_PERSON_STUDIO_WORKFLOW.md) out of the
box, but the data model and access control were built so a team can be added
**later, without rework**. Nothing you did solo needs to be redone — you simply
start inviting people onto the projects that already exist.

This guide covers that transition: the access model, how to bring collaborators
onto a story world or a work, and how the daily loop changes once you're more
than one.

---

## The access model (two layers)

1. **Global role** (`UserRole`) — account-level: `admin`, `editor`, `reviewer`,
   `production_manager`, `marketing`, `archive_reader`. Set when the account is
   created (`/api/users`, admin-only). This gates account-wide and
   admin-only actions.
2. **Project membership** (`ProjectMembership`) — per **StoryWorld** or per
   **Work**: a collaborator is granted a **project role** which maps to a set of
   **permission scopes**. This is what actually authorises work on a given
   project, checked on top of the global role (`admin` bypasses).

A solo studio simply has one `admin` who implicitly owns everything; adding
collaborators means creating accounts and granting them memberships.

### Project roles

`owner`, `director`, `editor`, `writer`, `artist`, `letterer`, `colourist`,
`animator`, `sound_designer`, `technician`, `production_manager`, `marketing`.

### Permission scopes

`view_project`, `edit_narrative`, `edit_visual_assets`, `manage_production`,
`upload_assets`, `review`, `approve`, `manage_collaborators`, `publish`,
`manage_rights`, `manage_marketing`. The policy service maps each project role to
the scopes it grants; project-scoped endpoints (and agents that declare
`required_permissions`) consult it via `policy.can(...)`.

### Membership lifecycle

`invited → active` (on accept), with `suspended` / `declined` / `revoked`. A
suspended membership can be reactivated. Every transition is written to a
**membership audit** trail.

---

## Step 1 — create accounts

As an `admin`, create an account per collaborator:

```
POST /api/users   { "email": …, "full_name": …, "role": "artist" }
```

Choose the global role to match what they do account-wide (most collaborators are
`editor` or a craft role; reserve `admin` for co-leads). Accounts can be
`deactivate`d / `activate`d and have passwords rotated.

## Step 2 — invite them onto a project

Grant a membership scoped to the **story world** (broad, all works within) or to a
single **work** (narrow):

```
POST /api/story-worlds/{world_id}/members   { "user_id": …, "role": "writer" }
POST /api/works/{work_id}/members           { "user_id": …, "role": "artist" }
```

The collaborator then **accepts** (`POST /api/memberships/{id}/accept`); they can
`decline`. Manage the membership over time with `suspend` / `reactivate` and
inspect history via `GET /api/memberships/{id}/audits`. Available project roles
are listed at `GET /api/collaboration/roles`.

Grant the **narrowest** scope that lets someone do their job: a colourist needs
`edit_visual_assets` / `upload_assets`, not `publish` or `manage_rights`.

## Step 3 — collaborators find their work

Each collaborator sees only their projects:

- `GET /api/me/projects` — the works/worlds they're an active member of.
- **Studio → My work** — their assigned/overdue/blocked tasks, the reviews
  requested of them, and their approval queue. The command centre is already
  per-user, so it "just works" for a team.

---

## How the daily loop changes

- **Assignment becomes real.** Assign production tasks to specific people; set
  reviewers. *My work* and the task saved-views (`my-assignments`, `overdue`,
  `blocked`, `awaiting-approval`) now partition the work across the team.
- **Approvals get teeth.** Request approval from a specific approver; gate
  publishing, rights changes and external integration runs behind someone with
  the right scope. Admin sign-off is still required for the highest-risk actions
  (publishing, external dispatch).
- **Agents respect project scope.** A supervised agent run checks the requester's
  permissions for the target work; proposals remain human-gated regardless of who
  ran them. Runs/proposals carry the `correlation_id` so activity is traceable.
- **The audit trail matters now.** Membership audits, publication history,
  production activity, rights status-history and integration run history give you
  a defensible record of who did what.

## Boundaries that still hold with a team

- **Public/private separation is unchanged.** Collaborators work on private
  records; only the curation hand-off + approval + publish path produces public
  projections, and only `publish`-scoped users (admin sign-off) can ship them.
- **Secrets stay out.** Integration credentials live only in the environment,
  resolved by reference; the API never returns secret values — adding people
  doesn't widen secret exposure.
- **Least privilege.** Because access is per-project and per-scope, onboarding a
  freelancer for one volume doesn't hand them the whole studio.

---

## Scaling further

The same primitives carry you up: more accounts, more memberships, narrower
scopes, and the division views (`Studio → divisions`) to watch publishing vs.
pictures vs. interactive vs. cross-media at a glance. When a division grows into
its own operation, see *future extraction* in [`ROADMAP.md`](ROADMAP.md) — the
bounded contexts (Pictures, the integration hub, LOGOSFORGE) are already drawn so
they can be split out without unpicking the rest.
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
