#!/usr/bin/env bash
# AUTO-REELS PRO v5.0 — Quick launcher for Linux/macOS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/cloud"

# Check Python version
PYTHON=$(command -v python3 || command -v python)
PY_VER=$("$PYTHON" -c "import sys; print(sys.version_info.major * 10 + sys.version_info.minor)")
if [ "$PY_VER" -lt 310 ]; then
    echo "❌ Python 3.10+ required. Found: $($PYTHON --version)"
    exit 1
fi

# Check FFmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo "❌ FFmpeg not found. Install it:"
    echo "   Mac:   brew install ffmpeg"
    echo "   Linux: sudo apt install ffmpeg"
    exit 1
fi

# Check yt-dlp
if ! command -v yt-dlp &>/dev/null; then
    echo "⚠  yt-dlp not found. Installing..."
    pip install yt-dlp
fi

# Check .env
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "⚠  No .env found. Running setup wizard..."
    "$PYTHON" main.py --setup
    exit 0
fi

# Load .env
set -a; source "$SCRIPT_DIR/.env"; set +a

# Install dependencies if not installed
if ! "$PYTHON" -c "import flask, apscheduler, rich, yt_dlp" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

echo ""
echo "⚡ AUTO-REELS PRO v5.0 starting..."
echo "   Dashboard: http://localhost:8888"
echo ""

exec "$PYTHON" main.py "$@"
