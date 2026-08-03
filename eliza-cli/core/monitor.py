import pathlib
import os
import re
import subprocess
from dataclasses import dataclass

import psutil

@dataclass
class SystemStats:
    cpu_percent: float
    memory_percent: float
    gpu_name: str
    gpu_present: bool
    gpu_memory_supported: bool
    gpu_memory_used: float
    gpu_memory_total: float
    gpu_util_percent: float
    gpu_temp_c: float
    disk_used_bytes: int
    disk_total_bytes: int
    disk_percent: float
    model_home_used_bytes: int

class MonitorEngine:
    def __init__(self, root_dir: pathlib.Path):
        self.root_dir = root_dir
        self.gpu_name = "N/A"
        self.model_home = self._resolve_model_home()

    def _resolve_model_home(self) -> pathlib.Path:
        env_model_home = os.getenv("MODEL_HOME")
        if env_model_home:
            return pathlib.Path(env_model_home).expanduser()

        env_file = self.root_dir / ".env"
        if env_file.exists():
            try:
                with open(env_file, "r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        if key.strip() == "MODEL_HOME":
                            return pathlib.Path(value.strip().strip('"').strip("'")).expanduser()
            except OSError:
                pass

        return pathlib.Path.home() / "models"

    def _query_gpu0_stats(self) -> tuple[str, bool, bool, float, float, float, float]:
        commands = [
            [
                "nvidia-smi",
                "--id=0",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu",
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
            gpu_name, gpu_present, memory_supported, gpu_used, gpu_total, gpu_util, gpu_temp = self._run_gpu_query(command)
            if gpu_present or gpu_total > 0:
                return gpu_name, gpu_present, memory_supported, gpu_used, gpu_total, gpu_util, gpu_temp

        return "N/A", False, False, 0.0, 0.0, 0.0, 0.0

    def _run_gpu_query(self, command: list[str]) -> tuple[str, bool, bool, float, float, float, float]:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=5)
        except Exception:
            return "N/A", False, False, 0.0, 0.0, 0.0, 0.0

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return "N/A", False, False, 0.0, 0.0, 0.0, 0.0

        for line in lines:
            parsed = self._parse_gpu_line(line)
            if parsed is not None:
                return parsed

        return "N/A", False, False, 0.0, 0.0, 0.0, 0.0

    def _parse_numeric(self, text: str) -> float | None:
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
        if match is None:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    def _parse_gpu_line(self, line: str) -> tuple[str, bool, bool, float, float, float, float] | None:
        parts = [part.strip() for part in line.split(",")]

        if len(parts) >= 6 and parts[0].isdigit():
            _, gpu_name, used_text, total_text, util_text, temp_text = parts
        elif len(parts) >= 5:
            gpu_name, used_text, total_text, util_text, temp_text = parts[-5], parts[-4], parts[-3], parts[-2], parts[-1]
        elif len(parts) >= 3:
            gpu_name, used_text, total_text = parts[-3], parts[-2], parts[-1]
            util_text = ""
            temp_text = ""
        else:
            return None

        used_val = self._parse_numeric(used_text)
        total_val = self._parse_numeric(total_text)
        util_val = self._parse_numeric(util_text)
        temp_val = self._parse_numeric(temp_text)

        gpu_name = gpu_name or "N/A"
        gpu_present = gpu_name != "N/A"
        memory_supported = used_val is not None and total_val is not None and total_val > 0

        used = used_val if used_val is not None else 0.0
        total = total_val if total_val is not None else 0.0
        util = util_val if util_val is not None else 0.0
        temp = temp_val if temp_val is not None else 0.0
        return gpu_name, gpu_present, memory_supported, used, total, util, temp

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
        disk_usage = psutil.disk_usage("/")

        gpu_name, gpu_present, gpu_memory_supported, gpu_used, gpu_total, gpu_util, gpu_temp = self._query_gpu0_stats()

        model_home = self.model_home
        model_home_used = 0
        if model_home.exists():
            try:
                model_home_used = sum(
                    path.stat().st_size for path in model_home.rglob("*") if path.is_file()
                )
            except OSError:
                model_home_used = 0

        return SystemStats(
            cpu_percent=cpu,
            memory_percent=mem,
            gpu_name=gpu_name,
            gpu_present=gpu_present,
            gpu_memory_supported=gpu_memory_supported,
            gpu_memory_used=gpu_used,
            gpu_memory_total=gpu_total,
            gpu_util_percent=gpu_util,
            gpu_temp_c=gpu_temp,
            disk_used_bytes=disk_usage.used,
            disk_total_bytes=disk_usage.total,
            disk_percent=disk_usage.percent,
            model_home_used_bytes=model_home_used,
        )
