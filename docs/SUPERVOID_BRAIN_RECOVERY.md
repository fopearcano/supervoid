# SUPERVOID Brain — Disaster recovery

Backup, restore and recovery procedures for the SUPERVOID Brain. The design goal
is that **no Brain state is irreplaceable**: the compiled state is a deterministic
function of the durable records + the event log, so a full rebuild always recovers
it exactly.

Related: [`SUPERVOID_BRAIN_OPERATIONS.md`](./SUPERVOID_BRAIN_OPERATIONS.md),
[`MIGRATIONS.md`](./MIGRATIONS.md), [`SUPERVOID_BRAIN_SECURITY.md`](./SUPERVOID_BRAIN_SECURITY.md).

## What is durable vs derived

| Class | Examples | Recovery |
|---|---|---|
| **Durable source of truth** | works, manuscripts, decisions, memory, tokens, identity links, retrieval docs/chunks/embeddings, tuning examples/datasets/adapters, `BrainEvent` log | restore from backup |
| **Derived (recomputable)** | `ProjectBrainState` / `StudioBrainState` + revisions, prefix checkpoints, session warmth | rebuild deterministically from durable records |

## Backup & restore (real, not mocked)

The backup is **self-registering**: it serialises every table in
`SQLModel.metadata` plus the asset storage tree, so every Brain-era record type is
covered automatically (verified by a round-trip test seeding all 14 Brain record
types).

```bash
# Back up the database + stored assets to a directory (with a manifest).
python scripts/backup_restore.py backup --out /backups/2026-06-27

# Restore into a fresh database + storage path.
python scripts/backup_restore.py restore --in /backups/2026-06-27
# Restoring over a NON-empty database requires --reset (guards against accidents).
python scripts/backup_restore.py restore --in /backups/2026-06-27 --reset
```

The manifest records per-table row counts, the asset file count, and the Alembic
revision. Restore migrates the schema to head first, clears tables in reverse
dependency order, then reloads rows topologically (FK-safe), and copies assets
back byte-for-byte.

### Suggested schedule (small team)

- **Database backup:** nightly, plus before every deploy/migration. Keep ≥ 14 days.
- **Asset storage:** included in the same backup directory.
- **RPO:** ≤ 24h with nightly backups (tighten with more frequent runs / WAL
  archiving on PostgreSQL). **RTO:** minutes — restore + a full state rebuild.

## Rebuilding compiled state (the deterministic oracle)

If compiled state is lost, stale, or suspect, rebuild it from the event log:

```bash
python scripts/brain_compiler.py            # compile studio + projects to head
# or, per project, via the Ops control:
#   POST /api/brain/ops/projects/{work_id}/rebuild?full=true
```

A full rebuild yields the **same checksum** as the incremental path (a tested
guarantee), so it is always safe. After a rebuild, sessions re-warm naturally;
optionally `projects/{id}/prewarm`.

## Event-log recovery

- **Backlog / stalled worker:** restart `brain_outbox.py worker`; check
  `outbox_status`.
- **Dead-lettered (FAILED) events:** `python scripts/brain_outbox.py replay` (or the
  ops `events/replay` control), then recompile.
- **Missed changes:** `python scripts/brain_outbox.py reconcile` detects and
  re-flags drift, then the worker recompiles affected projects.

## Runbooks

### vLLM unavailable
The Gateway returns `503` (`provider_unavailable`); **no state is corrupted**.
1. Check the GPU host and `deploy/brain` containers; restart vLLM; run `vllm-smoke.sh`.
2. Confirm `GET /api/brain/ops/health` → vLLM `reachable`. The Gateway recovers
   automatically — no app restart needed.
3. If extended, set a `controls/maintenance` note so members see the status.

### LibreChat unavailable
The Brain is unaffected (LibreChat is the *client*). Members simply can't reach the
chat UI. Restart `deploy/brain/docker-compose.librechat.yml`. The optional LibreChat
health probe reports `unreachable` meanwhile; the Gateway keeps serving API clients.

### Stale compiler
`health = stale` (compiled state behind head). `events/replay` any dead-letters,
then `rebuild` the affected project(s). If the cause is a code change to the
compiler/state-builders, a `full` rebuild re-derives everything.

### Token compromise
`POST /api/brain/ops/tokens/{token_id}/revoke` (immediate). The use of a revoked
token is rejected and logged as a `SecurityEvent`. Re-issue a fresh token to the
member.

### Full database loss
1. Provision a clean database; `restore --in <latest backup>`.
2. `python scripts/brain_compiler.py` (full rebuild of compiled state).
3. Restart the outbox worker; verify ops health `healthy`.
4. Spot-check: a member chat turn scoped to a project returns state + citations.

## Migration safety

Schema changes ship as additive Alembic migrations with a **single head**
(verified by a test). `python scripts/manage_db.py check` asserts the migration
chain matches the models before deploy. Restore always migrates to head first, so a
backup taken at an older revision restores cleanly into the current schema.
