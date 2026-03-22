"""CleanupManager — removes stale downloads, clips, and old logs."""

import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)


class CleanupManager:
    def __init__(self, base_dir: Path, max_age_hours: int = 72):
        self.base = Path(base_dir)
        self.max_age_s = max_age_hours * 3600

    def run(self):
        total = 0
        total += self._purge(self.base / "downloads", ["*.mp4", "*.mkv", "*.webm"])
        total += self._purge(self.base / "output", ["*.mp4", "*.srt", "*.wav"])
        total += self._purge_logs(self.base / "logs", keep_days=7)
        log.info("Cleanup complete: removed %d files", total)
        return total

    def _purge(self, directory: Path, patterns: list) -> int:
        if not directory.exists():
            return 0
        count = 0
        now = time.time()
        for pattern in patterns:
            for f in directory.rglob(pattern):
                try:
                    age = now - f.stat().st_mtime
                    if age > self.max_age_s:
                        f.unlink()
                        count += 1
                        log.debug("Removed: %s (age %.0fh)", f.name, age / 3600)
                except Exception as exc:
                    log.warning("Could not remove %s: %s", f, exc)
        return count

    def _purge_logs(self, log_dir: Path, keep_days: int = 7) -> int:
        if not log_dir.exists():
            return 0
        count = 0
        now = time.time()
        keep_s = keep_days * 86400
        for f in log_dir.glob("*.log"):
            if f.name == "autoreels.log":
                continue  # keep current log
            try:
                if now - f.stat().st_mtime > keep_s:
                    f.unlink()
                    count += 1
            except Exception:
                pass
        return count
