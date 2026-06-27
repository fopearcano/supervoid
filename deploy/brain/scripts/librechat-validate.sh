#!/usr/bin/env bash
#
# Validate the SUPERVOID LibreChat deployment configuration BEFORE bringing it up.
# Runs the structural validator (always) and, when Docker is available, also
# `docker compose config` to catch compose syntax errors.
#
#   ./librechat-validate.sh                       # structure only
#   ./librechat-validate.sh --env-file ../../.env.librechat   # + secrets

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRAIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$BRAIN_DIR/docker-compose.librechat.yml"

PY="${PYTHON:-python3}"
"$PY" "$SCRIPT_DIR/validate_librechat_config.py" "$@"

if command -v docker >/dev/null 2>&1; then
  echo "==> docker compose config (syntax check)"
  # --env-file may be among "$@"; pass through only if a real file is given.
  if docker compose -f "$COMPOSE_FILE" config >/dev/null 2>err.log; then
    echo "PASS — docker compose config parses."
  else
    echo "WARN — docker compose config reported issues (often just unset env vars):"
    sed 's/^/    /' err.log || true
  fi
  rm -f err.log
else
  echo "(docker not available — skipped 'docker compose config')"
fi
