#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SGLANG_VENV="${SGLANG_VENV:-$ROOT_DIR/.venvs/sglang}"
SGLANG_PYTHON="${SGLANG_PYTHON:-$SGLANG_VENV/bin/python}"
SGLANG_BIN="${SGLANG_BIN:-$SGLANG_VENV/bin/sglang}"
export PATH="$SGLANG_VENV/bin:$PATH"

sglang_cmd=()
if [[ -x "$SGLANG_PYTHON" ]] && "$SGLANG_PYTHON" -c 'import sglang.launch_server' >/dev/null 2>&1; then
  sglang_cmd=("$SGLANG_PYTHON" -m sglang.launch_server)
elif [[ -x "$SGLANG_BIN" ]]; then
  sglang_cmd=("$SGLANG_BIN")
  sglang_cmd+=(serve)
elif command -v sglang >/dev/null 2>&1; then
  sglang_cmd=("$(command -v sglang)")
  sglang_cmd+=(serve)
else
  echo "SGLang runtime not found. Run ./scripts/setup sglang or set SGLANG_PYTHON/SGLANG_BIN in .env." >&2
  exit 1
fi

model_path="${MODEL_PATH:-${MODEL_DIR:-${MODEL_ID:?MODEL_ID is required}}}"

cmd=(
  "${sglang_cmd[@]}"
  --model-path "$model_path"
  --host "${HOST:-0.0.0.0}"
  --port "${PORT:-8001}"
)

if [[ -n "${QUANTIZATION:-}" ]]; then
  cmd+=(--quantization "$QUANTIZATION")
fi

if [[ -n "${TP_SIZE:-}" ]]; then
  cmd+=(--tp-size "$TP_SIZE")
fi

if [[ -n "${MAX_MODEL_LEN:-}" ]]; then
  cmd+=(--context-length "$MAX_MODEL_LEN")
fi

if [[ -n "${MEM_FRACTION_STATIC:-}" ]]; then
  cmd+=(--mem-fraction-static "$MEM_FRACTION_STATIC")
fi

if [[ "${TRUST_REMOTE_CODE:-false}" == "true" ]]; then
  cmd+=(--trust-remote-code)
fi

if [[ -n "${KV_CACHE_DTYPE:-}" ]]; then
  cmd+=(--kv-cache-dtype "$KV_CACHE_DTYPE")
fi

if [[ -n "${ATTENTION_BACKEND:-}" ]]; then
  cmd+=(--attention-backend "$ATTENTION_BACKEND")
fi

if [[ -n "${CHUNKED_PREFILL_SIZE:-}" ]]; then
  cmd+=(--chunked-prefill-size "$CHUNKED_PREFILL_SIZE")
fi

if [[ -n "${REASONING_PARSER:-}" ]]; then
  cmd+=(--reasoning-parser "$REASONING_PARSER")
fi

if [[ -n "${TOOL_CALL_PARSER:-}" ]]; then
  cmd+=(--tool-call-parser "$TOOL_CALL_PARSER")
fi

if [[ -n "${MAMBA_RADIX_CACHE_STRATEGY:-}" ]]; then
  cmd+=(--mamba-radix-cache-strategy "$MAMBA_RADIX_CACHE_STRATEGY")
fi

if [[ -n "${MAMBA_SSM_DTYPE:-}" ]]; then
  cmd+=(--mamba-ssm-dtype "$MAMBA_SSM_DTYPE")
fi

if [[ -n "${SERVED_MODEL_NAME:-}" ]]; then
  cmd+=(--served-model-name "$SERVED_MODEL_NAME")
fi

if [[ -n "${API_KEY:-}" ]]; then
  cmd+=(--api-key "$API_KEY")
fi

if [[ -n "${CHAT_TEMPLATE:-}" ]]; then
  cmd+=(--chat-template "$CHAT_TEMPLATE")
fi

echo "Starting eliza-medium SGLang: ${cmd[*]}"
exec "${cmd[@]}"
