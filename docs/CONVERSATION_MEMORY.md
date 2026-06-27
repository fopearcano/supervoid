# Conversation memory & decision extraction (Prompt 13)

Controlled long-term memory for the SUPERVOID Brain. The Brain *proposes* durable
memory from conversations; it never silently rewrites the studio's truth. Canon,
rights and production status always come from structured domain records — never
from inferred memory.

## Flow

```
completed Brain response
  → gateway enqueues  conversation.turn_completed   (outbox, atomic with the turn)
  → consumer routes it to the analyzer              (NOT a recompile — a chat
                                                      turn never invalidates state)
  → analyzer extracts candidates (best-effort LLM)  (empty on dry-run / failure)
  → promotion rules decide, per candidate:
        canon/rights/production  → PROPOSED DecisionRecord (needs approval)
        decision                 → PROPOSED DecisionRecord
        member preference, eligible → auto-accepted VERIFIED memory
        everything else          → UNVERIFIED memory (Memory Review inbox)
```

Implementation: `app/services/brain/memory.py` (analyzer + rules),
`app/services/brain/memory_review.py` (inbox actions), gateway hook in
`app/routers/brain_gateway.py` (`_persist_assistant`), consumer dispatch in
`app/services/brain/consumer.py` (`_handle_event`).

## Memory kinds

`fact` · `preference` · `procedure` (procedural lesson) · `decision` ·
`commitment` · `unresolved_question` · `task_suggestion`
(`BrainMemoryKind`). Decisions are recorded as `DecisionRecord` rows, not memory.

## Rules

- **Casual conversation is archived, not promoted.** The turn's messages persist;
  chit-chat yields no candidates, so nothing durable is created.
- **Canon / rights / production come from structured records.** Any such claim
  (flagged by the model, or caught by a keyword guard as defence-in-depth)
  becomes a PROPOSED `DecisionRecord` (or `AgentActionProposal`) that needs
  approval — it is never written as a verified memory and never touches a canon
  column directly.
- **Preference auto-accept** happens only when ALL hold: same user
  (`scope=member`, `member_user_id == owner`), low risk, confidence ≥
  `brain_memory_auto_accept_min_confidence` (default 0.85), and it neither grants
  permissions nor alters canon. Otherwise it lands UNVERIFIED in the inbox.
- **Decisions have an explicit status:** `proposed → approved | rejected |
  superseded`.
- **Contradictions** with current *verified* state are detected (same scope +
  `topic_key`). A superseding preference retires the prior; other contradictions
  are flagged for review.
- **Never overwrite.** Edits, merges and supersessions create a NEW row that
  supersedes the old; the old row is retained as `superseded` with full
  provenance (source turn, original author, prior content). Status transitions
  (accept / reject / expire) mutate in place.
- **Rejected stays rejected.** A previously rejected topic is never
  auto-resurrected as verified, and rejected items are excluded from compiled
  state.

## Memory Review inbox

`GET /api/brain/memory/inbox` lists pending (UNVERIFIED) items the caller may
review, filtered to their access (no cross-member or cross-project leakage).
Actions (`POST /api/brain/memory/{id}/…`), all scope-gated:

| Action      | Effect                                                            |
|-------------|------------------------------------------------------------------|
| `accept`    | UNVERIFIED → VERIFIED; supersedes a same-topic verified prior.    |
| `reject`    | → REJECTED; excluded from state, never auto-resurfaced.           |
| `edit`      | New superseding row, original verification preserved; provenance. |
| `supersede` | New VERIFIED successor; original → SUPERSEDED.                    |
| `merge`     | New VERIFIED item superseding all sources (same scope + kind).    |
| `expire`    | → EXPIRED; drops out of compiled state.                           |

Scope gating: studio = admin; project = `APPROVE` on the Work/StoryWorld;
member / conversation = the owning user (admins bypass).

## Compiled state

Approved decisions (`status=approved`, not superseded) and verified memories
(`verification=verified`, scope-matched) flow into compiled state through the
deterministic builders (`state_builders._scoped_decisions` / `_scoped_memory` →
`canon_facts`, `unresolved_questions`, `next_priorities`, studio
`strategic_priorities`). `memory.*` events invalidate those sections so a newly
verified/retired project- or studio-scoped item surfaces on the next compile.

## Independent boundaries (safety)

Tests in `tests/test_brain_memory.py` enforce the four invariants:

1. a hallucinated fact cannot become canon (→ PROPOSED decision, never verified);
2. one member's preference cannot become another's (`member` scope is per-user);
3. a project-private memory cannot leak to another project (`work_id` /
   `story_world_id` scoping);
4. a rejected memory cannot reappear as verified.

Plus the auto-accept gate, contradiction + supersede, never-overwrite edits/merges,
the enqueue hook, and compiled-state inclusion/exclusion.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `brain_memory_analysis_enabled` | `true` | Master switch for the analysis job. |
| `brain_memory_analysis_model` | `None` | Override model for extraction (else `ai_model`). |
| `brain_memory_auto_accept_min_confidence` | `0.85` | Preference auto-accept threshold. |
| `brain_memory_max_candidates_per_turn` | `12` | Anti-spam cap per turn. |
| `brain_memory_recent_turns` | `6` | Recent turns fed to the extractor. |
