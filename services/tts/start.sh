#!/usr/bin/env bash
set -euo pipefail

echo "Starting TTS service on ${HOST:-0.0.0.0}:${PORT:-8012} with backend ${BACKEND:-piper}"
exec uv run --project . uvicorn services.tts.app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8012}"
