"""
TikTokUploader v3.0 — TikTok Content Posting API client.

Uses the TikTok Content Posting API (v2) to upload video files directly
to a TikTok creator account.

Docs: https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide

Requirements:
  - TikTok Developer App with content.post scope
  - Access token from TikTok OAuth2

Note: TikTok's API requires an approved developer app. For sandbox
testing, set use_sandbox=True in the config.
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

TIKTOK_API = "https://open.tiktokapis.com/v2"
CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB chunks (TikTok min is 5MB)


@dataclass
class TikTokConfig:
    access_token: str
    open_id: str = ""                  # from OAuth exchange
    privacy_level: str = "PUBLIC_TO_EVERYONE"  # or SELF_ONLY, FRIEND_ONLY
    allow_comments: bool = True
    allow_duet: bool = True
    allow_stitch: bool = True
    disabled: bool = False             # set True to skip TikTok uploads


@dataclass
class TikTokUploadResult:
    success: bool
    publish_id: Optional[str] = None
    video_id: Optional[str] = None
    share_url: Optional[str] = None
    error: Optional[str] = None
    clip_path: Optional[Path] = None


class TikTokUploader:
    """Upload videos to TikTok via the Content Posting API."""

    def __init__(self, config: TikTokConfig):
        self.cfg = config
        self._last_upload = 0.0
        self._min_gap_s = 60  # TikTok is stricter about rate limits

    # ── Public API ─────────────────────────────────────────────────────────

    def upload_clip(
        self,
        clip_path: Path,
        title: str,
        caption: str,
        hashtags: list = None,
    ) -> TikTokUploadResult:
        if self.cfg.disabled or not self.cfg.access_token:
            return TikTokUploadResult(False, error="TikTok upload disabled or no token")

        if not clip_path.exists():
            return TikTokUploadResult(False, error=f"File not found: {clip_path}")

        # Rate-limit guard
        elapsed = time.time() - self._last_upload
        if elapsed < self._min_gap_s:
            time.sleep(self._min_gap_s - elapsed)

        file_size = clip_path.stat().st_size
        log.info("[TikTok] Uploading: %s (%.1f MB)", clip_path.name, file_size / 1_048_576)

        full_caption = self._build_caption(title, caption, hashtags or [])

        for attempt in range(1, 4):
            try:
                result = self._do_upload(clip_path, file_size, full_caption)
                self._last_upload = time.time()
                return result
            except _TikTokTokenError as exc:
                log.error("[TikTok] Token error: %s", exc)
                return TikTokUploadResult(False, error=f"Token error: {exc}")
            except Exception as exc:
                log.warning("[TikTok] Upload attempt %d/3 failed: %s", attempt, exc)
                if attempt < 3:
                    time.sleep(2 ** attempt * 15)

        return TikTokUploadResult(False, error="TikTok upload failed after 3 attempts")

    def verify_token(self) -> bool:
        """Check if the access token is valid."""
        if not self.cfg.access_token:
            return False
        try:
            url = f"{TIKTOK_API}/user/info/?fields=display_name,open_id"
            resp = self._get(url)
            user = resp.get("data", {}).get("user", {})
            if user.get("open_id"):
                self.cfg.open_id = user["open_id"]
            log.info("[TikTok] Token valid — user: %s", user.get("display_name", "unknown"))
            return True
        except Exception as exc:
            log.error("[TikTok] Token check failed: %s", exc)
            return False

    # ── Upload flow ────────────────────────────────────────────────────────

    def _do_upload(self, clip_path: Path, file_size: int, caption: str) -> TikTokUploadResult:
        # Phase 1: Initialize upload session
        publish_id, upload_url = self._init_upload(file_size)
        log.debug("[TikTok] Upload session: publish_id=%s", publish_id)

        # Phase 2: Upload file in chunks
        self._upload_chunks(upload_url, clip_path, file_size)
        log.debug("[TikTok] Chunks uploaded")

        # Phase 3: Wait for processing & publish
        video_id = self._poll_status(publish_id)

        share_url = f"https://www.tiktok.com/@me/video/{video_id}" if video_id else ""
        return TikTokUploadResult(
            success=True,
            publish_id=publish_id,
            video_id=video_id,
            share_url=share_url,
            clip_path=clip_path,
        )

    def _init_upload(self, file_size: int):
        """Initialize a chunked upload session."""
        url = f"{TIKTOK_API}/post/publish/video/init/"
        payload = {
            "post_info": {
                "title": "",  # set at publish stage
                "privacy_level": self.cfg.privacy_level,
                "disable_duet": not self.cfg.allow_duet,
                "disable_comment": not self.cfg.allow_comments,
                "disable_stitch": not self.cfg.allow_stitch,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": CHUNK_SIZE,
                "total_chunk_count": (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE,
            },
        }
        resp = self._post_json(url, payload)
        data = resp.get("data", {})
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")
        if not publish_id or not upload_url:
            raise RuntimeError(f"TikTok init upload failed: {resp}")
        return publish_id, upload_url

    def _upload_chunks(self, upload_url: str, path: Path, file_size: int):
        """Upload file in chunks to TikTok's upload endpoint."""
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
        with open(path, "rb") as fh:
            for chunk_idx in range(total_chunks):
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                start = chunk_idx * CHUNK_SIZE
                end = start + len(chunk) - 1
                headers = {
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                }
                for attempt in range(3):
                    try:
                        req = Request(upload_url, data=chunk, headers=headers, method="PUT")
                        with urlopen(req, timeout=300):
                            pass
                        break
                    except Exception as exc:
                        if attempt == 2:
                            raise RuntimeError(f"TikTok chunk {chunk_idx} failed: {exc}")
                        time.sleep(5 * (attempt + 1))
                pct = int(100 * (chunk_idx + 1) / total_chunks)
                log.debug("[TikTok] Upload: %d%%", pct)

    def _poll_status(self, publish_id: str, max_wait: int = 120) -> Optional[str]:
        """Poll until the video is processed, return video_id."""
        url = f"{TIKTOK_API}/post/publish/status/fetch/"
        payload = {"publish_id": publish_id}
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                resp = self._post_json(url, payload)
                status = resp.get("data", {}).get("status")
                video_id = resp.get("data", {}).get("publicaly_available_post_id", [])
                if isinstance(video_id, list) and video_id:
                    video_id = str(video_id[0])
                else:
                    video_id = None
                if status == "PUBLISH_COMPLETE":
                    return video_id
                if status in ("FAILED", "ERROR"):
                    fail_reason = resp.get("data", {}).get("fail_reason", "unknown")
                    raise RuntimeError(f"TikTok publish failed: {fail_reason}")
                time.sleep(5)
            except RuntimeError:
                raise
            except Exception as exc:
                log.warning("[TikTok] Status poll error: %s", exc)
                time.sleep(5)
        log.warning("[TikTok] Timed out waiting for publish_id=%s", publish_id)
        return None

    # ── Caption builder ────────────────────────────────────────────────────

    def _build_caption(self, title: str, caption: str, hashtags: list) -> str:
        tags = " ".join(f"#{t.lstrip('#')}" for t in hashtags[:10]) if hashtags else ""
        base_tags = "#fyp #foryou #viral #movierecap #reels"
        text = f"{title[:80]}\n\n{base_tags}"
        if tags:
            text += f" {tags}"
        return text[:2200]  # TikTok caption limit

    # ── HTTP helpers ───────────────────────────────────────────────────────

    def _post_json(self, url: str, payload: dict) -> dict:
        body = json.dumps(payload).encode()
        req = Request(url, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {self.cfg.access_token}")
        req.add_header("Content-Type", "application/json; charset=UTF-8")
        try:
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            err_code = data.get("error", {}).get("code", "ok")
            if err_code not in ("ok", "success", 0):
                msg = data.get("error", {}).get("message", str(data))
                if "token" in msg.lower() or err_code in ("access_token_invalid",):
                    raise _TikTokTokenError(msg)
                raise RuntimeError(f"TikTok API error [{err_code}]: {msg}")
            return data
        except HTTPError as exc:
            body = exc.read().decode()[:300]
            if exc.code in (401, 403):
                raise _TikTokTokenError(body)
            raise RuntimeError(f"HTTP {exc.code}: {body}")

    def _get(self, url: str) -> dict:
        req = Request(url)
        req.add_header("Authorization", f"Bearer {self.cfg.access_token}")
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())


class _TikTokTokenError(RuntimeError):
    pass
