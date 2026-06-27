# Optional fine-tuning data pipeline (Prompt 18)

A **prepared, never auto-run** LoRA/PEFT fine-tuning pipeline. The objective is to
teach **behaviour, not current project facts**: how to answer well, choose the
right tool, refuse correctly, plan production, structure proposals, gate actions
behind approval, and know when retrieval is (and isn't) needed.

Nothing here trains or deploys a model automatically. Collection is gated behind
`tuning_enabled`; an adapter is deployable **only** when it beats the base on the
project-specific evaluation **without weakening permissions or approval
behaviour**. The whole surface is **admin-only** (`/api/brain/tuning/...`).

## What is collected (only with explicit approval)

Nine behaviour categories (`TuningExampleKind`), each an example to learn from:

| Kind | Teaches |
|---|---|
| `strong_response` | an exemplary assistant answer |
| `corrected_response` | a human-corrected answer |
| `tool_choice` | the correct MCP tool selection |
| `refusal` | a correct refusal |
| `production_plan` | a good production plan |
| `structured_proposal` | a good gated proposal |
| `requires_approval` | an action that must require approval |
| `retrieval_unnecessary` | answering from hot state without retrieval |
| `retrieval_required` | when cold retrieval is genuinely needed |

## What is excluded (enforced by the sanitiser)

Every candidate is sanitised on the way in (`app/services/tuning/sanitize.py`):

| Excluded | Handling |
|---|---|
| raw passwords / tokens / secrets | **always redacted** (no exception) |
| chain-of-thought | **always stripped** (we teach the final answer, not the trace) |
| private contracts | **blocked** unless explicitly approved **and** anonymised |
| private member data (emails / phones) | **blocked** unless anonymised |
| temporary task statuses / obsolete-fact markers | **flagged** for the reviewer |
| unapproved model outputs | never exported — the review workflow is the gate |

Exclusions are evaluated on the *cleaned* text, so a redacted secret can never be
mistaken for member data, and content removed as chain-of-thought never leaks.

## Review and approval workflow

A candidate is created `PENDING`. A reviewer `APPROVED`s or `REJECTED`s it. Only
`APPROVED` candidates are ever exported, and once exported they are frozen
(`EXPORTED`, with their dataset version + split recorded). Nothing is collected
or promoted automatically.

```
POST /api/brain/tuning/candidates                 # propose (requires tuning_enabled)
POST /api/brain/tuning/candidates/{id}/approve
POST /api/brain/tuning/candidates/{id}/reject
```

## Versioned export + train/validation split

`POST /api/brain/tuning/datasets` exports all approved, not-yet-exported examples
to **versioned JSONL** (a portable SFT chat format: the input messages with the
gold assistant turn appended, plus behaviour metadata). The split is **by project
and task category**: each `(project, category)` group contributes to both train
and validation, deterministically — so neither split is dominated by one project
and no group leaks entirely to one side. Export refuses to overwrite a version or
to export fewer than `tuning_min_examples`. A manifest records counts by kind,
project, category and split.

Files land under `storage/<tuning_export_subdir>/<version>/{train,val}.jsonl`.

## Adapter registry

`TuningAdapter` records everything a deployment decision needs:

- **base model**
- **dataset version** it was trained on
- **training parameters** (LoRA rank / alpha / dropout, learning rate, epochs)
- **licence**
- **evaluation results** (base-vs-adapter on the Phase-17 corpus)
- **deployment status** (`registered → evaluated → approved → deployed`, or
  `rolled_back` / `rejected`)

```
POST /api/brain/tuning/adapters                   # register (no weights stored — a ref only)
POST /api/brain/tuning/adapters/{id}/evaluate     # run the project corpus base vs adapter
POST /api/brain/tuning/adapters/{id}/approve      # only if the deploy gate passes
POST /api/brain/tuning/adapters/{id}/deploy       # only if approved; one active at a time
POST /api/brain/tuning/adapters/{id}/rollback     # back to the base model
GET  /api/brain/tuning/adapters/{id}/vllm-config  # vLLM LoRA serving config
GET  /api/brain/tuning/active                      # deployed adapter, or base
```

## Evaluation against the Phase-17 corpus

`evaluate` runs the **Phase-17 SUPERVOID corpus** (`app/eval`) against the base
and the adapter on **throwaway in-memory databases** (never the real one), then
records the comparison. Offline (dry-run) the two sides are identical, so the
adapter does not beat the base and deployment stays blocked — the correct safe
default. A real comparison points the adapter provider at the vLLM serving the
LoRA.

## The deploy gate (the core guard)

An adapter is deployable **iff all** hold (`tuning.compare_results`):

1. **beats the base** — not worse overall (pass-rate and correctness ≥ base) and
   strictly better on at least one of pass-rate / mean-score / correctness;
2. **does not weaken permissions** — permissions dimension ≥ base;
3. **does not weaken approval** — approval dimension ≥ base;
4. **meets the absolute floor** — pass-rate ≥ `tuning_deploy_min_pass_rate` and
   correctness ≥ `tuning_deploy_min_correctness`.

`approve` and `deploy` both re-check the gate and refuse (HTTP 409) when it is not
satisfied. Deploying demotes any previously-deployed adapter, so exactly one is
ever active.

## vLLM LoRA deployment + rollback

`vllm-config` / `active` emit a vLLM-compatible LoRA serving config
(`--enable-lora --max-lora-rank N --lora-modules name=path`, plus the matching
env). **Deployment is recorded in the registry; applying the config to the
running vLLM (restart with these flags) is a deliberate deploy-host step** — the
backend never re-routes live inference automatically. `rollback` clears the
active adapter so the base model is served again.

## Configuration

```
tuning_enabled            = false   # gate collection (nothing auto-runs)
tuning_export_subdir      = tuning/datasets
tuning_val_fraction       = 0.2
tuning_min_examples       = 10
tuning_default_base_model = supervoid-brain
tuning_lora_rank/alpha/dropout, tuning_learning_rate, tuning_epochs   # recorded, not executed
tuning_adapter_mount_dir  = /opt/brain/adapters
tuning_vllm_max_lora_rank = 32
tuning_deploy_min_pass_rate   = 0.9
tuning_deploy_min_correctness = 0.9
```

## Layout

```
app/models/tuning.py              # TuningExample, TuningDataset, TuningAdapter
app/services/tuning/
  sanitize.py    # strip CoT, redact secrets, exclusion rules
  candidates.py  # propose + review workflow
  export.py      # versioned JSONL + project/category split
  adapters.py    # registry, eval comparison, deploy gate, deploy/rollback, vLLM config
app/routers/brain_tuning.py       # admin-only API
tests/test_tuning.py
```
