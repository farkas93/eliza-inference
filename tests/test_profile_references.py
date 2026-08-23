from __future__ import annotations

import pathlib
import subprocess
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]


class ProfileReferenceTest(unittest.TestCase):
    def test_all_documented_and_executable_profiles_resolve(self) -> None:
        result = subprocess.run(
            [str(ROOT_DIR / "scripts" / "validate-profile-references")],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validated", result.stdout)


if __name__ == "__main__":
    unittest.main()
