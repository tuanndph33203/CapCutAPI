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
from flask import Flask, request, jsonify, Response, send_from_directory, send_file, render_template

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
    try:
        from capcut_api.cloud.gdrive_manager import get_gdrive_manager
        audio_dir = get_gdrive_manager().get_outputs_dir() / "novel_audio"
        if not (audio_dir / filename).exists():
            audio_dir = ROOT_DIR / "data" / "outputs" / "novel_audio"
    except Exception:
        audio_dir = ROOT_DIR / "data" / "outputs" / "novel_audio"
    if not audio_dir.exists():
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

@master_app.route('/api/tts/voices', methods=['GET'])
@master_app.route('/api/voices', methods=['GET'])
def get_tts_voices():
    """Lấy danh mục các giọng đọc NghiTTS kèm thông tin giới tính, vùng miền, phong cách và câu thoại mẫu."""
    try:
        import urllib.parse
        from capcut_api.ai.nghitts_service import list_available_nghitts_voices
        raw_voices = list_available_nghitts_voices()
        enriched_voices = {
            name: {
                **meta,
                "preview_url": f"/api/tts/preview?voice={urllib.parse.quote(name)}"
            }
            for name, meta in raw_voices.items()
        }
        return jsonify({
            "success": True,
            "total": len(enriched_voices),
            "voices": enriched_voices
        })
    except Exception as e:
        logger.error(f"Lỗi get TTS voices: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/tts/preview', methods=['GET', 'POST'])
def preview_tts_voice():
    """Tạo hoặc phát file âm thanh mẫu (.wav) của giọng đọc NghiTTS (Preview Voice Sample)."""
    try:
        from capcut_api.ai.nghitts_service import get_voice_sample_audio_path, resolve_nghitts_voice
        
        voice_query = request.args.get("voice") or (request.get_json(silent=True) or {}).get("voice") or "Ngọc Huyền (mới)"
        custom_text = request.args.get("text") or (request.get_json(silent=True) or {}).get("text")
        
        resolved_voice = resolve_nghitts_voice(voice_query)
        sample_path = get_voice_sample_audio_path(resolved_voice, custom_text=custom_text)
        
        if not os.path.exists(sample_path) or os.path.getsize(sample_path) == 0:
            return jsonify({"success": False, "error": f"Không thể tạo audio mẫu cho giọng {resolved_voice}"}), 500
            
        return send_file(sample_path, mimetype="audio/wav")
    except Exception as e:
        logger.error(f"Lỗi preview TTS voice: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/tts/sync_drive', methods=['POST'])
@master_app.route('/api/tts/upload_to_drive', methods=['POST'])
def sync_tts_voices_to_drive():
    """Đồng bộ và sao lưu model giọng đọc (.onnx) và file âm thanh mẫu (.wav) lên Google Drive."""
    try:
        from capcut_api.ai.nghitts_service import sync_voices_to_gdrive
        data = request.get_json(silent=True) or {}
        voice = data.get("voice")
        download_missing = bool(data.get("download_missing", False))
        
        target_voices = None
        if voice and voice.lower() not in ("all", "*"):
            target_voices = [voice]
            
        result = sync_voices_to_gdrive(voice_names=target_voices, download_missing=download_missing)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Lỗi sync TTS to Drive: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/tts/drive_status', methods=['GET'])
def get_tts_drive_status():
    """Lấy trạng thái đồng bộ kho giọng đọc trên Google Drive."""
    try:
        from capcut_api.cloud.gdrive_manager import get_gdrive_manager
        from capcut_api.ai.nghitts_service import list_available_nghitts_voices
        
        gdrive = get_gdrive_manager()
        voices = list_available_nghitts_voices()
        
        models_dir = str(gdrive.get_tts_models_dir()) if gdrive else ""
        samples_dir = str(gdrive.get_tts_samples_dir()) if gdrive else ""
        
        synced_models = [name for name, v in voices.items() if v.get("is_in_drive")]
        synced_samples = [name for name, v in voices.items() if v.get("is_sample_ready")]
        
        return jsonify({
            "success": True,
            "is_drive_active": gdrive.mode == "desktop_mount" if gdrive else False,
            "mode": gdrive.mode if gdrive else "none",
            "models_dir": models_dir,
            "samples_dir": samples_dir,
            "synced_models_count": len(synced_models),
            "synced_samples_count": len(synced_samples),
            "synced_models": synced_models,
            "voices": voices
        })
    except Exception as e:
        logger.error(f"Lỗi get TTS drive status: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/generate_script_text', methods=['POST'])
def generate_master_novel_script_text():
    """API Chỉ tạo Kịch bản Văn bản dạng thuần (.txt) từ AI/Kho truyện mà chưa chạy TTS."""
    try:
        data = request.get_json(silent=True) or {}
        novel_id = str(data.get("novel_id", "Pham nhan tu tien"))
        current_episode_num = int(data.get("current_episode_num") or 0)
        next_episode_num = int(data.get("next_episode_num") or 0)
        transcript_text = str(data.get("transcript_text", "")).strip()
        video_path_str = str(data.get("video_path", "")).strip()
        srt_path_str = str(data.get("srt_path", "")).strip()
        prompt = str(data.get("prompt") or data.get("custom_prompt") or "").strip()

        # Tự động phát hiện bộ truyện nếu tên video hoặc prompt chứa tên truyện
        context_str = (video_path_str + " " + prompt).lower()
        if any(k in context_str for k in ["phàm nhân", "pham nhan", "hàn lập", "han lap"]):
            novel_id = "Pham nhan tu tien"
        elif any(k in context_str for k in ["tiên nghịch", "tien nghich", "vương lâm", "vuong lam", "仙逆"]):
            novel_id = "xianni"

        # Tự động trích xuất số tập từ Prompt nếu người dùng nhập trong Prompt (ví dụ: "viết tiếp tập 190", "viết tập 191 dựa trên tập 189")
        if prompt:
            # 1. Tìm cấu trúc rõ ràng: "Viết tập X ... từ / dựa trên / mốc của tập Y"
            target_match = re.search(r'(?:vi[ếe]t\s+(?:ti[ếe]p\s+)?(?:cho\s+)?t[aậ]p|t[aậ]p\s+m[ớo]i|k[ịi]ch\s+b[ảa]n\s+t[aậ]p)\s*(\d+)', prompt, re.IGNORECASE)
            ref_match = re.search(r'(?:t[ừu]|d[ựu]a\s+tr[êe]n|n[ốo]i\s+ti[ếe]p|sau|m[ốo]c|t[aậ]p\s+tr[ướu]c).*?t[aậ]p\s*(\d+)', prompt, re.IGNORECASE)

            if target_match and ref_match:
                next_episode_num = int(target_match.group(1))
                current_episode_num = int(ref_match.group(1))
            elif target_match:
                next_episode_num = int(target_match.group(1))
                if not current_episode_num or current_episode_num <= 0:
                    current_episode_num = max(1, next_episode_num - 1)
            elif ref_match:
                current_episode_num = int(ref_match.group(1))
                if not next_episode_num or next_episode_num <= 0:
                    next_episode_num = current_episode_num + 1
            else:
                m_p = re.findall(r'(?:t[aậ]p|ep|episode)\s*(\d+)', prompt, re.IGNORECASE)
                if m_p:
                    eps = [int(x) for x in m_p]
                    if len(eps) >= 2:
                        current_episode_num = min(eps)
                        next_episode_num = max(eps)
                    elif len(eps) == 1:
                        target_ep = eps[0]
                        if any(w in prompt.lower() for w in ["viết tiếp", "tiếp tập", "spoiler", "tập sau", "tập mới", "tập kế", "viết tập"]):
                            next_episode_num = target_ep
                            if not current_episode_num or current_episode_num <= 0:
                                current_episode_num = max(1, target_ep - 1)
                        else:
                            if not current_episode_num or current_episode_num <= 0:
                                current_episode_num = target_ep
                            if not next_episode_num or next_episode_num <= 0:
                                next_episode_num = target_ep + 1

        # Đảm bảo tuyệt đối: next_episode_num (tập đang viết) luôn lớn hơn current_episode_num (tập tham khảo)
        if current_episode_num > 0 and next_episode_num > 0 and next_episode_num < current_episode_num:
            current_episode_num, next_episode_num = next_episode_num, current_episode_num

        # Tự động trích xuất số tập từ tên file video nếu chưa có
        if video_path_str and (not current_episode_num or current_episode_num <= 0):
            first_line = video_path_str.splitlines()[0].strip()
            if first_line:
                vp_name = Path(first_line).name
                m = re.search(r'(?:t[aậ]p|ep|episode)[\s_.-]*(\d+)', vp_name, re.IGNORECASE) or re.search(r'(\d+)', vp_name)
                if m:
                    current_episode_num = int(m.group(1))

        if not next_episode_num:
            next_episode_num = (current_episode_num + 1) if current_episode_num > 0 else 2
        if not current_episode_num:
            current_episode_num = max(1, next_episode_num - 1)

        # BƯỚC 1: LẤY LỜI THOẠI THAM KHẢO TỪ VIDEO / SRT (TỪ STEP 1-2)
        if not transcript_text:
            # 1.1 Kiểm tra nếu có đường dẫn file SRT trực tiếp
            if srt_path_str and Path(srt_path_str).exists():
                transcript_text = Path(srt_path_str).read_text(encoding="utf-8", errors="ignore")

            # 1.2 Kiểm tra file video từ Step 1-2
            if not transcript_text and video_path_str:
                raw_vp = video_path_str.splitlines()[0].strip()
                vp = Path(raw_vp)
                if not vp.exists():
                    user_dl = Path(os.environ.get("USERPROFILE", r"C:\Users\admin.TRANANH")) / "Downloads"
                    cand_dl = user_dl / vp.name
                    if cand_dl.exists():
                        vp = cand_dl
                if vp.exists():
                    if vp.suffix.lower() == ".srt":
                        transcript_text = vp.read_text(encoding="utf-8", errors="ignore")
                    else:
                        # Tìm file srt cùng tên
                        srt_cand = vp.with_suffix(".srt")
                        if srt_cand.exists():
                            transcript_text = srt_cand.read_text(encoding="utf-8", errors="ignore")
                        else:
                            # Tìm file srt trong cùng thư mục theo số tập hoặc tên video
                            search_ep_nums = [n for n in [current_episode_num, next_episode_num] if n > 0]
                            search_ep_nums.extend([int(x) for x in re.findall(r'\d+', vp.stem) if int(x) > 0])
                            for ep_n in search_ep_nums:
                                if not transcript_text:
                                    for sp in vp.parent.glob(f"*{ep_n}*.srt"):
                                        transcript_text = sp.read_text(encoding="utf-8", errors="ignore")
                                        break
                            if not transcript_text:
                                for sp in vp.parent.glob("*.srt"):
                                    if vp.stem.lower() in sp.stem.lower() or sp.stem.lower() in vp.stem.lower():
                                        transcript_text = sp.read_text(encoding="utf-8", errors="ignore")
                                        break
                        
                        # Nếu chưa có file SRT, thử chạy local Whisper để bóc tách lời thoại từ video tham khảo
                        if not transcript_text:
                            logger.info(f"Chưa có file SRT cho video tham khảo Step 1-2 '{vp}'. Thử chạy local Whisper...")
                            try:
                                from capcut_api.ai.local_whisper_captions import transcribe_video_to_segments, segments_to_srt
                                segments, _ = transcribe_video_to_segments(str(vp), language="zh")
                                transcript_text = segments_to_srt(segments)
                                if transcript_text:
                                    srt_cand.write_text(transcript_text, encoding="utf-8")
                            except Exception as whisper_err:
                                logger.warning(f"Bỏ qua bước Whisper do lỗi: {whisper_err}")

            # 1.3 Quét tìm trong Downloads nếu có số tập
            if not transcript_text and (current_episode_num > 0 or next_episode_num > 0):
                user_dl = Path(os.environ.get("USERPROFILE", r"C:\Users\admin.TRANANH")) / "Downloads"
                for target_ep in [next_episode_num, current_episode_num]:
                    if target_ep > 0:
                        for cand in user_dl.glob(f"*{target_ep}*.srt"):
                            transcript_text = cand.read_text(encoding="utf-8", errors="ignore")
                            break
                    if transcript_text:
                        break

            # 1.4 Quét trong data/scene_analysis
            if not transcript_text and (current_episode_num > 0 or next_episode_num > 0):
                for target_ep in [next_episode_num, current_episode_num]:
                    if target_ep > 0:
                        for cand in Path("data/scene_analysis").glob(f"**/*{target_ep}*.srt"):
                            transcript_text = cand.read_text(encoding="utf-8", errors="ignore")
                            break
                    if transcript_text:
                        break

        # Nếu không có lời thoại video tham khảo, tự động fallback dùng tri thức tiểu thuyết & prompt để không chặn người dùng
        if not transcript_text or len(transcript_text.strip()) < 10:
            transcript_text = f"Tập {current_episode_num} vừa khép lại. Nhân vật chính cùng các thế lực chuẩn bị bước vào những diễn biến mới trong Tập {next_episode_num}."

        from capcut_api.ai.novel_recap_engine import NovelVideoPipelineService
        service = NovelVideoPipelineService(novel_id=novel_id)
        
        all_novels = service.repo.list_all_novels()
        novel_obj = next((n for n in all_novels if n["id"] == novel_id), None)
        novel_title = novel_obj["name"] if novel_obj else "Phàm Nhân Tu Tiên"

        # BƯỚC 2: DÒ TÌM CHƯƠNG TƯƠNG ỨNG TỪ NGUỒN THAM KHẢO & PROMPT
        context, detection_info = service.get_dynamic_novel_context(
            novel_id, transcript_text, prompt, current_episode_num=current_episode_num, next_episode_num=next_episode_num
        )
        if not context:
            return jsonify({
                "success": False, 
                "error": detection_info.get("error", "Không thể xác định chương truyện từ lời thoại đưa vào.")
            }), 400

        # BƯỚC 3: SINH KỊCH BẢN AI ĐIỀU KHIỂN THEO PROMPT & THAM KHẢO
        # Cập nhật số tập chính xác tuyệt đối được Bộ Óc AI phân tích từ yêu cầu tự nhiên của người dùng
        if detection_info.get("target_episode"):
            try:
                next_episode_num = int(detection_info["target_episode"])
            except Exception:
                pass
        if detection_info.get("reference_episode"):
            try:
                current_episode_num = int(detection_info["reference_episode"])
            except Exception:
                pass

        curr_summary = detection_info.get("bridge_summary") or detection_info.get("ending_summary") or transcript_text[-500:]
        script = service.generate_script(curr_summary, context, current_episode_num, next_episode_num, novel_title=novel_title, custom_prompt=prompt, detection_info=detection_info)
        
        full_plain_text = script.get("full_plain_text")
        scenes = script.get("scenes", [])
        if not full_plain_text:
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

            opening_hook = script.get("opening_hook", "").strip()
            if opening_hook:
                output_lines.extend(split_into_sentences_with_pauses(opening_hook))
                output_lines.append("")

            for sc in scenes:
                vo = sc.get("voiceover", "").strip()
                if vo and vo != opening_hook:
                    sent_lines = split_into_sentences_with_pauses(vo)
                    output_lines.extend(sent_lines)
                    output_lines.append("")

            closing_outro = script.get("closing_outro", "").strip()
            if closing_outro:
                output_lines.extend(split_into_sentences_with_pauses(closing_outro))

            full_plain_text = "\n".join(output_lines).strip()

        # Tự động lưu kịch bản vào DatabaseManager (MongoDB Atlas hoặc Local Fallback)
        saved_doc = None
        try:
            from capcut_api.database.mongo_manager import get_db_manager
            db = get_db_manager()
            saved_doc = db.save_script(
                novel_id=novel_id,
                target_episode=next_episode_num,
                script_data=script,
                detection_info=detection_info,
                custom_prompt=prompt
            )
        except Exception as db_err:
            logger.warning(f"Không thể lưu kịch bản vào Database: {db_err}")

        return jsonify({
            "success": True,
            "detected_info": detection_info,
            "title": script.get("title"),
            "full_plain_text": full_plain_text,
            "script": script,
            "scenes_count": len(scenes),
            "script_id": saved_doc.get("script_id") if saved_doc else None
        })
    except Exception as e:
        logger.error(f"Lỗi generate script text: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/analyze_scenes', methods=['POST'])
def analyze_master_novel_scenes():
    """Dùng BỘ ÓC AI (Gemini/DeepSeek) để đọc hiểu kịch bản và phân tích thành các PHÂN CẢNH ĐIỆN ẢNH (Cinematic Scenes) hoàn chỉnh."""
    try:
        data = request.get_json(silent=True) or {}
        script_text = str(data.get("script_text", "")).strip()
        novel_title = str(data.get("novel_title") or data.get("novel_id") or "Phàm Nhân Tu Tiên").strip()
        user_prompt = str(data.get("prompt", "")).strip()

        if not script_text:
            return jsonify({"success": False, "error": "Chưa có nội dung kịch bản để phân tích."}), 400

        from capcut_api.api.gui_app import build_ai_translation_config, call_ai_json_object
        ai_config = build_ai_translation_config(item_config={}, purpose="context")

        sys_prompt = f"""Bạn là BẬC THẦY ĐẠO DIỄN PHÂN CẢNH & HÌNH ẢNH HOẠT HÌNH 3D (Animation Storyboard Director & Visual Editor).

NHIỆM VỤ:
Phân tích đoạn kịch bản thuyết minh hoạt hình {novel_title} dưới đây và chia thành các PHÂN CẢNH ĐIỆN ẢNH (Cinematic Scenes) mạch lạc, sống động, khớp với video hoạt hình.

QUY TẮC BẮT BUỘC TUÂN THỦ:
1. TUYỆT ĐỐI KHÔNG CHIA MỖI CÂU LÀ MỘT CẢNH! 
   Mỗi phân cảnh BẮT BUỘC là một khối bối cảnh trọn vẹn (khoảng 3 đến 8 câu, thời lượng khoảng 15 đến 35 giây).
2. TIÊU CHÍ XÁC ĐỊNH ĐIỂM CHUYỂN CẢNH (SCENE BREAK):
   Chỉ chuyển cảnh khi có sự thay đổi rõ ràng về:
   - Địa điểm / Không gian (ví dụ: từ đại điện sang mật thất, từ chiến trường sang hoang nguyên).
   - Tuyến nhân vật hoặc góc quay trọng tâm (ví dụ: chuyển từ lời bàn luận của Hàn Lập sang hành động của kẻ thù).
   - Bước ngoặt hành động lớn (bùng nổ chiêu thức, kẻ địch mới xuất hiện, bước ngoặt tình thế).
3. ĐẦU RA JSON BẮT BUỘC:
{{
  "scenes": [
    {{
      "scene_id": 1,
      "title": "Tiêu đề phân cảnh ngắn gọn, hấp dẫn",
      "location": "Địa điểm bối cảnh",
      "characters": ["Nhân vật xuất hiện"],
      "action_summary": "Tóm tắt diễn biến hình ảnh",
      "visual_prompt": "Mô tả chi tiết hình ảnh anime 3D cho cảnh này để tìm/cắt ảnh từ phim",
      "voiceover": "Toàn bộ đoạn văn thuyết minh của phân cảnh này. Các câu bên trong ngăn cách bằng [0.2]. TUYỆT ĐỐI KHÔNG để [0.5] ở giữa cảnh.",
      "estimated_duration_sec": 25
    }}
  ]
}}"""

        res = None
        if ai_config and ai_config.get("enabled"):
            try:
                res = call_ai_json_object(ai_config, sys_prompt, {"script_text": script_text, "custom_instruction": user_prompt})
            except Exception as ai_err:
                logger.warning(f"Lỗi gọi AI phân cảnh: {ai_err}")

        parsed_scenes = []
        if isinstance(res, dict) and "scenes" in res and len(res["scenes"]) > 0:
            parsed_scenes = res["scenes"]
        else:
            # Fallback thông minh: Tự động gom 3-6 câu thành 1 phân cảnh (thời lượng 20-30s), tuyệt đối không để 1 câu 1 cảnh
            clean_lines = [l.strip() for l in script_text.splitlines() if l.strip()]
            sentences = []
            for l in clean_lines:
                if not re.match(r'^\[\d+(?:\.\d+)?\]$', l):
                    sentences.append(l)

            # Gom nhóm 4 câu thành 1 phân cảnh
            chunk_size = 4
            for i in range(0, len(sentences), chunk_size):
                chunk = sentences[i:i + chunk_size]
                vo = "\n[0.2]\n".join(chunk)
                sc_id = (i // chunk_size) + 1
                parsed_scenes.append({
                    "scene_id": sc_id,
                    "title": f"Phân Cảnh #{sc_id}: Diễn biến {chunk[0][:30]}...",
                    "location": "Bối cảnh phim",
                    "characters": ["Nhân vật chính"],
                    "action_summary": f"Diễn biến phân cảnh {sc_id}",
                    "visual_prompt": f"Anime 3D {novel_title}, scene {sc_id}, cinematic lighting, 4k",
                    "voiceover": vo,
                    "estimated_duration_sec": round(len(vo.split()) / 3.3, 1)
                })

        # Xây dựng lại full_plain_text với [0.5] CHỈ ĐỨNG GIỮA CÁC PHÂN CẢNH
        scene_vos = []
        for sc in parsed_scenes:
            vo = sc.get("voiceover", "").strip()
            if vo:
                scene_vos.append(vo)

        formatted_script = "\n[0.5]\n".join(scene_vos)

        return jsonify({
            "success": True,
            "scenes": parsed_scenes,
            "scenes_count": len(parsed_scenes),
            "full_plain_text": formatted_script
        })
    except Exception as e:
        logger.error(f"Lỗi analyze_master_novel_scenes: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/recap', methods=['POST'])
@master_app.route('/api/novel/pipeline/run', methods=['POST'])
def generate_master_novel_recap():
    """API Tạo kịch bản + TTS NghiTTS 1.2x + AI Phân cảnh + Project CapCut Draft đầy đủ 5 bước."""
    try:
        data = request.get_json(silent=True) or {}
        novel_id = str(data.get("novel_id", "Pham nhan tu tien"))
        if "voice_name" in data and "voice" not in data:
            data["voice"] = data["voice_name"]
        
        from capcut_api.ai.novel_recap_engine import NovelVideoPipelineService
        service = NovelVideoPipelineService(novel_id=novel_id)
        result = service.run_full_novel_recap(**data)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Lỗi generate novel recap: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/open_capcut', methods=['POST'])
def open_capcut_draft_api():
    """API Kích hoạt mở ứng dụng CapCut PC và thư mục dự án."""
    try:
        data = request.get_json(silent=True) or {}
        draft_folder = data.get("draft_folder", "")
        from capcut_api.ai.novel_video_pipeline import NovelVideoPipeline
        pipeline = NovelVideoPipeline()
        res = pipeline.step5_open_capcut_and_export(draft_folder=draft_folder, auto_launch=True)
        return jsonify({"success": True, "result": res})
    except Exception as e:
        logger.error(f"Lỗi open CapCut: {e}", exc_info=True)
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

# =========================================================================
# 🎬 SCENE ANALYSIS & GOOGLE DRIVE CLOUD SYNC ENDPOINTS
# =========================================================================

@master_app.route('/api/novel/scenes/upload_video', methods=['POST'])
def upload_novel_scene_video():
    """Tải lên video tập phim để chuẩn bị phân tích phân cảnh."""
    try:
        novel_id = request.form.get("novel_id", "Pham nhan tu tien")
        episode_num = int(request.form.get("episode_num", 186))
        
        if 'video' not in request.files:
            return jsonify({"success": False, "error": "Không tìm thấy file video trong yêu cầu."}), 400
            
        file = request.files['video']
        if file.filename == '':
            return jsonify({"success": False, "error": "Chưa chọn file video."}), 400

        from capcut_api.cloud.gdrive_manager import get_gdrive_manager
        upload_dir = get_gdrive_manager().get_uploads_dir()
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Lưu file video trực tiếp vào Google Drive 5TB
        clean_name = f"{novel_id}_Tap_{episode_num}_{Path(file.filename).name}"
        save_path = upload_dir / clean_name
        file.save(str(save_path))
        
        return jsonify({
            "success": True,
            "filename": clean_name,
            "path": str(save_path.resolve()),
            "message": f"Đã tải lên video '{clean_name}' thành công!"
        })
    except Exception as e:
        logger.error(f"Lỗi upload scene video: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/scenes/full_pipeline', methods=['POST'])
def run_novel_scene_full_pipeline():
    """
    Quy trình phân tích phân cảnh toàn diện:
    1. Whisper Audio-to-SRT
    2. AI nhận xét & chọn lọc mốc nổi bật
    3. Cắt Keyframes sắc nét
    4. AI mô tả chi tiết khung cảnh
    5. Lưu vào Database
    6. Tự động đẩy ảnh lên Google Drive
    """
    try:
        data = request.get_json(silent=True) or {}
        novel_id = str(data.get("novel_id", "Pham nhan tu tien"))
        novel_name = str(data.get("novel_name", novel_id))
        episode_num = int(data.get("episode_num", 186))
        video_path = data.get("video_path")
        auto_upload_drive = bool(data.get("auto_upload_drive", True))

        from capcut_api.ai.scene_analyzer import SceneAnalyzerService
        svc = SceneAnalyzerService()
        res = svc.run_full_scene_pipeline(
            novel_id=novel_id,
            novel_name=novel_name,
            episode_num=episode_num,
            video_path=video_path,
            auto_upload_drive=auto_upload_drive
        )
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi run full scene pipeline: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/scenes/list', methods=['GET'])
def list_novel_scenes_api():
    """Lấy danh sách các tập phim đã phân tích cảnh của bộ truyện."""
    try:
        novel_id = request.args.get("novel_id", "Pham nhan tu tien")
        from capcut_api.ai.scene_analyzer import SceneAnalyzerService
        svc = SceneAnalyzerService()
        episodes = svc.list_analyzed_episodes(novel_id)
        return jsonify({"success": True, "novel_id": novel_id, "episodes": episodes})
    except Exception as e:
        logger.error(f"Lỗi list novel scenes: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/scenes/details', methods=['GET'])
def get_novel_scene_details_api():
    """Lấy chi tiết danh sách phân cảnh của 1 tập phim."""
    try:
        novel_id = request.args.get("novel_id", "Pham nhan tu tien")
        episode = int(request.args.get("episode", 186))
        from capcut_api.ai.scene_analyzer import SceneAnalyzerService
        svc = SceneAnalyzerService()
        res = svc.get_episode_analysis_details(novel_id, episode)
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi get novel scene details: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/scenes/thumbnail', methods=['GET'])
def serve_scene_thumbnail():
    """Phục vụ ảnh thumbnail của phân cảnh."""
    try:
        novel_id = request.args.get("novel_id", "Pham nhan tu tien")
        episode = int(request.args.get("episode", 186))
        filename = request.args.get("filename", "")
        clean_id = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "default"
        from capcut_api.cloud.gdrive_manager import get_gdrive_manager
        gdrive_scenes = get_gdrive_manager().get_scene_analysis_dir()
        
        # 1. Kiểm tra Google Drive trước
        gdrive_kf = gdrive_scenes / clean_id / f"tap_{episode}" / "keyframes"
        if (gdrive_kf / filename).exists():
            return send_from_directory(str(gdrive_kf), filename)

        # 2. Fallback thư mục local nếu có
        local_kf = ROOT_DIR / "data" / "scene_analysis" / clean_id / f"tap_{episode}" / "keyframes"
        if (local_kf / filename).exists():
            return send_from_directory(str(local_kf), filename)

        # 3. Tìm trong các folder khác trên Google Drive
        for other_kf in gdrive_scenes.glob(f"*/tap_{episode}/keyframes/{filename}"):
            if other_kf.exists():
                return send_from_directory(str(other_kf.parent), filename)

        # 4. Tìm trong các folder local khác
        for other_kf in (ROOT_DIR / "data" / "scene_analysis").glob(f"*/tap_{episode}/keyframes/{filename}"):
            if other_kf.exists():
                return send_from_directory(str(other_kf.parent), filename)

        return send_from_directory(str(gdrive_kf if gdrive_kf.exists() else local_kf), filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

@master_app.route('/api/novel/scenes/upload_drive', methods=['POST'])
def upload_novel_scenes_drive_api():
    """API Đẩy toàn bộ dữ liệu phân cảnh của tập phim lên Google Drive."""
    try:
        data = request.get_json(silent=True) or {}
        novel_id = str(data.get("novel_id", "Pham nhan tu tien"))
        novel_name = str(data.get("novel_name", novel_id))
        episode = int(data.get("episode_num", 186))
        sync_keyframes = bool(data.get("sync_keyframes", True))
        sync_clips = bool(data.get("sync_clips", False))

        from capcut_api.cloud.google_drive_service import GoogleDriveService
        drive_svc = GoogleDriveService()
        res = drive_svc.sync_episode_scenes(
            novel_id=novel_id,
            novel_name=novel_name,
            episode_num=episode,
            sync_keyframes=sync_keyframes,
            sync_clips=sync_clips
        )
        return jsonify(res)
    except Exception as e:
        logger.error(f"Lỗi upload scenes to drive: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/google_drive/config', methods=['GET', 'POST'])
def handle_google_drive_config():
    """Lấy hoặc lưu cấu hình Google Drive."""
    try:
        from capcut_api.cloud.google_drive_service import GoogleDriveService
        drive_svc = GoogleDriveService()
        if request.method == 'GET':
            cfg = drive_svc._load_config()
            return jsonify({
                "success": True,
                "config": {
                    "client_id": cfg.get("client_id", ""),
                    "has_client_secret": bool(cfg.get("client_secret")),
                    "has_refresh_token": bool(cfg.get("refresh_token")),
                    "has_access_token": bool(cfg.get("access_token")),
                    "target_folder_id": cfg.get("target_folder_id", "")
                }
            })
        else:
            data = request.get_json(silent=True) or {}
            current_cfg = drive_svc._load_config()
            for k in ["client_id", "client_secret", "refresh_token", "access_token", "target_folder_id"]:
                if k in data and data[k] is not None:
                    current_cfg[k] = data[k]
            drive_svc.save_config(current_cfg)
            return jsonify({"success": True, "message": "Đã lưu cấu hình Google Drive thành công!"})
    except Exception as e:
        logger.error(f"Lỗi Google Drive config: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/google_drive/test', methods=['POST'])
def test_google_drive_connection():
    """Kiểm tra kết nối Google Drive API."""
    try:
        from capcut_api.cloud.google_drive_service import GoogleDriveService
        drive_svc = GoogleDriveService()
        res = drive_svc.test_connection()
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# =========================================================================
# CLOUD STORAGE & DATABASE MANAGEMENT APIS
# =========================================================================

@master_app.route('/api/system/storage_status', methods=['GET'])
def get_system_storage_status():
    """Lấy tổng hợp trạng thái lưu trữ: MongoDB Atlas, Google Drive 5TB, Cache cục bộ."""
    try:
        from capcut_api.database.mongo_manager import get_db_manager
        from capcut_api.cloud.gdrive_manager import get_gdrive_manager
        from capcut_api.cloud.cleanup_service import get_disk_cache_summary

        db_mgr = get_db_manager()
        gdrive_mgr = get_gdrive_manager()
        cache_summary = get_disk_cache_summary()

        return jsonify({
            "success": True,
            "database": db_mgr.get_status(),
            "google_drive": gdrive_mgr.get_storage_info(),
            "local_cache": cache_summary
        })
    except Exception as e:
        logger.error(f"Lỗi lấy storage status: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/system/cleanup_cache', methods=['POST'])
def trigger_cache_cleanup():
    """Kích hoạt dọn dẹp video MP4 trùng lặp và file audio tạm để giải phóng ổ đĩa C."""
    try:
        data = request.get_json(silent=True) or {}
        keep_recent = int(data.get("keep_recent_uploads", 1))
        dry_run = bool(data.get("dry_run", False))

        from capcut_api.cloud.cleanup_service import cleanup_local_cache
        res = cleanup_local_cache(keep_recent_uploads=keep_recent, dry_run=dry_run)
        return jsonify({
            "success": True,
            "result": res,
            "message": f"Đã giải phóng {res.get('freed_mb', 0)} MB dung lượng ổ đĩa thành công!"
        })
    except Exception as e:
        logger.error(f"Lỗi cleanup cache: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/scripts/history', methods=['GET'])
def list_scripts_history():
    """Lấy danh sách các kịch bản đã sinh ra từ MongoDB hoặc Local Fallback."""
    try:
        novel_id = request.args.get("novel_id")
        limit = int(request.args.get("limit", 50))
        from capcut_api.database.mongo_manager import get_db_manager
        db_mgr = get_db_manager()
        scripts = db_mgr.list_scripts(novel_id=novel_id, limit=limit)
        return jsonify({"success": True, "count": len(scripts), "scripts": scripts})
    except Exception as e:
        logger.error(f"Lỗi lấy lịch sử scripts: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/novel/scripts/<script_id>', methods=['GET', 'DELETE'])
def script_detail_or_delete(script_id: str):
    """Xem chi tiết hoặc xóa một kịch bản từ Database."""
    try:
        from capcut_api.database.mongo_manager import get_db_manager
        db_mgr = get_db_manager()
        if request.method == 'DELETE':
            success = db_mgr.delete_script(script_id)
            return jsonify({"success": success, "message": f"Đã xóa kịch bản {script_id}"})
        
        script = db_mgr.get_script(script_id)
        if not script:
            return jsonify({"success": False, "error": "Không tìm thấy kịch bản"}), 404
        return jsonify({"success": True, "script": script})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# =========================================================================
# CLOUD ASSET REGISTRY & DOWNLOAD RETRIEVAL APIS
# Cho phép định danh, tra cứu và tải dữ liệu từ Google Drive 5TB / MongoDB
# =========================================================================

@master_app.route('/api/cloud/assets', methods=['GET'])
def list_cloud_assets():
    """Lấy danh sách các file/tài nguyên trên Cloud đã được định nghĩa chuẩn."""
    try:
        category = request.args.get("category")
        novel_id = request.args.get("novel_id")
        episode = request.args.get("episode")
        episode_int = int(episode) if episode and episode.isdigit() else None
        search = request.args.get("search")
        limit = int(request.args.get("limit", 200))

        from capcut_api.cloud.asset_registry import get_asset_registry
        reg = get_asset_registry()
        assets = reg.list_assets(
            category=category,
            novel_id=novel_id,
            episode=episode_int,
            search=search,
            limit=limit
        )
        return jsonify({
            "success": True,
            "count": len(assets),
            "assets": assets
        })
    except Exception as e:
        logger.error(f"Lỗi list cloud assets: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/cloud/assets/episodes', methods=['GET'])
def list_cloud_episodes():
    """Lấy tổng hợp tài nguyên gom theo từng Tập phim (Raw, Keyframes, SRT, Script, Audio)."""
    try:
        novel_id = request.args.get("novel_id")
        from capcut_api.cloud.asset_registry import get_asset_registry
        reg = get_asset_registry()
        episodes = reg.get_episodes_summary(novel_id=novel_id)
        return jsonify({
            "success": True,
            "count": len(episodes),
            "episodes": episodes
        })
    except Exception as e:
        logger.error(f"Lỗi list cloud episodes: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/cloud/assets/manifest', methods=['GET'])
def get_cloud_manifest():
    """Lấy toàn bộ manifest thống kê của Google Drive 5TB."""
    try:
        from capcut_api.cloud.asset_registry import get_asset_registry
        reg = get_asset_registry()
        manifest = reg.manifest_cache or reg._load_or_build_manifest()
        return jsonify({"success": True, "manifest": manifest})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/cloud/assets/rescan', methods=['POST'])
def rescan_cloud_drive():
    """Kích hoạt quét lại và lập chỉ mục toàn bộ Google Drive 5TB."""
    try:
        from capcut_api.cloud.asset_registry import get_asset_registry
        reg = get_asset_registry()
        manifest = reg.scan_and_index_drive()
        return jsonify({
            "success": True,
            "message": f"Đã quét và lập chỉ mục {manifest.get('total_assets', 0)} tài nguyên!",
            "manifest": manifest
        })
    except Exception as e:
        logger.error(f"Lỗi rescan cloud drive: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/cloud/download', methods=['GET'])
def download_cloud_asset():
    """
    Tải trực tiếp 1 file từ Google Drive / Cloud về máy người dùng qua trình duyệt.
    Hỗ trợ tham số: asset_id hoặc relative_path.
    """
    try:
        from flask import send_file
        asset_id = request.args.get("asset_id")
        relative_path = request.args.get("relative_path")
        
        from capcut_api.cloud.asset_registry import get_asset_registry
        reg = get_asset_registry()

        query_key = asset_id or relative_path
        if not query_key:
            return jsonify({"success": False, "error": "Cần truyền asset_id hoặc relative_path"}), 400

        target_file = reg.get_asset_file_path(query_key)
        if not target_file or not target_file.exists():
            return jsonify({"success": False, "error": f"Không tìm thấy file trên Cloud: {query_key}"}), 404

        return send_file(
            str(target_file.resolve()),
            as_attachment=True,
            download_name=target_file.name
        )
    except Exception as e:
        logger.error(f"Lỗi download cloud asset: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/cloud/download_bundle', methods=['GET'])
def download_episode_bundle_zip():
    """
    Tạo và tải trọn gói file ZIP của 1 tập phim (Keyframes, SRT, Script, Scenes JSON)
    để người dùng tải về dùng ngay trên máy khác.
    """
    try:
        from flask import send_file
        novel_id = request.args.get("novel_id", "Phamnhantutien")
        episode = int(request.args.get("episode", 186))
        include_video = request.args.get("include_video", "false").lower() == "true"

        from capcut_api.cloud.asset_registry import get_asset_registry
        reg = get_asset_registry()
        zip_path = reg.create_episode_bundle_zip(novel_id=novel_id, episode=episode, include_raw_video=include_video)

        return send_file(
            str(zip_path.resolve()),
            as_attachment=True,
            download_name=zip_path.name
        )
    except Exception as e:
        logger.error(f"Lỗi download episode bundle zip: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@master_app.route('/api/cloud/pull_to_local', methods=['POST'])
def pull_cloud_asset_to_local():
    """Kéo tài nguyên từ Cloud về máy tính cục bộ để làm việc offline."""
    try:
        data = request.get_json(silent=True) or {}
        asset_id = data.get("asset_id")
        if not asset_id:
            return jsonify({"success": False, "error": "Chưa chọn asset_id để kéo về"}), 400

        from capcut_api.cloud.asset_registry import get_asset_registry
        reg = get_asset_registry()
        res = reg.pull_asset_to_local(asset_id)
        return jsonify(res)
    except Exception as e:
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
