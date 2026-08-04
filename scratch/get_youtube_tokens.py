import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
import urllib.parse
import webbrowser
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config.json"

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

yt_creds = config.get("social_credentials", {}).get("youtube", {})
client_id = yt_creds.get("client_id")
client_secret = yt_creds.get("client_secret")

if not client_id or not client_secret:
    print("❌ Chưa cấu hình client_id hoặc client_secret trong config.json!")
    exit(1)

REDIRECT_URI = "http://localhost:5000/callback"

auth_params = {
    "client_id": client_id,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
    "access_type": "offline",
    "prompt": "consent"
}

auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(auth_params)}"

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [None])[0]

        if code:
            token_resp = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": REDIRECT_URI,
                    "grant_type": "authorization_code"
                }
            )
            token_data = token_resp.json()
            if "access_token" in token_data:
                config["social_credentials"]["youtube"]["enabled"] = True
                config["social_credentials"]["youtube"]["access_token"] = token_data.get("access_token", "")
                if token_data.get("refresh_token"):
                    config["social_credentials"]["youtube"]["refresh_token"] = token_data.get("refresh_token")
                
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("<h1>✅ Kết nối YouTube thành công! Bạn có thể đóng cửa sổ này.</h1>".encode("utf-8"))
                print("\n🎉 ĐÃ LẤY REFRESH TOKEN THÀNH CÔNG VÀ LƯU VÀO CONFIG.JSON!")
                global auth_success
                auth_success = True
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Lỗi: {token_data}".encode("utf-8"))
                print(f"❌ Lỗi lấy token: {token_data}")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write("Không nhận được mã authorization code!".encode("utf-8"))

print(f"\n🌐 URL cấp quyền YouTube: {auth_url}\n")
webbrowser.open(auth_url)

auth_success = False
server = HTTPServer(("127.0.0.1", 5000), OAuthCallbackHandler)
while not auth_success:
    server.handle_request()

