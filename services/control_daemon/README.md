# Eliza Inference Control Daemon

FastAPI daemon exposing a REST interface on port `8030` to start, stop, and check the status of local DGX inference services (`eliza-medium`, `eliza-small`, STT, TTS, vocode-bridge).

## Purpose

When running heavy PySpark / GPU training jobs (e.g., via `nlp-lab` or JupyterHub notebooks), training scripts can issue a REST call to `http://localhost:8030/stack/stop` to safely unload model weights from GPU VRAM and system memory, and call `http://localhost:8030/stack/start` when training finishes.

## Endpoints

- `GET /health` - Health check endpoint
- `GET /status` - Stack status output (`./scripts/status-stack`)
- `POST /stack/start` - Starts the full inference stack (`./scripts/start-stack`)
- `POST /stack/stop` - Stops the full inference stack (`./scripts/stop-stack`)
- `POST /service/{name}/start` - Starts a specific service (`./scripts/start <name>`)
- `POST /service/{name}/stop` - Stops a specific service (`./scripts/stop <name>`)

Mutating operations are serialized. If another start/stop operation is active, the daemon returns HTTP `409` instead of running both commands concurrently.

## Optional Authentication

Authentication is disabled by default for trusted-LAN use. To protect mutating `POST` endpoints, set this in `.env` and restart the daemon:

```bash
CONTROL_DAEMON_TOKEN="replace-with-a-random-token"
```

Clients must then send:

```text
Authorization: Bearer replace-with-a-random-token
```

`GET /health` and `GET /status` remain unauthenticated. Command timeouts are configurable with `CONTROL_START_TIMEOUT_SECONDS`, `CONTROL_STOP_TIMEOUT_SECONDS`, and `CONTROL_STATUS_TIMEOUT_SECONDS`.

## Quick Installation & Systemd Setup

Run the installation script inside `eliza-inference`:

```bash
./scripts/installation-suite/install-control-daemon
```

This automatically generates the systemd service file tailored to your local path (`~/eliza-inference`), exports `PYTHONPATH`, and starts the systemd service.

## Running manually

```bash
./services/control-daemon/start.sh
```
