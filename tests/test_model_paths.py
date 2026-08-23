from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "eliza-cli"))

from core.model_manager import ModelManager


class ModelPathTest(unittest.TestCase):
    def test_nested_env_values_resolve_for_sglang_model_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = pathlib.Path(temporary_dir)
            model_home = root / "models"
            (root / ".env").write_text(
                f'MODEL_HOME="{model_home}"\nHF_HOME="$MODEL_HOME/huggingface"\n',
                encoding="utf-8",
            )
            profile_path = root / "qwen.env"
            profile_path.write_text(
                '\n'.join(
                    [
                        'BACKEND="sglang"',
                        'MODEL_ID="Qwen/Qwen3.8-27B-FP8"',
                        'MODEL_DIR="$HF_HOME/hub/Qwen/Qwen3.8-27B-FP8"',
                    ]
                ),
                encoding="utf-8",
            )
            profile = types.SimpleNamespace(
                name="medium/qwen3.8-27b-fp8-sglang-256k",
                path=str(profile_path),
                backend="sglang",
            )

            manager = ModelManager(root)
            expected = model_home / "huggingface" / "hub" / "Qwen" / "Qwen3.8-27B-FP8"

            self.assertEqual(manager.env["HF_HOME"], str(model_home / "huggingface"))
            self.assertEqual(manager._expected_paths_for_profile(profile), [expected.resolve()])

    def test_cyclic_env_values_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = pathlib.Path(temporary_dir)
            (root / ".env").write_text(
                'MODEL_HOME="$HF_HOME/models"\nHF_HOME="$MODEL_HOME/huggingface"\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Cyclic environment variable reference"):
                ModelManager(root)

    def test_sglang_launcher_prefers_local_model_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            temp_path = pathlib.Path(temporary_dir)
            fake_sglang = temp_path / "sglang"
            args_path = temp_path / "args.txt"
            fake_sglang.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    printf '%s\n' "$@" > "$SGLANG_ARGS_FILE"
                    """
                ),
                encoding="utf-8",
            )
            fake_sglang.chmod(0o755)
            local_model = temp_path / "Qwen3.8-27B-FP8"
            local_model.mkdir()

            env = os.environ.copy()
            env.update(
                {
                    "SGLANG_PYTHON": str(fake_sglang),
                    "SGLANG_ARGS_FILE": str(args_path),
                    "MODEL_ID": "Qwen/Qwen3.8-27B-FP8",
                    "MODEL_DIR": str(local_model),
                    "HOST": "127.0.0.1",
                    "PORT": "8001",
                }
            )
            result = subprocess.run(
                [str(ROOT_DIR / "services" / "eliza-medium" / "start-sglang.sh")],
                cwd=ROOT_DIR,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            arguments = args_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(arguments[:2], ["-m", "sglang.launch_server"])
            model_path_index = arguments.index("--model-path") + 1
            self.assertEqual(arguments[model_path_index], str(local_model))


if __name__ == "__main__":
    unittest.main()
