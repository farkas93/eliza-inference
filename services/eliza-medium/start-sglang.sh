#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SGLANG_VENV="${SGLANG_VENV:-$ROOT_DIR/.venvs/sglang}"
SGLANG_BIN="${SGLANG_BIN:-$SGLANG_VENV/bin/sglang}"
export PATH="$SGLANG_VENV/bin:$PATH"

sglang_cmd=()
if [[ -x "$SGLANG_BIN" ]]; then
  sglang_cmd=("$SGLANG_BIN")
elif command -v sglang >/dev/null 2>&1; then
  sglang_cmd=("$(command -v sglang)")
else
  echo "SGLang CLI not found. Run ./scripts/setup sglang or set SGLANG_BIN in .env." >&2
  exit 1
fi

cmd=(
  "${sglang_cmd[@]}" serve
  --model-path "${MODEL_ID:?MODEL_ID is required}"
  --host "${HOST:-0.0.0.0}"
  --port "${PORT:-8001}"
)

if [[ -n "${TP_SIZE:-}" ]]; then
  cmd+=(--tp-size "$TP_SIZE")
fi

if [[ -n "${MAX_MODEL_LEN:-}" ]]; then
  cmd+=(--context-length "$MAX_MODEL_LEN")
fi

if [[ -n "${MEM_FRACTION_STATIC:-}" ]]; then
  cmd+=(--mem-fraction-static "$MEM_FRACTION_STATIC")
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
