"""
JobQueue v5.0 — SQLite-backed job queue with priority, analytics fields.
"""

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class JobState(str, Enum):
    QUEUED      = "queued"
    DOWNLOADING = "downloading"
    PROCESSING  = "processing"
    UPLOADING   = "uploading"
    DONE        = "done"
    FAILED      = "failed"


@dataclass
class Job:
    video_id: str
    channel_id: str
    title: str
    youtube_url: str
    duration: int
    state: str = JobState.QUEUED
    local_path: Optional[str] = None
    output_clips: List[str] = field(default_factory=list)
    fb_post_ids: List[str] = field(default_factory=list)
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    retries: int = 0
    max_retries: int = 3
    priority: int = 0           # higher = processed first
    quality_score: float = 0.0  # average clip quality score


class JobQueue:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def add(self, job: Job) -> bool:
        try:
            with self._conn() as c:
                c.execute(
                    """INSERT INTO jobs 
                    (video_id,channel_id,title,youtube_url,duration,state,
                     local_path,output_clips,fb_post_ids,error,created_at,updated_at,
                     retries,max_retries,priority,quality_score)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        job.video_id, job.channel_id, job.title, job.youtube_url,
                        job.duration, job.state, job.local_path,
                        json.dumps(job.output_clips), json.dumps(job.fb_post_ids),
                        job.error, job.created_at, job.updated_at,
                        job.retries, job.max_retries, job.priority, job.quality_score,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def update(self, video_id: str, **kwargs):
        kwargs["updated_at"] = time.time()
        for k in ("output_clips", "fb_post_ids"):
            if k in kwargs and isinstance(kwargs[k], list):
                kwargs[k] = json.dumps(kwargs[k])
        sets = ", ".join(f"{k}=?" for k in kwargs)
        with self._conn() as c:
            c.execute(
                f"UPDATE jobs SET {sets} WHERE video_id=?",
                list(kwargs.values()) + [video_id],
            )

    def get(self, video_id: str) -> Optional[Job]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM jobs WHERE video_id=?", (video_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def exists(self, video_id: str) -> bool:
        with self._conn() as c:
            return bool(
                c.execute("SELECT 1 FROM jobs WHERE video_id=?", (video_id,)).fetchone()
            )

    def pending(self) -> List[Job]:
        """Return jobs ready to process, ordered by priority then created_at."""
        with self._conn() as c:
            rows = c.execute(
                """SELECT * FROM jobs
                WHERE state=? OR (state=? AND retries < max_retries)
                ORDER BY priority DESC, created_at""",
                (JobState.QUEUED, JobState.FAILED),
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def recent(self, limit: int = 20) -> List[Job]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def stats(self) -> Dict[str, int]:
        with self._conn() as c:
            rows = c.execute("SELECT state, COUNT(*) FROM jobs GROUP BY state").fetchall()
        return {r[0]: r[1] for r in rows}

    def purge_done(self, older_than_days: int = 7):
        cutoff = time.time() - older_than_days * 86400
        with self._conn() as c:
            c.execute(
                "DELETE FROM jobs WHERE state=? AND updated_at<?",
                (JobState.DONE, cutoff),
            )

    def set_priority(self, video_id: str, priority: int):
        """Boost or lower a job's priority."""
        self.update(video_id, priority=priority)

    # ── Internals ──────────────────────────────────────────────────────────
    def _init_db(self):
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    video_id     TEXT PRIMARY KEY,
                    channel_id   TEXT,
                    title        TEXT,
                    youtube_url  TEXT,
                    duration     INTEGER,
                    state        TEXT,
                    local_path   TEXT,
                    output_clips TEXT,
                    fb_post_ids  TEXT,
                    error        TEXT,
                    created_at   REAL,
                    updated_at   REAL,
                    retries      INTEGER DEFAULT 0,
                    max_retries  INTEGER DEFAULT 3,
                    priority     INTEGER DEFAULT 0,
                    quality_score REAL DEFAULT 0
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_state    ON jobs(state)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_updated  ON jobs(updated_at)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_priority ON jobs(priority)")
            # Migration: add new columns if upgrading from v3
            for col, definition in [
                ("priority",     "INTEGER DEFAULT 0"),
                ("quality_score","REAL DEFAULT 0"),
            ]:
                try:
                    c.execute(f"ALTER TABLE jobs ADD COLUMN {col} {definition}")
                except Exception:
                    pass

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_job(self, row) -> Job:
        d = dict(row)
        d["output_clips"] = json.loads(d.get("output_clips") or "[]")
        d["fb_post_ids"]  = json.loads(d.get("fb_post_ids")  or "[]")
        d.setdefault("priority", 0)
        d.setdefault("quality_score", 0.0)
        return Job(**d)
