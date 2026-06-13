#!/usr/bin/env bash
set -euo pipefail

case "${BACKEND:-llamacpp}" in
  llamacpp)
    exec "$(dirname "$0")/start-llamacpp.sh"
    ;;
  vllm)
    exec "$(dirname "$0")/start-vllm.sh"
    ;;
  *)
    echo "Unsupported voice backend: ${BACKEND:-}" >&2
    exit 2
    ;;
esac
