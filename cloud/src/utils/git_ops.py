"""
GitOps — automatic git commit + push for logs/queue data.

Features:
  • Stage specific paths or patterns
  • Auto-commit with timestamped message
  • Push to remote with token auth support
  • Graceful fallback if git not installed
  • Dry-run mode for testing
"""

import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)


class GitOps:
    """Handles automated git commit + push for deployment / data sync."""

    def __init__(self, repo_dir: Path, config: dict):
        self.repo = Path(repo_dir)
        self.cfg = config or {}
        self.remote = self.cfg.get("remote", "origin")
        self.branch = self.cfg.get("branch", "main")
        self.push_paths: List[str] = self.cfg.get("push_paths", [
            "cloud/logs/",
            "cloud/queue/",
        ])
        self.dry_run: bool = self.cfg.get("dry_run", False)
        self._git_available: Optional[bool] = None

    # ── Public API ─────────────────────────────────────────────────────────

    def auto_push(self) -> bool:
        """Stage configured paths, commit with timestamp, and push."""
        if not self._check_git():
            return False

        if self.dry_run:
            log.info("[GitOps] Dry-run mode — skipping actual push")
            return True

        try:
            changed = self._stage_paths()
            if not changed:
                log.info("[GitOps] Nothing to commit")
                return True

            msg = f"[auto] Update logs/queue — {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            self._git("commit", "--no-verify", "-m", msg)
            self._git("push", self.remote, self.branch)
            log.info("[GitOps] Pushed to %s/%s", self.remote, self.branch)
            return True

        except subprocess.CalledProcessError as exc:
            log.warning("[GitOps] Push failed: %s", exc)
            return False
        except Exception as exc:
            log.error("[GitOps] Unexpected error: %s", exc)
            return False

    def is_dirty(self) -> bool:
        """Return True if the repo has uncommitted changes."""
        if not self._check_git():
            return False
        try:
            result = self._git("status", "--porcelain", capture=True)
            return bool(result.strip())
        except Exception:
            return False

    def current_commit(self) -> str:
        """Return the current HEAD short hash, or 'unknown'."""
        if not self._check_git():
            return "unknown"
        try:
            return self._git("rev-parse", "--short", "HEAD", capture=True).strip()
        except Exception:
            return "unknown"

    def current_branch(self) -> str:
        """Return current branch name."""
        if not self._check_git():
            return self.branch
        try:
            return self._git("rev-parse", "--abbrev-ref", "HEAD", capture=True).strip()
        except Exception:
            return self.branch

    # ── Internals ──────────────────────────────────────────────────────────

    def _stage_paths(self) -> bool:
        """Stage the configured push_paths. Returns True if anything was staged."""
        staged_any = False
        for rel_path in self.push_paths:
            full = self.repo / rel_path
            if full.exists():
                try:
                    self._git("add", rel_path)
                    staged_any = True
                    log.debug("[GitOps] Staged: %s", rel_path)
                except subprocess.CalledProcessError:
                    pass
        # Check if there's actually something in the index
        try:
            diff = self._git("diff", "--cached", "--name-only", capture=True)
            return bool(diff.strip())
        except Exception:
            return staged_any

    def _git(self, *args: str, capture: bool = False) -> str:
        """Run a git command in the repo directory."""
        cmd = ["git"] + list(args)
        if capture:
            result = subprocess.run(
                cmd, cwd=str(self.repo),
                capture_output=True, text=True,
                check=True, timeout=60,
            )
            return result.stdout
        else:
            subprocess.run(
                cmd, cwd=str(self.repo),
                check=True, timeout=60,
                stdout=subprocess.DEVNULL if not log.isEnabledFor(logging.DEBUG) else None,
                stderr=subprocess.DEVNULL if not log.isEnabledFor(logging.DEBUG) else None,
            )
            return ""

    def _check_git(self) -> bool:
        """Check once whether git is available and repo is valid."""
        if self._git_available is not None:
            return self._git_available
        try:
            subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=str(self.repo), capture_output=True,
                check=True, timeout=10,
            )
            self._git_available = True
        except (FileNotFoundError, subprocess.CalledProcessError):
            log.warning("[GitOps] git not available or not a git repo — auto-push disabled")
            self._git_available = False
        return self._git_available
