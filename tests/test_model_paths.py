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
                    "TRUST_REMOTE_CODE": "true",
                    "KV_CACHE_DTYPE": "fp8_e4m3",
                    "ATTENTION_BACKEND": "flashinfer",
                    "CHUNKED_PREFILL_SIZE": "2048",
                    "REASONING_PARSER": "qwen3",
                    "TOOL_CALL_PARSER": "qwen3_coder",
                    "MAMBA_RADIX_CACHE_STRATEGY": "extra_buffer",
                    "MAMBA_SSM_DTYPE": "float32",
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
            self.assertIn("--trust-remote-code", arguments)
            expected_options = {
                "--kv-cache-dtype": "fp8_e4m3",
                "--attention-backend": "flashinfer",
                "--chunked-prefill-size": "2048",
                "--reasoning-parser": "qwen3",
                "--tool-call-parser": "qwen3_coder",
                "--mamba-radix-cache-strategy": "extra_buffer",
                "--mamba-ssm-dtype": "float32",
            }
            for option, expected_value in expected_options.items():
                with self.subTest(option=option):
                    self.assertEqual(arguments[arguments.index(option) + 1], expected_value)

    def test_list_models_missing_file_has_missing_status_and_no_parent_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = pathlib.Path(temporary_dir)
            model_home = root / "models"
            (root / ".env").write_text(f'MODEL_HOME="{model_home}"\n', encoding="utf-8")
            profile_path = root / "missing.env"
            profile_path.write_text(
                "\n".join(
                    [
                        'BACKEND="ds4dfm"',
                        'MODEL_DIR="$MODEL_HOME/ds4dfm"',
                        'MODEL_FILE="MQ-Q5-SSD-PLE-BF16/Qwen3.8-Flash-Next-MQ-Q5-SSD-PLE-BF16-00001-of-00003.gguf"',
                        'SIDECAR_DIR="MQ-Q6-SSD-PLE-BF16/ple"',
                    ]
                ),
                encoding="utf-8",
            )
            profile = types.SimpleNamespace(
                name="medium/qwen3.8-flash-next-ds4dfm-262k",
                path=str(profile_path),
                backend="ds4dfm",
            )

            manager = ModelManager(root)
            entries = manager.list_models({profile.name: profile})

            by_path = {entry.path: entry for entry in entries}
            expected_model_path = str((model_home / "ds4dfm" / "MQ-Q5-SSD-PLE-BF16" / "Qwen3.8-Flash-Next-MQ-Q5-SSD-PLE-BF16-00001-of-00003.gguf").resolve())
            expected_sidecar_path = str((model_home / "ds4dfm" / "MQ-Q6-SSD-PLE-BF16" / "ple").resolve())

            self.assertIn(expected_model_path, by_path)
            self.assertEqual(by_path[expected_model_path].status, "missing")
            self.assertEqual(by_path[expected_model_path].size_bytes, 0)

            self.assertIn(expected_sidecar_path, by_path)
            self.assertEqual(by_path[expected_sidecar_path].status, "missing")
            self.assertEqual(by_path[expected_sidecar_path].size_bytes, 0)

            # Ensure parent directories are NOT listed as model entries
            self.assertNotIn(str((model_home / "ds4dfm" / "MQ-Q5-SSD-PLE-BF16").resolve()), by_path)
            self.assertNotIn(str((model_home / "ds4dfm").resolve()), by_path)
            # Ensure no orphans
            self.assertEqual([e for e in entries if e.status == "orphan"], [])

    def test_list_models_sums_shards_and_links_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = pathlib.Path(temporary_dir)
            model_home = root / "models"
            ds4_dir = model_home / "ds4dfm"
            q5_dir = ds4_dir / "MQ-Q5-SSD-PLE-BF16"
            q6_ple_dir = ds4_dir / "MQ-Q6-SSD-PLE-BF16" / "ple"
            q5_dir.mkdir(parents=True)
            q6_ple_dir.mkdir(parents=True)

            (root / ".env").write_text(f'MODEL_HOME="{model_home}"\n', encoding="utf-8")

            # Create 3 shards with known sizes
            shard1 = q5_dir / "Qwen3.8-Flash-Next-MQ-Q5-SSD-PLE-BF16-00001-of-00003.gguf"
            shard2 = q5_dir / "Qwen3.8-Flash-Next-MQ-Q5-SSD-PLE-BF16-00002-of-00003.gguf"
            shard3 = q5_dir / "Qwen3.8-Flash-Next-MQ-Q5-SSD-PLE-BF16-00003-of-00003.gguf"
            shard1.write_bytes(b"A" * 1000)
            shard2.write_bytes(b"B" * 2000)
            shard3.write_bytes(b"C" * 3000)

            # Create sidecar files
            (q6_ple_dir / "ple-bf16-00001-of-00004.bin").write_bytes(b"P" * 400)
            (q6_ple_dir / "ple-bf16-00002-of-00004.bin").write_bytes(b"Q" * 500)

            profile_path = root / "ds4dfm.env"
            profile_path.write_text(
                "\n".join(
                    [
                        'BACKEND="ds4dfm"',
                        'MODEL_DIR="$MODEL_HOME/ds4dfm"',
                        'MODEL_FILE="MQ-Q5-SSD-PLE-BF16/Qwen3.8-Flash-Next-MQ-Q5-SSD-PLE-BF16-00001-of-00003.gguf"',
                        'SIDECAR_DIR="MQ-Q6-SSD-PLE-BF16/ple"',
                    ]
                ),
                encoding="utf-8",
            )
            profile = types.SimpleNamespace(
                name="medium/qwen3.8-flash-next-ds4dfm-262k",
                path=str(profile_path),
                backend="ds4dfm",
            )

            manager = ModelManager(root)
            entries = manager.list_models({profile.name: profile})
            by_path = {entry.path: entry for entry in entries}

            resolved_shard1 = str(shard1.resolve())
            self.assertIn(resolved_shard1, by_path)
            self.assertEqual(by_path[resolved_shard1].status, "linked")
            # Size must be sum of all 3 shards: 1000 + 2000 + 3000 = 6000
            self.assertEqual(by_path[resolved_shard1].size_bytes, 6000)

            resolved_sidecar = str(q6_ple_dir.resolve())
            self.assertIn(resolved_sidecar, by_path)
            self.assertEqual(by_path[resolved_sidecar].status, "linked")
            # Sidecar size is directory content: 400 + 500 = 900
            self.assertEqual(by_path[resolved_sidecar].size_bytes, 900)

            # Shards 2 and 3 should not be separate rows
            self.assertNotIn(str(shard2.resolve()), by_path)
            self.assertNotIn(str(shard3.resolve()), by_path)

            # Neither the parent folders nor ds4dfm should be orphan rows
            self.assertEqual([e for e in entries if e.status == "orphan"], [])


if __name__ == "__main__":
    unittest.main()
