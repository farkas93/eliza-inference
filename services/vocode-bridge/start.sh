#!/usr/bin/env bash
set -euo pipefail

echo "Starting Vocode bridge on ${HOST:-0.0.0.0}:${PORT:-8021}"
exec uv run --project . uvicorn services.vocode_bridge.app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8021}"
