# SUPERVOID Brain — Model evaluation & selection

How a model (or a fine-tuned adapter) is chosen for the SUPERVOID Brain. The rule
is simple and enforced in code: **decide from real SUPERVOID task results, never
from generic benchmarks, and never weaken permissions or approval behaviour.**

Related: [`EVALUATION.md`](./EVALUATION.md), [`FINE_TUNING.md`](./FINE_TUNING.md),
[`VLLM_DEPLOYMENT.md`](./VLLM_DEPLOYMENT.md).

## The evaluation harness (Phase 17)

A SUPERVOID-specific harness (`app/eval`, CLI `scripts/run_eval.py`) runs a
**versioned corpus** (`eval-v1`, 15 cases) against the **real governed surfaces**
(MCP tools, retrieval, policy, compiled state) with a per-case principal — so it
scores real system behaviour, not just model text.

```bash
python scripts/run_eval.py list                 # show the corpus
python scripts/run_eval.py run                  # vs the CONFIGURED provider
python scripts/run_eval.py run --out-dir eval-reports
```

It builds a **throwaway in-memory database** (never the real one) and writes a
JSON + Markdown report.

### Deterministic dimensions (the primary metric)

`schema · tools · permissions · citations · approval · correctness`. A case passes
only when every dimension it opts into passes. Optional model-graded quality is a
**secondary** signal and never gates a case.

### Benchmarked per case

latency · prompt/completion tokens · retrieval count · stable-prefix size · cache
eligibility.

## Comparing candidate models — by configuration, not code

Candidates are compared by changing **configuration** (`ai_provider`, `ai_model`,
`ai_base_url`) and re-running the harness — never by editing code. Each report is
tagged with the provider + model.

| `ai_provider` | Live? | Recommends a default? |
|---|---|---|
| `dry_run` (offline) | no | **no** — validates the harness only |
| `vllm` | yes | yes, if deterministic checks pass the floor |

The report recommends a production default **only** from a **live** provider's
results, and only when the deterministic pass-rate and correctness meet the floor.
A dry-run run is explicitly *not* a basis for a model decision.

## Choosing a base model

1. Stand up a candidate on vLLM (see `VLLM_DEPLOYMENT.md`), set `ai_model`.
2. `python scripts/run_eval.py run` → read the report.
3. Compare candidates' reports; pick the one that passes the SUPERVOID corpus with
   the best latency/cost profile. Record the decision with the report attached.

## Fine-tuned adapters (Phase 18)

The optional LoRA/PEFT pipeline (`/api/brain/tuning`, see `FINE_TUNING.md`) is
**prepared, never auto-run**. It teaches behaviour from explicitly approved,
sanitised examples and registers adapters with their base model, dataset version,
training parameters, licence and evaluation results.

### The deploy gate (enforced)

`evaluate` runs the **Phase-17 corpus** against the base and the adapter (throwaway
DBs). An adapter is deployable **only when all** hold:

1. **beats the base** — not worse overall and strictly better on at least one of
   pass-rate / mean-score / correctness;
2. **does not weaken permissions** (permissions dimension ≥ base);
3. **does not weaken approval** (approval dimension ≥ base);
4. **meets the absolute floor** (`tuning_deploy_min_pass_rate` /
   `tuning_deploy_min_correctness`).

`approve` and `deploy` re-check the gate and refuse (`409`) otherwise; exactly one
adapter is ever deployed; `rollback` returns serving to the base model. Offline,
base == adapter, so deployment stays safely blocked.

## Re-evaluation cadence

- Re-run the corpus on every model/provider change, every prompt-template /
  constitution / profile change that affects behaviour, and before deploying any
  adapter.
- Version the corpus (`CORPUS_VERSION`) when cases change, so reports remain
  comparable over time.
- Keep eval reports alongside the deploy record for each model decision.
