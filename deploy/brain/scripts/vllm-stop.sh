#!/usr/bin/env bash
#
# Stop the SUPERVOID Brain vLLM server.
#
#   ./vllm-stop.sh                # stop + remove the container (keeps the HF cache volume)
#   ./vllm-stop.sh --volumes      # also remove the HF cache volume (re-downloads next run)
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
brain::init "$@"
brain::require_env_file

if printf '%s\n' "${BRAIN_ARGS[@]:-}" | grep -qx -- '--volumes'; then
  warn "removing containers AND volumes (HF cache will be re-downloaded)"
  brain::compose down --volumes
else
  info "stopping and removing the vLLM container (HF cache volume preserved)"
  brain::compose down
fi
ok "stopped"
