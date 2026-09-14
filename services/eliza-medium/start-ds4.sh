#!/usr/bin/env bash
set -euo pipefail

# Project root directory. could be problematic, the way we get it.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DS4_DIR="${DS4_DIR:-$HOME/src/ds4}"
DS4_SERVER_BIN="${DS4_SERVER_BIN:-$DS4_DIR/ds4-server}"
MODEL_FILE="${MODEL_FILE:-ds4flash.gguf}"
KV_TO_DISK="${DS4_KV_TO_DISK:-false}"
KV_DIR="${DS4_KV_DIR:-$ROOT_DIR/.runtime/ds4-kv}"
# Estimated to be a good to have 16GB for kv cache, assuming interested in 256k context
KV_MB="${DS4_KV_MB:-16384}"

if [[ ! -x "$DS4_SERVER_BIN" ]]; then
  if command -v ds4-server >/dev/null 2>&1; then
    DS4_SERVER_BIN="$(command -v ds4-server)"
  else
    echo "ds4-server not found. Run ./scripts/setup ds4 first or set DS4_SERVER_BIN." >&2
    exit 1
  fi
fi

resolve_model_path() {
  local candidate
  if [[ -n "${MODEL_PATH:-}" ]]; then
    printf '%s\n' "$MODEL_PATH"
    return 0
  fi
  for candidate in "${MODEL_DIR:-$DS4_DIR}/$MODEL_FILE" "$DS4_DIR/gguf/$MODEL_FILE" "$DS4_DIR/$MODEL_FILE"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  printf '%s\n' "${MODEL_DIR:-$DS4_DIR}/$MODEL_FILE"
}

MODEL_PATH="$(resolve_model_path)"
if [[ ! -f "$MODEL_PATH" ]]; then
  echo "ds4 model not found: $MODEL_PATH" >&2
  echo "Download it with ./scripts/download-models eliza-medium --profile <profile>" >&2
  echo "or run ${DS4_DIR}/download_model.sh <target> and set MODEL_PATH/MODEL_DIR/MODEL_FILE." >&2
  exit 1
fi

cmd=(
  "$DS4_SERVER_BIN"
  -m "$MODEL_PATH"
  --ctx "${CTX_SIZE:-32768}"
  --host "${HOST:-0.0.0.0}"
  --port "${PORT:-8001}"
)

# ds4 resolves relative runtime assets from the working directory.
if [[ -d "$DS4_DIR" ]]; then
  cmd+=(--chdir "$DS4_DIR")
fi

case "${DS4_BACKEND_DEVICE:-auto}" in
  auto) ;;
  cuda | metal | cpu) cmd+=("--${DS4_BACKEND_DEVICE}") ;;
  *)
    echo "Unsupported DS4_BACKEND_DEVICE: ${DS4_BACKEND_DEVICE}" >&2
    exit 2
    ;;
esac

if [[ -n "${DS4_POWER:-}" ]]; then
  cmd+=(--power "$DS4_POWER")
fi

if [[ "${DS4_MTP:-false}" == "true" ]]; then
  cmd+=(--mtp)
fi

if [[ -n "${DS4_VISION_FILE:-}" ]]; then
  cmd+=(--vision "$DS4_VISION_FILE")
fi

if [[ "$KV_TO_DISK" == "true" ]]; then
  mkdir -p "$KV_DIR"
  cmd+=(
    --kv-disk-dir "$KV_DIR"
    --kv-disk-space-mb "$KV_MB"
  )
fi

case "$(basename "$MODEL_PATH")" in
  GLM* | glm*)
    if [[ -n "${DS4_POWER:-}" && "${DS4_POWER}" != "100" ]]; then
      echo "Warning: GLM models currently require --power 100; ds4 will refuse to start with ${DS4_POWER}." >&2
    fi
    ;;
esac

if [[ -n "${DS4_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  extra_args=(${DS4_EXTRA_ARGS})
  cmd+=("${extra_args[@]}")
fi

WEAR_LOG="${DS4_WEAR_LOG:-$ROOT_DIR/.runtime/kv-wear-raw.log}"
mkdir -p "$(dirname "$WEAR_LOG")"
echo "Starting eliza-medium ds4: ${cmd[*]}"
echo "KV wear log: $WEAR_LOG"

# Run ds4-server, pass all output through, and tee kv cache stored lines to wear log
"${cmd[@]}" 2>&1 | awk -v wear="$WEAR_LOG" '
  /kv cache stored/ { print >> wear; print; next }
  { print }
'
