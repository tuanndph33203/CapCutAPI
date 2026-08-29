#!/usr/bin/env python3
"""
Interactive 1-Click YouTube OAuth 2.0 Token Generator
------------------------------------------------------
Helps you automatically obtain `refresh_token` and `access_token`
and saves them directly into `config.json`.
"""

import os
import sys
import json
import time
import urllib.parse
import webbrowser
import http.server
import socketserver
from pathlib import Path

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly"
]

CALLBACK_PORT = 8080
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

auth_code_holder = {"code": None, "error": None}


class OAuthCallbackHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence default server logs
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            query_params = urllib.parse.parse_qs(parsed.query)
            if "code" in query_params:
                auth_code_holder["code"] = query_params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                html = """
                <html>
                <body style="font-family: Arial; text-align: center; padding: 50px; background: #0f172a; color: #f8fafc;">
                    <h1 style="color: #22c55e;">🎉 Xác thực Google thành công!</h1>
                    <p style="font-size: 18px;">Bạn có thể đóng tab này và quay lại cửa sổ dòng lệnh (Terminal).</p>
                </body>
                </html>
                """
                self.wfile.write(html.encode("utf-8"))
            else:
                err = query_params.get("error", ["Unknown error"])[0]
                auth_code_holder["error"] = err
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h1>Xác thực thất bại: {err}</h1>".encode("utf-8"))


def load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def main():
    print("=" * 70)
    print("      🚀 CÔNG CỤ TỰ ĐỘNG LẤY REFRESH TOKEN YOUTUBE OAUTH 2.0")
    print("=" * 70)

    cfg = load_config()
    existing_creds = cfg.get("social_credentials", {}).get("youtube", {})

    client_id = existing_creds.get("client_id", "").strip()
    client_secret = existing_creds.get("client_secret", "").strip()

    # If not in config, prompt user
    if not client_id:
        print("\n👉 Vui lòng nhập Google Client ID (từ Google Cloud Console):")
        client_id = input("Client ID: ").strip()

    if not client_secret:
        print("\n👉 Vui lòng nhập Google Client Secret:")
        client_secret = input("Client Secret: ").strip()

    if not client_id or not client_secret:
        print("\n❌ LỖI: Client ID hoặc Client Secret không được để trống!")
        return

    # Prepare OAuth URL
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_request_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print("\n🌐 Đang khởi động máy chủ callback tại http://localhost:8080...")
    
    # Start local HTTP server
    try:
        server = socketserver.TCPServer(("localhost", CALLBACK_PORT), OAuthCallbackHandler)
    except OSError as e:
        print(f"\n❌ Lỗi: Cổng {CALLBACK_PORT} đang bị chiếm dụng bởi ứng dụng khác ({e}).")
        return

    print("🌐 Đang tự động mở trình duyệt để bạn đăng nhập Google & Cho phép quyền...")
    print(f"👉 Nếu trình duyệt không tự mở, hãy click link sau:\n{auth_request_url}\n")
    webbrowser.open(auth_request_url)

    # Wait for callback
    print("⏳ Đang chờ bạn xác thực trên trình duyệt...")
    while auth_code_holder["code"] is None and auth_code_holder["error"] is None:
        server.handle_request()

    server.server_close()

    if auth_code_holder["error"]:
        print(f"\n❌ Xác thực thất bại: {auth_code_holder['error']}")
        return

    code = auth_code_holder["code"]
    print(f"\n✅ Đã nhận Authorization Code từ Google!")
    print("🔄 Đang gửi request đổi lấy Refresh Token...")

    import requests
    token_resp = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    )

    if token_resp.status_code != 200:
        print(f"\n❌ Lỗi đổi token: {token_resp.text}")
        return

    tokens = token_resp.json()
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")

    if not refresh_token:
        print("\n⚠️ Cảnh báo: Google không trả về refresh_token (có thể do tài khoản đã cấp quyền trước đó).")
        print("💡 Hãy thử gỡ liên kết app tại https://myaccount.google.com/permissions rồi chạy lại.")
    else:
        print(f"\n🎉 LẤY THÀNH CÔNG REFRESH TOKEN!")

    # Save to config.json
    if "social_credentials" not in cfg:
        cfg["social_credentials"] = {}

    cfg["social_credentials"]["youtube"] = {
        "enabled": True,
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token or existing_creds.get("refresh_token", ""),
        "access_token": access_token or ""
    }

    save_config(cfg)
    print("💾 ĐÃ TỰ ĐỘNG LƯU VÀO FILE 'config.json'!")
    print("=" * 70)
    print("🚀 BÂY GIỜ HỆ THỐNG ĐÃ SẴN SÀNG ĐẨY VIDEO LÊN YOUTUBE!")
    print("=" * 70)


if __name__ == "__main__":
    main()
