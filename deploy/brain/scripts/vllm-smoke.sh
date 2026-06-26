#!/usr/bin/env bash
#
# OpenAI-compatible smoke tests for the SUPERVOID Brain vLLM server.
# The phase is complete only when these pass against a running server.
#
#   ./vllm-smoke.sh                          # uses $REPO/.env.brain
#   ./vllm-smoke.sh --env-file ../../.env.brain.test
#   BRAIN_SMOKE_BASE_URL=http://127.0.0.1:8000 ./vllm-smoke.sh
#
# Tests: health · model-list · chat-completion · request-id echo ·
#        structured-output (JSON schema) · tool-call · streaming.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
brain::init "$@"

PASS=0; FAIL=0; WARN=0
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

run() { # run <label> <fn>
  local label="$1"; shift
  info "test: $label"
  set +e; "$@"; local rc=$?; set -e
  case "$rc" in
    0) PASS=$((PASS+1)) ;;
    2) WARN=$((WARN+1)) ;;
    *) FAIL=$((FAIL+1)) ;;
  esac
}

# --- 1. health -------------------------------------------------------------
t_health() {
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BASE_URL/health" || echo 000)"
  if [ "$code" = "200" ]; then ok "GET /health -> 200"; return 0; fi
  err "GET /health -> $code (is the server up? try vllm-logs.sh)"; return 1
}

# --- 2. model list ---------------------------------------------------------
t_models() {
  local body
  body="$(brain::curl --max-time 15 "$BASE_URL/v1/models")" || { err "GET /v1/models failed"; return 1; }
  if ! printf '%s' "$body" | jq -e '.data | length > 0' >/dev/null 2>&1; then
    err "/v1/models returned no models: $(printf '%s' "$body" | head -c 300)"; return 1
  fi
  local ids; ids="$(printf '%s' "$body" | jq -r '.data[].id' | paste -sd, -)"
  ok "GET /v1/models -> [$ids]"
  if printf '%s' "$body" | jq -e --arg m "$MODEL_NAME" '.data[] | select(.id == $m)' >/dev/null 2>&1; then
    ok "served model '$MODEL_NAME' present"
  else
    warn "served model '$MODEL_NAME' not in list (using first listed model for remaining tests)"
    MODEL_NAME="$(printf '%s' "$body" | jq -r '.data[0].id')"
  fi
  return 0
}

# --- 3. chat completion + request-id echo ----------------------------------
t_chat() {
  local rid="supervoid-smoke-$$-chat" body req
  req="$(jq -n --arg m "$MODEL_NAME" '{model:$m, temperature:0, max_tokens:16,
        messages:[{role:"user", content:"Reply with exactly the word: pong"}]}')"
  body="$(brain::curl --max-time 60 -D "$TMP/h.txt" \
        -H 'Content-Type: application/json' -H "X-Request-Id: $rid" \
        -X POST "$BASE_URL/v1/chat/completions" -d "$req")" || { err "chat request failed"; return 1; }
  local content; content="$(printf '%s' "$body" | jq -r '.choices[0].message.content // empty')"
  if [ -z "$content" ]; then err "no assistant content: $(printf '%s' "$body" | head -c 300)"; return 1; fi
  ok "chat -> '$(printf '%s' "$content" | tr -d '\n' | head -c 60)'"
  # request-id echo (separate signal; soft-fail since it depends on the flag)
  if grep -qi "^x-request-id:.*$rid" "$TMP/h.txt"; then
    ok "request-id echoed (X-Request-Id)"
  elif grep -qi '^x-request-id:' "$TMP/h.txt"; then
    ok "request-id header present (server-minted)"
  else
    warn "no X-Request-Id response header (enable VLLM_ENABLE_REQUEST_ID_HEADERS=1)"
  fi
  return 0
}

# --- 4. structured output (JSON schema) ------------------------------------
t_structured() {
  local body req
  req="$(jq -n --arg m "$MODEL_NAME" '{
    model:$m, temperature:0, max_tokens:200,
    messages:[{role:"user", content:"Return JSON for a city: the city name and its population."}],
    response_format:{type:"json_schema", json_schema:{name:"city", strict:true, schema:{
      type:"object", additionalProperties:false,
      properties:{city:{type:"string"}, population:{type:"integer"}},
      required:["city","population"]}}}}')"
  body="$(brain::curl --max-time 60 -H 'Content-Type: application/json' \
        -X POST "$BASE_URL/v1/chat/completions" -d "$req")" || { err "structured request failed"; return 1; }
  local content; content="$(printf '%s' "$body" | jq -r '.choices[0].message.content // empty')"
  if [ -z "$content" ]; then err "no content: $(printf '%s' "$body" | head -c 300)"; return 1; fi
  if printf '%s' "$content" | jq -e '.city and (.population|type=="number")' >/dev/null 2>&1; then
    ok "structured output valid JSON: $(printf '%s' "$content" | tr -d '\n' | head -c 80)"
    return 0
  fi
  err "structured output did not match schema: $(printf '%s' "$content" | head -c 200)"; return 1
}

# --- 5. tool call ----------------------------------------------------------
t_tools() {
  local body req
  req="$(jq -n --arg m "$MODEL_NAME" '{
    model:$m, temperature:0, max_tokens:200, tool_choice:"auto",
    messages:[{role:"user", content:"What is the weather in Paris? Use the get_weather tool."}],
    tools:[{type:"function", function:{name:"get_weather",
      description:"Get the current weather for a city",
      parameters:{type:"object", properties:{city:{type:"string"}}, required:["city"]}}}]}')"
  body="$(brain::curl --max-time 60 -H 'Content-Type: application/json' \
        -X POST "$BASE_URL/v1/chat/completions" -d "$req")" || { err "tool request failed"; return 1; }
  local name; name="$(printf '%s' "$body" | jq -r '.choices[0].message.tool_calls[0].function.name // empty')"
  if [ "$name" = "get_weather" ]; then
    ok "tool call emitted: $(printf '%s' "$body" | jq -c '.choices[0].message.tool_calls[0].function')"
    return 0
  fi
  if printf '%s' "$body" | jq -e '.choices[0].message.tool_calls | length > 0' >/dev/null 2>&1; then
    warn "tool_calls present but not get_weather: $(printf '%s' "$body" | jq -c '.choices[0].message.tool_calls')"; return 2
  fi
  warn "no tool_calls (server may lack --enable-auto-tool-choice/--tool-call-parser, or model declined): $(printf '%s' "$body" | jq -r '.choices[0].message.content // empty' | head -c 120)"
  return 2
}

# --- 6. streaming ----------------------------------------------------------
t_streaming() {
  local req
  req="$(jq -n --arg m "$MODEL_NAME" '{model:$m, stream:true, temperature:0, max_tokens:32,
        messages:[{role:"user", content:"Count: one two three four five."}]}')"
  brain::curl --no-buffer --max-time 60 -H 'Content-Type: application/json' \
        -X POST "$BASE_URL/v1/chat/completions" -d "$req" >"$TMP/stream.txt" 2>/dev/null || {
    err "streaming request failed"; return 1; }
  local chunks done_marker
  chunks="$(grep -c '^data: ' "$TMP/stream.txt" || true)"
  done_marker="$(grep -c '^data: \[DONE\]' "$TMP/stream.txt" || true)"
  local content_chunks
  content_chunks="$(grep '^data: ' "$TMP/stream.txt" | grep -v '\[DONE\]' \
        | sed 's/^data: //' | jq -r 'try (.choices[0].delta.content // empty)' 2>/dev/null | grep -c . || true)"
  if [ "${chunks:-0}" -ge 2 ] && [ "${done_marker:-0}" -ge 1 ] && [ "${content_chunks:-0}" -ge 1 ]; then
    ok "streaming: $chunks SSE events, $content_chunks token deltas, [DONE] received"
    return 0
  fi
  err "streaming incomplete (events=$chunks deltas=$content_chunks done=$done_marker)"; return 1
}

say "${_C_DIM}SUPERVOID Brain — vLLM OpenAI-compatible smoke tests${_C_OFF}"
say "${_C_DIM}base: $BASE_URL  model: $MODEL_NAME${_C_OFF}"
run "health"            t_health
run "model-list"        t_models
run "chat + request-id" t_chat
run "structured-output" t_structured
run "tool-call"         t_tools
run "streaming"         t_streaming

say ""
say "summary: ${_C_GREEN}${PASS} passed${_C_OFF}, ${_C_YEL}${WARN} warned${_C_OFF}, ${_C_RED}${FAIL} failed${_C_OFF}"
[ "$FAIL" -eq 0 ] || { err "smoke tests FAILED"; exit 1; }
ok "smoke tests passed"
