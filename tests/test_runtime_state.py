from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
RUNTIME_STATE = ROOT_DIR / "scripts" / "lib" / "runtime_state.py"


class RuntimeStateTest(unittest.TestCase):
    def run_state(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNTIME_STATE), *args],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_concurrent_updates_preserve_all_services(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            state_path = pathlib.Path(temporary_dir) / "service_profiles.json"
            processes = [
                subprocess.Popen(
                    [
                        sys.executable,
                        str(RUNTIME_STATE),
                        "set",
                        "--state",
                        str(state_path),
                        "--service",
                        f"service-{index}",
                        "--profile",
                        f"profile-{index}",
                    ],
                    cwd=ROOT_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for index in range(20)
            ]

            for process in processes:
                _, stderr = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, stderr)

            with state_path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
            self.assertEqual(len(state), 20)
            for index in range(20):
                self.assertEqual(state[f"service-{index}"], f"profile-{index}")

    def test_invalid_json_is_reported_instead_of_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            state_path = pathlib.Path(temporary_dir) / "service_profiles.json"
            state_path.write_text("{invalid", encoding="utf-8")

            result = self.run_state("all", "--state", str(state_path))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Invalid runtime state JSON", result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), "{invalid")


if __name__ == "__main__":
    unittest.main()
