"""
InstagramUploader v3.0 — Instagram Reels publishing via Graph API.

Uses the Instagram Graph API (v19+) to publish Reels to an
Instagram Business or Creator account linked to a Facebook Page.

Docs: https://developers.facebook.com/docs/instagram-api/guides/reels-publishing

Requirements:
  - Instagram Business or Creator account
  - Connected Facebook Page
  - instagram_basic, instagram_content_publish permissions
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

IG_GRAPH = "https://graph.facebook.com/v19.0"

HASHTAGS_IG = (
    "#reels #instareels #viral #fyp #movierecap #filmrecap "
    "#movies #foryou #explore #trending #movienight #filmnight "
    "#hollywoodmovies #cinema #entertainment #viralreels #shorts"
)


@dataclass
class InstagramConfig:
    ig_user_id: str               # Instagram User ID (numeric)
    access_token: str             # Page or User access token with IG permissions
    share_to_feed: bool = True    # also show in main feed
    disabled: bool = False        # set True to skip IG uploads


@dataclass
class InstagramUploadResult:
    success: bool
    media_id: Optional[str] = None
    permalink: Optional[str] = None
    error: Optional[str] = None
    clip_path: Optional[Path] = None


class InstagramUploader:
    """Publish Reels to Instagram via the Graph API."""

    def __init__(self, config: InstagramConfig):
        self.cfg = config
        self._last_upload = 0.0
        self._min_gap_s = 45

    # ── Public API ─────────────────────────────────────────────────────────

    def upload_clip(
        self,
        clip_path: Path,
        title: str,
        caption: str,
        hashtags: list = None,
        video_url: str = "",   # public CDN URL or hosted URL of the video
    ) -> InstagramUploadResult:
        """
        Upload a Reel to Instagram.

        Instagram Graph API requires the video to be hosted at a public URL.
        Pass video_url if the clip is hosted somewhere; otherwise this method
        will return an error since local file upload is not supported directly.

        Workaround: Host clips on a temporary CDN or public server.
        """
        if self.cfg.disabled or not self.cfg.access_token or not self.cfg.ig_user_id:
            return InstagramUploadResult(False, error="Instagram upload disabled or no credentials")

        if not video_url:
            return InstagramUploadResult(
                False,
                error="Instagram requires a public video URL. Host the clip first.",
            )

        elapsed = time.time() - self._last_upload
        if elapsed < self._min_gap_s:
            time.sleep(self._min_gap_s - elapsed)

        full_caption = self._build_caption(title, caption, hashtags or [])
        log.info("[Instagram] Publishing Reel: %s", clip_path.name if clip_path else title)

        for attempt in range(1, 4):
            try:
                result = self._do_publish(video_url, full_caption)
                self._last_upload = time.time()
                result.clip_path = clip_path
                return result
            except _IGTokenError as exc:
                return InstagramUploadResult(False, error=f"Token error: {exc}")
            except Exception as exc:
                log.warning("[Instagram] Attempt %d/3 failed: %s", attempt, exc)
                if attempt < 3:
                    time.sleep(2 ** attempt * 10)

        return InstagramUploadResult(False, error="Instagram upload failed after 3 attempts")

    def verify_token(self) -> bool:
        """Verify the token has Instagram publishing permissions."""
        if not self.cfg.access_token or not self.cfg.ig_user_id:
            return False
        try:
            url = (
                f"{IG_GRAPH}/{self.cfg.ig_user_id}"
                f"?fields=id,username,account_type"
                f"&access_token={self.cfg.access_token}"
            )
            resp = self._get(url)
            log.info(
                "[Instagram] Token valid — @%s (id=%s)",
                resp.get("username"), resp.get("id"),
            )
            return True
        except Exception as exc:
            log.error("[Instagram] Token check failed: %s", exc)
            return False

    # ── Upload flow ────────────────────────────────────────────────────────

    def _do_publish(self, video_url: str, caption: str) -> InstagramUploadResult:
        # Step 1: Create media container
        container_id = self._create_container(video_url, caption)
        log.debug("[Instagram] Container created: %s", container_id)

        # Step 2: Wait for container to be ready
        self._wait_for_container(container_id)

        # Step 3: Publish container
        media_id = self._publish_container(container_id)
        permalink = f"https://www.instagram.com/p/{media_id}/"
        log.info("[Instagram] Published! media_id=%s", media_id)
        return InstagramUploadResult(success=True, media_id=media_id, permalink=permalink)

    def _create_container(self, video_url: str, caption: str) -> str:
        url = f"{IG_GRAPH}/{self.cfg.ig_user_id}/media"
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],
            "share_to_feed": "true" if self.cfg.share_to_feed else "false",
            "access_token": self.cfg.access_token,
        }
        resp = self._post(url, payload)
        container_id = resp.get("id")
        if not container_id:
            raise RuntimeError(f"Failed to create IG container: {resp}")
        return container_id

    def _wait_for_container(self, container_id: str, max_wait: int = 300):
        """Poll until the container status is FINISHED."""
        url = (
            f"{IG_GRAPH}/{container_id}"
            f"?fields=status_code,status"
            f"&access_token={self.cfg.access_token}"
        )
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                resp = self._get(url)
                status = resp.get("status_code", "")
                if status == "FINISHED":
                    return
                if status == "ERROR":
                    raise RuntimeError(f"Container processing failed: {resp.get('status')}")
                log.debug("[Instagram] Container status: %s — waiting...", status)
                time.sleep(8)
            except RuntimeError:
                raise
            except Exception as exc:
                log.warning("[Instagram] Status poll error: %s", exc)
                time.sleep(8)
        raise RuntimeError(f"Container {container_id} timed out after {max_wait}s")

    def _publish_container(self, container_id: str) -> str:
        url = f"{IG_GRAPH}/{self.cfg.ig_user_id}/media_publish"
        payload = {
            "creation_id": container_id,
            "access_token": self.cfg.access_token,
        }
        resp = self._post(url, payload)
        media_id = resp.get("id")
        if not media_id:
            raise RuntimeError(f"Failed to publish IG container: {resp}")
        return media_id

    # ── Caption builder ────────────────────────────────────────────────────

    def _build_caption(self, title: str, caption: str, hashtags: list) -> str:
        extra = " ".join(f"#{t.lstrip('#')}" for t in hashtags[:10]) if hashtags else ""
        text = f"{title[:80]}\n\n{HASHTAGS_IG}"
        if extra:
            text += f" {extra}"
        return text[:2200]

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
                    if code in (190, 102, 200):
                        raise _IGTokenError(msg)
                except _IGTokenError:
                    raise
                except Exception:
                    msg = raw[:200]
                if attempt == retries:
                    raise RuntimeError(f"Instagram API error: {msg}")
                time.sleep(2 ** attempt)
            except URLError as exc:
                if attempt == retries:
                    raise RuntimeError(f"Network error: {exc}")
                time.sleep(2 ** attempt)
        return {}

    def _get(self, url: str) -> dict:
        with urlopen(Request(url), timeout=30) as resp:
            return json.loads(resp.read().decode())


class _IGTokenError(RuntimeError):
    pass
