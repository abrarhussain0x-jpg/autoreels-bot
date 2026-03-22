"""
AnalyticsTracker v5.0 — Performance tracking for all platforms.

Tracks every upload, platform results, quality scores.
Provides weekly/monthly reports and trend analysis.
"""

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class AnalyticsTracker:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id     TEXT NOT NULL,
                    clip_num     INTEGER,
                    title        TEXT,
                    platform     TEXT NOT NULL,
                    post_id      TEXT,
                    quality_score REAL DEFAULT 0,
                    uploaded_at  REAL NOT NULL,
                    date_str     TEXT NOT NULL
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_date ON uploads(date_str)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_platform ON uploads(platform)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_video ON uploads(video_id)")

    def log_upload(
        self,
        video_id: str,
        clip_num: int,
        title: str,
        platform_results: Dict[str, Optional[str]],
        quality_score: float = 0,
    ):
        """Record upload results for all platforms."""
        now = time.time()
        date_str = date.today().isoformat()
        with self._conn() as c:
            for platform, post_id in platform_results.items():
                if post_id:
                    c.execute(
                        "INSERT INTO uploads "
                        "(video_id, clip_num, title, platform, post_id, quality_score, uploaded_at, date_str) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (video_id, clip_num, title, platform, post_id, quality_score, now, date_str)
                    )

    def daily_totals(self, days: int = 7) -> List[Dict]:
        """Get daily upload totals by platform for the last N days."""
        results = []
        for i in range(days - 1, -1, -1):
            d = (date.today() - timedelta(days=i)).isoformat()
            with self._conn() as c:
                rows = c.execute(
                    "SELECT platform, COUNT(*) as cnt FROM uploads "
                    "WHERE date_str=? GROUP BY platform",
                    (d,)
                ).fetchall()
            day_data = {"date": d}
            for row in rows:
                day_data[row[0]] = row[1]
            results.append(day_data)
        return results

    def weekly_totals(self) -> Dict[str, int]:
        """Get total uploads per platform for the last 7 days."""
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        with self._conn() as c:
            rows = c.execute(
                "SELECT platform, COUNT(*) FROM uploads "
                "WHERE date_str >= ? GROUP BY platform",
                (cutoff,)
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def total_uploads(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM uploads").fetchone()[0]

    def recent_uploads(self, limit: int = 20) -> List[Dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT video_id, clip_num, title, platform, post_id, quality_score, uploaded_at "
                "FROM uploads ORDER BY uploaded_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def platform_breakdown(self) -> Dict[str, int]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT platform, COUNT(*) FROM uploads GROUP BY platform"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def top_videos(self, limit: int = 10) -> List[Dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT video_id, title, COUNT(*) as clips, AVG(quality_score) as avg_score "
                "FROM uploads GROUP BY video_id ORDER BY clips DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def weekly_report_text(self) -> str:
        weekly = self.weekly_totals()
        total = sum(weekly.values())
        daily = self.daily_totals(7)
        today_total = sum(
            v for k, v in daily[-1].items() if k != "date"
        ) if daily else 0

        lines = [
            f"📈 Weekly Analytics Report",
            f"",
            f"Total this week: {total} uploads",
            f"Today: {today_total} uploads",
            f"",
            "By platform:",
        ]
        for platform, count in sorted(weekly.items(), key=lambda x: -x[1]):
            lines.append(f"  • {platform.capitalize()}: {count}")

        top = self.top_videos(3)
        if top:
            lines.append("")
            lines.append("Top 3 videos by clips:")
            for v in top:
                lines.append(f"  • {v['title'][:50]} ({v['clips']} clips)")

        return "\n".join(lines)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn
