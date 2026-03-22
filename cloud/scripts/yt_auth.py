#!/usr/bin/env python3
"""
yt_auth.py — YouTube Shorts OAuth2 setup helper.

Run this once to authorize AUTO-REELS PRO to upload to your YouTube channel.
It will open a browser window for Google sign-in and save credentials to
cloud/config/yt_credentials.json.

Usage:
    cd autoreels-pro-v5
    python cloud/scripts/yt_auth.py
"""

import json
import sys
import webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import urlopen, Request

BASE = Path(__file__).parent.parent
CREDS_OUT = BASE / "config" / "yt_credentials.json"
CLIENT_SECRETS = BASE / "config" / "client_secret.json"  # download from Google Cloud Console

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
REDIRECT_URI = "http://localhost:8090"
AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class _CallbackHandler(BaseHTTPRequestHandler):
    code = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        _CallbackHandler.code = params.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body style=\"font-family:sans-serif;text-align:center;"
            b"padding:60px;background:#111;color:#0f0\">"
            b"<h2>Authorization successful!</h2>"
            b"<p>You can close this window and return to the terminal.</p>"
            b"</body></html>"
        )

    def log_message(self, *args):
        pass


def main():
    if not CLIENT_SECRETS.exists():
        print(f"\n❌ client_secret.json not found at {CLIENT_SECRETS}")
        print("\nTo get it:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create a project and enable 'YouTube Data API v3'")
        print("  3. Go to Credentials → Create → OAuth 2.0 Client ID")
        print("  4. Application type: Desktop App")
        print("  5. Download JSON → save as cloud/config/client_secret.json")
        sys.exit(1)

    with open(CLIENT_SECRETS) as f:
        secrets = json.load(f)

    # Support both "installed" and "web" format
    client_data = secrets.get("installed") or secrets.get("web") or secrets
    client_id = client_data.get("client_id")
    client_secret = client_data.get("client_secret")

    if not client_id or not client_secret:
        print("❌ Invalid client_secret.json format")
        sys.exit(1)

    # Build auth URL
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{AUTH_URL}?{urlencode(params)}"

    print("\n⚡ AUTO-REELS PRO v5.0 — YouTube Shorts Authorization")
    print("=" * 55)
    print(f"\nOpening browser for Google sign-in...")
    print(f"If it doesn't open, visit:\n  {auth_url}\n")

    webbrowser.open(auth_url)

    # Start local server to capture callback
    server = HTTPServer(("localhost", 8090), _CallbackHandler)
    print("Waiting for authorization callback...")
    server.handle_request()  # handle one request then stop

    code = _CallbackHandler.code
    if not code:
        print("❌ Authorization failed — no code received")
        sys.exit(1)

    # Exchange code for tokens
    payload = urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    try:
        req = Request(TOKEN_URL, data=payload, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urlopen(req, timeout=30) as resp:
            tokens = json.load(resp)
    except Exception as exc:
        print(f"❌ Token exchange failed: {exc}")
        sys.exit(1)

    # Save credentials
    creds = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": tokens.get("refresh_token"),
        "access_token": tokens.get("access_token"),
        "token_type": tokens.get("token_type"),
        "scope": tokens.get("scope"),
    }

    CREDS_OUT.parent.mkdir(parents=True, exist_ok=True)
    CREDS_OUT.write_text(json.dumps(creds, indent=2), encoding="utf-8")

    print(f"\n✅ Authorization successful!")
    print(f"   Credentials saved to: {CREDS_OUT}")
    print(f"\nNext steps:")
    print("  1. In config/config.yaml, set youtube_shorts.disabled: false")
    print("  2. Run: python main.py --check  to verify")
    print("  3. Run: python main.py --daemon  to start!\n")


if __name__ == "__main__":
    main()
