from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

app = FastAPI(
    title="Eliza Inference Control Daemon",
    version="1.0.0",
    description="REST API interface for starting, stopping, and inspecting local DGX inference services.",
)

logger = logging.getLogger("control-daemon")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def _run_script(script_name: str, *args: str) -> dict[str, Any]:
    script_path = ROOT_DIR / "scripts" / script_name
    if not script_path.exists():
        raise HTTPException(status_code=500, detail=f"Script not found: {script_name}")

    cmd = [str(script_path), *args]
    logger.info("Executing command: %s", " ".join(cmd))
    try:
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True, timeout=120)
        return {
            "success": res.returncode == 0,
            "returncode": res.returncode,
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip(),
        }
    except subprocess.TimeoutExpired as exc:
        logger.error("Command timed out: %s", " ".join(cmd))
        raise HTTPException(status_code=504, detail=f"Script timed out: {script_name}") from exc
    except Exception as exc:
        logger.exception("Failed to execute: %s", " ".join(cmd))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "control-daemon", "root_dir": str(ROOT_DIR)}


@app.get("/status")
def status() -> dict[str, Any]:
    res = _run_script("status-stack")
    return {
        "status": "online" if res["success"] else "degraded",
        "output": res["stdout"],
        "error": res["stderr"] if not res["success"] else None,
    }


@app.post("/stack/start")
def start_stack() -> dict[str, Any]:
    logger.info("Received request to start full inference stack")
    res = _run_script("start-stack")
    if not res["success"]:
        raise HTTPException(status_code=500, detail=f"Failed to start stack: {res['stderr']}")
    return {"status": "started", "output": res["stdout"]}


@app.post("/stack/stop")
def stop_stack() -> dict[str, Any]:
    logger.info("Received request to stop full inference stack (releasing GPU/VRAM)")
    res = _run_script("stop-stack")
    if not res["success"]:
        raise HTTPException(status_code=500, detail=f"Failed to stop stack: {res['stderr']}")
    return {"status": "stopped", "output": res["stdout"]}


@app.post("/service/{service_name}/start")
def start_service(service_name: str) -> dict[str, Any]:
    logger.info("Received request to start service: %s", service_name)
    res = _run_script("start", service_name)
    if not res["success"]:
        raise HTTPException(status_code=500, detail=f"Failed to start service {service_name}: {res['stderr']}")
    return {"status": "started", "service": service_name, "output": res["stdout"]}


@app.post("/service/{service_name}/stop")
def stop_service(service_name: str) -> dict[str, Any]:
    logger.info("Received request to stop service: %s", service_name)
    res = _run_script("stop", service_name)
    if not res["success"]:
        raise HTTPException(status_code=500, detail=f"Failed to stop service {service_name}: {res['stderr']}")
    return {"status": "stopped", "service": service_name, "output": res["stdout"]}
