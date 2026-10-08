#!/usr/bin/env bash
set -euo pipefail

LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-llama-server}"
if [[ "${LLAMA_RUNTIME:-}" == "unsloth-mtp" ]]; then
  LLAMA_SERVER_BIN="${LLAMA_MTP_SERVER_BIN:-${LLAMA_MTP_DIR:-$HOME/src/llama.cpp-qwen-mtp}/build/bin/llama-server}"
fi
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
  if [[ "$SPEC_TYPE" == "draft-mtp" ]]; then
    if [[ -z "${DRAFT_MODEL_FILE:-}" ]]; then
      echo "draft-mtp requires DRAFT_MODEL_FILE" >&2
      exit 1
    fi
    draft_path="${DRAFT_MODEL_PATH:-$MODEL_DIR/$DRAFT_MODEL_FILE}"
    if [[ ! -f "$draft_path" ]]; then
      echo "MTP draft head not found: $draft_path. Run scripts/download-models with this profile." >&2
      exit 1
    fi
    help_output="$("$LLAMA_SERVER_BIN" --help 2>&1)" || {
      echo "MTP runtime unavailable; run ./scripts/setup llamacpp --qwen-mtp" >&2
      exit 1
    }
    if [[ "$help_output" != *draft-mtp* ]]; then
      echo "Selected llama-server lacks draft-mtp support; run ./scripts/setup llamacpp --qwen-mtp" >&2
      exit 1
    fi
    cmd+=(--model-draft "$draft_path" --spec-draft-n-max "${SPEC_DRAFT_N_MAX:-3}")
  fi
  cmd+=(--spec-type "$SPEC_TYPE")
fi

if [[ -n "${MODEL_NAME:-}" ]]; then
  cmd+=(--alias "$MODEL_NAME")
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

if [[ "${FIT:-}" == "off" ]]; then
  cmd+=(--fit off)
elif [[ "${FIT:-}" == "on" ]]; then
  cmd+=(--fit on)
fi

if [[ -n "${OVERRIDE_TENSOR:-}" ]]; then
  cmd+=(--override-tensor "$OVERRIDE_TENSOR")
fi

if [[ -n "${N_CPU_MOE:-}" ]]; then
  cmd+=(--n-cpu-moe "$N_CPU_MOE")
fi

echo "Starting eliza-medium llama.cpp: ${cmd[*]}"
exec "${cmd[@]}"
