# The One-Person Studio — Daily Workflow

SUPERVOID is built to be run, end to end, by a single person — writer, artist,
producer, and publisher at once — and to scale to a team later without rework
(see [`COLLABORATIVE_STUDIO_WORKFLOW.md`](COLLABORATIVE_STUDIO_WORKFLOW.md)).

This guide describes the *daily* loop: where to start, what to do in order, and
which surfaces matter when you wear every hat. It assumes the seed data or your
own first StoryWorld already exists.

Progressive disclosure is the governing idea: the **Studio** command centre puts
the few things that need you today up front, and every deeper surface (rights,
CRM, editions, the agent inbox) is one click away but never in your face.

---

## 0. Sign in

- Log in; your role is `admin` for a solo studio (full access).
- The app opens on **Studio** (the command centre). Everything below hangs off it.

## 1. Start at the command centre (`Studio`)

The command centre is read-only aggregation across every domain — it never holds
its own data, so it is always a faithful mirror of the system.

Check, in order:

1. **Studio overview** — story worlds, works (by division & status), graphic-novel
   completion %, upcoming releases. Your "is anything on fire / shipping soon?".
2. **My work** — tasks assigned to you (or unassigned), what's **overdue**, what's
   **blocked** (explicit or by unmet dependencies), reviews requested of you, and
   your approval queue. This is your to-do list for the day.
3. **Agent inbox** — open findings by severity, **pending proposals** awaiting
   your approval, failed runs, recent completed analyses.
4. **Asset health** — placeholder versions with no file yet, versions missing
   provenance, **expiring/expired licences**, unapproved versions, public works
   missing credits.
5. **Business alerts** — rights expiries, contract deadlines, distribution
   readiness, contact follow-ups, upcoming releases.

If all five are quiet, you're free to make. If not, clear the blocking items
first — they're ordered by urgency.

## 2. Develop the narrative

- **Story Worlds** → create/maintain the world, series, and canon.
- Create a **Work** in the world and pick its `primary_division`
  (publishing / pictures / interactive / cross-media) and `primary_medium`.
- Add a **Manuscript** (the text draft) under the Work; move it through its
  editorial workflow (`transition`) as it matures.

> Open a Work's **command page** (Studio → a work) for a single-screen view of
> that one project across every domain: narrative, production, assets,
> collaborators, rights, editions, adaptations, public release, agent history.

## 3. Produce

- **GN Studio** — build the graphic-novel hierarchy (volume → chapter → sequence
  → page → panel → element). Use page `validate` and the production `readiness`
  check to see what's missing before you call a page done.
- **Pictures** — for screen work, build the project (units → sequences → scenes →
  shots), promoting from an adaptation dossier where relevant.
- **Tasks** — track the actual work as production tasks: set due dates, mark
  blockers, transition status. The command centre's *My work* reads straight from
  here, so keeping tasks honest keeps the dashboard honest.
- Approvals: gate anything that needs a deliberate sign-off with an approval
  request (in a solo studio you both request and approve — the record still
  matters for your own audit trail).

## 4. Manage assets, provenance & licences

- **Assets** — create an asset per deliverable, then upload **versions** (checksum
  deduped). Promote/roll back the current version as you iterate.
- Record **provenance** on each version (human-made, AI-assisted, mixed — with the
  details). This is what lets you publish with a clear conscience and a clear
  paper trail.
- Record a **licence** per source asset and keep it `approved` and current —
  asset health and the curation validator both depend on it.

## 5. Let the agents help (supervised)

- **Agents** — run a read-only analysis (e.g. manuscript consistency) any time;
  findings land in the agent inbox immediately.
- When an agent proposes a change, it arrives as a **gated proposal**. Nothing
  mutates until you approve it; destructive / publishing / rights / external
  proposals always require an explicit (admin) approval. Approve → execute, or
  reject with a reason. Every run is traceable by its `correlation_id`.

## 6. Publish to the public reader (curation)

The public Graphic Novel Webviewer is a *separate, published projection* — private
files are never exposed automatically. To publish:

1. **Curation** → create a `PublishedWork` (or `from-work`), build its public
   volumes/chapters/pages, and hand off page derivatives explicitly
   (`handoff/page`) — you choose the public image; the private source stays put.
2. Add panels for **cinematic mode** and public media / hotspots as desired.
3. `validate` (credits, licences, provenance, structure) → fix any blocking
   errors → `request-approval` → `approve` → `publish`. `preview` shows the exact
   public API representation before you commit.
4. `unpublish` later removes the public projection **without** touching the
   private source; the publication history is preserved.

## 7. Run the business

- **Rights** — maintain rights profiles, windows, options, chain-of-title and
  evidence; watch `warnings` for expiries.
- **Contacts** (CRM) — organizations, contacts, interactions, opportunities.
  Nothing is sent automatically; follow-ups surface in business alerts for *you*
  to action.
- **Editions** — define editions and generate **export packages** (ONIX / KDP /
  Ingram / web / press-kit / ARC). These produce validated packages and
  checklists for you to upload by hand — they do not upload for you.

## 8. End of day — protect your work

Everything lives in the local SQLite database and the `storage/` tree. Back both
up together:

```bash
cd backend
python scripts/backup_restore.py backup --out ../backups/$(date +%Y-%m-%d)
```

This dumps every record (including all the new domains) plus the asset files. To
restore into a fresh database + storage path:

```bash
python scripts/backup_restore.py restore --in ../backups/<date>
```

(The container is ephemeral in hosted runs — commit and push anything you want to
keep, and keep backups off-box.)

---

## The loop, in one line

**Studio (triage) → make (narrative / production / assets) → supervise agents →
curate & publish → run the business → back up.** Repeat. Add collaborators only
when you actually need them — the system is already shaped for it.
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
