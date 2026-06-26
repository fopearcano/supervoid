#!/usr/bin/env bash
#
# SUPERVOID Brain — vLLM container entrypoint.
#
# Assembles the `vllm serve` command line from environment variables so that the
# whole deployment is env-driven (no model id or tuning baked into the image or
# compose file). Conditional flags (quantization, tool-call parser, chat
# template, reasoning parser) are added ONLY when their env var is set, so we
# never enable, e.g., automatic tool choice without a configured parser.
#
# Set VLLM_PRINT_CMD=1 to print the assembled command and exit WITHOUT starting
# the server — used by the test harness to validate arg assembly offline (no GPU).
#
# Secrets: the API key is passed via the VLLM_API_KEY *environment variable*
# (which the vLLM OpenAI server reads natively); it is deliberately NOT placed on
# the command line, so it never appears in `ps`/process listings or logs.
set -euo pipefail

# Truthy helper: treats 1/true/yes/on (any case) as true.
_truthy() { case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in 1|true|yes|on) return 0 ;; *) return 1 ;; esac; }

MODEL="${VLLM_MODEL:?VLLM_MODEL is required (e.g. Qwen/Qwen3-30B-A3B-Instruct-2507)}"
SERVED_NAME="${VLLM_SERVED_MODEL_NAME:-supervoid-brain}"
HOST="${VLLM_HOST:-0.0.0.0}"
PORT="${VLLM_PORT:-8000}"
TP_SIZE="${VLLM_TENSOR_PARALLEL_SIZE:-1}"
MAX_LEN="${VLLM_MAX_MODEL_LEN:-32768}"          # conservative default, NOT the model maximum
GPU_UTIL="${VLLM_GPU_MEMORY_UTILIZATION:-0.90}"
MAX_SEQS="${VLLM_MAX_NUM_SEQS:-256}"
DTYPE="${VLLM_DTYPE:-auto}"

ARGS=(
  serve "$MODEL"
  --served-model-name "$SERVED_NAME"
  --host "$HOST"
  --port "$PORT"
  --tensor-parallel-size "$TP_SIZE"
  --max-model-len "$MAX_LEN"
  --gpu-memory-utilization "$GPU_UTIL"
  --max-num-seqs "$MAX_SEQS"
  --dtype "$DTYPE"
)

# --- Automatic Prefix Caching (on by default; explicit for clarity) ----------
if _truthy "${VLLM_ENABLE_PREFIX_CACHING:-1}"; then
  ARGS+=(--enable-prefix-caching)
fi

# --- Chunked prefill (where supported; on by default) ------------------------
if _truthy "${VLLM_ENABLE_CHUNKED_PREFILL:-1}"; then
  ARGS+=(--enable-chunked-prefill)
fi

# --- Request-id headers (echo inbound X-Request-Id, else mint uuid4) ----------
if _truthy "${VLLM_ENABLE_REQUEST_ID_HEADERS:-1}"; then
  ARGS+=(--enable-request-id-headers)
fi

# --- trust-remote-code (Qwen3 and some others need it) -----------------------
if _truthy "${VLLM_TRUST_REMOTE_CODE:-0}"; then
  ARGS+=(--trust-remote-code)
fi

# --- Quantization (ONLY if explicitly set; e.g. awq, gptq, fp8, awq_marlin) ---
if [ -n "${VLLM_QUANTIZATION:-}" ]; then
  ARGS+=(--quantization "$VLLM_QUANTIZATION")
fi

# --- Tool calling: enable automatic tool choice ONLY with a parser configured -
if [ -n "${VLLM_TOOL_CALL_PARSER:-}" ]; then
  ARGS+=(--enable-auto-tool-choice --tool-call-parser "$VLLM_TOOL_CALL_PARSER")
fi

# --- Chat template (ONLY if provided; otherwise the model default is used) -----
if [ -n "${VLLM_CHAT_TEMPLATE:-}" ]; then
  ARGS+=(--chat-template "$VLLM_CHAT_TEMPLATE")
fi

# --- Optional reasoning parser (e.g. for thinking models; off for -Instruct) ---
if [ -n "${VLLM_REASONING_PARSER:-}" ]; then
  ARGS+=(--reasoning-parser "$VLLM_REASONING_PARSER")
fi

# --- Strict, schema-based tool calling where supported ------------------------
# vLLM enforces tool/JSON schemas through its structured-outputs (guided
# decoding) backend. Allow overriding the backend; default to "auto".
if [ -n "${VLLM_GUIDED_DECODING_BACKEND:-}" ]; then
  ARGS+=(--guided-decoding-backend "$VLLM_GUIDED_DECODING_BACKEND")
fi

# --- Escape hatch: raw extra args appended verbatim --------------------------
# shellcheck disable=SC2206
if [ -n "${VLLM_EXTRA_ARGS:-}" ]; then
  EXTRA=(${VLLM_EXTRA_ARGS})
  ARGS+=("${EXTRA[@]}")
fi

if _truthy "${VLLM_PRINT_CMD:-0}"; then
  printf 'vllm'
  printf ' %q' "${ARGS[@]}"
  printf '\n'
  exit 0
fi

echo "[vllm-entrypoint] starting: vllm ${ARGS[*]}"
exec vllm "${ARGS[@]}"
