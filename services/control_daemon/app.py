from __future__ import annotations

import logging
import os
import secrets
import subprocess
import threading
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException

app = FastAPI(
    title="Eliza Inference Control Daemon",
    version="1.0.0",
    description="REST API interface for starting, stopping, and inspecting local DGX inference services.",
)

logger = logging.getLogger("control-daemon")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONTROL_START_TIMEOUT_SECONDS = int(os.environ.get("CONTROL_START_TIMEOUT_SECONDS", "1200"))
CONTROL_STOP_TIMEOUT_SECONDS = int(os.environ.get("CONTROL_STOP_TIMEOUT_SECONDS", "180"))
CONTROL_STATUS_TIMEOUT_SECONDS = int(os.environ.get("CONTROL_STATUS_TIMEOUT_SECONDS", "30"))
_operation_lock = threading.Lock()
_active_operation: str | None = None


def _require_control_token(authorization: str | None = Header(default=None)) -> None:
    expected_token = os.environ.get("CONTROL_DAEMON_TOKEN", "")
    if not expected_token:
        return

    scheme, separator, provided_token = (authorization or "").partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not secrets.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing control daemon token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _status_snapshot() -> dict[str, Any]:
    command = [str(ROOT_DIR / "scripts" / "status-stack")]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=CONTROL_STATUS_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    return {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _run_script(script_name: str, *args: str, timeout_seconds: int = CONTROL_STATUS_TIMEOUT_SECONDS) -> dict[str, Any]:
    script_path = ROOT_DIR / "scripts" / script_name
    if not script_path.exists():
        raise HTTPException(status_code=500, detail=f"Script not found: {script_name}")

    cmd = [str(script_path), *args]
    logger.info("Executing command: %s", " ".join(cmd))
    try:
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, timeout=timeout_seconds)
        return {
            "success": res.returncode == 0,
            "returncode": res.returncode,
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip(),
        }
    except subprocess.TimeoutExpired as exc:
        logger.error("Command timed out: %s", " ".join(cmd))
        raise HTTPException(
            status_code=504,
            detail={
                "message": f"Script timed out after {timeout_seconds}s: {script_name}",
                "stack_status": _status_snapshot(),
            },
        ) from exc
    except Exception as exc:
        logger.exception("Failed to execute: %s", " ".join(cmd))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _run_lifecycle_operation(
    operation_name: str,
    script_name: str,
    *args: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    global _active_operation
    if not _operation_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail=f"Another lifecycle operation is running: {_active_operation or 'unknown'}",
        )
    _active_operation = operation_name
    try:
        return _run_script(script_name, *args, timeout_seconds=timeout_seconds)
    finally:
        _active_operation = None
        _operation_lock.release()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "control-daemon", "root_dir": str(ROOT_DIR)}


@app.get("/status")
def status() -> dict[str, Any]:
    res = _run_script("status-stack", timeout_seconds=CONTROL_STATUS_TIMEOUT_SECONDS)
    return {
        "status": "online" if res["success"] else "degraded",
        "output": res["stdout"],
        "error": res["stderr"] if not res["success"] else None,
    }


@app.post("/stack/start", dependencies=[Depends(_require_control_token)])
def start_stack() -> dict[str, Any]:
    logger.info("Received request to start full inference stack")
    res = _run_lifecycle_operation(
        "stack/start",
        "start-stack",
        timeout_seconds=CONTROL_START_TIMEOUT_SECONDS,
    )
    if not res["success"]:
        raise HTTPException(status_code=500, detail=f"Failed to start stack: {res['stderr']}")
    return {"status": "started", "output": res["stdout"]}


@app.post("/stack/stop", dependencies=[Depends(_require_control_token)])
def stop_stack() -> dict[str, Any]:
    logger.info("Received request to stop full inference stack (releasing GPU/VRAM)")
    res = _run_lifecycle_operation(
        "stack/stop",
        "stop-stack",
        timeout_seconds=CONTROL_STOP_TIMEOUT_SECONDS,
    )
    if not res["success"]:
        raise HTTPException(status_code=500, detail=f"Failed to stop stack: {res['stderr']}")
    return {"status": "stopped", "output": res["stdout"]}


@app.post("/service/{service_name}/start", dependencies=[Depends(_require_control_token)])
def start_service(service_name: str) -> dict[str, Any]:
    logger.info("Received request to start service: %s", service_name)
    res = _run_lifecycle_operation(
        f"service/{service_name}/start",
        "start",
        service_name,
        timeout_seconds=CONTROL_START_TIMEOUT_SECONDS,
    )
    if not res["success"]:
        raise HTTPException(status_code=500, detail=f"Failed to start service {service_name}: {res['stderr']}")
    return {"status": "started", "service": service_name, "output": res["stdout"]}


@app.post("/service/{service_name}/stop", dependencies=[Depends(_require_control_token)])
def stop_service(service_name: str) -> dict[str, Any]:
    logger.info("Received request to stop service: %s", service_name)
    res = _run_lifecycle_operation(
        f"service/{service_name}/stop",
        "stop",
        service_name,
        timeout_seconds=CONTROL_STOP_TIMEOUT_SECONDS,
    )
    if not res["success"]:
        raise HTTPException(status_code=500, detail=f"Failed to stop service {service_name}: {res['stderr']}")
    return {"status": "stopped", "service": service_name, "output": res["stdout"]}
