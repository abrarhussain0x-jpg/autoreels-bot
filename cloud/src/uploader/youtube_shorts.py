"""
YouTubeShortsUploader v5.0 — Upload clips as YouTube Shorts.

Uses YouTube Data API v3 (resumable upload).
Requires OAuth2 credentials (credentials.json from Google Cloud Console).
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

YT_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YT_API_URL = "https://www.googleapis.com/youtube/v3"
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB chunks


@dataclass
class YouTubeShortsConfig:
    credentials_file: str       # path to OAuth2 credentials JSON
    channel_id: str = ""        # optional, for verification
    category_id: str = "24"     # 24 = Entertainment
    privacy_status: str = "public"   # public / private / unlisted
    made_for_kids: bool = False
    disabled: bool = False


@dataclass
class YouTubeShortsResult:
    success: bool
    video_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class YouTubeShortsUploader:
    def __init__(self, config: YouTubeShortsConfig):
        self.cfg = config
        self._token: Optional[str] = None
        self._token_expiry: float = 0
        self._load_credentials()

    def _load_credentials(self):
        """Load OAuth2 credentials from file."""
        creds_path = Path(self.cfg.credentials_file)
        if not creds_path.exists():
            log.warning("[YT Shorts] Credentials file not found: %s", creds_path)
            return
        try:
            with open(creds_path, encoding="utf-8") as f:
                self._creds = json.load(f)
        except Exception as exc:
            log.error("[YT Shorts] Failed to load credentials: %s", exc)
            self._creds = None

    def _get_access_token(self) -> Optional[str]:
        """Get or refresh access token using refresh_token flow."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        if not hasattr(self, "_creds") or not self._creds:
            return None

        creds = self._creds
        if "refresh_token" not in creds:
            log.error("[YT Shorts] No refresh_token in credentials")
            return None

        payload = urlencode({
            "client_id": creds.get("client_id", ""),
            "client_secret": creds.get("client_secret", ""),
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        }).encode()

        try:
            req = Request(
                "https://oauth2.googleapis.com/token",
                data=payload, method="POST"
            )
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                self._token = data.get("access_token")
                expires_in = int(data.get("expires_in", 3600))
                self._token_expiry = time.time() + expires_in
                # Save updated credentials
                creds["access_token"] = self._token
                Path(self.cfg.credentials_file).write_text(
                    json.dumps(creds, indent=2), encoding="utf-8"
                )
                return self._token
        except Exception as exc:
            log.error("[YT Shorts] Token refresh failed: %s", exc)
            return None

    def upload_clip(
        self,
        clip_path: Path,
        title: str,
        description: str,
        hashtags: list = None,
        thumbnail_path: Optional[Path] = None,
    ) -> YouTubeShortsResult:
        if self.cfg.disabled:
            return YouTubeShortsResult(False, error="YouTube Shorts upload disabled")

        if not clip_path.exists():
            return YouTubeShortsResult(False, error=f"File not found: {clip_path}")

        token = self._get_access_token()
        if not token:
            return YouTubeShortsResult(False, error="No access token available")

        # Build description with hashtag #Shorts for YouTube algorithm
        tags = hashtags or []
        hashtag_str = " ".join(f"#{t.lstrip('#')}" for t in tags[:15])
        full_desc = f"{description}\n\n{hashtag_str}\n\n#Shorts"

        # Build metadata
        metadata = {
            "snippet": {
                "title": title[:100],
                "description": full_desc[:5000],
                "categoryId": self.cfg.category_id,
                "tags": [t.lstrip("#") for t in tags[:500]],
                "defaultLanguage": "en",
            },
            "status": {
                "privacyStatus": self.cfg.privacy_status,
                "selfDeclaredMadeForKids": self.cfg.made_for_kids,
            },
        }

        file_size = clip_path.stat().st_size

        for attempt in range(1, 4):
            try:
                # Step 1: Initiate resumable upload session
                session_url = self._init_upload_session(token, metadata, file_size)
                if not session_url:
                    raise RuntimeError("Failed to get upload session URL")

                # Step 2: Upload file in chunks
                video_id = self._upload_file(session_url, clip_path, file_size, token)
                if not video_id:
                    raise RuntimeError("Upload completed but no video_id returned")

                url = f"https://www.youtube.com/shorts/{video_id}"
                log.info("[YT Shorts] Uploaded! video_id=%s url=%s", video_id, url)

                # Optional: upload thumbnail
                if thumbnail_path and thumbnail_path.exists():
                    self._upload_thumbnail(video_id, thumbnail_path, token)

                return YouTubeShortsResult(True, video_id=video_id, url=url)

            except Exception as exc:
                log.warning("[YT Shorts] Attempt %d/3 failed: %s", attempt, exc)
                if attempt < 3:
                    time.sleep(2 ** attempt * 8)

        return YouTubeShortsResult(False, error="Upload failed after 3 attempts")

    def _init_upload_session(self, token: str, metadata: dict, file_size: int) -> Optional[str]:
        meta_json = json.dumps(metadata).encode("utf-8")
        url = f"{YT_UPLOAD_URL}?uploadType=resumable&part=snippet,status"
        req = Request(url, data=meta_json, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json; charset=UTF-8")
        req.add_header("X-Upload-Content-Type", "video/mp4")
        req.add_header("X-Upload-Content-Length", str(file_size))
        with urlopen(req, timeout=30) as resp:
            return resp.headers.get("Location")

    def _upload_file(self, session_url: str, path: Path, file_size: int, token: str) -> Optional[str]:
        offset = 0
        with open(path, "rb") as fh:
            while offset < file_size:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                end = offset + len(chunk) - 1
                req = Request(session_url, data=chunk, method="PUT")
                req.add_header("Authorization", f"Bearer {token}")
                req.add_header("Content-Range", f"bytes {offset}-{end}/{file_size}")
                req.add_header("Content-Type", "video/mp4")
                try:
                    with urlopen(req, timeout=300) as resp:
                        if resp.status in (200, 201):
                            data = json.loads(resp.read())
                            return data.get("id")
                        # 308 = Resume Incomplete, continue
                        offset += len(chunk)
                except HTTPError as exc:
                    if exc.code == 308:
                        # Check Range header for resume offset
                        range_hdr = exc.headers.get("Range", "")
                        if range_hdr:
                            offset = int(range_hdr.split("-")[1]) + 1
                        else:
                            offset += len(chunk)
                    elif exc.code in (200, 201):
                        data = json.loads(exc.read())
                        return data.get("id")
                    else:
                        raise
                pct = int(100 * offset / file_size)
                if pct % 25 == 0:
                    log.debug("[YT Shorts] Upload: %d%%", pct)
        return None

    def _upload_thumbnail(self, video_id: str, thumb_path: Path, token: str):
        try:
            url = f"{YT_API_URL}/thumbnails/set?videoId={video_id}"
            with open(thumb_path, "rb") as f:
                data = f.read()
            req = Request(url, data=data, method="POST")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type", "image/jpeg")
            with urlopen(req, timeout=60):
                log.info("[YT Shorts] Thumbnail uploaded for %s", video_id)
        except Exception as exc:
            log.warning("[YT Shorts] Thumbnail upload failed: %s", exc)

    def verify_token(self) -> bool:
        token = self._get_access_token()
        if not token:
            return False
        try:
            req = Request(
                f"{YT_API_URL}/channels?part=id&mine=true",
            )
            req.add_header("Authorization", f"Bearer {token}")
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                return bool(data.get("items"))
        except Exception:
            return False
