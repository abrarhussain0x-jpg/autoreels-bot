"""Health Monitor — system resource and token health checks."""

import logging
import os
import shutil
import time
from pathlib import Path

log = logging.getLogger(__name__)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class HealthMonitor:
    def __init__(self, base_dir: Path):
        self.base = Path(base_dir)

    def disk_free_gb(self) -> str:
        try:
            total, used, free = shutil.disk_usage(str(self.base))
            return f"{free / 1e9:.1f} GB"
        except Exception:
            return "?"

    def cpu_pct(self) -> str:
        if HAS_PSUTIL:
            return f"{psutil.cpu_percent(interval=0.1):.0f}%"
        return "n/a"

    def mem_pct(self) -> str:
        if HAS_PSUTIL:
            return f"{psutil.virtual_memory().percent:.0f}%"
        return "n/a"

    def disk_ok(self, min_gb: float = 2.0) -> bool:
        try:
            _, _, free = shutil.disk_usage(str(self.base))
            return free / 1e9 >= min_gb
        except Exception:
            return True

    def report(self) -> str:
        lines = [
            f"Disk: {self.disk_free_gb()} free",
            f"CPU: {self.cpu_pct()}",
            f"Mem: {self.mem_pct()}",
        ]
        if HAS_PSUTIL:
            load = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)
            lines.append(f"Load: {load[0]:.1f} {load[1]:.1f} {load[2]:.1f}")
        return "\n".join(lines)
