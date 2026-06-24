#!/usr/bin/env bash
set -euo pipefail

echo "Starting STT service on ${HOST:-0.0.0.0}:${PORT:-8011} with backend ${BACKEND:-faster-whisper}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STT_VENV="${STT_VENV:-$ROOT_DIR/.venvs/stt}"
if [[ ! -x "$STT_VENV/bin/python" ]]; then
  echo "STT venv missing: $STT_VENV. Run ./scripts/setup stt." >&2
  exit 1
fi
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$STT_VENV/bin/python" -m uvicorn services.stt.app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8011}"
