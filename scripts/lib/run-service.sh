#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib/common.sh"
set -a
load_env
parse_service_profile "$@"
source_profile
set +a
mkdir -p "$LOG_DIR"
# Preserve attached tmux logs without putting the model in a status-hiding pipeline.
exec > >(tee -a "$LOG_FILE") 2>&1

state_file="$SERVICE_SUPERVISOR_DIR/$SERVICE.supervisor.json"
if [[ "$SERVICE" == "eliza-medium" && "${ELIZA_MEDIUM_AUTORESTART:-true}" == "true" ]]; then
  supervisor_python="$(service_control_python)"
  canonical_profile="${PROFILE_PATH#"$ROOT_DIR/configs/profiles/"}"
  canonical_profile="${canonical_profile%.env}"
  exec "$supervisor_python" -u "$ROOT_DIR/scripts/lib/service_supervisor.py" run \
    --state "$state_file" --service "$SERVICE" --profile "$canonical_profile" \
    --health-url "http://127.0.0.1:${PORT:-$ELIZA_MEDIUM_PORT}/v1/models" \
    --restart-delay "${ELIZA_MEDIUM_RESTART_DELAY_SECONDS:-2}" \
    --max-restart-delay "${ELIZA_MEDIUM_RESTART_MAX_DELAY_SECONDS:-60}" \
    --reset-after "${ELIZA_MEDIUM_RESTART_RESET_SECONDS:-300}" \
    --shutdown-timeout "${SERVICE_SHUTDOWN_TIMEOUT_SECONDS:-10}" \
    -- "$SERVICE_DIR/start.sh"
fi
rm -f "$state_file"
exec "$SERVICE_DIR/start.sh"
