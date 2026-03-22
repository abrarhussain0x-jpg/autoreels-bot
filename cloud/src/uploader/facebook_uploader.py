"""
FacebookUploader v3.0 — Production-grade upload client:
  • Resumable chunked upload (Graph API v19)
  • Exponential back-off retry
  • Token expiry detection + warning
  • Upload-rate limiter (avoid daily limits)
  • Viral caption generator
  • Reel + Video support
"""

import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

FB_GRAPH = "https://graph.facebook.com/v19.0"
CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB

HOOKS = [
    "WAIT FOR THE END! You won't believe this! 🔥",
    "This ending will SHOCK you! 😱",
    "Most people stop watching... don't be one of them!",
    "The twist at the end changed EVERYTHING!",
    "Nobody talks about this part! 🤯",
    "This scene broke the internet! 👀",
    "Watch till the end — your jaw will DROP 😳",
    "The scene everyone is talking about! 🔥",
]

CTAS = [
    "Follow TimeFast for daily movie recaps!",
    "Save this so you don't forget Part {next}! 📌",
    "Tag someone who NEEDS to watch this!",
    "Follow for Part {next} dropping soon! 🎬",
    "Like + Follow for more viral recaps! ❤️",
]

HASHTAGS = (
    "#movierecap #filmrecap #storyrecap #viral #reels "
    "#movies #recap #storytime #movienight #filmnight "
    "#hollywoodmovies #moviesummary #mustwatch #foryou #fyp "
    "#trending #movielovers #cinema #filmlovers #viralreels "
    "#shorts #entertainment #movieclip #filmclip"
)


@dataclass
class UploadResult:
    success: bool
    post_id: Optional[str] = None
    video_id: Optional[str] = None
    permalink: Optional[str] = None
    error: Optional[str] = None
    clip_path: Optional[Path] = None


@dataclass
class FacebookConfig:
    page_id: str
    page_access_token: str
    default_caption: str = "Watch this amazing clip!"
    published: bool = True
    upload_as_reel: bool = True


class FacebookUploader:
    def __init__(self, config: FacebookConfig):
        self.cfg = config
        self._last_upload = 0.0
        self._min_gap_s = 30  # minimum seconds between uploads

    # ── Public API ─────────────────────────────────────────────────────────
    def upload_clip(self, clip_path: Path, title: str,
                    caption: str, hashtags=None, clip_num: int = 1) -> UploadResult:
        if not clip_path.exists():
            return UploadResult(False, error=f"File not found: {clip_path}")

        # Rate-limit guard
        elapsed = time.time() - self._last_upload
        if elapsed < self._min_gap_s:
            wait = self._min_gap_s - elapsed
            log.info("Rate-limit pause: %.0fs", wait)
            time.sleep(wait)

        file_size = clip_path.stat().st_size
        log.info("Uploading: %s (%.1f MB)", clip_path.name, file_size / 1_048_576)

        full_caption = self._build_caption(title, caption, hashtags or [], clip_num)

        for attempt in range(1, 4):
            try:
                result = self._do_upload(clip_path, file_size, title, full_caption)
                self._last_upload = time.time()
                return result
            except _TokenExpiredError as exc:
                log.error("Facebook token expired: %s", exc)
                return UploadResult(False, error=f"Token expired: {exc}")
            except Exception as exc:
                log.warning("Upload attempt %d/3 failed: %s", attempt, exc)
                if attempt < 3:
                    time.sleep(2 ** attempt * 10)

        return UploadResult(False, error="Upload failed after 3 attempts")

    def verify_token(self) -> bool:
        try:
            url = (f"{FB_GRAPH}/me?fields=id,name,access_token"
                   f"&access_token={self.cfg.page_access_token}")
            resp = self._get(url)
            log.info("Token valid — page: %s (id=%s)", resp.get("name"), resp.get("id"))
            return True
        except Exception as exc:
            log.error("Token check failed: %s", exc)
            return False

    def token_expires_in_days(self) -> Optional[int]:
        try:
            url = (f"{FB_GRAPH}/debug_token"
                   f"?input_token={self.cfg.page_access_token}"
                   f"&access_token={self.cfg.page_access_token}")
            resp = self._get(url)
            exp = resp.get("data", {}).get("expires_at", 0)
            if exp:
                return max(0, int((exp - time.time()) / 86400))
        except Exception:
            pass
        return None

    # ── Upload flow ────────────────────────────────────────────────────────
    def _do_upload(self, clip_path: Path, file_size: int,
                   title: str, caption: str) -> UploadResult:
        # Phase 1 — start resumable session
        video_id, upload_url = self._init_upload(file_size)
        log.debug("Upload session: video_id=%s", video_id)

        # Phase 2 — transfer file in chunks
        self._upload_file(upload_url, clip_path, file_size)
        log.debug("File transfer complete")

        # Phase 3 — publish
        post_id = self._publish(video_id, caption, title)
        permalink = f"https://www.facebook.com/{self.cfg.page_id}/videos/{video_id}"
        log.info("Published! post_id=%s url=%s", post_id, permalink)
        return UploadResult(True, post_id=post_id, video_id=video_id,
                            permalink=permalink, clip_path=clip_path)

    def _init_upload(self, file_size: int):
        url = f"{FB_GRAPH}/{self.cfg.page_id}/videos"
        resp = self._post(url, {
            "upload_phase": "start",
            "file_size": str(file_size),
            "access_token": self.cfg.page_access_token,
        })
        video_id = resp.get("video_id") or resp.get("id")
        upload_url = resp.get("upload_url")
        if not video_id or not upload_url:
            raise RuntimeError(f"Init upload failed: {resp}")
        return video_id, upload_url

    def _upload_file(self, upload_url: str, path: Path, file_size: int):
        offset = 0
        with open(path, "rb") as fh:
            while offset < file_size:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                headers = {
                    "Authorization": f"OAuth {self.cfg.page_access_token}",
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(len(chunk)),
                    "file_offset": str(offset),
                }
                for attempt in range(3):
                    try:
                        req = Request(upload_url, data=chunk, headers=headers, method="POST")
                        with urlopen(req, timeout=180) as resp:
                            data = json.loads(resp.read().decode())
                            offset = int(data.get("start_offset", offset + len(chunk)))
                        break
                    except HTTPError as exc:
                        body = exc.read().decode()[:200]
                        if attempt == 2:
                            raise RuntimeError(f"Chunk upload error: {body}")
                        time.sleep(5 * (attempt + 1))
                pct = int(100 * offset / file_size)
                log.debug("Upload: %d%%", pct)

    def _publish(self, video_id: str, caption: str, title: str) -> str:
        url = f"{FB_GRAPH}/{self.cfg.page_id}/videos"
        payload = {
            "upload_phase": "finish",
            "video_id": video_id,
            "title": title[:100],
            "description": caption[:63206],
            "access_token": self.cfg.page_access_token,
            "published": "true" if self.cfg.published else "false",
        }
        if self.cfg.upload_as_reel:
            payload["content_tags"] = "[]"
        resp = self._post(url, payload)
        return resp.get("id") or video_id

    # ── Caption builder ────────────────────────────────────────────────────
    def _build_caption(self, title: str, caption: str,
                       hashtags: list, clip_num: int) -> str:
        hook = random.choice(HOOKS)
        cta = random.choice(CTAS).format(next=clip_num + 1)
        parts = [
            f"PART {clip_num} — {title[:60]}",
            "",
            hook,
            "",
            cta,
            "",
            HASHTAGS,
        ]
        text = "\n".join(parts)
        if hashtags:
            extra = " ".join(f"#{t.lstrip('#')}" for t in hashtags[:10])
            text += f"\n{extra}"
        return text[:63206]

    # ── HTTP helpers ───────────────────────────────────────────────────────
    def _post(self, url: str, data: dict, retries: int = 3) -> dict:
        body = urlencode(data).encode("utf-8")
        for attempt in range(1, retries + 1):
            try:
                req = Request(url, data=body, method="POST")
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
                with urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode())
            except HTTPError as exc:
                raw = exc.read().decode()
                try:
                    err_obj = json.loads(raw).get("error", {})
                    code = err_obj.get("code", 0)
                    msg = err_obj.get("message", raw[:200])
                    if code in (190, 102):  # token expired/invalid
                        raise _TokenExpiredError(msg)
                except _TokenExpiredError:
                    raise
                except Exception:
                    msg = raw[:200]
                if attempt == retries:
                    raise RuntimeError(f"Facebook API error: {msg}")
                time.sleep(2 ** attempt)
            except URLError as exc:
                if attempt == retries:
                    raise RuntimeError(f"Network error: {exc}")
                time.sleep(2 ** attempt)
        return {}

    def _get(self, url: str) -> dict:
        with urlopen(Request(url), timeout=30) as resp:
            return json.loads(resp.read().decode())


class _TokenExpiredError(RuntimeError):
    pass
