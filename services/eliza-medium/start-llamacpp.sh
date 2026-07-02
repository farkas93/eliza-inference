#!/usr/bin/env bash
set -euo pipefail

LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-llama-server}"
MODEL_PATH="${MODEL_PATH:-${MODEL_DIR:?MODEL_DIR is required}/${MODEL_FILE:?MODEL_FILE is required}}"

cmd=(
  "$LLAMA_SERVER_BIN"
  -m "$MODEL_PATH"
  --host "${HOST:-0.0.0.0}"
  --port "${PORT:-8001}"
  --ctx-size "${CTX_SIZE:-32768}"
  --batch-size "${BATCH_SIZE:-1024}"
  --ubatch-size "${UBATCH_SIZE:-1024}"
  --n-gpu-layers "${N_GPU_LAYERS:-999}"
)

if [[ "${JINJA:-true}" == "true" ]]; then
  cmd+=(--jinja)
fi

if [[ -n "${SPEC_TYPE:-}" ]]; then
  cmd+=(--spec-type "$SPEC_TYPE")
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

if [[ -n "${CACHE_TYPE_K:-}" ]]; then
  cmd+=(--cache-type-k "$CACHE_TYPE_K")
fi

if [[ -n "${CACHE_TYPE_V:-}" ]]; then
  cmd+=(--cache-type-v "$CACHE_TYPE_V")
fi

if [[ -n "${PARALLEL:-}" ]]; then
  cmd+=(--parallel "$PARALLEL")
fi

echo "Starting eliza-medium llama.cpp: ${cmd[*]}"
exec "${cmd[@]}"
