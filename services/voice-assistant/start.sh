#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'MSG'
voice-assistant is a placeholder for the Vocode orchestration layer.
Start stt, eliza-small, and tts independently, then point Vocode at their /v1 endpoints.
See docs/vocode-pipeline.md.
MSG
exit 1
