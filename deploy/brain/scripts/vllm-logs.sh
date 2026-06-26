#!/usr/bin/env bash
#
# Tail the SUPERVOID Brain vLLM server logs.
#
#   ./vllm-logs.sh                 # last 200 lines, then follow
#   ./vllm-logs.sh --tail 500      # last 500 lines, then follow
#   ./vllm-logs.sh --no-follow     # dump and exit
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
brain::init "$@"
brain::require_env_file

follow="--follow"
tail_n="200"
i=0
while [ "$i" -lt "${#BRAIN_ARGS[@]}" ]; do
  case "${BRAIN_ARGS[$i]}" in
    --no-follow) follow="" ;;
    --tail) i=$((i + 1)); tail_n="${BRAIN_ARGS[$i]}" ;;
    *) : ;;  # ignore unknown extras
  esac
  i=$((i + 1))
done

if [ -n "$follow" ]; then
  brain::compose logs --follow --tail "$tail_n" vllm
else
  brain::compose logs --tail "$tail_n" vllm
fi
