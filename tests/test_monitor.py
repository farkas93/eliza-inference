from __future__ import annotations

import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "eliza-cli"))

from core.monitor import MonitorEngine, SystemStats, format_gpu_status


class MonitorTest(unittest.TestCase):
    def test_gb10_uses_unified_system_memory_when_nvidia_smi_memory_is_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            monitor = MonitorEngine(pathlib.Path(temporary_dir))
            virtual_memory = types.SimpleNamespace(
                total=120 * 1024**3,
                available=80 * 1024**3,
                percent=33.3,
            )
            disk_usage = types.SimpleNamespace(used=10, total=100, percent=10.0)
            with (
                patch.object(
                    monitor,
                    "_query_gpu0_stats",
                    return_value=("NVIDIA GB10", True, False, 0.0, 0.0, 3.0, 41.0),
                ),
                patch("core.monitor.psutil.cpu_percent", return_value=5.0),
                patch("core.monitor.psutil.virtual_memory", return_value=virtual_memory),
                patch("core.monitor.psutil.disk_usage", return_value=disk_usage),
            ):
                stats = monitor.get_stats()

        self.assertTrue(stats.gpu_memory_supported)
        self.assertEqual(stats.gpu_memory_used, 40 * 1024)
        self.assertEqual(stats.gpu_memory_total, 120 * 1024)
        self.assertEqual(
            format_gpu_status(stats),
            "GPU0 mem 40.0/120 GiB util 3% temp 41C (NVIDIA GB10)",
        )

    def test_discrete_gpu_memory_is_formatted_in_gib(self) -> None:
        stats = SystemStats(
            cpu_percent=0,
            memory_percent=0,
            gpu_name="NVIDIA RTX 5090",
            gpu_present=True,
            gpu_memory_supported=True,
            gpu_memory_used=16384,
            gpu_memory_total=32768,
            gpu_util_percent=0,
            gpu_temp_c=52,
            disk_used_bytes=0,
            disk_total_bytes=0,
            disk_percent=0,
            model_home_used_bytes=0,
        )

        self.assertEqual(
            format_gpu_status(stats),
            "GPU0 mem 16.0/32 GiB temp 52C (NVIDIA RTX 5090)",
        )


if __name__ == "__main__":
    unittest.main()
