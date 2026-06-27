# Evaluation harness (Prompt 17)

A SUPERVOID-specific evaluation system that must be run **before any
fine-tuning**. It scores models on real SUPERVOID tasks — not generic
benchmarks — and only recommends a production default model from real results
against a **live** provider.

The harness drives the **actual governed surfaces** (MCP tool handlers, the
retrieval service, the policy service, the compiled state) with a per-case
principal, so the deterministic checks reflect real system behaviour, not just
model text.

## Run it

From `backend/` with the virtualenv active:

```bash
python scripts/run_eval.py list                 # print the corpus, no run
python scripts/run_eval.py run                  # run vs the CONFIGURED provider
python scripts/run_eval.py run --out-dir eval-reports
python scripts/run_eval.py run --json r.json --md r.md
```

`run` builds a **throwaway in-memory database** seeded by the eval world builder
— it never reads or writes the real SUPERVOID database — runs the versioned
corpus, and writes a JSON + markdown report. The process exits non-zero if any
deterministic check regresses, so CI can gate on it.

## Compare candidates through configuration, not code

The harness runs against whatever provider is configured:

| `ai_provider` | Provider | Live? | Recommends a default model? |
|---|---|---|---|
| `dry_run` (default) | offline canned responses | no | **no** |
| `vllm` | the configured vLLM (`ai_base_url` / `ai_model`) | yes | yes, if checks pass |

To compare two candidate models you change **configuration** (`ai_model` /
`ai_base_url`) and re-run — never code. Each run is tagged with the provider and
model in its report filename and body.

## The corpus (`eval-v1`)

Versioned by `CORPUS_VERSION` and stored as data in `app/eval/corpus.py` (15
cases, one per required scenario):

| Case | Scenario |
|---|---|
| `prod-priorities-1` | identify today's production priorities |
| `canon-1` | answer a canon question |
| `explain-decision-1` | explain an old decision with evidence |
| `blocker-1` | locate a blocker |
| `compare-1` | compare a graphic-novel panel and a shot |
| `rights-conflict-1` | detect a rights conflict |
| `provenance-1` | find an asset with incomplete provenance |
| `permissions-1` | respect project permissions |
| `refuse-1` | refuse unauthorised access |
| `task-proposal-1` | create a task proposal |
| `approval-publication-1` | require approval for publication |
| `fact-vs-memory-1` | distinguish verified fact from memory |
| `mcp-tool-1` | use the correct MCP tool |
| `avoid-retrieval-1` | avoid unnecessary retrieval |
| `injection-1` | survive a malicious-document prompt injection |

Every case records: **input**, **user identity**, **project**, **expected state
version**, **expected tools**, **forbidden tools**, **expected evidence**,
**expected approval behaviour**, and a **scoring rubric**.

The seed world (`app/eval/world.py`) is a small fixed studio: members at every
access level (admin, project owner, editor, outsider), a canon work with a
logline in compiled state, an approved decision with rationale, a blocked task, a
rights conflict (expired clearance), an asset with incomplete provenance, a
verified canon fact vs an unverified memory, and a **malicious memo** in the cold
index for the injection case.

## Deterministic checks (primary metric)

Each case is scored on the dimensions its rubric opts into — all deterministic,
all checked against what the real surfaces did:

| Dimension | Checks |
|---|---|
| `schema` | the tool returned a valid JSON-able structure |
| `tools` | the expected tool(s) were used and no forbidden tool was attempted |
| `permissions` | the surface refused / admitted exactly as expected |
| `citations` | the expected evidence source types were returned |
| `approval` | a write became a gated proposal (no direct mutation); a critical action additionally needed `APPROVE` |
| `correctness` | the task-specific ground truth (e.g. a blocker exists, provenance is incomplete, the injection is fenced) |

A case **passes** only when every dimension it opts into passes.

## Model-graded quality (secondary metric only)

Optional model-graded quality is wired as a `model_grade` slot on each result.
It is a **secondary** signal and **never gates** a case — deterministic checks
are the contract.

## Benchmark metrics

Every case also records, from a real assemble + provider turn: **latency**,
**prompt / completion tokens**, **retrieval count**, **stable-prefix size**, and
**cache eligibility** (whether the assembled prefix is stable across
re-assembly). A benchmark failure never affects the deterministic checks.

## The report and the recommendation

`build_report()` produces the JSON; `to_markdown()` renders it. The model
recommendation is **strictly gated on liveness**:

- **Dry-run** → recommends *no* model, with an explicit message that the run
  validates the harness and the governed surfaces but is **not** a basis for a
  model decision. Re-run against the configured vLLM to choose a default.
- **Live (vLLM)** → recommends the configured model **only** if the deterministic
  pass rate and correctness are at/above threshold (≥ 0.9). Otherwise it
  withholds the recommendation and points at the failing dimensions.

This enforces the rule that the default model is recommended **only after real
SUPERVOID task results**.

## Layout

```
app/eval/
  corpus.py    # versioned cases (data) + dimensions + EvalKind
  world.py     # the deterministic seed studio (+ malicious memo)
  runners.py   # per-kind exercisers that drive the real surfaces + benchmark
  scoring.py   # deterministic dimension scoring
  harness.py   # orchestrator: run the corpus vs a provider, aggregate
  report.py    # report builder + liveness-gated recommendation + markdown
scripts/run_eval.py   # CLI (throwaway DB, configured provider, JSON+md report)
tests/test_eval.py    # harness tests
```
