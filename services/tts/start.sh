#!/usr/bin/env bash
set -euo pipefail

echo "Starting TTS service on ${HOST:-0.0.0.0}:${PORT:-8012} with backend ${BACKEND:-piper}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TTS_VENV="${TTS_VENV:-$ROOT_DIR/.venvs/tts}"
PIPER_BIN="${PIPER_BIN:-$TTS_VENV/bin/piper}"
if [[ "$PIPER_BIN" == "piper" && -x "$TTS_VENV/bin/piper" ]]; then
  PIPER_BIN="$TTS_VENV/bin/piper"
fi
if [[ ! -x "$TTS_VENV/bin/python" ]]; then
  echo "TTS venv missing: $TTS_VENV. Run ./scripts/install-tts." >&2
  exit 1
fi
if [[ ! -x "$PIPER_BIN" ]]; then
  echo "Piper binary missing: $PIPER_BIN. Run ./scripts/install-tts." >&2
  exit 1
fi
export PIPER_BIN
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
echo "Using Piper binary: $PIPER_BIN"
exec "$TTS_VENV/bin/python" -m uvicorn services.tts.app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8012}"
