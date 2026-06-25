# SUPERVOID Studio System — Implementation Plan

> **Status:** planning only. This document does **not** change functional
> application code. It audits the current SUPERVOID Publishing repository
> against the target architecture of an **AI-native, one-person transmedia
> studio that can later support collaborators**, and lays out a
> dependency-ordered path to get there.

## 0. Baseline (verified before writing this plan)

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `pytest -q` | **189 passed**, 1 warning (pre-existing pydantic `StyleAnalysisResult` field-shadow notice) |
| Frontend typecheck + build | `npm run build` (`tsc -b && vite build`) | **clean** — 118 modules; admin (`App`) and public (`PublicViewerApp`) bundles code-split |
| Working tree | `git status` | clean, branch `claude/confident-albattani-fujtxk` |

Census: **27 models**, **21 private route groups (120 endpoints: 63 GET / 24 POST
/ 16 PATCH / 17 DELETE)** plus the public reader, **189 tests across 20 files**,
7 admin pages + 31 components, and a separate public-viewer SPA tree.

Guiding constraints (carried from the repo and the brief): local-first modular
monolith; FastAPI + SQLModel + Pydantic + React/TS/Tailwind conventions; the
private `/api` vs public `/public` + `/reader` separation; dark/archival/
cinematic design language; reuse existing models over duplication; no mandatory
cloud services; no hardcoded credentials/endpoints; every external/AI side
effect auditable and human-approved; additive, backward-compatible migrations.

---

## 1. Inventory of the existing system

### 1.1 Work & manuscript domain
- **Models:** `Work` (central catalogue entity — `work_type`, `WorkStatus`,
  genre, synopsis, internal_pitch, target_audience, language, word/page counts,
  `author_id`), `Manuscript` (text draft of a Work: `work_id`, `version`,
  `DraftStatus`, `submission_date`, file-metadata placeholder, `WorkflowStatus`),
  `Author` (name, pen name, contact, bio, notes), `Review` (verdict
  accept/reject/revise/hold + 5-score rubric + written report), `EditorialNote`,
  `WorkflowEvent` (status-transition audit trail).
- **Enums:** `WorkType` (book, graphic_novel, novella, anthology, art_book,
  essay, **adaptation_candidate**, other), `WorkStatus`, `WorkflowStatus`,
  `DraftStatus`, `ReviewVerdict`.
- **API:** `/api/works`, `/api/manuscripts`, `/api/authors`, `/api/reviews`,
  `/api/editorial-notes`, `/api/workflow-events` (+ `/api/workflow/transitions`).
- **Service:** `services/workflow.py` — deterministic `WorkflowStatus` state
  machine (`TRANSITIONS`, `can_transition`, `transition()` writes a
  `WorkflowEvent` atomically).

### 1.2 Graphic-novel production
- **Model:** `GraphicNovelProduction` (1:1 per Work) — per-stream `StreamStatus`
  for script → storyboard → character/environment design → page layout →
  lettering → colouring → final files, plus volume/issue numbers.
- **API:** `/api/graphic-novel-productions` (CRUD, filter by `work_id`).
- **Granularity:** board-level roll-up only. **No page/panel/scene/shot tree.**

### 1.3 Production items
- **Model:** `ProductionItem` (manuscript- and optionally work-scoped task) —
  `ProductionStage` (layout, cover_design, prepress, printing),
  `ProductionItemStatus` (pending/in_progress/blocked/done), `assignee_id`
  (User), `due_date`, notes. `ProductionRecord` (1:1 edition roll-up: ISBN,
  release date, per-format/stage `StreamStatus`).
- **API:** `/api/production-items` (filters incl. `due_before`/`due_after`),
  `/api/production-records`.
- **Limits:** flat tasks; **no dependencies, no approval gates, no
  cross-medium scope.**

### 1.4 Attachments & storage
- **Model:** `Attachment` (manuscript-scoped: `storage_key`, `sha256`,
  `content_type`, `size_bytes`, `AttachmentKind`, `placeholder:` convention,
  uploader).
- **Service:** `services/storage.py` — `LocalFileStorage` (write/read/delete by
  key under `settings.storage_path`; sha256 on write; placeholder keys bypass
  disk). Module-cached `get_storage()`.
- **API:** `/api/attachments`.
- **Limits:** single current file per record; **no version history, no
  provenance, manuscript-only scope.**

### 1.5 AI provider & feature layer
- **Providers:** `services/ai/providers/` — `LLMProvider` Protocol,
  `DryRunProvider` (deterministic, default, offline), `OpenAICompatibleProvider`
  (`httpx`), `registry.get_provider()` (config-selected, cached;
  `KNOWN_PROVIDERS`, `PROVIDER_DEFAULTS`).
- **Features:** `services/ai/features/` — summarize, style_analysis,
  editorial_suggestions, semantic_tags, consistency_check; compose a manuscript
  bundle, call the provider, parse typed results.
- **Audit:** `AIInsight` model persists each run (manuscript_id, `AIFeature`,
  provider, model, JSON payload). `/api/ai/...` POST endpoints + `/providers`.
- **Config:** `ai_provider` / `ai_base_url` / `ai_api_key` / `ai_model` /
  `ai_request_timeout`.
- **Scope today:** read-only editorial analyses on manuscripts. **No
  side-effecting/agentic actions, no tool calls, no run-approval queue.**

### 1.6 Knowledge graph
- **Models:** `KnowledgeEntity` (typed `EntityKind`: character, place, theme,
  motif, organization, work, person, period, other; unique `slug`),
  `KnowledgeRelationship` (typed `RelationshipKind` edges, weight),
  `ManuscriptEntityLink` (manuscript ↔ entity, `ManuscriptLinkRole`,
  relevance).
- **Service:** `services/knowledge.py` — `slugify`, BFS `neighborhood()`.
- **API:** `/api/knowledge` + manuscript-scoped entity-links router.
- **Strength:** this is already a serviceable **story-world canon graph** — the
  natural substrate for narrative IP worldbuilding (currently linked only to
  manuscripts).

### 1.7 Authentication & roles
- **Model:** `User` (email, hashed_password, `full_name`, `UserRole`,
  `is_active`).
- **Roles (global):** admin, editor, reviewer, production_manager, marketing,
  archive_reader.
- **Auth:** JWT (`auth/security.py`, `auth/dependencies.py`); deps `AUTHED`,
  `ADMIN_ONLY`, `require_role(*roles)`, `get_current_user`; `/api/auth/login`.
- **Limits:** roles are **global/studio-wide only — no per-project / per-IP
  scoping**, no external collaborators, no agent identities.

### 1.8 Rights & contracts
- **Models:** `Rights` (per-Work, per territory/language profile; `RightStatus`
  per right: print/ebook/audiobook/film/adaptation/merchandising; holder,
  expiration) and `Contract` (links `Author` + `Work`/`Manuscript`; advance,
  royalty, status, signed/expiration dates).
- **API:** `/api/rights`, `/api/contracts`.
- **Limits:** rights scope to a single Work (not IP/adaptation); contracts
  reference only `Author` (no licensees/distributors/vendors); **no contacts
  CRM, no distribution channels/releases.**

### 1.9 Public reader (transmedia output surface #1)
- **Models:** `PublishedWork → PublishedVolume → PublishedChapter →
  PublishedPage`, `PublicHotspot`, `PublicMediaAsset` (public projection only —
  no private fields by construction; `source_work_id` stored, never serialised).
- **API/UI:** read-only `/public/*` (GET-only, unauthenticated) + the
  `/reader/*` cinematic SPA (`frontend/src/public-viewer/`).
- **Bridge:** `publish_work_to_public_reader()` copies public metadata only.
- **Note:** the cleanest existing pattern for a *public distribution surface*;
  reusable for future media (e.g., a Movies viewer) via the content-agnostic
  `player/` module.

### 1.10 LOGOSFORGE & SUPERVOID Movies integration seams
- **Descriptors:** `app/integrations/` — typed, read-only `Integration`
  contracts (`base.py`: `IntegrationCapability`/`Status`/`Direction`),
  `LOGOSFORGE` (capabilities `import_manuscript`, `sync_knowledge_graph`,
  `return_editorial_notes` — status **planned**), `MOVIES`, `ECOSYSTEM` map.
- **Registry:** persisted `IntegrationPoint` model + `/api/integrations/points`
  CRUD (type/status), alongside read-only descriptor endpoints
  `/api/integrations`, `/ecosystem`, `/{key}`.
- **State:** seams declared; **no live/dry-run adapters wired yet** (LOGOSFORGE
  Phase 4 explicitly deferred).

---

## 2. Gap analysis (current → target)

Legend — **Reuse:** existing building block to extend. **Gap:** what's missing.

| # | Target capability | Current foundation (Reuse) | Gap |
| --- | --- | --- | --- |
| 1 | **Narrative IPs & story worlds** | Knowledge graph (`KnowledgeEntity`/`Relationship`), `Work` catalogue, `adaptation_candidate` work type | No top-level **IP/StoryWorld** entity grouping Works, canon, timeline; knowledge graph is manuscript-scoped, not world-scoped |
| 2 | **Transmedia adaptations** | `Work.work_type` (incl. adaptation_candidate), `Rights.adaptation_rights`, `MOVIES` seam | No explicit **Adaptation** linking a source IP/Work to a target-medium Work; no medium taxonomy beyond `WorkType` |
| 3 | **Page/panel/scene/shot production** | `GraphicNovelProduction` (stream board), `ProductionItem`, `PublishedPage` (public) | No private **granular production tree** (page→panel, scene→shot, sequence/beat); no per-unit status/assignee/asset binding |
| 4 | **Asset versioning & AI provenance** | `Attachment` + `LocalFileStorage` (sha256), `PublicMediaAsset`, `AIInsight` (audit shape) | No **Asset/AssetVersion** chain; no provenance (human vs agent vs tool, model, prompt, params, inputs) |
| 5 | **Collaborators & project-level permissions** | `User` + global `UserRole`, JWT/`require_role` | No **per-scope membership** (studio/IP/Work), no external collaborators, no agent principals |
| 6 | **Task dependencies & approvals** | `ProductionItem`, `WorkflowEvent` (audit), `Review` (verdicts) | No generic **Task** with dependency edges; no **Approval** gate model distinct from editorial reviews |
| 7 | **Supervised agents** | AI provider registry + dry-run default + `AIInsight` audit | No **Agent / AgentRun / AgentAction** with proposed→approved→applied lifecycle; no human-in-the-loop queue |
| 8 | **External tool adapters** | AI provider Protocol+registry (template), `IntegrationPoint` | No **ToolAdapter** layer (image-gen, TTS, video, publish) with dry-run-first, config-gated HTTP |
| 9 | **Rights, contacts & distribution** | `Rights`, `Contract`, `PublishingCalendarEvent` | Rights are Work-only; contracts reference only `Author`; no **Contact** CRM, no **DistributionChannel/Release** |
| 10 | **Studio command centre** | `/api/dashboard` + `Dashboard` page, `IndicatorCards`/`DeadlinesTable`/`RecentActivityFeed`, `AppShell` nav | No cross-IP **command centre**: agent-run approval queue, task/dependency board, asset/provenance browser, distribution calendar |

---

## 3. Dependency-ordered implementation plan

> The brief references "the following phases" without an explicit list, so the
> phases below are **derived from the §2 gap areas and ordered by hard
> dependency** (each phase only depends on those above it). Each is a single
> focused, independently shippable, test-backed increment.

**Phase A — Story Worlds & IP foundation** *(gap 1)*
Introduce `StoryWorld` (the IP/universe). Extend `Work` with nullable
`story_world_id`. Re-scope the knowledge graph to a world (add nullable
`story_world_id` to `KnowledgeEntity`; keep manuscript links). Endpoints
`/api/story-worlds`; admin "Story Worlds" view. *Depends on: nothing.*

**Phase B — Transmedia adaptations** *(gap 2)*
`Adaptation` linking a source (`story_world_id` and/or `work_id`) to a
target-medium `Work` + `AdaptationStatus`/`Medium`. Reuse `WorkType`/
`adaptation_candidate`. *Depends on: A.*

**Phase C — Granular production tree** *(gap 3)*
`ProductionUnit` (self-referential tree; `unit_type`: sequence/scene/shot/
spread/page/panel/beat; `work_id`, order, status, assignee). Keep
`GraphicNovelProduction` as the board roll-up. *Depends on: A (Works).*

**Phase D — Assets & AI provenance** *(gap 4)*
`Asset` + `AssetVersion` (version chain over `LocalFileStorage`) +
`AssetProvenance` (source human/agent/tool, model, prompt, params, input hash).
Bind assets to Work/ProductionUnit/StoryWorld. Keep `Attachment` (back-compat).
*Depends on: A, C.*

**Phase E — Collaborators & project permissions** *(gap 5)*
`Membership` (user × scope[studio|story_world|work] × `ProjectRole`). Add a
scope-aware permission dependency layer alongside global roles. *Depends on: A.*

**Phase F — Tasks, dependencies & approvals** *(gap 6)*
Generic `Task` (scope: work/unit/asset) + `TaskDependency` (DAG) + `Approval`
(decision gate, distinct from `Review`). `ProductionItem` retained / optionally
back-fed. *Depends on: C, E.*

**Phase G — Supervised agents** *(gap 7)*
`Agent` (config, model ref, tool allowlist, autonomy level), `AgentRun`
(proposed→awaiting_approval→approved→running→completed/failed/rejected,
auditable), `AgentAction` (per side-effect; **destructive/external actions
require human approval before apply**). Reuse AI registry + `AIInsight` audit
pattern. *Depends on: D (produces versioned assets w/ provenance), F
(approvals/tasks), E (who supervises).*

**Phase H — External tool adapters** *(gap 8)*
`services/tools/` adapter Protocol + registry (image-gen, TTS, video, publish),
**dry-run default, config-gated HTTP, no hardcoded endpoints** — mirrors the AI
provider pattern. Agents call tools only via this layer; every call recorded in
provenance. *Depends on: G.*

**Phase I — Rights, contacts & distribution** *(gap 9)*
`Contact` CRM (licensee/distributor/agent/vendor/external collaborator); extend
`Contract` to reference a `Contact` counterparty; extend `Rights` with nullable
`story_world_id`/`adaptation_id`; `DistributionChannel` + `Release` (reuse
`PublishingCalendarEvent` for dated milestones). *Depends on: A, B.*

**Phase J — Studio command centre** *(gap 10)*
Cross-IP `/studio` aggregation endpoints + a command-centre UI: agent-run
approval queue, task/dependency board, asset/provenance browser, distribution
calendar. Reuse dashboard components + `AppShell` nav. *Depends on: all above.*

Each phase ships with: additive models/migrations, schemas, routers, frontend
types + view, **backend tests + frontend typecheck/build green**, and doc
updates — matching the repo's established per-phase discipline.

---

## 4. Migration risk & backward compatibility

**Hard rule:** every change is **additive**. No existing field, enum value,
route, schema key, or test contract is renamed or removed in any phase.

### Must remain backward compatible
- **Public separation:** the `/public/*` API and `/reader/*` SPA must keep
  exposing *only* the `Published*` projection. New private studio data (IPs,
  agents, provenance, tasks, contacts) must **never** reach the public layer.
  Guarded by `test_public_reader.py` (no-private-leak assertions) — keep green.
- **All 120 `/api/*` endpoints** and their response shapes. New fields on
  existing read schemas are additive-only (consumers ignore extras; the
  frontend uses explicit interfaces).
- **Models extended (additive, nullable columns only):** `Work`
  (`story_world_id`), `KnowledgeEntity` (`story_world_id`), `Rights`
  (`story_world_id`/`adaptation_id`), `Contract` (`contact_id`). Do **not** add
  `NOT NULL` columns to populated tables.
- **Integration descriptor contract:** `test_integrations.py` asserts the
  LOGOSFORGE descriptor `status == "planned"`. Operational status for new
  adapters must be reported via *new* endpoints, not by mutating descriptors.
- **Workflow state machine:** `test_workflow_service.py` pins the `TRANSITIONS`
  graph. The new generic `Task`/`Approval` system must sit *beside* it, not
  rewrite manuscript workflow.
- **Auth/roles:** `UserRole` and `require_role`/`AUTHED`/`ADMIN_ONLY` semantics
  must keep working (`test_auth.py`, `test_routers.py`). `Membership` adds
  scoped permission *on top of* global roles, not instead of them.
- **`Attachment`** stays the manuscript-file model. New `Asset`/`AssetVersion`
  is a parallel studio-asset system; do not repurpose `Attachment`'s table.
- **Tests to watch:** `test_models.py`, `test_routers.py`, `test_domain_core.py`,
  `test_public_reader.py`, `test_integrations.py`, `test_workflow*.py`,
  `test_validation.py`, `test_pagination_sorting.py`.

### Schema-migration mechanics (the real risk)
The app uses `SQLModel.metadata.create_all()` (no Alembic). `create_all` creates
**missing tables** but does **not** alter existing tables. Therefore:
- **New tables** (the bulk of this plan) are zero-risk: they auto-create on fresh
  DBs and in tests (which build the schema per-run).
- **New columns on existing tables** (the few extends above) will **not** appear
  on a pre-existing SQLite DB without a migration. Mitigation: (a) prefer new
  tables/association tables over column-adds where reasonable; (b) keep adds
  nullable; (c) **introduce Alembic as the first step of Phase A** (or as a
  dedicated hardening pre-phase) so column-adds are applied non-destructively in
  dev/prod. Tests and fresh dev DBs are unaffected either way.

---

## 5. Target architecture (ASCII)

```
                         SUPERVOID ENTANGLED (ecosystem)
                                     │
        ┌────────────────────────────┴───────────────────────────────┐
        │            SUPERVOID Studio (AI-native, private /api)         │
        │                                                              │
        │   StoryWorld (IP / universe)  ──*──  Adaptation              │
        │      │  └─ canon: KnowledgeEntity/Relationship (world-scoped)│
        │      *                                                        │
        │    Work (book · graphic_novel · film · game · audio …)        │
        │      │                                                        │
        │      ├─ Manuscript (text drafts, WorkflowStatus)             │
        │      ├─ GraphicNovelProduction (board roll-up)               │
        │      └─ ProductionUnit tree                                  │
        │            sequence → scene → shot                           │
        │            volume   → spread → page → panel                  │
        │                 │                                            │
        │                 └─ Asset ──* AssetVersion ──1 Provenance     │
        │                        (human | agent | tool · model·prompt) │
        │                                ▲                             │
        │   Task (DAG: TaskDependency) ──┘   Approval (human gate)     │
        │      ▲                                   ▲                   │
        │      │            ┌── proposes ──────────┘                   │
        │   Agent ──* AgentRun ──* AgentAction ── apply (post-approval)│
        │      │                         │                            │
        │      └── calls ──> ToolAdapter (image/TTS/video/publish)     │
        │                     dry-run default · config-gated HTTP       │
        │                                                              │
        │   Membership (user × scope × ProjectRole)  ── permissions    │
        │   Rights · Contract · Contact(CRM) · DistributionChannel/Release
        │   AIInsight (audit)        IntegrationPoint (LOGOSFORGE/Movies)
        │                                                              │
        │   ── Studio Command Centre (cross-IP UI + /studio aggregates)│
        └───────────────────────────┬──────────────────────────────────┘
                                     │ publish_*  (public-safe projection only)
                       ┌─────────────┴─────────────┐
                       │  Public projection (/public, GET-only)
                       │  PublishedWork→Volume→Chapter→Page, Hotspot, Media
                       └─────────────┬─────────────┘
                                     │
                          /reader/*  cinematic SPA  (+ future media viewers)
```

---

## 6. Proposed models, tables, endpoints & frontend (EXTEND vs NEW)

> **EXTEND** = add nullable columns/relationships to an existing model (no
> duplication). **NEW** = a new table/module. Phase letters map to §3.

### Backend models / tables

| Model | Kind | Phase | Notes |
| --- | --- | --- | --- |
| `StoryWorld` | **NEW** (`story_worlds`) | A | IP/universe: title, slug, logline, bible/summary, status, owner |
| `Work.story_world_id` | **EXTEND** `works` | A | nullable FK; Works belong to an IP |
| `KnowledgeEntity.story_world_id` | **EXTEND** | A | world-scope canon; keep manuscript links |
| `Adaptation` | **NEW** (`adaptations`) | B | source (story_world/work) → target Work; `Medium`, `AdaptationStatus` |
| `Medium` / `AdaptationStatus` enums | **NEW** | B | medium taxonomy beyond `WorkType` |
| `ProductionUnit` | **NEW** (`production_units`) | C | self-FK tree; `ProductionUnitType` (sequence/scene/shot/spread/page/panel/beat); status, assignee, order |
| `GraphicNovelProduction` | **EXTEND/keep** | C | remains the board roll-up; units add granularity |
| `Asset` | **NEW** (`assets`) | D | studio asset; bound to work/unit/story_world; `AssetType` |
| `AssetVersion` | **NEW** (`asset_versions`) | D | version chain (`supersedes_id`, storage_key, sha256, created_by) |
| `AssetProvenance` | **NEW** (`asset_provenance`) | D | source kind (human/agent/tool), `agent_run_id`, tool, model, prompt, params(JSON), input hash |
| `Attachment` | **keep** | D | manuscript files stay; not repurposed |
| `Membership` | **NEW** (`memberships`) | E | user × scope(studio/story_world/work) × `ProjectRole` |
| `ProjectRole` enum | **NEW** | E | owner/collaborator/reviewer/viewer/agent_supervisor |
| `Task` | **NEW** (`tasks`) | F | generic, cross-medium: scope, assignee, status, due |
| `TaskDependency` | **NEW** (`task_dependencies`) | F | DAG edges (task_id, depends_on_id) |
| `Approval` | **NEW** (`approvals`) | F | decision gate on task/asset_version/agent_action |
| `ProductionItem` | **keep** | F | production-stage tasks retained for back-compat |
| `Agent` | **NEW** (`agents`) | G | config, provider/model ref, tool allowlist, autonomy level, enabled |
| `AgentRun` | **NEW** (`agent_runs`) | G | auditable lifecycle; requested_by/approved_by; reuse `AIInsight` audit shape |
| `AgentAction` | **NEW** (`agent_actions`) | G | per side-effect; proposed→approved→applied/rejected; result ref |
| `ToolAdapter` (registry config) | **NEW** `services/tools/` + optional `tool_adapters` table | H | dry-run default; config-gated HTTP; mirrors AI registry |
| `Contact` | **NEW** (`contacts`) | I | CRM: licensee/distributor/agent/vendor/external collaborator |
| `Contract.contact_id` | **EXTEND** `contracts` | I | counterparty beyond `Author` (nullable) |
| `Rights.story_world_id` / `.adaptation_id` | **EXTEND** `rights` | I | IP/adaptation-level rights (nullable) |
| `DistributionChannel` | **NEW** (`distribution_channels`) | I | store/festival/streamer/web |
| `Release` | **NEW** (`releases`) | I | work/adaptation × channel × date; reuse `PublishingCalendarEvent` for milestones |

### Backend endpoints (new route groups, all under `/api`, role/scope-gated)

| Route group | Phase |
| --- | --- |
| `/api/story-worlds` (+ `/{id}/canon`, `/{id}/works`) | A |
| `/api/adaptations` | B |
| `/api/production-units` (tree: `?parent_id`, `?work_id`) | C |
| `/api/assets`, `/api/assets/{id}/versions`, `/api/asset-versions/{id}` (+ upload reusing storage) | D |
| `/api/memberships` (+ scope-aware `me/permissions`) | E |
| `/api/tasks`, `/api/tasks/{id}/dependencies`, `/api/approvals` | F |
| `/api/agents`, `/api/agent-runs` (+ `/{id}/approve`,`/reject`), `/api/agent-actions/{id}/apply` | G |
| `/api/tools` (status/registry, dry-run) | H |
| `/api/contacts`, `/api/distribution-channels`, `/api/releases` | I |
| `/api/studio/overview`, `/api/studio/approvals`, `/api/studio/activity` (or extend `/api/dashboard`) | J |

### Frontend sections (admin SPA — extend `AppShell` nav + `App.tsx` views)

| Section | Phase | Reuse |
| --- | --- | --- |
| **Story Worlds** (IP list + world bible + canon graph) | A | knowledge graph components, `SectionHeading`/`Eyebrow` |
| **Adaptations** (per-world adaptation map) | B | `WorkTypeTag`, status badges |
| **Production tree** (page/panel · scene/shot board) | C | `ProductionBoard`, `StreamStatusBadge` |
| **Assets & provenance** (version timeline, provenance inspector) | D | `AttachmentsPanel` patterns, media viewers |
| **Collaborators** (members & scoped roles) | E | `AuthContext`, role UI |
| **Tasks** (dependency board + approvals) | F | `DeadlinesTable`, `StatusDot`, `TransitionControl` |
| **Agents** (config + **run approval queue**) | G | `AIPanel`, dark dialog patterns |
| **Tools** (adapter status, dry-run badges) | H | `StatusBadge` |
| **Contacts / Distribution** (CRM + release calendar) | I | `ReleaseCalendar`, `ContractsPanel` |
| **Studio Command Centre** (`/studio` cross-IP cockpit) | J | `IndicatorCards`, `RecentActivityFeed`, `UpcomingReleasesTable` |

### Cross-cutting principles (apply to every phase)
- **AI-native & auditable:** every agent/tool action persists provenance and an
  `AgentRun`/`AgentAction` audit trail; reuse the `AIInsight` + dry-run pattern.
- **Human-in-the-loop:** destructive or external side effects (apply an
  AgentAction, call a live tool, publish) require an explicit `Approval` by a
  user with the right scoped role — never auto-applied.
- **Local-first:** all new adapters default to a dry-run/offline mode; live
  modes are config-gated with no hardcoded endpoints or credentials.
- **Additive & reversible:** new tables first; nullable column extends; Alembic
  introduced before any column-add reaches a persistent DB.

---

*End of plan. No application code was modified to produce this document.*
