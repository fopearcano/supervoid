#!/usr/bin/env bash
#
# Start the SUPERVOID Brain vLLM server (detached) and wait for health.
#
#   ./vllm-start.sh                         # uses $REPO/.env.brain
#   ./vllm-start.sh --env-file ../../.env.brain.test
#
# Honours --pull to refresh the pinned image first.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
brain::init "$@"
brain::require_env_file

if printf '%s\n' "${BRAIN_ARGS[@]:-}" | grep -qx -- '--pull'; then
  info "pulling image ${VLLM_IMAGE:-vllm/vllm-openai:v0.20.0}"
  brain::compose pull vllm || true
fi

info "starting vLLM (model: ${VLLM_MODEL:-?}, served as: ${MODEL_NAME})"
brain::compose up -d

# Generous wait: first run downloads the model.
brain::wait_healthy "${BRAIN_HEALTH_TIMEOUT:-1800}" || {
  err "startup did not become healthy; recent logs:"
  brain::compose logs --tail 60 vllm || true
  exit 1
}
info "listening (private) at ${BASE_URL} — served model: ${MODEL_NAME}"
say  "Next:  ./vllm-smoke.sh${BRAIN_ENV_FILE:+ --env-file $BRAIN_ENV_FILE}"
