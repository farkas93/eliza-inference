from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tempfile
import textwrap
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
START = ROOT_DIR / "scripts" / "start"
RESTART = ROOT_DIR / "scripts" / "restart"


class ServiceLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.temp_path = pathlib.Path(self.temporary_dir.name)
        self.bin_dir = self.temp_path / "bin"
        self.bin_dir.mkdir()
        fake_tmux = self.bin_dir / "tmux"
        fake_tmux.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                command_name="${1:-}"
                shift || true
                session=""
                while [[ $# -gt 0 ]]; do
                  if [[ "$1" == "-t" || "$1" == "-s" ]]; then
                    session="${2:-}"
                    shift 2
                  else
                    shift
                  fi
                done
                marker="$FAKE_TMUX_DIR/$session"
                case "$command_name" in
                  has-session) [[ -f "$marker" ]] ;;
                  new-session)
                    if [[ "${FAKE_TMUX_FAIL_NEW:-false}" != "true" ]]; then
                      touch "$marker"
                    fi
                    ;;
                  kill-session) rm -f "$marker" ;;
                  *) exit 2 ;;
                esac
                """
            ),
            encoding="utf-8",
        )
        fake_tmux.chmod(0o755)

        self.state_path = self.temp_path / "service_profiles.json"
        self.env = os.environ.copy()
        self.env.update(
            {
                "PATH": f"{self.bin_dir}:{self.env['PATH']}",
                "BASE_VENV": str(ROOT_DIR / ".venv"),
                "FAKE_TMUX_DIR": str(self.temp_path),
                "LOG_DIR": str(self.temp_path / "logs"),
                "RUNTIME_STATE_FILE": str(self.state_path),
                "START_LIVENESS_DELAY_SECONDS": "0",
            }
        )

    def tearDown(self) -> None:
        self.temporary_dir.cleanup()

    def run_command(self, command: pathlib.Path, profile: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(command), "eliza-small", "--profile", profile],
            cwd=ROOT_DIR,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )

    def load_state(self) -> dict[str, str]:
        if not self.state_path.exists():
            return {}
        with self.state_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def test_start_rejects_different_profile_for_live_session(self) -> None:
        first = "small/gemma4-e4b-q4-llamacpp-128k"
        second = "small/gemma4-e2b-q4-llamacpp-8k"

        self.assertEqual(self.run_command(START, first).returncode, 0)
        result = self.run_command(START, second)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already running with profile", result.stderr)
        self.assertEqual(self.load_state()["eliza-small"], first)

    def test_restart_switches_recorded_profile(self) -> None:
        first = "small/gemma4-e4b-q4-llamacpp-128k"
        second = "small/gemma4-e2b-q4-llamacpp-8k"

        self.assertEqual(self.run_command(START, first).returncode, 0)
        result = self.run_command(RESTART, second)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.load_state()["eliza-small"], second)

    def test_start_records_canonical_profile_for_alias(self) -> None:
        result = self.run_command(START, "small/gemma4-e2b-fast")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.load_state()["eliza-small"],
            "small/gemma4-e2b-q4-llamacpp-8k",
        )

    def test_failed_launch_does_not_record_profile(self) -> None:
        self.env["FAKE_TMUX_FAIL_NEW"] = "true"
        result = self.run_command(START, "small/gemma4-e4b-q4-llamacpp-128k")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exited during startup", result.stderr)
        self.assertNotIn("eliza-small", self.load_state())


if __name__ == "__main__":
    unittest.main()
