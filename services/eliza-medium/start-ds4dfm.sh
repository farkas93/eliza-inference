#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DS4DFM_DIR="${DS4DFM_DIR:-$HOME/src/ds4-dfm-rs}"
DS4DFM_SERVER_BIN="${DS4DFM_SERVER_BIN:-$DS4DFM_DIR/ds4-server}"
MODEL_FILE="${MODEL_FILE:-Qwen3.8-Flash-Next-MQ-Q5-SSD-PLE-BF16-00001-of-00003.gguf}"
KV_TO_DISK="${DS4DFM_KV_TO_DISK:-false}"
KV_DIR="${DS4DFM_KV_DIR:-$ROOT_DIR/.runtime/ds4dfm-kv}"
KV_MB="${DS4DFM_KV_MB:-32768}"

if [[ ! -x "$DS4DFM_SERVER_BIN" ]]; then
  echo "ds4-dfm-rs server not found: $DS4DFM_SERVER_BIN" >&2
  echo "Build it with ./scripts/setup ds4dfm" >&2
  exit 1
fi

resolve_model_path() {
  local candidate
  if [[ -n "${MODEL_PATH:-}" ]]; then
    printf '%s\n' "$MODEL_PATH"
    return 0
  fi
  for candidate in \
    "${MODEL_DIR:-$DS4DFM_DIR}/$MODEL_FILE" \
    "${MODEL_DIR:-$DS4DFM_DIR}/MQ-Q5-SSD-PLE-BF16/$MODEL_FILE" \
    "$DS4DFM_DIR/models/$MODEL_FILE" \
    "$DS4DFM_DIR/models/MQ-Q5-SSD-PLE-BF16/$MODEL_FILE" \
    "$DS4DFM_DIR/$MODEL_FILE"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  printf '%s\n' "${MODEL_DIR:-$DS4DFM_DIR}/$MODEL_FILE"
}

MODEL_PATH="$(resolve_model_path)"
if [[ ! -f "$MODEL_PATH" ]]; then
  echo "ds4dfm model not found: $MODEL_PATH" >&2
  echo "Download it with ./scripts/download-models eliza-medium --profile medium/qwen3.8-flash-next-ds4dfm-262k" >&2
  exit 1
fi

cmd=(
  "$DS4DFM_SERVER_BIN"
  -m "$MODEL_PATH"
  --ctx "${CTX_SIZE:-262144}"
  --host "${HOST:-0.0.0.0}"
  --port "${PORT:-8001}"
  --model-id "${DS4DFM_MODEL_ID:-qwen3.8-flash-next}"
  --max-seqs "${DS4DFM_MAX_SEQS:-1}"
  --prefix-reuse "${DS4DFM_PREFIX_REUSE:-auto}"
  --no-update-check
)

case "${DS4DFM_BACKEND_DEVICE:-cuda}" in
  cuda | metal | cpu) cmd+=("--${DS4DFM_BACKEND_DEVICE:-cuda}") ;;
  *)
    echo "Unsupported DS4DFM_BACKEND_DEVICE: ${DS4DFM_BACKEND_DEVICE}" >&2
    exit 2
    ;;
esac

cmd+=(--mem-floor-gb "${DS4DFM_MEM_FLOOR_GB:-2}")

if [[ -n "${DS4DFM_MTP_DRAFT:-}" ]] && [[ "$DS4DFM_MTP_DRAFT" != "0" ]]; then
  cmd+=(--mtp-draft "$DS4DFM_MTP_DRAFT")
fi

if [[ "$KV_TO_DISK" == "true" ]]; then
  mkdir -p "$KV_DIR"
  cmd+=(
    --kv-disk-dir "$KV_DIR"
    --kv-disk-space-mb "$KV_MB"
  )
fi

# ds4-dfm-rs memory governance settings for Spark unified memory.
# observe mode and zero graph headroom prevent false quote_overflow at boot.
export DS4_MEMGOV="${DS4DFM_MEMGOV:-observe}"
export DS4_SESSION_GRAPH_FIT="${DS4DFM_SESSION_GRAPH_FIT:-0}"
export DS4_SESSION_GRAPH_HEADROOM_MB="${DS4DFM_SESSION_GRAPH_HEADROOM_MB:-0}"
export DS4_QWEN_BATCH="${DS4DFM_QWEN_BATCH:-1}"
export DS4_QWEN_PLE_CACHE_MB="${DS4DFM_QWEN_PLE_CACHE_MB:-512}"
export DS4_QWEN_PLE_WORKERS="${DS4DFM_QWEN_PLE_WORKERS:-16}"
export DS4_QWEN_PREFILL_CHUNK="${DS4DFM_QWEN_PREFILL_CHUNK:-8192}"
if [[ -n "${DS4DFM_PLE_DIR:-}" ]]; then
  export DS4_QWEN_PLE_DIR="$DS4DFM_PLE_DIR"
fi

if [[ -n "${DS4DFM_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  extra_args=(${DS4DFM_EXTRA_ARGS})
  cmd+=("${extra_args[@]}")
fi

if [[ "${DS4DFM_PREFLIGHT:-false}" == "true" ]]; then
  echo "Preflight (resolved serving plan):"
  "${cmd[@]}" --check-config
fi

echo "Starting eliza-medium ds4dfm: ${cmd[*]}"
echo "Served model id: ${DS4DFM_MODEL_ID:-qwen3.8-flash-next} on :${PORT:-8001} (ctx ${CTX_SIZE:-262144}, max-seqs ${DS4DFM_MAX_SEQS:-1})"

# The engine self-governs unified memory; no runtime knobs are needed here.
exec "${cmd[@]}"
