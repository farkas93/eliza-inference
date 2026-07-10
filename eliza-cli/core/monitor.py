import pathlib
import re
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
        commands = [
            [
                "nvidia-smi",
                "--id=0",
                "--query-gpu=name,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            [
                "nvidia-smi",
                "--id=0",
                "--query-gpu=name,memory.used,memory.total",
                "--format=csv,noheader",
            ],
        ]

        for command in commands:
            gpu_name, gpu_used, gpu_total = self._run_gpu_query(command)
            if gpu_name != "N/A" or gpu_total > 0:
                return gpu_name, gpu_used, gpu_total

        return "N/A", 0.0, 0.0

    def _run_gpu_query(self, command: list[str]) -> tuple[str, float, float]:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=5)
        except Exception:
            return "N/A", 0.0, 0.0

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return "N/A", 0.0, 0.0

        for line in lines:
            parsed = self._parse_gpu_line(line)
            if parsed is not None:
                return parsed

        return "N/A", 0.0, 0.0

    def _parse_gpu_line(self, line: str) -> tuple[str, float, float] | None:
        parts = [part.strip() for part in line.split(",")]

        if len(parts) == 4 and parts[0].isdigit():
            _, gpu_name, used_text, total_text = parts
        elif len(parts) >= 3:
            gpu_name, used_text, total_text = parts[-3], parts[-2], parts[-1]
        else:
            return None

        used = self._parse_memory_value(used_text)
        total = self._parse_memory_value(total_text)
        return gpu_name or "N/A", used, total

    def _parse_memory_value(self, text: str) -> float:
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
        if match is None:
            return 0.0
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0

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
