"""
Notifier — multi-channel alert system.
Supports: Telegram Bot, Discord Webhook, Console fallback.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Optional
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)


class Notifier:
    """Route notifications to one or more channels (fire-and-forget in a thread)."""

    def __init__(self, config: dict):
        self.cfg = config or {}
        self._tg_token = self.cfg.get("telegram", {}).get("token", "")
        self._tg_chat = str(self.cfg.get("telegram", {}).get("chat_id", ""))
        self._discord_url = self.cfg.get("discord", {}).get("webhook_url", "")
        self._enabled = self.cfg.get("enabled", True)

    # ── Public API ─────────────────────────────────────────────────────────
    def send(self, title: str, body: str = "", urgent: bool = False):
        if not self._enabled:
            return
        msg = f"*{title}*" if title else ""
        if body:
            msg += f"\n{body}"
        threading.Thread(target=self._dispatch, args=(msg, urgent), daemon=True).start()

    def send_upload_success(self, title: str, clip_num: int, post_id: str, permalink: str):
        msg = (
            f"✅ *Upload Successful*\n"
            f"📹 {title[:60]}\n"
            f"🎬 Clip #{clip_num}\n"
            f"🆔 Post: `{post_id}`\n"
            f"🔗 {permalink}"
        )
        self._dispatch(msg)

    def send_error(self, context: str, error: str):
        msg = f"❌ *Error in {context}*\n`{error[:300]}`"
        self._dispatch(msg, urgent=True)

    def send_daily_report(self, uploads: int, limit: int, clips: int):
        pct = int(100 * uploads / limit) if limit else 0
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        msg = (
            f"📊 *Daily Report*\n"
            f"Uploads: {uploads}/{limit} [{bar}] {pct}%\n"
            f"Total clips: {clips}\n"
            f"Status: {'✅ Limit reached' if uploads >= limit else '🔄 In progress'}"
        )
        self._dispatch(msg)

    # ── Internal ───────────────────────────────────────────────────────────
    def _dispatch(self, message: str, urgent: bool = False):
        if self._tg_token and self._tg_chat:
            self._send_telegram(message)
        if self._discord_url:
            self._send_discord(message)
        if not self._tg_token and not self._discord_url:
            log.info("[NOTIFY] %s", message.replace("*", ""))

    def _send_telegram(self, text: str):
        url = f"https://api.telegram.org/bot{self._tg_token}/sendMessage"
        data = urlencode({
            "chat_id": self._tg_chat,
            "text": text,
            "parse_mode": "Markdown",
        }).encode()
        try:
            req = Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urlopen(req, timeout=10) as r:
                resp = json.loads(r.read())
                if not resp.get("ok"):
                    log.warning("Telegram send failed: %s", resp)
        except Exception as exc:
            log.warning("Telegram error: %s", exc)

    def _send_discord(self, text: str):
        # Strip markdown bold for Discord (uses ** not *)
        content = text.replace("*", "**")
        payload = json.dumps({"content": content[:2000]}).encode()
        try:
            req = Request(self._discord_url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=10):
                pass
        except Exception as exc:
            log.warning("Discord error: %s", exc)
