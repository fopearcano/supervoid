#!/usr/bin/env bash
#
# Shared helpers for the SUPERVOID Brain / vLLM scripts.
# Source this; do not execute directly.

set -euo pipefail

# Resolve directories relative to this file.
_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRAIN_DIR="$(cd "$_LIB_DIR/.." && pwd)"
REPO_ROOT="$(cd "$BRAIN_DIR/../.." && pwd)"
COMPOSE_FILE="$BRAIN_DIR/docker-compose.vllm.yml"

# --- pretty output ---------------------------------------------------------
if [ -t 1 ]; then
  _C_GREEN=$'\033[32m'; _C_RED=$'\033[31m'; _C_YEL=$'\033[33m'; _C_DIM=$'\033[2m'; _C_OFF=$'\033[0m'
else
  _C_GREEN=""; _C_RED=""; _C_YEL=""; _C_DIM=""; _C_OFF=""
fi
say()  { printf '%s\n' "$*"; }
info() { printf '%s==>%s %s\n' "$_C_DIM" "$_C_OFF" "$*"; }
ok()   { printf '%sPASS%s %s\n' "$_C_GREEN" "$_C_OFF" "$*"; }
warn() { printf '%sWARN%s %s\n' "$_C_YEL" "$_C_OFF" "$*"; }
err()  { printf '%sFAIL%s %s\n' "$_C_RED" "$_C_OFF" "$*"; }

# --- arg + env handling ----------------------------------------------------
# Usage: brain::init "$@"   (consumes a leading/any "--env-file PATH")
# Sets: BRAIN_ENV_FILE, and exports the env file's variables.
# Leaves remaining args in the BRAIN_ARGS array.
BRAIN_ARGS=()
brain::init() {
  BRAIN_ENV_FILE="${BRAIN_ENV_FILE:-$REPO_ROOT/.env.brain}"
  BRAIN_ARGS=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --env-file) BRAIN_ENV_FILE="$2"; shift 2 ;;
      --env-file=*) BRAIN_ENV_FILE="${1#*=}"; shift ;;
      *) BRAIN_ARGS+=("$1"); shift ;;
    esac
  done

  if [ -f "$BRAIN_ENV_FILE" ]; then
    info "env file: $BRAIN_ENV_FILE"
    set -a
    # shellcheck disable=SC1090
    . "$BRAIN_ENV_FILE"
    set +a
  else
    warn "env file not found: $BRAIN_ENV_FILE (using defaults / current env)"
  fi

  # Client-facing connection details (host port; loopback by default).
  VLLM_PORT="${VLLM_PORT:-8000}"
  local bind="${VLLM_BIND_ADDR:-127.0.0.1}"
  local hostport="${VLLM_PUBLISH_PORT:-$VLLM_PORT}"
  BASE_URL="${BRAIN_SMOKE_BASE_URL:-http://${bind}:${hostport}}"
  MODEL_NAME="${VLLM_SERVED_MODEL_NAME:-supervoid-brain}"
}

brain::require_env_file() {
  if [ ! -f "$BRAIN_ENV_FILE" ]; then
    err "no env file at $BRAIN_ENV_FILE"
    say "Create one:  cp $REPO_ROOT/.env.brain.example $REPO_ROOT/.env.brain   (then edit)"
    say "Or test:     cp $BRAIN_DIR/.env.brain.test.example $REPO_ROOT/.env.brain.test  and pass --env-file $REPO_ROOT/.env.brain.test"
    exit 2
  fi
}

# docker compose wrapper bound to our file + env file.
brain::compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$BRAIN_ENV_FILE" "$@"
}

# --- HTTP helpers ----------------------------------------------------------
# curl wrapper: brain::curl <curl-args...>  (adds auth header if configured)
brain::curl() {
  local auth=()
  if [ -n "${VLLM_API_KEY:-}" ]; then auth=(-H "Authorization: Bearer ${VLLM_API_KEY}"); fi
  curl --silent --show-error "${auth[@]}" "$@"
}

# Wait for /health to return 200 (timeout seconds).
brain::wait_healthy() {
  local timeout="${1:-600}" waited=0
  info "waiting for $BASE_URL/health (timeout ${timeout}s)"
  while [ "$waited" -lt "$timeout" ]; do
    if curl --silent --fail --max-time 5 "$BASE_URL/health" >/dev/null 2>&1; then
      ok "server healthy after ${waited}s"; return 0
    fi
    sleep 5; waited=$((waited + 5))
  done
  err "server not healthy after ${timeout}s"; return 1
}
