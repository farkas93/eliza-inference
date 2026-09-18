#!/usr/bin/env bash
set -euo pipefail

FLASH_REPO="${FLASH_REPO:-$HOME/src/qwen3.8-Flash-DGX}"
FLASH_IMAGE="${FLASH_IMAGE:-qwen38-flash-dgx}"
FLASH_CONTAINER="${FLASH_CONTAINER:-qwen38-flash}"
FLASH_MODEL="${FLASH_MODEL:-nvidia/Qwen3.8-Flash-Next-NVFP4}"
FLASH_HF_CACHE="${FLASH_HF_CACHE:-${HF_HOME:-$HOME/models/huggingface}}"
FLASH_MODE="${FLASH_MODE:-hybrid}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found. The flash backend runs vLLM from the patched image built by ./scripts/setup flash." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon is not reachable (permissions or service not running)." >&2
  exit 1
fi

if [[ ! -x "$FLASH_REPO/scripts/serve.sh" ]]; then
  echo "flash recipe not found: $FLASH_REPO/scripts/serve.sh" >&2
  echo "Clone and build it with ./scripts/setup flash" >&2
  exit 1
fi

if ! docker image inspect "$FLASH_IMAGE" >/dev/null 2>&1; then
  echo "flash image not built: $FLASH_IMAGE" >&2
  echo "Build it with ./scripts/setup flash" >&2
  exit 1
fi

flash_snapshot_dir() {
  local repo="$FLASH_HF_CACHE/hub/models--${FLASH_MODEL//\//--}" rev
  for rev in "$(cat "$repo/refs/main" 2>/dev/null || true)" "$(cat "$repo/refs/master" 2>/dev/null || true)"; do
    if [[ -n "$rev" && -d "$repo/snapshots/$rev" ]]; then
      printf '%s\n' "$repo/snapshots/$rev"
      return 0
    fi
  done
  local candidate
  shopt -s nullglob
  for candidate in "$repo"/snapshots/*/; do
    case "$candidate" in
      *-fp8hybrid*) continue ;;
    esac
    if [[ -d "$candidate" ]]; then
      printf '%s\n' "${candidate%/}"
      return 0
    fi
  done
  shopt -u nullglob
  return 1
}

SNAPSHOT_DIR="$(flash_snapshot_dir || true)"
if [[ -z "$SNAPSHOT_DIR" ]]; then
  echo "flash checkpoint not found under $FLASH_HF_CACHE/hub for $FLASH_MODEL" >&2
  echo "Download it with ./scripts/download-models eliza-medium --profile <flash profile>" >&2
  exit 1
fi

if [[ "$FLASH_MODE" == "hybrid" || "$FLASH_MODE" == "hybrid-mtp" ]]; then
  if [[ ! -f "${SNAPSHOT_DIR}-fp8hybrid/.prepared" ]]; then
    echo "hybrid checkpoint layout is missing: ${SNAPSHOT_DIR}-fp8hybrid" >&2
    echo "Prepare it with ./scripts/download-models eliza-medium --profile <flash profile>" >&2
    exit 1
  fi
fi

pass_env() {
  local upstream_name="$1" local_name="$2"
  local value="${!local_name:-}"
  if [[ -n "$value" ]]; then
    export "$upstream_name=$value"
  fi
}

export NAME="$FLASH_CONTAINER"
export IMAGE="$FLASH_IMAGE"
export MODEL="$FLASH_MODEL"
export HF_CACHE="$FLASH_HF_CACHE"
pass_env MODE FLASH_MODE
pass_env PORT PORT
pass_env CTX CTX_SIZE
pass_env YARN FLASH_YARN
pass_env MTP FLASH_MTP
pass_env SEQS FLASH_SEQS
pass_env GPU_MEM FLASH_GPU_MEM
pass_env KV_DTYPE FLASH_KV_DTYPE
pass_env KV_CACHE_MEM FLASH_KV_CACHE_MEM
pass_env PREFIX_CACHE FLASH_PREFIX_CACHE
pass_env DET_TOPK FLASH_DET_TOPK
pass_env EXACT_TOPK FLASH_EXACT_TOPK
pass_env PAD_M4 FLASH_PAD_M4
pass_env DRAFT_VOCAB FLASH_DRAFT_VOCAB
pass_env MADVISE FLASH_MADVISE
pass_env WORKERS FLASH_WORKERS
pass_env PREWARM FLASH_PREWARM
pass_env COMPILE_CACHE FLASH_COMPILE_CACHE
pass_env LOG_REQUESTS FLASH_LOG_REQUESTS
pass_env PROM_MULTIPROC FLASH_PROM_MULTIPROC
pass_env BASE FLASH_BASE
pass_env EXTRA FLASH_EXTRA_ARGS

echo "Starting eliza-medium flash: image=$FLASH_IMAGE container=$FLASH_CONTAINER model=$FLASH_MODEL name=${MODEL_NAME:-qwen3.8-flash-next} serving on :${PORT:-8001} mode=${FLASH_MODE} ctx=${CTX_SIZE:-262144}"
echo "First boot loads ~75 GiB of weights and can take 8-13 minutes; watch ./scripts/logs eliza-medium"

"$FLASH_REPO/scripts/serve.sh"

# serve.sh starts the container detached; stay attached to its logs so the tmux
# session, ./scripts/status and the log file follow the container lifecycle.
exec docker logs -f --timestamps "$FLASH_CONTAINER"
