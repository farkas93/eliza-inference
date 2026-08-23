from __future__ import annotations

import os
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


class ControlDaemonTest(unittest.TestCase):
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
