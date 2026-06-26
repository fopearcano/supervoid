# vLLM deployment — SUPERVOID Brain (Phase 1)

A production-shaped, **optional** vLLM deployment for the dedicated AI
workstation. It provides an **OpenAI-compatible** inference endpoint for the
SUPERVOID Brain. It is independent of the main application stack
(`docker-compose.yml`) and can be started, tested and benchmarked on its own.

> This is **Phase 1** of the Brain initiative (see
> [`BRAIN_IMPLEMENTATION_PLAN.md`](./BRAIN_IMPLEMENTATION_PLAN.md)). It adds **no
> application code** and changes nothing in the existing backend/frontend. The
> Brain Gateway, LibreChat and the MCP server are later phases.

---

## Governance (read first)

- **vLLM is raw, ungoverned inference.** It performs no authentication beyond an
  optional static API key, no policy checks, and no auditing.
- **Bind it to the private network only.** The provided compose file publishes
  the port on **`127.0.0.1`** by default. **Never** bind it to `0.0.0.0`, and
  **never** place it behind the internet-facing reverse proxy (nginx).
- **In production, the SUPERVOID Brain Gateway is the only client.** LibreChat
  and the rest of the system talk to the **Gateway**, which enforces auth, the
  policy service, the model allowlist, request-id correlation, redaction and
  logging. **LibreChat must not connect to vLLM directly.**
- The API key is passed via the `VLLM_API_KEY` **environment variable** (read
  natively by vLLM); it is never placed on the command line, so it does not
  appear in `ps` or logs.

---

## Topology & ports

```
SUPERVOID Brain Gateway (later phase)  ──>  vLLM  (this deployment)
                                            ├─ container port: VLLM_PORT (default 8000)
                                            ├─ host binding:   VLLM_BIND_ADDR:VLLM_PUBLISH_PORT
                                            │                  (default 127.0.0.1:8000 — PRIVATE)
                                            └─ docker network: supervoid-brain (reach as `vllm:8000`)
```

| Setting | Default | Meaning |
|---|---|---|
| `VLLM_PORT` | `8000` | port vLLM listens on inside the container |
| `VLLM_BIND_ADDR` | `127.0.0.1` | host interface the port is published on — **keep private** |
| `VLLM_PUBLISH_PORT` | `=VLLM_PORT` | host port |
| `BRAIN_NETWORK_NAME` | `supervoid-brain` | docker network other Brain services join |

To serve a Gateway running on **another LAN host**, set `VLLM_BIND_ADDR` to a
**private LAN IP** (e.g. `10.0.0.5`) — never a public address.

---

## Prerequisites

- An NVIDIA GPU host with recent drivers.
- Docker Engine + the **NVIDIA Container Toolkit** (so `--gpus`/device
  reservations work).
- Outbound HTTPS to Hugging Face on first run (to download the model), or a
  pre-populated HF cache volume.

---

## Quick start

```bash
# 1. configure (on the GPU host)
cp .env.brain.example .env.brain
$EDITOR .env.brain                       # set VLLM_API_KEY; pick model/sizing

# 2. start (first run downloads the model — can take a while)
./deploy/brain/scripts/vllm-start.sh

# 3. verify (OpenAI-compatible smoke tests)
./deploy/brain/scripts/vllm-smoke.sh

# 4. (optional) benchmark
./deploy/brain/scripts/vllm-bench.sh

# logs / stop
./deploy/brain/scripts/vllm-logs.sh
./deploy/brain/scripts/vllm-stop.sh      # add --volumes to drop the HF cache
```

All scripts accept `--env-file <path>` (default `./.env.brain`).

---

## Default documented candidate model

```
VLLM_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
VLLM_SERVED_MODEL_NAME=supervoid-brain
```

A strong, efficient MoE instruct model with native tool calling. **It is not
hardcoded into application logic** — SUPERVOID references the *served name*
(`supervoid-brain`), so you can swap the checkpoint without touching the app.

The initial context is capped at a **conservative `VLLM_MAX_MODEL_LEN=32768`**
(not the model maximum); raise it only after validating VRAM headroom.

---

## Environment reference

Everything is environment-driven (see `.env.brain.example`). Conditional flags
are added by `deploy/brain/vllm-entrypoint.sh` **only when set**.

| Variable | Default | Notes |
|---|---|---|
| `VLLM_IMAGE` | `vllm/vllm-openai:v0.20.0` | **pinned**, never `latest`; prefer a digest |
| `VLLM_MODEL` | *(required)* | HF id or local path |
| `VLLM_SERVED_MODEL_NAME` | `supervoid-brain` | stable name the app/Gateway use |
| `VLLM_HOST` | `0.0.0.0` | bind inside the container |
| `VLLM_PORT` | `8000` | container port |
| `VLLM_BIND_ADDR` | `127.0.0.1` | host interface (**private**) |
| `VLLM_TENSOR_PARALLEL_SIZE` | `1` | set to #GPUs for tensor parallelism |
| `VLLM_MAX_MODEL_LEN` | `32768` | conservative; not the model max |
| `VLLM_GPU_MEMORY_UTILIZATION` | `0.90` | lower if you see OOM |
| `VLLM_MAX_NUM_SEQS` | `256` | max concurrent sequences |
| `VLLM_DTYPE` | `auto` | `auto`/`bfloat16`/`float16` |
| `VLLM_ENABLE_PREFIX_CACHING` | `1` | **Automatic Prefix Caching** |
| `VLLM_ENABLE_CHUNKED_PREFILL` | `1` | chunked prefill (where supported) |
| `VLLM_ENABLE_REQUEST_ID_HEADERS` | `1` | echo/mint `X-Request-Id` |
| `VLLM_TRUST_REMOTE_CODE` | `0` | set `1` for Qwen3 and similar |
| `VLLM_TOOL_CALL_PARSER` | *(empty)* | e.g. `hermes`; enables **auto tool choice only when set** |
| `VLLM_CHAT_TEMPLATE` | *(empty)* | path to a Jinja template; **must match the tool parser** |
| `VLLM_REASONING_PARSER` | *(empty)* | for thinking models; leave empty for `-Instruct` |
| `VLLM_QUANTIZATION` | *(empty)* | `awq`/`awq_marlin`/`gptq`/`fp8`… — validate first |
| `VLLM_GUIDED_DECODING_BACKEND` | *(empty)* | structured-output backend; `auto` if empty |
| `VLLM_EXTRA_ARGS` | *(empty)* | raw passthrough, e.g. `--kv-cache-dtype fp8` |
| `VLLM_API_KEY` | *(empty)* | **set a strong key**; read natively (never on argv) |
| `HUGGING_FACE_HUB_TOKEN` | *(empty)* | for gated models |
| `VLLM_GPU_COUNT` | `all` | GPUs to reserve |

### Features enabled

- **Automatic Prefix Caching** (`--enable-prefix-caching`) — reuses shared
  prompt prefixes across requests.
- **Request-id headers** (`--enable-request-id-headers`) — echoes an inbound
  `X-Request-Id` or mints a `uuid4`, so the Gateway can correlate calls.
- **Chunked prefill** (`--enable-chunked-prefill`) — better long-context
  throughput where supported.
- **Automatic tool choice** (`--enable-auto-tool-choice --tool-call-parser …`) —
  enabled **only** when `VLLM_TOOL_CALL_PARSER` is set, so we never advertise
  tool calling without a compatible parser.
- **Strict, schema-based outputs** — JSON-schema `response_format` and tool
  schemas are enforced by vLLM's structured-outputs (guided decoding) backend.

---

## Scripts

| Script | Purpose |
|---|---|
| `scripts/vllm-start.sh` | start detached, wait for health (`--pull` to refresh image) |
| `scripts/vllm-stop.sh` | stop & remove container (`--volumes` to drop HF cache) |
| `scripts/vllm-logs.sh` | tail logs (`--tail N`, `--no-follow`) |
| `scripts/vllm-smoke.sh` | OpenAI-compatible smoke tests (acceptance gate) |
| `scripts/vllm-bench.sh` | concurrency + context-prefix-reuse benchmarks |

### Smoke tests (acceptance gate)

`vllm-smoke.sh` runs, against a live server:

1. **health** — `GET /health` → 200
2. **model-list** — `GET /v1/models` lists the served model
3. **chat-completion** — a non-streaming completion returns content
4. **request-id** — the response echoes the `X-Request-Id` we sent
5. **structured-output** — a JSON-schema `response_format` returns schema-valid JSON
6. **tool-call** — a `tools` request returns `tool_calls` for the function
7. **streaming** — `stream:true` yields multiple SSE deltas and `[DONE]`

Exit code is non-zero if any **hard** check fails. Tool-calling is reported as a
warning (not a hard failure) if the model declines, since that depends on the
chat template / model behaviour.

### Benchmarks

`vllm-bench.sh` runs two quick sanity benchmarks (tune via `BENCH_CONCURRENCY`,
`BENCH_REQUESTS`, `BENCH_MAX_TOKENS`):

- **Concurrency** — fires N requests with a parallelism cap; reports throughput
  (req/s), average and max latency.
- **Context-prefix reuse** — sends a long shared prefix twice (different
  suffixes) and compares time-to-first-token; with Automatic Prefix Caching the
  warm call should be faster. For a rigorous study use vLLM's own
  `benchmark_serving.py`.

---

## Smaller fallback / test profile

A smaller model for CI, laptops, and harness validation — selected **purely via
environment variables**, no compose/code edits:

```bash
cp deploy/brain/.env.brain.test.example .env.brain.test     # Qwen3-0.6B, 8k ctx
./deploy/brain/scripts/vllm-start.sh --env-file .env.brain.test
./deploy/brain/scripts/vllm-smoke.sh --env-file .env.brain.test
```

### Validating the harness with no GPU (offline)

You can prove the smoke/bench **scripts** themselves work without any GPU or
model, using the included test double (it is **not** vLLM and says nothing about
a real model):

```bash
MOCK_API_KEY=test-key MOCK_REQUIRE_KEY=1 \
  python3 deploy/brain/testing/mock_vllm_server.py &      # 127.0.0.1:8000

cat > .env.brain.mock <<'EOF'
VLLM_SERVED_MODEL_NAME=supervoid-brain
VLLM_PORT=8000
VLLM_API_KEY=test-key
EOF

./deploy/brain/scripts/vllm-smoke.sh --env-file .env.brain.mock   # all PASS
./deploy/brain/scripts/vllm-bench.sh --env-file .env.brain.mock
kill %1
```

---

## Pinning the image

The example pins `vllm/vllm-openai:v0.20.0` (a real, published tag) — **not
`latest`**. Before production:

1. Pick the latest **tested** release for your GPUs/CUDA from
   <https://hub.docker.com/r/vllm/vllm-openai/tags> or the
   [GitHub releases](https://github.com/vllm-project/vllm/releases).
2. Pull and record the **digest**, then pin by digest for immutability:
   ```bash
   docker pull vllm/vllm-openai:vX.Y.Z
   docker inspect --format='{{index .RepoDigests 0}}' vllm/vllm-openai:vX.Y.Z
   # -> set VLLM_IMAGE=vllm/vllm-openai@sha256:<digest>
   ```

---

## Validating a quantized checkpoint (AWQ / GPTQ / FP8 / …)

**Do not assume a community quantized checkpoint works.** Quantized weights vary
in method, calibration, group size, and kernel support, and may fail to load,
silently degrade quality, or break tool calling. Validate **before** making one
the production default:

1. **Stage it.** In a *non-production* env file set `VLLM_MODEL` to the
   quantized repo and `VLLM_QUANTIZATION` to its method
   (`awq`/`awq_marlin`/`gptq`/`gptq_marlin`/`fp8`/`compressed-tensors`). Start
   with a small `VLLM_MAX_MODEL_LEN` and modest `VLLM_GPU_MEMORY_UTILIZATION`.
2. **Confirm it loads.** `vllm-start.sh` must become healthy; check
   `vllm-logs.sh` for the chosen quant kernel and **no fallback/warning** about
   an unsupported scheme.
3. **Run the smoke tests.** `vllm-smoke.sh` must pass health, model-list, chat,
   structured-output and streaming. Tool-calling must still emit `tool_calls`
   (quantization sometimes degrades this — verify explicitly).
4. **Check quality, not just liveness.** Run a handful of representative
   editorial prompts and compare against the full-precision model. Watch for
   repetition, format drift, refusals, or broken JSON/tool arguments.
5. **Benchmark.** `vllm-bench.sh` — confirm throughput/latency and VRAM use are
   acceptable, and that prefix caching still helps.
6. **Soak.** Leave it under light concurrent load for a while; watch for OOM,
   CUDA errors, or memory growth in `vllm-logs.sh`.
7. **Only then** promote it: pin the repo (and revision/commit), record the
   validated `VLLM_IMAGE` digest, and update your production `.env.brain`.

Record the checkpoint repo, **revision/commit hash**, quant method, GPU model,
vLLM image digest, and context length you validated — quantized results are
hardware- and version-specific.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Tool calls never fire | chat template doesn't match the parser — set `VLLM_CHAT_TEMPLATE` to the model's tool-use template; confirm `VLLM_TOOL_CALL_PARSER` (Qwen3 → `hermes`) |
| CUDA out of memory | lower `VLLM_GPU_MEMORY_UTILIZATION`, lower `VLLM_MAX_MODEL_LEN`, lower `VLLM_MAX_NUM_SEQS`, or raise `VLLM_TENSOR_PARALLEL_SIZE` |
| Health never green | model still downloading/loading — raise `VLLM_HEALTH_START_PERIOD` / `BRAIN_HEALTH_TIMEOUT`; check `vllm-logs.sh` |
| Gated model 401/403 | set `HUGGING_FACE_HUB_TOKEN` |
| `trust_remote_code` error | set `VLLM_TRUST_REMOTE_CODE=1` |
| Smoke `model-list` mismatch | client uses `VLLM_SERVED_MODEL_NAME`; the harness falls back to the first listed model and warns |
| `--enable-request-id-headers` perf at very high QPS | terminate request-id at the Gateway/router instead; flag is fine for normal loads |

---

## Phase completion criteria

This phase is complete when the deployment can be **started independently** on
the GPU host and **`vllm-smoke.sh` passes** the OpenAI-compatible checks (health,
model-list, chat, request-id, structured-output, streaming; tool-call passing or
explained). The smoke/bench **harness** is validated offline in this repo against
the bundled test double; the **model** acceptance run happens on the GPU host.
