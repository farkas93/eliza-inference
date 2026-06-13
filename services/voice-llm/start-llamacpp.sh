#!/usr/bin/env bash
set -euo pipefail

LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-llama-server}"
MODEL_PATH="${MODEL_PATH:-${MODEL_DIR:?MODEL_DIR is required}/${MODEL_FILE:?MODEL_FILE is required}}"
MMPROJ_PATH="${MMPROJ_PATH:-}"

if [[ -z "$MMPROJ_PATH" && -n "${MMPROJ_FILE:-}" ]]; then
  MMPROJ_PATH="${MODEL_DIR:?MODEL_DIR is required}/$MMPROJ_FILE"
fi

cmd=(
  "$LLAMA_SERVER_BIN"
  -m "$MODEL_PATH"
  --host "${HOST:-0.0.0.0}"
  --port "${PORT:-8002}"
  --ctx-size "${CTX_SIZE:-8192}"
  --batch-size "${BATCH_SIZE:-512}"
  --ubatch-size "${UBATCH_SIZE:-512}"
  --n-gpu-layers "${N_GPU_LAYERS:-999}"
)

if [[ -n "$MMPROJ_PATH" && -f "$MMPROJ_PATH" ]]; then
  cmd+=(--mmproj "$MMPROJ_PATH")
elif [[ -n "$MMPROJ_PATH" ]]; then
  echo "Warning: mmproj file not found, starting text-only: $MMPROJ_PATH" >&2
fi

if [[ "${JINJA:-true}" == "true" ]]; then
  cmd+=(--jinja)
fi

if [[ -n "${REASONING:-}" ]]; then
  cmd+=(--reasoning "$REASONING")
fi

if [[ -n "${REASONING_BUDGET:-}" ]]; then
  cmd+=(--reasoning-budget "$REASONING_BUDGET")
fi

if [[ "${FLASH_ATTN:-auto}" == "off" ]]; then
  cmd+=(--flash-attn off)
elif [[ "${FLASH_ATTN:-auto}" == "on" ]]; then
  cmd+=(--flash-attn on)
fi

echo "Starting voice-llm llama.cpp: ${cmd[*]}"
exec "${cmd[@]}"
