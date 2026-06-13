#!/usr/bin/env bash
set -euo pipefail

VLLM_BIN="${VLLM_BIN:-vllm}"

cmd=(
  "$VLLM_BIN" serve "${MODEL_ID:?MODEL_ID is required}"
  --host "${HOST:-0.0.0.0}"
  --port "${PORT:-8002}"
  --max-model-len "${MAX_MODEL_LEN:-8192}"
  --max-num-seqs "${MAX_NUM_SEQS:-1}"
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION:-0.15}"
  --dtype "${DTYPE:-auto}"
)

if [[ "${ENABLE_PREFIX_CACHING:-false}" == "true" ]]; then
  cmd+=(--enable-prefix-caching)
fi

if [[ "${LANGUAGE_MODEL_ONLY:-false}" == "true" ]]; then
  cmd+=(--language-model-only)
fi

if [[ "${ENABLE_THINKING:-}" == "false" ]]; then
  cmd+=(--default-chat-template-kwargs '{"enable_thinking": false}')
fi

echo "Starting voice-llm vLLM: ${cmd[*]}"
exec "${cmd[@]}"
