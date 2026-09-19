#!/usr/bin/env bash
set -euo pipefail

case "${BACKEND:-llamacpp}" in
  llamacpp)
    exec "$(dirname "$0")/start-llamacpp.sh"
    ;;
  vllm)
    exec "$(dirname "$0")/start-vllm.sh"
    ;;
  sglang)
    exec "$(dirname "$0")/start-sglang.sh"
    ;;
  ds4)
    exec "$(dirname "$0")/start-ds4.sh"
    ;;
  ds4dfm)
    exec "$(dirname "$0")/start-ds4dfm.sh"
    ;;
  flash)
    exec "$(dirname "$0")/start-flash.sh"
    ;;
  *)
    echo "Unsupported eliza-medium backend: ${BACKEND:-}" >&2
    exit 2
    ;;
esac
