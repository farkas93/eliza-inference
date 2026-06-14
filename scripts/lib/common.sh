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
  QWEN_CODER_PORT="${QWEN_CODER_PORT:-8001}"
  VOICE_LLM_PORT="${VOICE_LLM_PORT:-8002}"
  STT_PORT="${STT_PORT:-8011}"
  TTS_PORT="${TTS_PORT:-8012}"
  VOCODE_BRIDGE_PORT="${VOCODE_BRIDGE_PORT:-8021}"
  VLLM_BIN="${VLLM_BIN:-$VLLM_VENV/bin/vllm}"
  LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-llama-server}"
  PIPER_BIN="${PIPER_BIN:-$TTS_VENV/bin/piper}"
  if [[ "$PIPER_BIN" == "piper" && -x "$TTS_VENV/bin/piper" ]]; then
    PIPER_BIN="$TTS_VENV/bin/piper"
  fi

  export MODEL_HOME HF_HOME LLAMA_CACHE LOG_DIR ELIZA_VENV_DIR BASE_VENV STT_VENV TTS_VENV VLLM_VENV VOCODE_VENV DEFAULT_HOST QWEN_CODER_PORT VOICE_LLM_PORT STT_PORT TTS_PORT VOCODE_BRIDGE_PORT VLLM_BIN LLAMA_SERVER_BIN PIPER_BIN
}

venv_python() {
  local service="$1"
  case "$service" in
    base) echo "$BASE_VENV/bin/python" ;;
    stt) echo "$STT_VENV/bin/python" ;;
    tts) echo "$TTS_VENV/bin/python" ;;
    vllm|qwen-coder|voice-llm-vllm) echo "$VLLM_VENV/bin/python" ;;
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
  ./scripts/$command_name qwen-coder --profile qwen-shared-200k
  ./scripts/$command_name voice-llm --profile voice-gemma4-e4b-default
USAGE
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
      qwen-coder) PROFILE="qwen-llamacpp-32k" ;;
      voice-llm) PROFILE="voice-gemma4-e4b-default" ;;
      stt) PROFILE="stt-faster-whisper-small-cpu" ;;
      tts) PROFILE="tts-piper-lessac" ;;
      voice-assistant) PROFILE="voice-assistant-local" ;;
      vocode-bridge) PROFILE="vocode-bridge-local" ;;
      *)
        echo "No default profile for service: $SERVICE" >&2
        exit 2
        ;;
    esac
  fi

  PROFILE_PATH="$ROOT_DIR/configs/profiles/$PROFILE.env"
  if [[ ! -f "$PROFILE_PATH" ]]; then
    echo "Profile not found: $PROFILE_PATH" >&2
    exit 1
  fi

  SERVICE_DIR="$ROOT_DIR/services/$SERVICE"
  if [[ ! -d "$SERVICE_DIR" ]]; then
    echo "Service not found: $SERVICE_DIR" >&2
    exit 1
  fi

  SESSION_NAME="eliza-$SERVICE"
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
