from __future__ import annotations

import os
import json
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

try:
    from fastapi import HTTPException
except ModuleNotFoundError as exc:  # pragma: no cover - base test venv intentionally stays small
    raise unittest.SkipTest("control daemon dependencies are not installed") from exc

from services.control_daemon import app as control_daemon
from fastapi.testclient import TestClient


class ControlDaemonTest(unittest.TestCase):
    def test_scheduler_advertisement_route_has_no_runtime_fields(self) -> None:
        report = {"version": 1, "rest_url": "http://slurm", "api_versions": ["v0.0.45"], "partitions": [], "workspace": "/jobs", "ready": False}
        with patch.object(control_daemon, "_run_script", return_value={"success": True, "stdout": json.dumps(report)}) as run:
            self.assertEqual(control_daemon.slurm_advertisement(), report)
            run.assert_called_once_with("environment", "advertise")
    def test_token_http_route_authenticates_and_uses_only_host_identity(self) -> None:
        receipt = {"user_name": "training-account", "token": "fixture-jwt", "expires_at": 1000}
        with patch.dict(os.environ, {"CONTROL_DAEMON_TOKEN": "fixture-control-token"}), patch.object(control_daemon, "_run_lifecycle_operation", return_value={"success": True, "stdout": json.dumps(receipt)}) as run:
            client = TestClient(control_daemon.app)
            self.assertEqual(client.post("/training/token").status_code, 401)
            run.assert_not_called()
            response = client.post("/training/token", headers={"Authorization": "Bearer fixture-control-token"}, json={"user_name": "root"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), receipt)
            self.assertEqual(run.call_args.args, ("training/token", "environment", "token"))

    def test_token_delegation_requires_configured_authentication(self) -> None:
        with patch.dict(os.environ, {"CONTROL_DAEMON_TOKEN": ""}):
            with self.assertRaises(HTTPException) as failure:
                control_daemon.training_token()
        self.assertEqual(failure.exception.status_code, 503)

    def test_environment_routes_return_persisted_state(self) -> None:
        state = {"version": 1, "phase": "training", "restore": []}
        with patch.object(control_daemon, "_run_script", return_value={"success": True, "stdout": json.dumps(state)}):
            self.assertEqual(control_daemon.environment_status(), state)
        with patch.object(control_daemon, "_run_lifecycle_operation", return_value={"success": True, "stdout": json.dumps(state)}) as run:
            self.assertEqual(control_daemon.switch_environment("training"), state)
            self.assertEqual(run.call_args.args[:3], ("environment/training", "environment", "training"))

    def test_environment_busy_returns_conflict_and_invalid_mode_is_rejected(self) -> None:
        with patch.object(control_daemon, "_run_lifecycle_operation", return_value={"success": False, "returncode": 3, "stderr": "jobs remain"}):
            with self.assertRaises(HTTPException) as failure:
                control_daemon.switch_environment("inference")
            self.assertEqual(failure.exception.status_code, 409)
        with self.assertRaises(HTTPException) as invalid:
            control_daemon.switch_environment("other")
        self.assertEqual(invalid.exception.status_code, 422)

    def test_authentication_is_disabled_when_token_is_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONTROL_DAEMON_TOKEN", None)
            control_daemon._require_control_token(None)

    def test_authentication_requires_matching_bearer_token_when_enabled(self) -> None:
        with patch.dict(os.environ, {"CONTROL_DAEMON_TOKEN": "secret"}):
            with self.assertRaises(HTTPException) as missing:
                control_daemon._require_control_token(None)
            self.assertEqual(missing.exception.status_code, 401)

            with self.assertRaises(HTTPException) as invalid:
                control_daemon._require_control_token("Bearer wrong")
            self.assertEqual(invalid.exception.status_code, 401)

            control_daemon._require_control_token("Bearer secret")

    def test_concurrent_lifecycle_operation_returns_conflict(self) -> None:
        self.assertTrue(control_daemon._operation_lock.acquire(blocking=False))
        control_daemon._active_operation = "stack/start"
        try:
            with self.assertRaises(HTTPException) as conflict:
                control_daemon._run_lifecycle_operation(
                    "stack/stop",
                    "stop-stack",
                    timeout_seconds=30,
                )
            self.assertEqual(conflict.exception.status_code, 409)
            self.assertIn("stack/start", str(conflict.exception.detail))
        finally:
            control_daemon._active_operation = None
            control_daemon._operation_lock.release()

    def test_timeout_response_includes_stack_status(self) -> None:
        timeout = subprocess.TimeoutExpired(cmd=["start-stack"], timeout=1)
        status_result = subprocess.CompletedProcess(
            args=["status-stack"],
            returncode=0,
            stdout="eliza-medium running",
            stderr="",
        )
        with patch("services.control_daemon.app.subprocess.run", side_effect=[timeout, status_result]):
            with self.assertRaises(HTTPException) as failure:
                control_daemon._run_script("start-stack", timeout_seconds=1)

        self.assertEqual(failure.exception.status_code, 504)
        self.assertEqual(
            failure.exception.detail["stack_status"]["stdout"],
            "eliza-medium running",
        )


if __name__ == "__main__":
    unittest.main()
