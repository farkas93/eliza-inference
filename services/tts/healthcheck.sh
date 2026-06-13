#!/usr/bin/env bash
set -euo pipefail

url="http://127.0.0.1:${PORT:-8012}/health"
if curl -fsS "$url" >/dev/null; then
  echo "health: ok ($url)"
else
  echo "health: failed ($url)" >&2
  exit 1
fi
