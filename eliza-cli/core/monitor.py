import psutil
import pathlib
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

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
        self.gpu_name = self._get_gpu_name()

    def _get_gpu_name(self) -> str:
        try:
            import subprocess
            res = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], 
                                 capture_output=True, text=True, check=True)
            return res.stdout.strip().split('\n')[0]
        except Exception:
            return "N/A"

    def get_stats(self) -> SystemStats:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        
        gpu_used = 0.0
        gpu_total = 0.0
        
        try:
            import subprocess
            res = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], 
                                 capture_output=True, text=True, check=True)
            lines = res.stdout.strip().split('\n')
            if lines:
                used, total = map(float, lines[0].split(','))
                gpu_used = used
                gpu_total = total
        except Exception:
            pass

        return SystemStats(
            cpu_percent=cpu,
            memory_percent=mem,
            gpu_name=self.gpu_name,
            gpu_memory_used=gpu_used,
            gpu_memory_total=gpu_total
        )
