#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VLLM_VENV="${VLLM_VENV:-$ROOT_DIR/.venvs/vllm}"
VLLM_BIN="${VLLM_BIN:-$VLLM_VENV/bin/vllm}"
export PATH="$VLLM_VENV/bin:$PATH"

vllm_cmd=()
if command -v "$VLLM_BIN" >/dev/null 2>&1 || [[ -x "$VLLM_BIN" ]]; then
  vllm_cmd=("$VLLM_BIN")
else
  echo "vLLM CLI not found and uv is unavailable. Run ./scripts/install-vllm or set VLLM_BIN in .env." >&2
  exit 1
fi

cmd=(
  "${vllm_cmd[@]}" serve "${MODEL_ID:?MODEL_ID is required}"
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

if [[ "${ENFORCE_EAGER:-false}" == "true" ]]; then
  cmd+=(--enforce-eager)
fi

if [[ -n "${MAX_CUDAGRAPH_CAPTURE_SIZE:-}" ]]; then
  cmd+=(--max-cudagraph-capture-size "$MAX_CUDAGRAPH_CAPTURE_SIZE")
fi

if [[ "${LANGUAGE_MODEL_ONLY:-false}" == "true" ]]; then
  cmd+=(--language-model-only)
fi

if [[ "${ENABLE_THINKING:-}" == "false" ]]; then
  cmd+=(--default-chat-template-kwargs '{"enable_thinking": false}')
fi

echo "Starting voice-llm vLLM: ${cmd[*]}"
exec env -u VLLM_BIN -u VLLM_VENV "${cmd[@]}"
