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


if __name__ == "__main__":
    unittest.main()
