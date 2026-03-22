# ⚡ AUTO-REELS PRO v5.0

**Maximum Viral Growth Engine** — Automatically converts YouTube videos into viral short-form clips and publishes them across Facebook Reels, TikTok, Instagram Reels, and YouTube Shorts.

---

## 🚀 What's New in v5.0 (5x upgrade from v3)

| Feature | v3 | v5.0 |
|---|---|---|
| Brand themes | 1 (hardcoded) | **5** (Classic / Neon / Minimal / Dark / Gold) |
| Video encoder | Software only | **Hardware acceleration** (NVENC / VAAPI / VideoToolbox) |
| Clip selection | Random / even | **Quality scored** (audio energy + motion analysis) |
| Channel scanning | Sequential | **Concurrent** (scan all channels in parallel) |
| Platform uploads | Sequential | **Concurrent** multi-platform upload |
| Error handling | Simple retry | **Circuit breaker** per platform |
| Dashboard | 15s meta-refresh | **Real-time WebSocket** with live charts |
| Analytics | None | **Full tracker** (per-clip, per-platform, weekly reports) |
| Platforms | FB / TikTok / IG | + **YouTube Shorts** (new!) |
| Channel filters | None | **Keyword** include/exclude, min views |
| Setup | Manual file editing | **Interactive wizard** (`--setup`) |
| Token check | Facebook only | **All platforms** + expiry warnings |

---

## 📦 Installation

### 1. Prerequisites

- **Python 3.10+**
- **FFmpeg** (must be in your PATH)
  - Windows: https://ffmpeg.org/download.html → add to PATH
  - Mac: `brew install ffmpeg`
  - Linux: `apt install ffmpeg`
- **yt-dlp**: `pip install yt-dlp`

### 2. Install Python dependencies

```bash
cd autoreels-pro-v5/cloud
pip install -r requirements.txt
```

### 3. Run the setup wizard

```bash
python main.py --setup
```

This will create your `.env` file and configure `config/config.yaml` interactively.

### 4. Verify your tokens

```bash
python main.py --check
```

### 5. Start the daemon

```bash
python main.py --daemon
```

Open the dashboard: **http://localhost:8888**

---

## 🎬 Usage

```bash
# Interactive setup (first time)
python main.py --setup

# Check all tokens are valid
python main.py --check

# Run one cycle and exit (good for testing)
python main.py --once

# Run continuously (production)
python main.py --daemon

# Disable web dashboard
python main.py --daemon --no-web

# Disable Rich terminal UI (plain logs)
python main.py --daemon --no-ui

# Use a different config file
python main.py --daemon --config config/my_config.yaml
```

---

## 🎨 Brand Themes

Change the theme in `config/config.yaml` → `branding.theme`:

| Theme | Style |
|---|---|
| `classic` | Red accent, gold text (YouTube-style) |
| `neon` | Cyan/magenta glow, dark background |
| `minimal` | Clean white on dark, no bright colors |
| `dark` | Deep blue, electric blue accents |
| `gold` | Luxury gold gradients, warm tones |

---

## ⚡ Hardware Acceleration

v5.0 **automatically detects** your hardware encoder at startup:

- **NVIDIA GPU** → `h264_nvenc` (fastest, requires CUDA drivers)
- **macOS** → `h264_videotoolbox` (Apple Silicon / Intel Mac)
- **Linux Intel/AMD** → `h264_vaapi` (requires `/dev/dri`)
- **No GPU** → `libx264` software fallback (always works)

To disable hardware acceleration:
```yaml
output:
  hardware_accel: false
```

---

## 📊 Dashboard

Open **http://localhost:8888** while the daemon is running.

**Tabs:**
- **Dashboard** — Live stats, upload progress, charts
- **Job Queue** — All jobs with state, quality score, retry button
- **Analytics** — Per-platform totals, top videos, 7-day history
- **Logs** — Live log tail with colour coding

---

## 🔧 Adding YouTube Shorts

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **YouTube Data API v3**
3. Create OAuth2 credentials (Desktop App) → Download `credentials.json`
4. Place it at `cloud/config/yt_credentials.json`
5. Run the auth script: `python scripts/yt_auth.py`
6. In `config.yaml`, set `youtube_shorts.disabled: false`

---

## 📁 Project Structure

```
autoreels-pro-v5/
├── .env.example               ← copy to .env, fill in tokens
└── cloud/
    ├── main.py                ← entry point
    ├── requirements.txt
    ├── config/
    │   └── config.yaml        ← all settings
    ├── src/
    │   ├── processor/
    │   │   └── video_processor.py    ← FFmpeg clip engine (5 themes)
    │   ├── scheduler/
    │   │   ├── pipeline.py           ← orchestrator (concurrent uploads)
    │   │   └── job_queue.py          ← SQLite job queue
    │   ├── monitor/
    │   │   └── youtube_monitor.py    ← concurrent channel scanner
    │   ├── uploader/
    │   │   ├── facebook_uploader.py  ← resumable chunked upload
    │   │   ├── tiktok_uploader.py    ← TikTok Content API
    │   │   ├── instagram_uploader.py ← Instagram Graph API
    │   │   └── youtube_shorts.py     ← YouTube Data API v3 (NEW)
    │   ├── dashboard/
    │   │   └── app.py                ← Flask + WebSocket real-time UI
    │   ├── analytics/
    │   │   └── tracker.py            ← SQLite analytics (NEW)
    │   ├── notifier/
    │   │   └── notifier.py           ← Telegram + Discord alerts
    │   ├── health/
    │   │   └── monitor.py            ← CPU/RAM/disk monitoring
    │   └── utils/
    │       ├── cleanup.py
    │       └── git_ops.py
    ├── logs/                  ← autoreels.log (auto-created)
    ├── queue/                 ← jobs.db, analytics.db (auto-created)
    ├── downloads/             ← temp video downloads (auto-cleaned)
    └── output/                ← generated clips (auto-cleaned)
```

---

## ⚙️ Key Config Options

### Channel keyword filtering
```yaml
channels:
  - url: https://www.youtube.com/@SomeChannel
    keywords_filter: ["recap", "explained", "full movie"]
    exclude_keywords: ["trailer", "short", "teaser"]
    min_views: 10000
```

### Concurrent uploads
```yaml
concurrent_uploads: 3    # upload to 3 platforms simultaneously
```

### Quality scoring
```yaml
quality_score_clips: true   # score clips by audio energy + motion
```

### AI Captions (via Anthropic Claude)
```yaml
ai_captions: true    # set ANTHROPIC_API_KEY in .env
```

---

## 🔔 Notifications

### Telegram
1. Create a bot with [@BotFather](https://t.me/BotFather)
2. Get your Chat ID from [@userinfobot](https://t.me/userinfobot)
3. Add to `.env`: `TELEGRAM_TOKEN=...` and `TELEGRAM_CHAT_ID=...`
4. Set `notifications.enabled: true` in config.yaml

### Discord
1. Server Settings → Integrations → Webhooks → New Webhook → Copy URL
2. Add to `.env`: `DISCORD_WEBHOOK=https://discord.com/api/webhooks/...`
3. Set `notifications.enabled: true` in config.yaml

---

## 🐳 Docker

```bash
# Build
docker build -t autoreels-pro-v5 .

# Run
docker run -d \
  --name autoreels \
  --env-file .env \
  -v $(pwd)/cloud/config:/app/cloud/config \
  -v $(pwd)/cloud/queue:/app/cloud/queue \
  -v $(pwd)/cloud/logs:/app/cloud/logs \
  -p 8888:8888 \
  autoreels-pro-v5
```

---

## ❓ Troubleshooting

| Issue | Fix |
|---|---|
| `yt-dlp not installed` | `pip install yt-dlp` then `yt-dlp --update` |
| `FFmpeg not found` | Install FFmpeg and ensure it's in PATH |
| `Facebook token expired` | Generate a new Long-Lived Page Token via Graph API Explorer |
| `No hardware encoder detected` | Install NVIDIA drivers / update GPU drivers |
| `Dashboard not loading` | Try `--no-web` flag, check port 8888 isn't in use |
| `Clips are empty` | Check FFmpeg version: `ffmpeg -version` (need 4.0+) |
| `Whisper not found` | `pip install openai-whisper` or disable subtitles in config |

---

## 📜 License

For personal and commercial use. Do not redistribute without permission.

---

*AUTO-REELS PRO v5.0 — Built for maximum viral growth* ⚡
