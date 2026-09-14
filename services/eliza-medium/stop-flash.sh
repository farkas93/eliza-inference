#!/usr/bin/env bash
set -euo pipefail

FLASH_CONTAINER="${FLASH_CONTAINER:-qwen38-flash}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[skip] docker not found; no flash container to stop."
  exit 0
fi

state="$(docker inspect -f '{{.State.Status}}' "$FLASH_CONTAINER" 2>/dev/null || echo absent)"
case "$state" in
  absent)
    echo "[skip] flash container not present: $FLASH_CONTAINER"
    ;;
  *)
    echo "Stopping flash container $FLASH_CONTAINER ($state)"
    docker stop "$FLASH_CONTAINER" >/dev/null
    ;;
esac
