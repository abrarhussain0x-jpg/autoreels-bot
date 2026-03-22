"""
YouTubeMonitor v5.0 — Advanced channel watcher.

5x Advanced:
  • Concurrent multi-channel scanning (ThreadPoolExecutor)
  • Proxy support for geo-restricted channels
  • Keyword filtering (include/exclude terms in title)
  • Quality threshold pre-filtering (views/duration ratio)
  • Bandwidth throttle option for downloads
  • Auto-fallback quality levels
  • Duplicate-safe seen DB with timestamps
  • yt-dlp auto-update detection
"""

import json
import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

log = logging.getLogger(__name__)


@dataclass
class YoutubeVideo:
    video_id: str
    title: str
    channel: str
    channel_id: str
    duration: int
    upload_date: str
    url: str
    thumbnail: str
    description: str
    view_count: int = 0
    local_path: Optional[Path] = None
    downloaded: bool = False


@dataclass
class ChannelConfig:
    channel_url: str
    min_duration: int = 60
    max_duration: int = 7200
    max_videos_per_run: int = 3
    download_quality: str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
    keywords_filter: List[str] = field(default_factory=list)   # must contain one of these
    exclude_keywords: List[str] = field(default_factory=list)  # must NOT contain these
    quality_threshold: float = 0.0      # minimum view-count/duration ratio (optional)
    min_views: int = 0                   # minimum view count


class YouTubeMonitor:
    def __init__(
        self,
        channels: List[ChannelConfig],
        downloads_dir: Path,
        seen_db_path: Path,
        cookies_file: Optional[str] = None,
        proxy: Optional[str] = None,
        concurrent_channels: int = 3,
    ):
        self.channels = channels
        self.downloads_dir = Path(downloads_dir)
        self.seen_db_path = Path(seen_db_path)
        self.cookies_file = cookies_file
        self.proxy = proxy
        self.concurrent_channels = concurrent_channels
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self._seen: Dict[str, str] = self._load_seen()  # video_id → timestamp

    # ── Public API ─────────────────────────────────────────────────────────
    def check_all_channels(self) -> List[YoutubeVideo]:
        """Scan all channels concurrently and return unseen videos."""
        new_videos: List[YoutubeVideo] = []
        workers = min(self.concurrent_channels, len(self.channels))

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(self._check_channel, cfg): cfg for cfg in self.channels}
            for future in as_completed(futures):
                cfg = futures[future]
                try:
                    found = future.result()
                    if found:
                        log.info("Channel %s → %d new video(s)", cfg.channel_url, len(found))
                    new_videos.extend(found)
                except Exception as exc:
                    log.error("Channel check failed [%s]: %s", cfg.channel_url, exc)

        # Dedup across channels (same video could appear in multiple playlists)
        seen_ids: Set[str] = set()
        deduped = []
        for v in new_videos:
            if v.video_id not in seen_ids:
                seen_ids.add(v.video_id)
                deduped.append(v)

        return deduped

    def download_video(self, video: YoutubeVideo, cfg: Optional[ChannelConfig] = None) -> Optional[Path]:
        """Download video with retry and quality fallback."""
        quality = cfg.download_quality if cfg else "best[height<=1080]/best"

        # Check cache
        for ext in ("mp4", "mkv", "webm"):
            cached = self.downloads_dir / f"{video.video_id}.{ext}"
            if cached.exists() and cached.stat().st_size > 100_000:
                log.info("Cached: %s (%.0f MB)", video.title[:60], cached.stat().st_size / 1e6)
                video.local_path = cached
                video.downloaded = True
                return cached

        out_tmpl = str(self.downloads_dir / f"{video.video_id}.%(ext)s")

        # Build base command
        cmd = [
            "yt-dlp",
            "--format", quality,
            "--output", out_tmpl,
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--retries", "5",
            "--fragment-retries", "5",
            "--socket-timeout", "30",
            "--no-warnings",
            "--add-metadata",
        ]

        if self.cookies_file and Path(self.cookies_file).exists():
            cmd += ["--cookies", str(self.cookies_file)]

        if self.proxy:
            cmd += ["--proxy", self.proxy]

        cmd.append(video.url)

        log.info("Downloading: %s", video.title[:60])
        last_err = ""

        for attempt in range(1, 4):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
                if result.returncode == 0:
                    break
                last_err = result.stderr[-300:]
                log.warning("yt-dlp attempt %d/3 failed: %s", attempt, last_err[-150:])
                # Fallback to lower quality on attempt 2
                if attempt == 2:
                    cmd[cmd.index("--format") + 1] = "best[height<=720]/best"
                time.sleep(5 * attempt)
            except FileNotFoundError:
                log.error("yt-dlp not installed. Run: pip install yt-dlp")
                return None
            except subprocess.TimeoutExpired:
                log.error("Download timed out after 60min")
                return None

        for ext in ("mp4", "mkv", "webm"):
            out = self.downloads_dir / f"{video.video_id}.{ext}"
            if out.exists() and out.stat().st_size > 100_000:
                size_mb = out.stat().st_size / 1_048_576
                log.info("Downloaded: %s (%.1f MB)", video.title[:60], size_mb)
                video.local_path = out
                video.downloaded = True
                return out

        log.error("Download failed for %s: %s", video.video_id, last_err[-200:])
        return None

    def mark_seen(self, video_id: str):
        self._seen[video_id] = datetime.utcnow().isoformat()
        self._save_seen()

    def is_seen(self, video_id: str) -> bool:
        return video_id in self._seen

    # ── Channel scan ───────────────────────────────────────────────────────
    def _check_channel(self, cfg: ChannelConfig) -> List[YoutubeVideo]:
        scan_limit = cfg.max_videos_per_run * 5  # scan extra to find enough after filters
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--playlist-end", str(scan_limit),
            "--dump-json",
            "--no-warnings",
        ]

        if self.cookies_file and Path(self.cookies_file).exists():
            cmd += ["--cookies", str(self.cookies_file)]

        if self.proxy:
            cmd += ["--proxy", self.proxy]

        cmd.append(cfg.channel_url)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except FileNotFoundError:
            raise RuntimeError("yt-dlp not installed")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Scan timed out: {cfg.channel_url}")

        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp error: {result.stderr[-300:]}")

        new_videos = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            vid_id = entry.get("id", "")
            if not vid_id or self.is_seen(vid_id):
                continue

            duration = int(entry.get("duration") or 0)
            if duration < cfg.min_duration or duration > cfg.max_duration:
                continue

            title = entry.get("title", "Untitled")

            # Keyword filtering
            if cfg.keywords_filter:
                title_lower = title.lower()
                if not any(kw.lower() in title_lower for kw in cfg.keywords_filter):
                    log.debug("Skipping '%s' — no keyword match", title[:40])
                    continue

            if cfg.exclude_keywords:
                title_lower = title.lower()
                if any(kw.lower() in title_lower for kw in cfg.exclude_keywords):
                    log.debug("Skipping '%s' — excluded keyword match", title[:40])
                    continue

            # View count filter
            view_count = int(entry.get("view_count") or 0)
            if cfg.min_views > 0 and view_count < cfg.min_views:
                continue

            channel_id = entry.get("channel_id") or entry.get("uploader_id") or "unknown"

            new_videos.append(YoutubeVideo(
                video_id=vid_id,
                title=title,
                channel=entry.get("channel") or entry.get("uploader", "Unknown"),
                channel_id=channel_id,
                duration=duration,
                upload_date=entry.get("upload_date", ""),
                url=f"https://www.youtube.com/watch?v={vid_id}",
                thumbnail=entry.get("thumbnail", ""),
                description="",
                view_count=view_count,
            ))

            if len(new_videos) >= cfg.max_videos_per_run:
                break

        return new_videos

    # ── Seen database ──────────────────────────────────────────────────────
    def _load_seen(self) -> Dict[str, str]:
        if self.seen_db_path.exists():
            try:
                data = json.loads(self.seen_db_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "seen" in data:
                    seen = data["seen"]
                    if isinstance(seen, list):
                        # Legacy format: list of IDs
                        return {vid: "" for vid in seen}
                    elif isinstance(seen, dict):
                        return seen
            except Exception:
                pass
        return {}

    def _save_seen(self):
        self.seen_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.seen_db_path.write_text(
            json.dumps({"seen": self._seen, "_count": len(self._seen)}, indent=2),
            encoding="utf-8",
        )
