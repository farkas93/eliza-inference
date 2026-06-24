#!/usr/bin/env bash
set -euo pipefail

echo "Starting Vocode bridge on ${HOST:-0.0.0.0}:${PORT:-8021}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VOCODE_VENV="${VOCODE_VENV:-$ROOT_DIR/.venvs/vocode}"
if [[ ! -x "$VOCODE_VENV/bin/python" ]]; then
  echo "Vocode bridge venv missing: $VOCODE_VENV. Run ./scripts/setup vocode." >&2
  exit 1
fi
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$VOCODE_VENV/bin/python" -m uvicorn services.vocode_bridge.app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8021}"
