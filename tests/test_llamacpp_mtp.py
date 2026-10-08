from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eliza-cli"))

from core.executor import Executor
from core.model_manager import ModelManager


class LlamaMTPTest(unittest.TestCase):
    def test_downloader_syncs_main_shards_and_explicit_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            scripts = root / "scripts"
            (scripts / "lib").mkdir(parents=True)
            shutil.copy2(ROOT / "scripts/download-models", scripts / "download-models")
            (scripts / "lib/common.sh").write_text(
                'load_env() { :; }\nparse_service_profile() { SERVICE="$1"; }\n'
                'source_profile() { :; }\n'
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            for name in ("uv", "python", "hf"):
                binary = bin_dir / name
                binary.write_text('#!/bin/bash\nprintf "%s\\n" "$*"\n')
                binary.chmod(0o755)
            env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
                       BASE_VENV=str(root), MODEL_HOME=str(root / "models"),
                       HF_HOME=str(root / "cache"), MODEL_DIR=str(root / "models/qwen"),
                       BACKEND="llamacpp", MODEL_REPO="unsloth/Qwen3.8-Flash-Next-GGUF",
                       MODEL_FILE="UD-Q4_K_XL/main-00001-of-00004.gguf",
                       HF_INCLUDE_MODEL="*UD-Q4_K_XL*",
                       DRAFT_MODEL_FILE="MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf")
            result = subprocess.run([str(scripts / "download-models"), "eliza-medium"],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--include *UD-Q4_K_XL*", result.stdout)
            self.assertIn("--include MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf", result.stdout)

    def test_launcher_passes_draft_and_rejects_unsupported_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            binary = root / "server"
            draft = root / "draft.gguf"
            draft.write_bytes(b"draft")
            binary.write_text(
                '#!/bin/bash\nif [[ "$1" == "--help" ]]; then\n'
                '  printf "%s\\n" "$FAKE_HELP"\nelse\n'
                '  printf "%s\\n" "$@"\nfi\n'
            )
            binary.chmod(0o755)
            env = dict(os.environ, LLAMA_RUNTIME="unsloth-mtp",
                       LLAMA_MTP_SERVER_BIN=str(binary), MODEL_DIR=str(root),
                       MODEL_FILE="main.gguf", DRAFT_MODEL_FILE=draft.name,
                       SPEC_TYPE="draft-mtp", SPEC_DRAFT_N_MAX="3",
                       FAKE_HELP="draft-mtp", MODEL_NAME="qwen3.8-flash-next")
            launcher = ROOT / "services/eliza-medium/start-llamacpp.sh"
            result = subprocess.run([str(launcher)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = result.stdout.splitlines()[1:]
            self.assertEqual(args[args.index("--model-draft") + 1], str(draft))
            self.assertEqual(args[args.index("--spec-draft-n-max") + 1], "3")
            self.assertEqual(args[args.index("--alias") + 1], "qwen3.8-flash-next")
            env["FAKE_HELP"] = "stock server"
            result = subprocess.run([str(launcher)], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("lacks draft-mtp", result.stderr)
            env["FAKE_HELP"] = "draft-mtp"
            draft.unlink()
            result = subprocess.run([str(launcher)], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("draft head not found", result.stderr)

    def test_tui_setup_selects_pinned_runtime_and_requires_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            profiles_dir = root / "configs/profiles/medium"
            profiles_dir.mkdir(parents=True)
            model_dir = root / "weights"
            model_dir.mkdir()
            (root / ".env").write_text(f'MODEL_HOME="{model_dir}"\n')
            (model_dir / "main.gguf").write_bytes(b"main")
            profile_path = profiles_dir / "mtp.env"
            profile_path.write_text(
                f'BACKEND="llamacpp"\nLLAMA_RUNTIME="unsloth-mtp"\n'
                f'MODEL_DIR="{model_dir}"\nMODEL_FILE="main.gguf"\n'
                'DRAFT_MODEL_FILE="draft.gguf"\n'
            )
            profile = types.SimpleNamespace(name="medium/mtp", path=str(profile_path),
                                            backend="llamacpp", service_name="eliza-medium")
            manager = ModelManager(root)
            profiles = {profile.name: profile}
            with patch.object(manager, "_estimate_download_size", return_value=None):
                self.assertFalse(manager.build_profile_states(profiles, {})[profile.name].ready)
                (model_dir / "draft.gguf").write_bytes(b"draft")
                self.assertTrue(manager.build_profile_states(profiles, {})[profile.name].ready)
            entries = manager.list_models(profiles)
            self.assertEqual(len(entries), 2)
            self.assertTrue(all(entry.status == "linked" for entry in entries))
            commands = Executor(root)._setup_commands_for("eliza-medium", profile.name)
            self.assertIn(["./scripts/setup", "llamacpp", "--qwen-mtp"], commands)


if __name__ == "__main__":
    unittest.main()
