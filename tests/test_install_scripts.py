from __future__ import annotations

import pathlib
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]


class InstallScriptTest(unittest.TestCase):
    def test_dgx_sglang_source_build_disables_optional_rust_extensions(self) -> None:
        installer = (ROOT_DIR / "scripts" / "installation-suite" / "install-sglang").read_text(
            encoding="utf-8"
        )

        self.assertIn('SGLANG_BUILD_RUST_EXTS="${SGLANG_BUILD_RUST_EXTS:-none}"', installer)
        self.assertIn('SGLANG_BUILD_RUST_EXTS="$SGLANG_BUILD_RUST_EXTS" uv pip install', installer)

    def test_clean_system_runs_defaults_and_starts_before_smoke_tests(self) -> None:
        installer = (ROOT_DIR / "scripts" / "installation-suite" / "setup-clean-system").read_text(
            encoding="utf-8"
        )

        self.assertNotIn('if [[ $# -eq 0 ]]', installer)
        start_index = installer.index('"$ROOT_DIR/scripts/restart" eliza-medium')
        smoke_index = installer.index('"$ROOT_DIR/scripts/smoke-test" eliza-medium')
        self.assertLess(start_index, smoke_index)


if __name__ == "__main__":
    unittest.main()
