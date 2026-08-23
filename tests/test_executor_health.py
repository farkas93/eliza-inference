from __future__ import annotations

import pathlib
import sys
import unittest
from unittest.mock import patch


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "eliza-cli"))

from core.executor import ExecutionError, Executor


class ExecutorHealthTest(unittest.TestCase):
    def test_health_wait_fails_immediately_when_session_exits(self) -> None:
        executor = Executor(ROOT_DIR)

        with patch.object(executor, "_service_session_running", return_value=False):
            with self.assertRaisesRegex(
                ExecutionError,
                r"Service exited before becoming healthy.*logs/eliza-medium\.log",
            ):
                executor._wait_for_health(
                    "http://127.0.0.1:8001/v1/models",
                    timeout_seconds=900,
                    progress_callback=None,
                    service_name="eliza-medium",
                )

    def test_start_cleans_up_state_after_health_failure(self) -> None:
        executor = Executor(ROOT_DIR)
        failure = ExecutionError("service exited")

        with (
            patch.object(executor, "ensure_service_ready"),
            patch.object(executor, "_run_command"),
            patch.object(executor, "_wait_for_health", side_effect=failure),
            patch.object(executor, "_cleanup_failed_service_start") as cleanup,
        ):
            with self.assertRaisesRegex(ExecutionError, "service exited"):
                executor.start_service(
                    "eliza-medium",
                    "medium/qwen3.8-27b-fp8-sglang-256k",
                    health_url="http://127.0.0.1:8001/v1/models",
                )

        cleanup.assert_called_once_with(
            "eliza-medium",
            "medium/qwen3.8-27b-fp8-sglang-256k",
            None,
        )


if __name__ == "__main__":
    unittest.main()
