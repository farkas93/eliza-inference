#!/usr/bin/env bash
set -euo pipefail

echo "Starting STT service on ${HOST:-0.0.0.0}:${PORT:-8011} with backend ${BACKEND:-faster-whisper}"
exec uv run --project . uvicorn services.stt.app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8011}"
