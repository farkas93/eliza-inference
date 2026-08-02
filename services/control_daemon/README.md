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

## Running manually

```bash
uvicorn services.control_daemon.app:app --host 0.0.0.0 --port 8030
```

## Systemd Service

Deploy using systemd:

```bash
cp systemd/eliza-control-daemon.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now eliza-control-daemon.service
```
