from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "eliza-cli"))

from core.models import Service
from core.runtime_probe import RuntimeProbe


class RuntimeProbeTest(unittest.TestCase):
    def test_models_health_endpoint_is_requested_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            probe = RuntimeProbe(pathlib.Path(temporary_dir))
            service = Service(
                name="eliza-medium",
                enabled=True,
                profile_id="medium/test",
                health_url="http://127.0.0.1:8001/v1/models",
                base_url="http://127.0.0.1:8001/v1",
            )
            response = MagicMock()
            response.status = 200
            response.read.return_value = json.dumps(
                {"object": "list", "data": [{"id": "eliza-medium"}]}
            ).encode()
            response.__enter__.return_value = response

            with (
                patch("core.runtime_probe.urlopen", return_value=response) as urlopen,
                patch.object(probe, "_tmux_running", return_value=True),
            ):
                merged = probe.merge_live_state({service.name: service}, {})

            self.assertEqual(urlopen.call_count, 1)
            self.assertEqual(merged[service.name].health, "ok")
            self.assertEqual(merged[service.name].live_model, "eliza-medium")


if __name__ == "__main__":
    unittest.main()
