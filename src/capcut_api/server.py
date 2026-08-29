#!/usr/bin/env python3
"""
CapCutAPI Unified Master Server (Port 9001)
===========================================
Consolidates all services into a single process:
1. React Frontend Single Page Application (Dashboard, Projects, Queue, Social Hub)
2. CapCut Pipeline & GUI Management APIs (gui_app)
3. CapCut Draft Creation & Video Render Engine API (server_app)
4. Multi-Platform Social Publisher & Scheduler (publisher_server)
5. Telegram Remote Control Bot (Background Daemon)
6. Precision Post Scheduler (APScheduler)
"""

from __future__ import annotations

import os
import sys
import time
import json
import re
import logging
import threading
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, Response, send_from_directory, render_template

# Setup pathing
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "api"))
sys.path.insert(0, str(BASE_DIR / "publisher"))
sys.path.insert(0, str(BASE_DIR / "bot"))
sys.path.insert(0, str(BASE_DIR / "core"))

# Configure unified logging
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("CapCutMasterServer")

# Paths for React Frontend
frontend_dist = ROOT_DIR / "frontend" / "dist"
templates_dir = ROOT_DIR / "templates"

# Create Unified Master Flask App with React frontend support
if frontend_dist.exists():
    logger.info(f"✅ Found React Frontend build at: {frontend_dist}")
    master_app = Flask(
        __name__,
        static_folder=str(frontend_dist / "assets"),
        static_url_path="/assets",
        template_folder=str(frontend_dist)
    )
else:
    logger.info(f"Using default templates at: {templates_dir}")
    master_app = Flask(
        __name__,
        template_folder=str(templates_dir)
    )

# Import sub-apps
try:
    from capcut_api.api.gui_app import app as gui_app
    for rule in list(gui_app.url_map.iter_rules()):
        view_func = gui_app.view_functions.get(rule.endpoint)
        if view_func and rule.endpoint not in master_app.view_functions and rule.rule != "/static/<path:filename>" and rule.rule != "/" and rule.rule != "/assets/<path:path>":
            master_app.add_url_rule(
                rule.rule,
                endpoint=f"gui_{rule.endpoint}",
                view_func=view_func,
                methods=rule.methods
            )
except Exception as e:
    logger.warning(f"Could not import gui_app routes: {e}")

try:
    from capcut_api.api.server_app import app as draft_app
    for rule in list(draft_app.url_map.iter_rules()):
        view_func = draft_app.view_functions.get(rule.endpoint)
        if view_func and rule.endpoint not in master_app.view_functions and rule.rule != "/static/<path:filename>":
            master_app.add_url_rule(
                rule.rule,
                endpoint=f"draft_{rule.endpoint}",
                view_func=view_func,
                methods=rule.methods
            )
except Exception as e:
    logger.warning(f"Could not import server_app routes: {e}")

try:
    from capcut_api.publisher.publisher_server import app as publisher_app
    for rule in list(publisher_app.url_map.iter_rules()):
        view_func = publisher_app.view_functions.get(rule.endpoint)
        if view_func and rule.endpoint not in master_app.view_functions and rule.rule != "/static/<path:filename>" and rule.rule != "/":
            master_app.add_url_rule(
                rule.rule,
                endpoint=f"pub_{rule.endpoint}",
                view_func=view_func,
                methods=rule.methods
            )
except Exception as e:
    logger.warning(f"Could not import publisher_server routes: {e}")

# Frontend Routes
@master_app.route("/", methods=["GET"])
@master_app.route("/novel", methods=["GET"])
@master_app.route("/projects", methods=["GET"])
@master_app.route("/queue", methods=["GET"])
@master_app.route("/social", methods=["GET"])
@master_app.route("/settings", methods=["GET"])
def index():
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        resp = send_from_directory(str(frontend_dist), "index.html")
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    return render_template("index.html")

@master_app.route("/outputs/novel_audio/<path:filename>", methods=["GET"])
def serve_master_novel_audio(filename):
    audio_dir = ROOT_DIR / "outputs" / "novel_audio"
    return send_from_directory(str(audio_dir), filename)

@master_app.route('/api/novels', methods=['GET'])
@master_app.route('/api/novel/list', methods=['GET'])
def list_master_novels():
    """Lấy danh sách toàn bộ các bộ truyện đã nhập."""
    try:
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        return jsonify({"success": True, "novels": repo.list_all_novels()})
    except Exception as e:
        logger.error(f"Lỗi list novels: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novels/import-folder', methods=['POST'])
def import_master_novel_folder():
    """Nhập truyện từ thư mục trên máy."""
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("novel_name", "").strip()
        folder = data.get("folder_path", "").strip()
        if not name or not folder:
            return jsonify({"success": False, "error": "Thiếu tên truyện hoặc đường dẫn thư mục"}), 400
        
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        res = repo.import_from_folder(name, folder)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi import folder: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novels/import-text', methods=['POST'])
def import_master_novel_text():
    """Nhập truyện từ file text hoặc paste văn bản raw."""
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("novel_name", "").strip()
        raw_text = data.get("raw_text", "").strip()
        if not name or not raw_text:
            return jsonify({"success": False, "error": "Thiếu tên truyện hoặc nội dung văn bản"}), 400
        
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        res = repo.import_from_text(name, raw_text)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi import text: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novels/upload-files', methods=['POST'])
def import_master_novel_files():
    """Nhập truyện từ danh sách 1 hoặc nhiều file upload (.txt, .md)."""
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("novel_name", "").strip()
        files = data.get("files", [])
        if not name or not files:
            return jsonify({"success": False, "error": "Thiếu tên truyện hoặc danh sách file"}), 400
        
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        res = repo.import_from_uploaded_files(name, files)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi upload novel files: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novels/delete', methods=['POST', 'DELETE'])
@master_app.route('/api/novel/delete', methods=['POST', 'DELETE'])
@master_app.route('/api/novels/<novel_id>', methods=['DELETE'])
@master_app.route('/api/novel/<novel_id>', methods=['DELETE'])
def delete_master_novel(novel_id=None):
    """Xóa bộ truyện khỏi danh sách."""
    try:
        if not novel_id:
            data = request.get_json(silent=True) or {}
            novel_id = data.get("novel_id", "").strip()
        if not novel_id:
            novel_id = request.args.get("novel_id", "").strip()
        if not novel_id:
            return jsonify({"success": False, "error": "Thiếu novel_id"}), 400
        
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        res = repo.delete_novel(novel_id)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi delete novel: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novels/<novel_id>/chapters', methods=['GET'])
@master_app.route('/api/novel/chapters', methods=['GET'])
def list_master_novel_chapters(novel_id=None):
    """Lấy danh sách các chương của 1 bộ truyện."""
    try:
        n_id = novel_id or request.args.get("novel_id", "Pham nhan tu tien")
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        chapters = repo.list_novel_chapters(n_id)
        return jsonify({"success": True, "novel_id": n_id, "chapters": chapters})
    except Exception as e:
        logger.error(f"Lỗi list novel chapters: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novels/<novel_id>/chapter', methods=['GET', 'POST'])
@master_app.route('/api/novel/chapter', methods=['GET', 'POST'])
def handle_master_novel_chapter(novel_id=None):
    """Đọc hoặc lưu nội dung chỉnh sửa của 1 chương."""
    try:
        n_id = novel_id or request.args.get("novel_id") or (request.get_json(silent=True) or {}).get("novel_id", "Pham nhan tu tien")
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        
        if request.method == 'GET':
            filename = request.args.get("file") or request.args.get("filename", "").strip()
            if not filename:
                return jsonify({"success": False, "error": "Thiếu filename"}), 400
            res = repo.get_chapter_content(n_id, filename)
            return jsonify(res)
        else:
            data = request.get_json(silent=True) or {}
            filename = data.get("filename") or data.get("file", "")
            content = data.get("content", "")
            if not filename:
                return jsonify({"success": False, "error": "Thiếu filename"}), 400
            res = repo.save_chapter_content(n_id, filename, content)
            return jsonify(res)
            filename = data.get("filename", "").strip()
            content = data.get("content", "")
            if not filename:
                return jsonify({"success": False, "error": "Thiếu filename"}), 400
            res = repo.save_chapter_content(novel_id, filename, content)
            return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi handle novel chapter: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novels/resplit', methods=['POST'])
def resplit_master_novel():
    """Tách lại toàn bộ chương từ file lớn và sinh lại Search Keys chuẩn."""
    try:
        data = request.get_json(silent=True) or {}
        novel_id = data.get("novel_id", "").strip()
        if not novel_id:
            return jsonify({"success": False, "error": "Thiếu novel_id"}), 400
        
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        res = repo.resplit_novel_chapters(novel_id)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi resplit novel: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novels/rename', methods=['POST'])
def rename_master_novel():
    """Đổi tên bộ truyện."""
    try:
        data = request.get_json(silent=True) or {}
        novel_id = data.get("novel_id", "").strip()
        new_name = data.get("new_name", "").strip()
        if not novel_id or not new_name:
            return jsonify({"success": False, "error": "Thiếu novel_id hoặc new_name"}), 400
        
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        res = repo.rename_novel(novel_id, new_name)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi rename novel: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novels/import-url', methods=['POST'])
def import_master_novel_url():
    """Nhập truyện từ link web."""
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("novel_name", "").strip()
        url = data.get("url", "").strip()
        if not url:
            return jsonify({"success": False, "error": "Thiếu URL trang truyện"}), 400
        
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        res = repo.import_from_url(name, url)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi import URL: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novels/visuals/<novel_id>', methods=['GET'])
def get_master_novel_visuals(novel_id):
    """Lấy danh sách hình ảnh trong Visuals Dataset của truyện."""
    try:
        from capcut_api.ai.visuals_dataset_manager import VisualsDatasetManager
        mgr = VisualsDatasetManager()
        images = mgr.list_dataset_images(novel_id)
        return jsonify({"success": True, "novel_id": novel_id, "count": len(images), "images": images})
    except Exception as e:
        logger.error(f"Lỗi lấy visuals dataset: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novels/extract_visuals', methods=['POST'])
def extract_master_novel_visuals():
    """Tự động trích xuất frame từ video vào Visuals Dataset."""
    try:
        data = request.get_json(silent=True) or {}
        video_path = data.get("video_path", "").strip()
        novel_id = data.get("novel_id", "").strip() or "Pham nhan tu tien"
        interval = float(data.get("interval_seconds", 3.0))
        max_frames = int(data.get("max_frames", 60))

        if not video_path:
            return jsonify({"success": False, "error": "Thiếu video_path"}), 400

        from capcut_api.ai.visuals_dataset_manager import VisualsDatasetManager
        mgr = VisualsDatasetManager()
        res = mgr.extract_frames_from_video(video_path, novel_id, interval, max_frames)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi extract visuals: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/generate_script_text', methods=['POST'])
def generate_master_novel_script_text():
    """API Chỉ tạo Kịch bản Văn bản dạng thuần (.txt) từ AI/Kho truyện mà chưa chạy TTS."""
    try:
        data = request.get_json(silent=True) or {}
        novel_id = str(data.get("novel_id", "Pham nhan tu tien"))
        current_episode_num = int(data.get("current_episode_num", 1))
        transcript_text = str(data.get("transcript_text", ""))
        prompt = data.get("prompt") or data.get("custom_prompt")

        from capcut_api.ai.novel_recap_engine import NovelVideoPipelineService
        service = NovelVideoPipelineService(novel_id=novel_id)
        
        all_novels = service.repo.list_all_novels()
        novel_obj = next((n for n in all_novels if n["id"] == novel_id), None)
        novel_title = novel_obj["name"] if novel_obj else "Phàm Nhân Tu Tiên"

        context = service.get_dynamic_novel_context(novel_id, transcript_text, prompt, current_episode_num=current_episode_num)
        curr_summary = transcript_text[:1500] if transcript_text else ""
        script = service.generate_script(curr_summary, context, current_episode_num, current_episode_num + 1, novel_title=novel_title, custom_prompt=prompt)
        
        # Tạo plain text thuần túy: mỗi câu 1 dòng kèm ký hiệu khoảng nghỉ [0.2], [0.5]
        scenes = script.get("scenes", [])
        output_lines = []

        def split_into_sentences_with_pauses(text: str) -> List[str]:
            raw_sents = [s.strip() for s in re.split(r'([\.\!\?…]+)', text) if s.strip()]
            sentences = []
            cur = ""
            for s in raw_sents:
                cur += s
                if re.match(r'[\.\!\?…]+', s):
                    sentences.append(cur.strip())
                    cur = ""
            if cur.strip():
                sentences.append(cur.strip())

            formatted = []
            for i, sent in enumerate(sentences):
                clean_s = re.sub(r'\[\d+(?:\.\d+)?\]', '', sent).strip()
                if not clean_s:
                    continue
                formatted.append(clean_s)
                pause = "[0.5]" if i == len(sentences) - 1 else "[0.2]"
                formatted.append(pause)
            return formatted

        for sc in scenes:
            vo = sc.get("voiceover", "").strip()
            if vo:
                sent_lines = split_into_sentences_with_pauses(vo)
                output_lines.extend(sent_lines)
                output_lines.append("")

        full_plain_text = "\n".join(output_lines).strip()
        return jsonify({
            "success": True,
            "title": script.get("title"),
            "full_plain_text": full_plain_text,
            "script": script,
            "scenes_count": len(scenes)
        })
    except Exception as e:
        logger.error(f"Lỗi generate script text: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/recap', methods=['POST'])
def generate_master_novel_recap():
    """API Tạo kịch bản + TTS + Project CapCut Draft đầy đủ tùy biến."""
    try:
        data = request.get_json(silent=True) or {}
        novel_id = str(data.get("novel_id", "xianni"))
        
        from capcut_api.ai.novel_recap_engine import NovelVideoPipelineService
        service = NovelVideoPipelineService(novel_id=novel_id)
        result = service.run_full_novel_recap(**data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Lỗi generate novel recap: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/scripts/list', methods=['GET'])
def list_novel_scripts_api():
    """API Lấy danh sách toàn bộ kịch bản đã tạo / có sẵn của bộ truyện."""
    try:
        novel_id = request.args.get("novel_id", "Pham nhan tu tien")
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        scripts = repo.list_novel_scripts(novel_id)
        return jsonify({"success": True, "novel_id": novel_id, "scripts": scripts})
    except Exception as e:
        logger.error(f"Lỗi list novel scripts: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/scripts/get', methods=['GET'])
def get_novel_script_api():
    """API Đọc nội dung 1 file kịch bản."""
    try:
        novel_id = request.args.get("novel_id", "Pham nhan tu tien")
        name = request.args.get("name", "")
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        res = repo.get_novel_script_content(novel_id, name)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi get novel script: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/scripts/save', methods=['POST'])
def save_novel_script_api():
    """API Lưu kịch bản mới hoặc kịch bản đã chỉnh sửa."""
    try:
        data = request.get_json(silent=True) or {}
        novel_id = str(data.get("novel_id", "Pham nhan tu tien"))
        name = str(data.get("name", "Kich_Ban_Review.txt"))
        content = str(data.get("content", ""))
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        res = repo.save_novel_script_content(novel_id, name, content)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi save novel script: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/scripts/delete', methods=['POST'])
def delete_novel_script_api():
    """API Xóa kịch bản."""
    try:
        data = request.get_json(silent=True) or {}
        novel_id = str(data.get("novel_id", "Pham nhan tu tien"))
        name = str(data.get("name", ""))
        from capcut_api.ai.novel_recap_engine import NovelRepositoryManager
        repo = NovelRepositoryManager()
        res = repo.delete_novel_script(novel_id, name)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi delete novel script: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route("/assets/<path:path>", methods=["GET"])
def serve_react_assets(path):
    if frontend_dist.exists():
        return send_from_directory(str(frontend_dist / "assets"), path)
    return "", 404

# Health & Unified Info Route
@master_app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "CapCutAPI Unified Master Server",
        "frontend": "React Single Page App (Active)",
        "version": "2.1.0",
        "timestamp": datetime.now().isoformat(),
        "modules": {
            "react_frontend": "active" if frontend_dist.exists() else "fallback_template",
            "gui_pipeline": "active",
            "draft_engine": "active",
            "social_publisher": "active",
            "scheduler": "active",
            "telegram_bot": "active"
        }
    })

def start_oauth_listeners():
    """Start background callback servers on port 4200 (Postiz redirect) and port 8080 (tool redirect)."""
    import http.server
    import urllib.parse
    import requests

    def handle_oauth_code(code: str, redirect_uri: str):
        try:
            cfg_path = ROOT_DIR / "config.json"
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            yt = cfg.get("social_credentials", {}).get("youtube", {})
            token_resp = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": yt.get("client_id", "").strip(),
                    "client_secret": yt.get("client_secret", "").strip(),
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                }
            )
            if token_resp.status_code == 200:
                tokens = token_resp.json()
                if "social_credentials" not in cfg:
                    cfg["social_credentials"] = {}
                if "youtube" not in cfg["social_credentials"]:
                    cfg["social_credentials"]["youtube"] = {}
                cfg["social_credentials"]["youtube"]["enabled"] = True
                if tokens.get("refresh_token"):
                    cfg["social_credentials"]["youtube"]["refresh_token"] = tokens.get("refresh_token")
                if tokens.get("access_token"):
                    cfg["social_credentials"]["youtube"]["access_token"] = tokens.get("access_token")
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
                logger.info(f"✅ Đã lưu thành công YouTube Token từ OAuth callback ({redirect_uri})!")
        except Exception as e:
            logger.warning(f"Lỗi xử lý OAuth callback: {e}")

    class OAuthHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed.query)
            code = query_params.get("code", [None])[0]
            
            # Determine redirect_uri used
            port = self.server.server_port
            if port == 4200:
                redirect_uri = "http://localhost:4200/integrations/social/youtube"
            else:
                redirect_uri = f"http://localhost:{port}/callback"

            if code:
                handle_oauth_code(code, redirect_uri)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html><head><meta charset="utf-8"><title>YouTube Connected</title>
            <style>body{font-family:-apple-system,BlinkMacSystemFont,Roboto,sans-serif;background:#09090b;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
            .card{background:#121216;border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:32px;text-align:center;max-width:400px;}
            h2{color:#22c55e;margin:0 0 10px 0;}p{color:#a1a1aa;font-size:14px;}</style></head>
            <body><div class="card"><h2>🎉 Kết Nối YouTube Thành Công!</h2><p>Hệ thống đã nhận Token OAuth. Cửa sổ đang tự đóng...</p></div>
            <script>
            try { if(window.opener) { window.opener.postMessage({type:'OAUTH_YOUTUBE_SUCCESS'},'*'); } } catch(e){}
            setTimeout(()=>{ window.close(); }, 1200);
            </script></body></html>
            """
            self.wfile.write(html.encode("utf-8"))

    def run_port(port: int):
        try:
            server = http.server.HTTPServer(("0.0.0.0", port), OAuthHandler)
            server.serve_forever()
        except Exception as e:
            logger.info(f"Port {port} listener not started: {e}")

    # Listen on port 4200 (exact Postiz URL) and port 8080
    threading.Thread(target=lambda: run_port(4200), name="OAuth4200Daemon", daemon=True).start()
    threading.Thread(target=lambda: run_port(8080), name="OAuth8080Daemon", daemon=True).start()


def start_telegram_bot_thread():
    """Start Telegram bot in a background thread if token is configured."""
    try:
        config_path = ROOT_DIR / "config.json"
        if not config_path.exists():
            logger.info("config.json not found, skipping Telegram Bot daemon")
            return

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        token = config.get("telegram_bot_token", "")
        if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
            logger.info("Telegram bot token not configured in config.json. Bot will stay in standby.")
            return

        logger.info("🚀 Khởi động Telegram Remote Control Bot trong background thread...")
        from capcut_api.bot.telegram_bot import main as bot_main
        
        bot_thread = threading.Thread(target=bot_main, name="TelegramBotDaemon", daemon=True)
        bot_thread.start()
        logger.info("✅ Telegram Bot Daemon đã chạy ngầm thành công!")
    except Exception as e:
        logger.warning(f"Không thể khởi động Telegram Bot: {e}")

def run_master_server(host: str = "0.0.0.0", port: int = 9001):
    """Run the unified master server."""
    start_oauth_listeners()
    start_telegram_bot_thread()

    print("\n" + "=" * 75)
    print(f"🎉🎉🎉 CapCutAPI Unified React & Backend Server tại http://127.0.0.1:{port}")
    print(f"🌟 React Web App:        http://127.0.0.1:{port}/")
    print(f"📁 Projects & Pipeline:  http://127.0.0.1:{port}/projects")
    print(f"📱 Social Hub & Publish: http://127.0.0.1:{port}/social")
    print(f"🎬 Draft API Endpoint:   http://127.0.0.1:{port}/create_draft")
    print(f"🚀 Publisher API:        http://127.0.0.1:{port}/api/v1/publish")
    print("=" * 75 + "\n")

    master_app.run(host=host, port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    run_master_server(port=9001)
