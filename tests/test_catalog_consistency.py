import ast
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eliza-cli"))
from core.model_manager import ModelManager


class CatalogConsistencyTest(unittest.TestCase):
    def test_piper_uses_runtime_paths_without_phantom_root_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            voice = root / "voices/en/en_US/lessac/medium"
            voice.mkdir(parents=True)
            for name in ("voice.onnx", "voice.onnx.json"):
                (voice / name).write_bytes(b"voice")
            profile_path = root / "piper.env"
            profile_path.write_text(
                f'BACKEND="piper"\nMODEL_DIR="{root}/voices"\n'
                'MODEL_FILE="voice.onnx"\nMODEL_CONFIG_FILE="voice.onnx.json"\n'
                'PIPER_VOICE_PATH="$MODEL_DIR/en/en_US/lessac/medium/$MODEL_FILE"\n'
                'PIPER_CONFIG_PATH="$PIPER_VOICE_PATH.json"\n'
            )
            (root / ".env").write_text(f'MODEL_HOME="{root}/voices"\n')
            profile = types.SimpleNamespace(name="tts/test", path=str(profile_path),
                                            backend="piper", service_name="tts")
            manager = ModelManager(root)
            with patch.object(manager, "_estimate_download_size", return_value=None):
                self.assertTrue(manager.build_profile_states({profile.name: profile}, {})[profile.name].ready)
            entries = manager.list_models({profile.name: profile})
            self.assertEqual(len(entries), 2)
            self.assertTrue(all(entry.status == "linked" for entry in entries))

    def test_same_projector_name_is_disambiguated_by_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / ".env").write_text(f'MODEL_HOME="{root}/models"\n')
            profiles = {}
            for name in ("first", "second"):
                model_dir = root / "models" / name
                model_dir.mkdir(parents=True)
                (model_dir / "mmproj.gguf").write_bytes(b"projector")
                profile_path = root / f"{name}.env"
                profile_path.write_text(f'MODEL_DIR="{model_dir}"\nMMPROJ_FILE="mmproj.gguf"\n')
                profiles[name] = types.SimpleNamespace(name=name, path=str(profile_path), backend="llamacpp")
            entries = ModelManager(root).list_models(profiles)
            self.assertEqual({entry.name for entry in entries}, {"first/mmproj.gguf", "second/mmproj.gguf"})

    def test_picker_reads_local_files_before_inventory_and_after_removal(self):
        # Exercise the real picker methods without requiring a graphical TUI
        # installation in the test environment.
        tree = ast.parse((ROOT / "eliza-cli/tui/app.py").read_text())
        app = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ElizaTUI")
        methods = [node for node in app.body if isinstance(node, ast.FunctionDef)
                   and node.name in {"_profile_ready_now", "_profile_selection_label", "_human_size"}]
        namespace = {"Profile": object}
        exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), "picker", "exec"), namespace)
        with tempfile.TemporaryDirectory() as directory:
            artifact = pathlib.Path(directory) / "model.gguf"
            artifact.write_bytes(b"model")
            profile = types.SimpleNamespace(name="medium/test", backend="llamacpp")
            picker = types.SimpleNamespace(
                profile_states={}, stack=types.SimpleNamespace(profiles={profile.name: profile}),
                model_manager=types.SimpleNamespace(_expected_paths_for_profile=lambda _: [artifact]),
            )
            picker._profile_ready_now = types.MethodType(namespace["_profile_ready_now"], picker)
            label = namespace["_profile_selection_label"](picker, profile)
            self.assertIn("RDY", label)
            artifact.unlink()
            self.assertIn("MISS", namespace["_profile_selection_label"](picker, profile))


if __name__ == "__main__":
    unittest.main()
