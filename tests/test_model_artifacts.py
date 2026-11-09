from __future__ import annotations

import pathlib
import json
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eliza-cli"))

from core.model_artifacts import gguf_shards, missing_paths
from core.model_manager import ModelManager


class ModelArtifactsTest(unittest.TestCase):
    def test_partial_shards_are_not_ready_or_separate_inventory_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            models = root / "models"
            models.mkdir()
            (root / ".env").write_text(f'MODEL_HOME="{models}"\n')
            profile_file = root / "model.env"
            profile_file.write_text(f'MODEL_DIR="{models}"\nMODEL_FILE="model-00001-of-00004.gguf"\n')
            profile = types.SimpleNamespace(name="medium/model", service_name="eliza-medium",
                                            path=str(profile_file), backend="llamacpp")
            first = models / "model-00001-of-00004.gguf"
            first.write_bytes(b"metadata")
            manager = ModelManager(root)
            with patch.object(manager, "_estimate_download_size", return_value=None):
                state = manager.build_profile_states({profile.name: profile}, {})[profile.name]
                self.assertFalse(state.ready)
                self.assertEqual(len(state.expected_paths), 4)
                self.assertFalse(manager.profile_ready(profile))
                entries = manager.list_models({profile.name: profile})
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0].status, "incomplete")
                for shard in gguf_shards(first)[1:]:
                    shard.write_bytes(b"weights")
                self.assertTrue(manager.profile_ready(profile))
                self.assertEqual(len(manager.list_models({profile.name: profile})), 1)
                gguf_shards(first)[2].write_bytes(b"")
                self.assertFalse(manager.profile_ready(profile))
                first.unlink()
                entry = manager.list_models({profile.name: profile})[0]
                self.assertEqual(entry.status, "incomplete")
                self.assertEqual(entry.size_bytes, len(b"weights") * 2)

    def test_download_size_globs_match_the_selected_pinned_quant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            profile_file = root / "quant.env"
            profile_file.write_text('MODEL_REPO="unsloth/model"\nMODEL_REVISION="pinned-revision"\n'
                                    'HF_INCLUDE_MODEL="UD-IQ4_XS/*"\nDRAFT_MODEL_FILE="MTP/draft.gguf"\n')
            profile = types.SimpleNamespace(name="medium/model", path=str(profile_file), backend="llamacpp")
            response = MagicMock()
            response.__enter__.return_value = response
            response.read.return_value = json.dumps([
                {"path": "UD-IQ4_XS/first.gguf", "size": 10},
                {"path": "UD-IQ4_XS/second.gguf", "size": 20},
                {"path": "MTP/draft.gguf", "size": 3},
                {"path": "UD-IQ3_XXS/model.gguf", "size": 100},
            ]).encode()
            with patch("core.model_manager.urlopen", return_value=response) as request:
                self.assertEqual(ModelManager(root)._estimate_download_size(profile), 33)
                self.assertIn("/tree/pinned-revision?", request.call_args.args[0].full_url)

    def test_launcher_preflight_reports_missing_siblings(self):
        with tempfile.TemporaryDirectory() as directory:
            first = pathlib.Path(directory) / "model-00001-of-00003.gguf"
            first.write_bytes(b"metadata")
            result = subprocess.run([sys.executable, str(ROOT / "scripts/lib/model_artifacts.py"), str(first)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 78)
            self.assertIn("model-00002-of-00003.gguf", result.stdout)
            self.assertIn("model-00003-of-00003.gguf", result.stdout)
            self.assertEqual(len(missing_paths((first,))), 2)

    def test_delete_sharded_entry_removes_the_complete_group_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            models = root / "models"
            models.mkdir()
            (root / ".env").write_text(f'MODEL_HOME="{models}"\n')
            first = models / "model-00001-of-00003.gguf"
            for shard in gguf_shards(first):
                shard.write_bytes(b"weights")
            other = models / "other.gguf"
            other.write_bytes(b"keep")
            profile_file = root / "model.env"
            profile_file.write_text(f'MODEL_DIR="{models}"\nMODEL_FILE="{first.name}"\n')
            profile = types.SimpleNamespace(name="medium/model", service_name="eliza-medium",
                                            path=str(profile_file), backend="llamacpp")
            manager = ModelManager(root)
            with patch.object(manager, "_estimate_download_size", return_value=None):
                states = manager.build_profile_states({profile.name: profile}, {})
            entry = next(entry for entry in manager.list_models({profile.name: profile}) if entry.path == str(first))
            self.assertEqual(manager.delete_entry_profile_files_only(entry, states), (3, 21))
            self.assertTrue(other.exists())


if __name__ == "__main__":
    unittest.main()
