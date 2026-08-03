#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8030}"

echo "Starting Eliza Control Daemon on ${HOST}:${PORT} using uv"
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

if command -v uv >/dev/null 2>&1; then
  exec uv run --project "$ROOT_DIR" python -m uvicorn services.control_daemon.app:app --host "$HOST" --port "$PORT"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  exec "$ROOT_DIR/.venv/bin/python" -m uvicorn services.control_daemon.app:app --host "$HOST" --port "$PORT"
else
  exec python3 -m uvicorn services.control_daemon.app:app --host "$HOST" --port "$PORT"
fi
