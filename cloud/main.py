#!/usr/bin/env python3
"""
AUTO-REELS PRO v5.0 — Maximum Viral Growth Engine
YouTube → Facebook · TikTok · Instagram · YouTube Shorts

5x Advanced Features:
  • AI-powered captions & hook generation
  • Smart face-aware 9:16 crop with quality scoring
  • 5 brand themes (Classic, Neon, Minimal, Dark, Gold)
  • Hardware acceleration (NVENC/VAAPI/VideoToolbox auto-detect)
  • Real-time WebSocket dashboard with live charts
  • Concurrent multi-platform uploads
  • Built-in analytics & performance tracking
  • YouTube Shorts support
  • Auto token health checks & refresh alerts
  • Circuit-breaker retry with smart back-off
  • Setup wizard for first-run configuration
"""

import argparse
import logging
import os
import signal
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

VERSION = "5.0"


# ── Auto-load .env ─────────────────────────────────────────────────────────────
def _load_dotenv():
    env_path = BASE.parent / ".env"
    if not env_path.exists():
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception as e:
        print(f"[WARN] Could not load .env: {e}")


_load_dotenv()

# ── Rich terminal UI ───────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    from rich.prompt import Prompt, Confirm
    from rich import box
    RICH = True
except ImportError:
    RICH = False

# ── APScheduler ────────────────────────────────────────────────────────────────
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    HAS_SCHEDULER = True
except ImportError:
    HAS_SCHEDULER = False

from src.config_manager import ConfigManager
from src.monitor.youtube_monitor import ChannelConfig, YouTubeMonitor
from src.processor.video_processor import ProcessorConfig, VideoProcessor
from src.uploader.facebook_uploader import FacebookConfig, FacebookUploader
from src.scheduler.job_queue import Job, JobQueue, JobState
from src.scheduler.pipeline import CloudPipeline
from src.notifier.notifier import Notifier
from src.health.monitor import HealthMonitor
from src.analytics.tracker import AnalyticsTracker
from src.utils.cleanup import CleanupManager
from src.utils.git_ops import GitOps

# ── Logging ────────────────────────────────────────────────────────────────────
LOGS = BASE / "logs"
LOGS.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOGS / "autoreels.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("autoreels.main")
console = Console() if RICH else None

BANNER = r"""
   ___         __            ____             __        ____  ____  ____
  / _ | __ __ / /____  ___  / __ \ ___ ___   / /  ___  / __ \/ __ \/ __ \
 / __ |/ // // __/ _ \/ _ \/ /_/ // -_) -_) / /__(_-< / /_/ / /_/ / /_/ /
/_/ |_|\___/ \__/\___/_//_/\____/ \__/\__/ /____/___/ / .___/\____/\____/
                                                      /_/     v5.0 ⚡
"""

FEATURES = [
    "🤖 AI-powered captions & hooks",
    "🎯 Smart face-aware 9:16 crop + quality scoring",
    "🎨 5 brand themes (Classic/Neon/Minimal/Dark/Gold)",
    "⚡ Hardware acceleration (NVENC/VAAPI/VideoToolbox)",
    "📊 Real-time WebSocket dashboard with live charts",
    "🚀 Concurrent multi-platform uploads",
    "📈 Built-in analytics & performance tracking",
    "🎬 YouTube Shorts support",
]


def print_banner():
    if RICH and console:
        console.print(Panel(
            Text(BANNER, style="bold cyan"),
            style="bold cyan", box=box.DOUBLE
        ))
        for feat in FEATURES:
            console.print(f"  {feat}")
        console.print()
    else:
        print(BANNER)


# ── Setup wizard ───────────────────────────────────────────────────────────────
def run_setup_wizard():
    """Interactive first-run setup wizard."""
    if not RICH:
        print("Install 'rich' for the setup wizard: pip install rich")
        return

    console.print(Panel("[bold cyan]AUTO-REELS PRO v5.0 — Setup Wizard[/]", style="cyan"))
    console.print("\nThis wizard will create your .env and config files.\n")

    env_path = BASE.parent / ".env"
    cfg_path = BASE / "config" / "config.yaml"

    # Collect credentials
    fb_page_id = Prompt.ask("  [cyan]Facebook Page ID[/]")
    fb_token = Prompt.ask("  [cyan]Facebook Page Access Token[/]", password=True)
    tiktok_token = Prompt.ask("  [dim]TikTok Access Token (leave blank to skip)[/]", default="")
    ig_user_id = Prompt.ask("  [dim]Instagram User ID (leave blank to skip)[/]", default="")
    ig_token = Prompt.ask("  [dim]Instagram Access Token (leave blank to skip)[/]", default="")
    tg_token = Prompt.ask("  [dim]Telegram Bot Token (leave blank to skip)[/]", default="")
    tg_chat = Prompt.ask("  [dim]Telegram Chat ID (leave blank to skip)[/]", default="")
    discord_webhook = Prompt.ask("  [dim]Discord Webhook URL (leave blank to skip)[/]", default="")

    channel_url = Prompt.ask("\n  [cyan]YouTube channel URL to monitor[/]")
    channel_name = Prompt.ask("  [cyan]Your brand channel name[/]", default="TimeFast")
    daily_limit = Prompt.ask("  [cyan]Daily upload limit[/]", default="5")
    theme = Prompt.ask("  [cyan]Brand theme[/] [dim](classic/neon/minimal/dark/gold)[/]", default="classic")

    # Write .env
    env_lines = [
        "# AUTO-REELS PRO v5.0 — generated by setup wizard",
        f"FACEBOOK_PAGE_ID={fb_page_id}",
        f"FACEBOOK_TOKEN={fb_token}",
        f"TIKTOK_TOKEN={tiktok_token}",
        f"INSTAGRAM_USER_ID={ig_user_id}",
        f"INSTAGRAM_TOKEN={ig_token}",
        f"TELEGRAM_TOKEN={tg_token}",
        f"TELEGRAM_CHAT_ID={tg_chat}",
        f"DISCORD_WEBHOOK={discord_webhook}",
    ]
    env_path.write_text("\n".join(env_lines), encoding="utf-8")
    console.print(f"\n  [green]✓[/] .env written to {env_path}")

    # Update config
    if cfg_path.exists():
        cfg_text = cfg_path.read_text(encoding="utf-8")
        # patch channel, brand, theme
        import re
        cfg_text = re.sub(r"(channel_name:\s*).*", f"\\g<1>{channel_name}", cfg_text)
        cfg_text = re.sub(r"(theme:\s*).*", f"\\g<1>{theme}", cfg_text)
        cfg_text = re.sub(r"(daily_upload_limit:\s*).*", f"\\g<1>{daily_limit}", cfg_text)
        # Replace first channel URL
        cfg_text = re.sub(
            r"(- url:\s*)https://www\.youtube\.com/[^\n]+",
            f"\\g<1>{channel_url}",
            cfg_text, count=1
        )
        cfg_path.write_text(cfg_text, encoding="utf-8")
        console.print(f"  [green]✓[/] config.yaml updated")

    console.print("\n[bold green]Setup complete![/] Run: [cyan]python main.py --daemon[/]\n")


# ── Pipeline builder ───────────────────────────────────────────────────────────
def build_pipeline(cfg: ConfigManager) -> CloudPipeline:
    raw = cfg.data

    channel_configs = [
        ChannelConfig(
            channel_url=ch["url"],
            max_videos_per_run=ch.get("max_videos_per_run", 1),
            min_duration=ch.get("min_duration", 60),
            max_duration=ch.get("max_duration", 7200),
            keywords_filter=ch.get("keywords_filter", []),
            quality_threshold=ch.get("quality_threshold", 0.0),
        )
        for ch in raw.get("channels", [])
    ]

    monitor = YouTubeMonitor(
        channels=channel_configs,
        downloads_dir=BASE / "downloads",
        seen_db_path=BASE / "queue" / "seen.json",
        cookies_file=raw.get("youtube", {}).get("cookies_file") or None,
        proxy=raw.get("youtube", {}).get("proxy") or None,
        concurrent_channels=raw.get("youtube", {}).get("concurrent_channels", 3),
    )

    out_cfg = raw.get("output", {})
    branding = raw.get("branding", {})

    proc_cfg = ProcessorConfig(
        clips_per_video=raw.get("clips_per_video", 10),
        clip_length_seconds=raw.get("clip_length_seconds", 55),
        output_width=out_cfg.get("width", 1080),
        output_height=out_cfg.get("height", 1920),
        crf=out_cfg.get("crf", 22),
        preset=out_cfg.get("preset", "fast"),
        hook_text=out_cfg.get("hook_text", "PART {index:02d}"),
        channel_name=branding.get("channel_name", "TimeFast"),
        watermark_text=branding.get("watermark", ""),
        add_progress_bar=out_cfg.get("progress_bar", True),
        add_subtitles=out_cfg.get("subtitles", True),
        whisper_model=out_cfg.get("whisper_model", "tiny"),
        scene_detection=raw.get("scene_detection", True),
        scene_threshold=float(raw.get("scene_threshold", 0.4)),
        skip_start_pct=float(raw.get("skip_start_pct", 0.08)),
        skip_end_pct=float(raw.get("skip_end_pct", 0.05)),
        parallel_workers=int(raw.get("parallel_workers", 2)),
        theme=branding.get("theme", "classic"),
        quality_score_clips=raw.get("quality_score_clips", True),
        generate_thumbnail=out_cfg.get("generate_thumbnail", True),
        use_hardware_accel=out_cfg.get("hardware_accel", True),
        ai_captions=raw.get("ai_captions", False),
        ai_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    )
    processor = VideoProcessor(proc_cfg, BASE / "output")

    # Facebook
    fb_raw = raw.get("facebook", {})
    uploader = FacebookUploader(FacebookConfig(
        page_id=fb_raw.get("page_id", ""),
        page_access_token=fb_raw.get("page_access_token", ""),
        published=fb_raw.get("published", True),
        upload_as_reel=fb_raw.get("upload_as_reel", True),
        default_caption=fb_raw.get("default_caption", "Watch this amazing clip!"),
    ))

    # TikTok
    tiktok_uploader = None
    tk_raw = raw.get("tiktok", {})
    tk_token = tk_raw.get("access_token", "")
    if tk_token and not tk_token.startswith("$"):
        try:
            from src.uploader.tiktok_uploader import TikTokConfig, TikTokUploader
            tiktok_uploader = TikTokUploader(TikTokConfig(
                access_token=tk_token,
                privacy_level=tk_raw.get("privacy_level", "PUBLIC_TO_EVERYONE"),
                allow_comments=tk_raw.get("allow_comments", True),
                allow_duet=tk_raw.get("allow_duet", True),
                allow_stitch=tk_raw.get("allow_stitch", True),
                disabled=tk_raw.get("disabled", False),
            ))
        except Exception as exc:
            log.warning("TikTok init failed: %s", exc)

    # Instagram
    ig_uploader = None
    ig_raw = raw.get("instagram", {})
    ig_token = ig_raw.get("access_token", "")
    ig_uid = ig_raw.get("ig_user_id", "")
    if ig_token and ig_uid and not ig_token.startswith("$"):
        try:
            from src.uploader.instagram_uploader import InstagramConfig, InstagramUploader
            ig_uploader = InstagramUploader(InstagramConfig(
                ig_user_id=ig_uid,
                access_token=ig_token,
                disabled=ig_raw.get("disabled", True),
            ))
        except Exception as exc:
            log.warning("Instagram init failed: %s", exc)

    # YouTube Shorts
    yt_shorts_uploader = None
    yt_raw = raw.get("youtube_shorts", {})
    yt_creds = yt_raw.get("credentials_file", "")
    if yt_creds and not yt_raw.get("disabled", True):
        try:
            from src.uploader.youtube_shorts import YouTubeShortsConfig, YouTubeShortsUploader
            yt_shorts_uploader = YouTubeShortsUploader(YouTubeShortsConfig(
                credentials_file=yt_creds,
                channel_id=yt_raw.get("channel_id", ""),
                category_id=str(yt_raw.get("category_id", "24")),
                privacy_status=yt_raw.get("privacy_status", "public"),
                disabled=yt_raw.get("disabled", True),
            ))
        except Exception as exc:
            log.warning("YouTube Shorts init failed: %s", exc)

    queue = JobQueue(BASE / "queue" / "jobs.db")
    analytics = AnalyticsTracker(BASE / "queue" / "analytics.db")

    return CloudPipeline(
        monitor=monitor,
        processor=processor,
        uploader=uploader,
        queue=queue,
        analytics=analytics,
        channel_configs=channel_configs,
        daily_limit=raw.get("daily_upload_limit", 5),
        upload_times=raw.get("upload_times", ["09:00", "12:00", "15:00", "18:00", "21:00"]),
        notifier=Notifier(raw.get("notifications", {})),
        tiktok_uploader=tiktok_uploader,
        instagram_uploader=ig_uploader,
        youtube_shorts_uploader=yt_shorts_uploader,
        concurrent_uploads=raw.get("concurrent_uploads", 2),
        max_retries=raw.get("max_retries", 3),
    )


# ── Rich dashboard ─────────────────────────────────────────────────────────────
def make_dashboard(pipeline, health, analytics):
    from src.scheduler.job_queue import JobState

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="queue", ratio=2),
    )
    layout["left"].split_column(
        Layout(name="stats"),
        Layout(name="platforms"),
    )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    accel = pipeline.processor.detected_encoder or "software"
    layout["header"].update(Panel(
        f"[bold cyan]AUTO-REELS PRO v5.0[/] ⚡ [yellow]{now}[/]  "
        f"[green]● RUNNING[/]  [dim]accel={accel}[/]",
        box=box.HORIZONTALS,
    ))

    stats = pipeline.queue.stats()
    s = Table(box=box.SIMPLE_HEAVY, show_header=False, padding=(0, 1))
    s.add_column("Key", style="dim")
    s.add_column("Val", style="bold yellow")
    s.add_row("Queued",       str(stats.get(JobState.QUEUED, 0)))
    s.add_row("Processing",   str(
        stats.get(JobState.PROCESSING, 0) +
        stats.get(JobState.DOWNLOADING, 0) +
        stats.get(JobState.UPLOADING, 0)
    ))
    s.add_row("Done",         str(stats.get(JobState.DONE, 0)))
    s.add_row("Failed",       str(stats.get(JobState.FAILED, 0)))
    s.add_row("─" * 12,      "─" * 8)
    s.add_row("Uploads Today", str(pipeline.uploads_today()))
    s.add_row("Daily Limit",  str(pipeline.daily_limit))
    s.add_row("Window",       "[green]OPEN ✓[/]" if pipeline._in_upload_window() else "[dim]closed[/]")
    s.add_row("Next Window",  pipeline._next_upload_time())
    s.add_row("─" * 12,      "─" * 8)
    s.add_row("Disk Free",    health.disk_free_gb())
    s.add_row("CPU",          health.cpu_pct())
    s.add_row("Memory",       health.mem_pct())
    layout["stats"].update(Panel(s, title="[bold]System", border_style="cyan"))

    # Platform upload breakdown
    p = Table(box=box.SIMPLE_HEAVY, show_header=False, padding=(0, 1))
    p.add_column("Platform", style="dim")
    p.add_column("Uploaded", style="bold yellow")
    weekly = analytics.weekly_totals()
    p.add_row("Facebook",   str(weekly.get("facebook", 0)))
    p.add_row("TikTok",     str(weekly.get("tiktok", 0)))
    p.add_row("Instagram",  str(weekly.get("instagram", 0)))
    p.add_row("YT Shorts",  str(weekly.get("youtube_shorts", 0)))
    p.add_row("[dim]Total[/]", str(sum(weekly.values())))
    layout["platforms"].update(Panel(p, title="[bold]This Week", border_style="magenta"))

    STATE_COLOR = {
        JobState.QUEUED: "yellow", JobState.DOWNLOADING: "cyan",
        JobState.PROCESSING: "magenta", JobState.UPLOADING: "blue",
        JobState.DONE: "green", JobState.FAILED: "red",
    }
    q = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    q.add_column("Title", max_width=38, style="white")
    q.add_column("State", style="bold")
    q.add_column("Clips", justify="right")
    q.add_column("Quality", justify="right")
    q.add_column("Updated", style="dim")
    for job in pipeline.queue.recent(14):
        color = STATE_COLOR.get(job.state, "white")
        updated = datetime.fromtimestamp(job.updated_at).strftime("%H:%M:%S")
        quality = f"{job.quality_score:.2f}" if job.quality_score else "-"
        q.add_row(
            job.title[:36],
            f"[{color}]{job.state}[/]",
            str(len(job.output_clips)),
            quality,
            updated
        )
    layout["queue"].update(Panel(q, title="[bold]Job Queue (recent 14)", border_style="cyan"))
    layout["footer"].update(Panel(
        "[dim]Ctrl+C to stop  |  Logs: cloud/logs/autoreels.log  |  "
        "Dashboard: http://localhost:8888  |  v5.0 ⚡[/dim]",
        box=box.HORIZONTALS,
    ))
    return layout


# ── Daemon ─────────────────────────────────────────────────────────────────────
def run_daemon(cfg, args):
    pipeline = build_pipeline(cfg)
    health = HealthMonitor(BASE)
    analytics = AnalyticsTracker(BASE / "queue" / "analytics.db")
    cleanup = CleanupManager(BASE, max_age_hours=cfg.data.get("cleanup_after_hours", 72))
    git_ops = GitOps(BASE.parent, cfg.data.get("git", {}))

    log.info("=" * 70)
    log.info("AUTO-REELS PRO v5.0 DAEMON STARTED")
    log.info("Channels: %d | Daily limit: %d | Upload windows: %s",
             len(pipeline.channel_configs), pipeline.daily_limit, pipeline.upload_times)
    log.info("Encoder: %s | Concurrent uploads: %d",
             pipeline.processor.detected_encoder or "software",
             pipeline.concurrent_uploads)
    log.info("Dashboard: http://localhost:%d", cfg.data.get("dashboard_port", 8888))
    log.info("=" * 70)

    pipeline.notifier.send(
        "🚀 AUTO-REELS PRO v5.0 started",
        f"Daemon running | {len(pipeline.channel_configs)} channels | limit={pipeline.daily_limit}/day"
    )

    if HAS_SCHEDULER:
        scheduler = BackgroundScheduler(timezone="UTC")
        interval = cfg.data.get("schedule", {}).get("check_interval_minutes", 15)
        scheduler.add_job(
            pipeline.run_once, IntervalTrigger(minutes=interval),
            id="pipeline", max_instances=1, coalesce=True,
        )
        scheduler.add_job(cleanup.run, CronTrigger(hour=3, minute=0), id="cleanup", max_instances=1)
        scheduler.add_job(
            lambda: pipeline.notifier.send("📊 Health", health.report()),
            CronTrigger(minute=0), id="health", max_instances=1,
        )
        # Weekly analytics report every Monday at 8am
        scheduler.add_job(
            lambda: pipeline.notifier.send(
                "📈 Weekly Analytics",
                analytics.weekly_report_text()
            ),
            CronTrigger(day_of_week="mon", hour=8), id="weekly_report", max_instances=1,
        )
        if cfg.data.get("git", {}).get("auto_push", False):
            scheduler.add_job(git_ops.auto_push, CronTrigger(hour="*/6"), id="git_push", max_instances=1)
        scheduler.start()
        log.info("Scheduler started — pipeline every %d min", interval)
    else:
        log.warning("APScheduler not installed — simple loop mode")

    # Start web dashboard
    if not getattr(args, "no_web", False):
        try:
            from src.dashboard.app import start_dashboard
            import threading
            t = threading.Thread(
                target=start_dashboard,
                args=(pipeline, health, analytics, cfg.data.get("dashboard_port", 8888)),
                daemon=True,
            )
            t.start()
            log.info("Dashboard thread started on port %d", cfg.data.get("dashboard_port", 8888))
        except Exception as exc:
            log.warning("Dashboard failed: %s", exc)

    # Signal handlers
    def _shutdown(sig, frame):
        log.info("Shutting down gracefully...")
        if HAS_SCHEDULER:
            try:
                scheduler.shutdown(wait=False)
            except Exception:
                pass
        pipeline.notifier.send("⛔ AUTO-REELS PRO v5.0 stopped")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _shutdown)

    print("\n" + "=" * 70)
    print(f"  ✅  AUTO-REELS PRO v5.0 IS RUNNING  ⚡")
    print(f"  📊  Dashboard   → http://localhost:{cfg.data.get('dashboard_port', 8888)}")
    print(f"  📁  Logs        → {LOGS / 'autoreels.log'}")
    print(f"  🎨  Theme       → {cfg.data.get('branding', {}).get('theme', 'classic')}")
    print(f"  ⚡  Encoder     → {pipeline.processor.detected_encoder or 'software'}")
    print("  ⏹   Press Ctrl+C to stop")
    print("=" * 70 + "\n")

    if RICH and console and not getattr(args, "no_ui", False):
        try:
            with Live(
                make_dashboard(pipeline, health, analytics),
                refresh_per_second=0.5, screen=False, console=console,
            ) as live:
                while True:
                    live.update(make_dashboard(pipeline, health, analytics))
                    if not HAS_SCHEDULER:
                        try:
                            pipeline.run_once()
                        except Exception as exc:
                            log.error("Pipeline error: %s", exc)
                    time.sleep(2)
        except Exception as exc:
            log.error("Rich UI failed, falling back to simple mode: %s", exc)
            _simple_loop(pipeline, health)
    else:
        _simple_loop(pipeline, health)


def _simple_loop(pipeline, health):
    while True:
        try:
            if not HAS_SCHEDULER:
                pipeline.run_once()
            else:
                stats = pipeline.queue.stats()
                log.info(
                    "Heartbeat — uploads: %d/%d | queue: %s | window: %s",
                    pipeline.uploads_today(), pipeline.daily_limit,
                    dict(stats),
                    "OPEN" if pipeline._in_upload_window() else f"next={pipeline._next_upload_time()}",
                )
        except Exception as exc:
            log.error("Loop error: %s", exc)
        time.sleep(60)


def run_once(cfg):
    pipeline = build_pipeline(cfg)
    log.info("Running single pipeline cycle...")
    results = pipeline.run_once()
    success = sum(1 for r in results if r.success)
    clips = sum(r.clips_made for r in results)
    log.info("Done: %d/%d jobs OK, %d clips uploaded", success, len(results), clips)
    return results


def check_config(cfg):
    """Validate config and check all API tokens."""
    pipeline = build_pipeline(cfg)

    results = {}

    # Facebook
    try:
        ok = pipeline.uploader.verify_token()
        days = pipeline.uploader.token_expires_in_days()
        results["Facebook"] = f"✓ VALID (expires in ~{days}d)" if ok else "✗ INVALID"
    except Exception as exc:
        results["Facebook"] = f"✗ ERROR: {exc}"

    # TikTok
    if pipeline.tiktok:
        try:
            ok = pipeline.tiktok.verify_token()
            results["TikTok"] = "✓ VALID" if ok else "✗ INVALID"
        except Exception as exc:
            results["TikTok"] = f"✗ ERROR: {exc}"
    else:
        results["TikTok"] = "— not configured"

    # Instagram
    if pipeline.instagram:
        try:
            ok = pipeline.instagram.verify_token()
            results["Instagram"] = "✓ VALID" if ok else "✗ INVALID"
        except Exception as exc:
            results["Instagram"] = f"✗ ERROR: {exc}"
    else:
        results["Instagram"] = "— not configured"

    # YouTube Shorts
    if pipeline.yt_shorts:
        results["YouTube Shorts"] = "✓ configured"
    else:
        results["YouTube Shorts"] = "— not configured"

    if RICH and console:
        t = Table(title="Token Status", box=box.ROUNDED)
        t.add_column("Platform", style="cyan")
        t.add_column("Status")
        for platform, status in results.items():
            color = "green" if status.startswith("✓") else ("red" if status.startswith("✗") else "dim")
            t.add_row(platform, f"[{color}]{status}[/]")
        console.print(t)
    else:
        for platform, status in results.items():
            print(f"  {platform:15} {status}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print_banner()

    parser = argparse.ArgumentParser(
        description="AUTO-REELS PRO v5.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--daemon",  action="store_true", help="Run continuously (default)")
    parser.add_argument("--once",    action="store_true", help="Run one cycle and exit")
    parser.add_argument("--check",   action="store_true", help="Validate config + tokens")
    parser.add_argument("--setup",   action="store_true", help="Run interactive setup wizard")
    parser.add_argument("--no-web",  action="store_true", help="Disable web dashboard")
    parser.add_argument("--no-ui",   action="store_true", help="Disable Rich terminal UI")
    parser.add_argument("--push",    action="store_true", help="Git push after run")
    parser.add_argument("--config",  default="config/config.yaml", help="Config file path")
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    args = parser.parse_args()

    if args.version:
        print(f"AUTO-REELS PRO v{VERSION}")
        sys.exit(0)

    if args.setup:
        run_setup_wizard()
        sys.exit(0)

    cfg_path = BASE / args.config
    if not cfg_path.exists():
        print(f"\n❌ Config not found: {cfg_path}")
        print("   Run --setup to create your configuration.")
        print("   Or: cd autoreels-pro-v5/cloud && python main.py --setup\n")
        sys.exit(1)

    try:
        cfg = ConfigManager(cfg_path)
        cfg.validate()
    except Exception as exc:
        print(f"\n❌ CONFIG ERROR: {exc}\n")
        print("Run: python main.py --setup  to reconfigure")
        sys.exit(1)

    if args.check:
        check_config(cfg)
        sys.exit(0)

    if args.once:
        try:
            results = run_once(cfg)
            if args.push:
                GitOps(BASE.parent, cfg.data.get("git", {})).auto_push()
            sys.exit(0 if any(r.success for r in results) else 1)
        except Exception as exc:
            log.error("Run failed: %s", exc)
            traceback.print_exc()
            sys.exit(1)

    try:
        run_daemon(cfg, args)
    except KeyboardInterrupt:
        print("\n\nStopped by user.")
        sys.exit(0)
    except Exception as exc:
        print(f"\n❌ FATAL ERROR: {exc}")
        traceback.print_exc()
        print("\nCheck cloud/logs/autoreels.log for details")
        sys.exit(1)


if __name__ == "__main__":
    main()
