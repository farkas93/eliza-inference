#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

load_env() {
  if [[ -f "$ROOT_DIR/.env" ]]; then
    # shellcheck disable=SC1091
    source "$ROOT_DIR/.env"
  fi

  MODEL_HOME="${MODEL_HOME:-$HOME/models}"
  HF_HOME="${HF_HOME:-$MODEL_HOME/huggingface}"
  LLAMA_CACHE="${LLAMA_CACHE:-$MODEL_HOME/llama}"
  LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"
  ELIZA_VENV_DIR="${ELIZA_VENV_DIR:-$ROOT_DIR/.venvs}"
  BASE_VENV="${BASE_VENV:-$ELIZA_VENV_DIR/base}"
  STT_VENV="${STT_VENV:-$ELIZA_VENV_DIR/stt}"
  TTS_VENV="${TTS_VENV:-$ELIZA_VENV_DIR/tts}"
  VLLM_VENV="${VLLM_VENV:-$ELIZA_VENV_DIR/vllm}"
  VOCODE_VENV="${VOCODE_VENV:-$ELIZA_VENV_DIR/vocode}"
  DEFAULT_HOST="${DEFAULT_HOST:-0.0.0.0}"
  ELIZA_MEDIUM_PORT="${ELIZA_MEDIUM_PORT:-8001}"
  ELIZA_SMALL_PORT="${ELIZA_SMALL_PORT:-8002}"
  STT_PORT="${STT_PORT:-8011}"
  TTS_PORT="${TTS_PORT:-8012}"
  VOCODE_BRIDGE_PORT="${VOCODE_BRIDGE_PORT:-8021}"
  VLLM_BIN="${VLLM_BIN:-$VLLM_VENV/bin/vllm}"
  LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-llama-server}"
  PIPER_BIN="${PIPER_BIN:-$TTS_VENV/bin/piper}"
  if [[ "$PIPER_BIN" == "piper" && -x "$TTS_VENV/bin/piper" ]]; then
    PIPER_BIN="$TTS_VENV/bin/piper"
  fi

  export MODEL_HOME HF_HOME LLAMA_CACHE LOG_DIR ELIZA_VENV_DIR BASE_VENV STT_VENV TTS_VENV VLLM_VENV VOCODE_VENV DEFAULT_HOST ELIZA_MEDIUM_PORT ELIZA_SMALL_PORT STT_PORT TTS_PORT VOCODE_BRIDGE_PORT VLLM_BIN LLAMA_SERVER_BIN PIPER_BIN
}

venv_python() {
  local service="$1"
  case "$service" in
    base) echo "$BASE_VENV/bin/python" ;;
    stt) echo "$STT_VENV/bin/python" ;;
    tts) echo "$TTS_VENV/bin/python" ;;
    vllm|eliza-medium|eliza-small-vllm) echo "$VLLM_VENV/bin/python" ;;
    vocode|vocode-bridge) echo "$VOCODE_VENV/bin/python" ;;
    *) echo "$BASE_VENV/bin/python" ;;
  esac
}

ensure_venv() {
  local path="$1"
  if [[ ! -x "$path/bin/python" ]]; then
    uv venv "$path"
  fi
}

run_base_python() {
  "$BASE_VENV/bin/python" "$@"
}

usage_service_profile() {
  local command_name="$1"
  cat <<USAGE
Usage: ./scripts/$command_name <service> [--profile <profile-name>]

Examples:
  ./scripts/$command_name eliza-medium --profile medium/qwen-llamacpp-32k
  ./scripts/$command_name eliza-small --profile small/gemma4-e2b-fast
USAGE
}

resolve_profile_path() {
  local profile="$1"
  local candidate

  candidate="$ROOT_DIR/configs/profiles/$profile.env"
  if [[ -f "$candidate" ]]; then
    echo "$candidate"
    return 0
  fi

  case "$profile" in
    eliza-medium-*) profile="medium/${profile#eliza-medium-}" ;;
    eliza-small-*) profile="small/${profile#eliza-small-}" ;;
    stt-*) profile="stt/${profile#stt-}" ;;
    tts-*) profile="tts/${profile#tts-}" ;;
    vocode-bridge-*) profile="vocode/${profile#vocode-}" ;;
    voice-assistant-*) profile="voice/${profile#voice-}" ;;
  esac

  candidate="$ROOT_DIR/configs/profiles/$profile.env"
  if [[ -f "$candidate" ]]; then
    echo "$candidate"
    return 0
  fi

  return 1
}

parse_service_profile() {
  SERVICE="${1:-}"
  PROFILE=""
  shift || true

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --profile)
        PROFILE="${2:-}"
        shift 2
        ;;
      -h|--help)
        usage_service_profile "${COMMAND_NAME:-start}"
        exit 0
        ;;
      *)
        echo "Unknown argument: $1" >&2
        exit 2
        ;;
    esac
  done

  if [[ -z "$SERVICE" ]]; then
    usage_service_profile "${COMMAND_NAME:-start}"
    exit 2
  fi

  if [[ -z "$PROFILE" ]]; then
    case "$SERVICE" in
      eliza-medium) PROFILE="medium/qwen-llamacpp-32k" ;;
      eliza-small) PROFILE="small/gemma4-e2b-fast" ;;
      stt) PROFILE="stt/faster-whisper-small-cpu" ;;
      tts) PROFILE="tts/piper-lessac" ;;
      voice-assistant) PROFILE="voice/assistant-local" ;;
      vocode-bridge) PROFILE="vocode/bridge-local" ;;
      *)
        echo "No default profile for service: $SERVICE" >&2
        exit 2
        ;;
    esac
  fi

  PROFILE_PATH="$(resolve_profile_path "$PROFILE" || true)"
  if [[ -z "$PROFILE_PATH" ]]; then
    echo "Profile not found under configs/profiles: $PROFILE" >&2
    exit 1
  fi

  SERVICE_DIR="$ROOT_DIR/services/$SERVICE"
  if [[ ! -d "$SERVICE_DIR" ]]; then
    echo "Service not found: $SERVICE_DIR" >&2
    exit 1
  fi

  if [[ "$SERVICE" == eliza-* ]]; then
    SESSION_NAME="$SERVICE"
  else
    SESSION_NAME="eliza-$SERVICE"
  fi
  LOG_FILE="$LOG_DIR/$SERVICE.log"
  export SERVICE PROFILE PROFILE_PATH SERVICE_DIR SESSION_NAME LOG_FILE
}

source_profile() {
  load_env
  set -a
  # shellcheck disable=SC1090
  source "$PROFILE_PATH"
  set +a
}

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Missing required command: $name" >&2
    return 1
  fi
}

tmux_has_session() {
  tmux has-session -t "$SESSION_NAME" >/dev/null 2>&1
}

service_base_url() {
  source_profile
  echo "http://127.0.0.1:${PORT}/v1"
}

service_model_name() {
  source_profile
  echo "${MODEL_NAME:-${MODEL_ID:-${MODEL_FILE:-local-model}}}"
}
