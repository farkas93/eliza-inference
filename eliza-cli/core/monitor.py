import pathlib
import subprocess
from dataclasses import dataclass

import psutil

@dataclass
class SystemStats:
    cpu_percent: float
    memory_percent: float
    gpu_name: str
    gpu_memory_used: float
    gpu_memory_total: float

class MonitorEngine:
    def __init__(self, root_dir: pathlib.Path):
        self.root_dir = root_dir
        self.gpu_name = "N/A"

    def _query_gpu0_stats(self) -> tuple[str, float, float]:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=2,
            )
        except Exception:
            return "N/A", 0.0, 0.0

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return "N/A", 0.0, 0.0

        for line in lines:
            parts = [part.strip() for part in line.split(",")]
            if len(parts) != 4:
                continue
            gpu_index, gpu_name, used_text, total_text = parts
            if gpu_index != "0":
                continue
            try:
                return gpu_name, float(used_text), float(total_text)
            except ValueError:
                return gpu_name or "N/A", 0.0, 0.0

        parts = [part.strip() for part in lines[0].split(",")]
        if len(parts) == 4:
            _, gpu_name, used_text, total_text = parts
            try:
                return gpu_name, float(used_text), float(total_text)
            except ValueError:
                return gpu_name or "N/A", 0.0, 0.0

        return "N/A", 0.0, 0.0

    def get_stats(self) -> SystemStats:
        cpu = psutil.cpu_percent(interval=0)
        mem = psutil.virtual_memory().percent

        gpu_name, gpu_used, gpu_total = self._query_gpu0_stats()

        return SystemStats(
            cpu_percent=cpu,
            memory_percent=mem,
            gpu_name=gpu_name,
            gpu_memory_used=gpu_used,
            gpu_memory_total=gpu_total,
        )
