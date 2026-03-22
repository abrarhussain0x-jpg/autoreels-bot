"""
Config Manager — loads YAML, merges environment variables,
validates required fields, and provides typed accessors.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# Keys that can be overridden by environment variables
ENV_MAP = {
    "FACEBOOK_PAGE_ID":   ("facebook", "page_id"),
    "FACEBOOK_TOKEN":     ("facebook", "page_access_token"),
    "TIKTOK_TOKEN":       ("tiktok", "access_token"),
    "INSTAGRAM_USER_ID":  ("instagram", "ig_user_id"),
    "INSTAGRAM_TOKEN":    ("instagram", "access_token"),
    "TELEGRAM_TOKEN":     ("notifications", "telegram", "token"),
    "TELEGRAM_CHAT_ID":   ("notifications", "telegram", "chat_id"),
    "DISCORD_WEBHOOK":    ("notifications", "discord", "webhook_url"),
    "YOUTUBE_COOKIES":    ("youtube", "cookies_file"),
    "YOUTUBE_PROXY":      ("youtube", "proxy"),
    "GIT_REMOTE":         ("git", "remote"),
    "GIT_BRANCH":         ("git", "branch"),
}

REQUIRED_FIELDS = [
    ("facebook", "page_id"),
    ("facebook", "page_access_token"),
    ("channels",),
]


class ConfigManager:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict = {}
        self._load()
        self._apply_env()

    def _load(self):
        with open(self.path, encoding="utf-8") as f:
            raw = f.read()
        # Expand ${VAR} / $VAR inside yaml values
        raw = re.sub(
            r"\$\{([^}]+)\}|\$([A-Z_][A-Z_0-9]*)",
            lambda m: os.environ.get(m.group(1) or m.group(2), m.group(0)),
            raw,
        )
        self.data = yaml.safe_load(raw) or {}
        log.info("Config loaded from %s", self.path)

    def _apply_env(self):
        for env_key, path in ENV_MAP.items():
            val = os.environ.get(env_key)
            if val:
                d = self.data
                for k in path[:-1]:
                    d = d.setdefault(k, {})
                d[path[-1]] = val
                log.debug("Env override applied: %s → %s", env_key, ".".join(path))

    def validate(self):
        errors = []
        for field_path in REQUIRED_FIELDS:
            d = self.data
            ok = True
            for k in field_path:
                if isinstance(d, dict) and k in d:
                    d = d[k]
                elif isinstance(d, list) and d:
                    break
                else:
                    ok = False
                    break
            if not ok or not d:
                errors.append(".".join(str(k) for k in field_path))
        if errors:
            raise ValueError(f"Config missing required fields: {', '.join(errors)}")
        log.info("Config validation passed")

    def get(self, *keys, default=None) -> Any:
        d = self.data
        for k in keys:
            if isinstance(d, dict):
                d = d.get(k)
            else:
                return default
            if d is None:
                return default
        return d

    def reload(self):
        self._load()
        self._apply_env()
        log.info("Config reloaded")
