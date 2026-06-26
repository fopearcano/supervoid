#!/usr/bin/env bash
#
# Lightweight benchmarks for the SUPERVOID Brain vLLM server:
#   1. concurrency benchmark   — throughput + latency under parallel load
#   2. context-prefix reuse    — TTFT cold vs warm (Automatic Prefix Caching)
#
#   ./vllm-bench.sh                          # uses $REPO/.env.brain
#   BENCH_CONCURRENCY=16 BENCH_REQUESTS=64 ./vllm-bench.sh --env-file ../../.env.brain.test
#
# Pure curl + jq; no extra deps. Intended as a sanity benchmark, not a
# replacement for vLLM's own benchmark_serving.py.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
brain::init "$@"

CONC="${BENCH_CONCURRENCY:-8}"
REQS="${BENCH_REQUESTS:-32}"
MAXTOK="${BENCH_MAX_TOKENS:-128}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# Resolve a usable model id (prefer served name, else first listed).
resolve_model() {
  local body; body="$(brain::curl --max-time 15 "$BASE_URL/v1/models" 2>/dev/null || true)"
  if printf '%s' "$body" | jq -e --arg m "$MODEL_NAME" '.data[]|select(.id==$m)' >/dev/null 2>&1; then
    printf '%s' "$MODEL_NAME"
  else
    printf '%s' "$(printf '%s' "$body" | jq -r '.data[0].id // empty')"
  fi
}

auth_header=()
[ -n "${VLLM_API_KEY:-}" ] && auth_header=(-H "Authorization: Bearer ${VLLM_API_KEY}")

# one_request <prompt> <max_tokens> <out-time-file>  -> writes time_total seconds
one_request() {
  local prompt="$1" maxtok="$2" out="$3" body
  body="$(jq -n --arg m "$MODEL" --arg p "$prompt" --argjson mt "$maxtok" \
        '{model:$m, temperature:0, max_tokens:$mt, messages:[{role:"user", content:$p}]}')"
  curl -s -o /dev/null -w '%{time_total}' "${auth_header[@]}" \
       -H 'Content-Type: application/json' --max-time 120 \
       -X POST "$BASE_URL/v1/chat/completions" -d "$body" >"$out" 2>/dev/null || echo "ERR" >"$out"
}

# ttft <prompt> -> echoes time_starttransfer (s) for a streamed request (TTFT proxy)
ttft() {
  local prompt="$1" body
  body="$(jq -n --arg m "$MODEL" --arg p "$prompt" \
        '{model:$m, stream:true, temperature:0, max_tokens:8, messages:[{role:"user", content:$p}]}')"
  curl -s -o /dev/null -w '%{time_starttransfer}' "${auth_header[@]}" --no-buffer \
       -H 'Content-Type: application/json' --max-time 120 \
       -X POST "$BASE_URL/v1/chat/completions" -d "$body" 2>/dev/null || echo "ERR"
}

MODEL="$(resolve_model)"
if [ -z "$MODEL" ]; then err "could not resolve a model from $BASE_URL/v1/models"; exit 1; fi
say "${_C_DIM}base: $BASE_URL  model: $MODEL${_C_OFF}"

# ===========================================================================
# 1. Concurrency benchmark
# ===========================================================================
info "concurrency benchmark: $REQS requests, $CONC in parallel, max_tokens=$MAXTOK"
start="$(date +%s.%N)"
pids=0
for i in $(seq 1 "$REQS"); do
  one_request "In one sentence, describe idea number $i." "$MAXTOK" "$TMP/t.$i" &
  pids=$((pids+1))
  if [ "$pids" -ge "$CONC" ]; then wait -n 2>/dev/null || wait; pids=$((pids-1)); fi
done
wait
end="$(date +%s.%N)"

oks=0; sum=0; max=0
for i in $(seq 1 "$REQS"); do
  v="$(cat "$TMP/t.$i" 2>/dev/null || echo ERR)"
  [ "$v" = "ERR" ] && continue
  oks=$((oks+1))
  sum="$(awk -v a="$sum" -v b="$v" 'BEGIN{printf "%.6f", a+b}')"
  max="$(awk -v a="$max" -v b="$v" 'BEGIN{print (b>a)?b:a}')"
done
wall="$(awk -v s="$start" -v e="$end" 'BEGIN{printf "%.3f", e-s}')"
if [ "$oks" -gt 0 ]; then
  avg="$(awk -v s="$sum" -v n="$oks" 'BEGIN{printf "%.3f", s/n}')"
  thr="$(awk -v n="$oks" -v w="$wall" 'BEGIN{printf "%.2f", (w>0)?n/w:0}')"
  ok "concurrency: $oks/$REQS ok · wall ${wall}s · throughput ${thr} req/s · avg ${avg}s · max ${max}s"
else
  err "concurrency benchmark: all requests failed"
fi

# ===========================================================================
# 2. Context-prefix reuse benchmark (Automatic Prefix Caching)
# ===========================================================================
info "context-prefix reuse benchmark (TTFT cold vs warm)"
# Build a long shared prefix so the prefix KV-cache reuse is measurable.
# (awk, not `yes|head`, to avoid SIGPIPE under `set -o pipefail`.)
prefix="$(awk 'BEGIN{s="SUPERVOID is a studio system for publishing graphic novels and screen works. "; o=""; for(i=0;i<120;i++) o=o s; print o}')"
q1="${prefix} Question: name one capability. Answer in 5 words."
q2="${prefix} Question: name another capability. Answer in 5 words."

# Warm the cache with the shared prefix, then measure.
_="$(ttft "$q1")"                 # cold (populate prefix cache)
cold="$(ttft "$q1")"             # may already be warm; report anyway
warm="$(ttft "$q2")"             # same prefix, different suffix -> should reuse
if [ "$cold" != "ERR" ] && [ "$warm" != "ERR" ]; then
  speedup="$(awk -v c="$cold" -v w="$warm" 'BEGIN{printf "%.2f", (w>0)?c/w:0}')"
  ok "TTFT shared-prefix: first ${cold}s · reuse ${warm}s · ratio ${speedup}x (>=1 indicates prefix reuse)"
  say "${_C_DIM}note: enable VLLM_ENABLE_PREFIX_CACHING=1 (default) for prefix reuse; cold figure already includes one warm-up call.${_C_OFF}"
else
  err "prefix-reuse benchmark failed (cold=$cold warm=$warm)"
fi
