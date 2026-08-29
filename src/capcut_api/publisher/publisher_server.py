#!/usr/bin/env python3
"""
Social Media Multi-Platform Publisher Microservice & Web Dashboard (Port 9002)
-----------------------------------------------------------------------------
Standalone REST API server & Web UI for managing social media publishing (YouTube, TikTok, Facebook, etc.),
handling visual OAuth 2.0 connection, smart scheduling (Khung giờ vàng), background queues, and analytics.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from flask import Flask, request, jsonify, render_template_string, redirect

# Set up logging
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("PublisherServer")

# Ensure proper path resolution
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "src" / "capcut_api"))
sys.path.insert(0, str(BASE_DIR))

try:
    from capcut_api.publisher.social_publisher import SocialPublisherManager, load_config, save_config, get_enabled_platforms
    from capcut_api.core.downloader import download_with_ytdlp
except ImportError:
    from social_publisher import SocialPublisherManager, load_config, save_config, get_enabled_platforms
    from capcut_api.core.downloader import download_with_ytdlp

app = Flask(__name__)
PORT = int(os.environ.get("PUBLISHER_PORT", 9002))

# Background jobs & Scheduler registry
jobs_lock = threading.Lock()
BACKGROUND_JOBS: Dict[str, Dict[str, Any]] = {}
SCHEDULED_POSTS: List[Dict[str, Any]] = []

# Initialize APScheduler for precision timed posting
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    scheduler.start()
    SCHEDULER_AVAILABLE = True
except Exception as sch_err:
    logger.warning(f"APScheduler init error: {sch_err}, falling back to background thread timer")
    scheduler = None
    SCHEDULER_AVAILABLE = False


def _execute_publish_job(payload: dict) -> dict:
    """Core execution logic for a single publish task (used by immediate, async, and scheduled jobs)."""
    file_path = payload.get("file_path")
    video_url = payload.get("video_url")
    title = payload.get("title", "Video Mới #Shorts")
    description = payload.get("description", "Xuất bản tự động qua CapCutAPI Publisher")
    platforms = payload.get("platforms") or ["youtube"]
    privacy_status = payload.get("privacy_status", "public")
    tags = payload.get("tags") or ["shorts", "trending"]
    thumbnail_file = payload.get("thumbnail_file")
    category_id = payload.get("category_id", "22")
    made_for_kids = payload.get("made_for_kids", False)
    delete_after = payload.get("delete_after_publish", False)

    # 1. Download if URL given instead of local file
    temp_downloaded = False
    if not file_path and video_url:
        downloads_dir = str(Path.home() / "Videos" / "default")
        dl_res = download_with_ytdlp(video_url, output_dir=downloads_dir)
        if dl_res.get("success") and dl_res.get("file_path"):
            file_path = dl_res["file_path"]
            temp_downloaded = True
            if not title or title == "Video Mới #Shorts":
                title = dl_res.get("title", title)
        else:
            return {
                "success": False,
                "error": f"Lỗi tải video từ URL: {dl_res.get('error')}"
            }

    if not file_path or not os.path.exists(file_path):
        return {
            "success": False,
            "error": f"File video không tồn tại: {file_path}"
        }

    # 2. Publish via SocialPublisherManager
    manager = SocialPublisherManager()
    pub_result = manager.publish_video(
        video_path_or_url=file_path,
        title=title,
        caption=description,
        platforms=platforms,
        privacy_status=privacy_status,
        tags=tags,
        thumbnail_file=thumbnail_file,
        category_id=category_id,
        made_for_kids=made_for_kids
    )

    # 3. Optional auto-cleanup
    if (delete_after or temp_downloaded) and os.path.exists(file_path) and pub_result.get("success"):
        try:
            os.remove(file_path)
            logger.info(f"Đã dọn dẹp file tạm: {file_path}")
        except Exception:
            pass

    return pub_result


def _run_background_pipeline(job_id: str, payload: dict):
    """Background worker wrapper"""
    with jobs_lock:
        BACKGROUND_JOBS[job_id]["status"] = "RUNNING"
        BACKGROUND_JOBS[job_id]["progress"] = 30
        BACKGROUND_JOBS[job_id]["message"] = "Đang xử lý tải & xuất bản video..."

    try:
        res = _execute_publish_job(payload)
        with jobs_lock:
            BACKGROUND_JOBS[job_id]["status"] = "COMPLETED" if res.get("success") else "FAILED"
            BACKGROUND_JOBS[job_id]["progress"] = 100
            BACKGROUND_JOBS[job_id]["publish_results"] = res
            BACKGROUND_JOBS[job_id]["updated_at"] = time.time()
            BACKGROUND_JOBS[job_id]["message"] = "Xuất bản thành công!" if res.get("success") else "Thất bại: " + str(res.get("error", "Lỗi không xác định"))
    except Exception as exc:
        logger.exception(f"Lỗi job {job_id}: {exc}")
        with jobs_lock:
            BACKGROUND_JOBS[job_id]["status"] = "FAILED"
            BACKGROUND_JOBS[job_id]["error"] = str(exc)
            BACKGROUND_JOBS[job_id]["updated_at"] = time.time()


# ==============================================================================
# WEB DASHBOARD HTML TEMPLATE
# ==============================================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CapCutAPI Social Publisher Studio (Port 9002)</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-main: #090d16;
            --bg-card: rgba(18, 26, 44, 0.75);
            --bg-card-hover: rgba(26, 36, 60, 0.85);
            --border-color: rgba(255, 255, 255, 0.08);
            --border-active: rgba(99, 102, 241, 0.5);
            --primary: #6366f1;
            --primary-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            --accent-youtube: #ef4444;
            --accent-tiktok: #00f2fe;
            --accent-facebook: #1877f2;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --font-main: 'Plus Jakarta Sans', -apple-system, sans-serif;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: var(--font-main);
            background: var(--bg-main);
            color: var(--text-main);
            min-height: 100vh;
            padding: 30px 20px;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(99, 102, 241, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(168, 85, 247, 0.12) 0%, transparent 40%);
        }

        .container { max-width: 1200px; margin: 0 auto; }

        /* Header */
        header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 30px;
        }
        .brand { display: flex; align-items: center; gap: 14px; }
        .brand-logo {
            width: 46px; height: 46px; border-radius: 12px;
            background: var(--primary-gradient);
            display: flex; align-items: center; justify-content: center;
            font-size: 24px; box-shadow: 0 8px 20px rgba(99, 102, 241, 0.35);
        }
        .brand-title h1 { font-size: 22px; font-weight: 800; letter-spacing: -0.5px; }
        .brand-title p { font-size: 13px; color: var(--text-muted); }
        .server-status {
            display: flex; align-items: center; gap: 8px;
            background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3);
            color: var(--success); padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 600;
        }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); box-shadow: 0 0 10px var(--success); }

        /* Navigation Tabs */
        .tabs { display: flex; gap: 10px; margin-bottom: 28px; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; }
        .tab-btn {
            background: transparent; border: none; color: var(--text-muted);
            padding: 10px 20px; font-size: 14px; font-weight: 600; font-family: var(--font-main);
            border-radius: 10px; cursor: pointer; transition: all 0.2s ease;
            display: flex; align-items: center; gap: 8px;
        }
        .tab-btn:hover { color: var(--text-main); background: rgba(255, 255, 255, 0.05); }
        .tab-btn.active { color: #fff; background: var(--primary-gradient); box-shadow: 0 4px 14px rgba(99, 102, 241, 0.3); }

        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.3s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

        /* Cards Grid */
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
        @media (max-width: 900px) { .grid-2 { grid-template-columns: 1fr; } }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(16px);
            transition: all 0.2s ease;
        }
        .card-header {
            display: flex; align-items: center; justify-content: space-between;
            margin-bottom: 20px; padding-bottom: 14px; border-bottom: 1px solid var(--border-color);
        }
        .card-header h2 { font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 8px; }

        /* Form elements */
        .form-group { margin-bottom: 18px; }
        .form-group label { display: block; font-size: 13px; font-weight: 600; color: var(--text-muted); margin-bottom: 8px; }
        .form-control {
            width: 100%; padding: 12px 14px; border-radius: 10px;
            background: rgba(10, 15, 29, 0.8); border: 1px solid var(--border-color);
            color: var(--text-main); font-size: 14px; font-family: var(--font-main);
            transition: border-color 0.2s; outline: none;
        }
        .form-control:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2); }
        textarea.form-control { resize: vertical; min-height: 90px; }

        /* Preset Buttons (Khung Giờ Vàng) */
        .presets-title { font-size: 12px; font-weight: 700; color: var(--warning); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
        .presets-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; margin-bottom: 18px; }
        .preset-btn {
            background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3);
            color: #fbbf24; padding: 8px 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
            cursor: pointer; transition: all 0.2s; font-family: var(--font-main);
        }
        .preset-btn:hover { background: rgba(245, 158, 11, 0.2); border-color: #fbbf24; }

        /* Social Connection Cards */
        .platform-item {
            display: flex; align-items: center; justify-content: space-between;
            padding: 16px; border-radius: 12px; background: rgba(10, 15, 29, 0.6);
            border: 1px solid var(--border-color); margin-bottom: 14px;
        }
        .platform-left { display: flex; align-items: center; gap: 14px; }
        .platform-icon {
            width: 42px; height: 42px; border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            font-size: 20px; font-weight: 800; color: #fff;
        }
        .icon-yt { background: var(--accent-youtube); }
        .icon-tt { background: #000; border: 1px solid rgba(255,255,255,0.2); color: var(--accent-tiktok); }
        .icon-fb { background: var(--accent-facebook); }
        .platform-info h3 { font-size: 15px; font-weight: 700; }
        .platform-info p { font-size: 12px; color: var(--text-muted); }

        .btn {
            display: inline-flex; align-items: center; justify-content: center; gap: 8px;
            padding: 10px 18px; border-radius: 10px; font-size: 13px; font-weight: 700;
            font-family: var(--font-main); cursor: pointer; border: none; transition: all 0.2s;
            text-decoration: none;
        }
        .btn-primary { background: var(--primary-gradient); color: #fff; box-shadow: 0 4px 14px rgba(99, 102, 241, 0.35); }
        .btn-primary:hover { opacity: 0.92; transform: translateY(-1px); }
        .btn-outline { background: transparent; border: 1px solid var(--border-color); color: var(--text-main); }
        .btn-outline:hover { background: rgba(255,255,255,0.06); border-color: var(--primary); }
        .btn-danger { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
        .btn-danger:hover { background: rgba(239, 68, 68, 0.3); }

        /* Jobs Table */
        .table-responsive { width: 100%; overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
        th { padding: 12px 16px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border-color); }
        td { padding: 14px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); vertical-align: middle; }
        tr:hover td { background: rgba(255, 255, 255, 0.02); }

        .badge {
            display: inline-block; padding: 4px 10px; border-radius: 20px;
            font-size: 11px; font-weight: 700; text-transform: uppercase;
        }
        .badge-success { background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); }
        .badge-pending { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
        .badge-failed { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
        .badge-running { background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.3); }

        .link-ext { color: #60a5fa; text-decoration: none; font-weight: 600; }
        .link-ext:hover { text-decoration: underline; }
    </style>
</head>
<body>

<div class="container">
    <!-- Header -->
    <header>
        <div class="brand">
            <div class="brand-logo">🚀</div>
            <div class="brand-title">
                <h1>Social Publisher Studio</h1>
                <p>Bộ điều khiển Xuất bản & Hẹn giờ Đa Nền tảng (Port {{ port }})</p>
            </div>
        </div>
        <div class="server-status">
            <div class="status-dot"></div>
            <span>Microservice Hoạt động</span>
        </div>
    </header>

    <!-- Navigation Tabs -->
    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('tab-publish')">📤 Đăng bài & Lên lịch</button>
        <button class="tab-btn" onclick="switchTab('tab-oauth')">🔐 Quản lý Kết nối OAuth</button>
        <button class="tab-btn" onclick="switchTab('tab-queue')">📋 Hàng đợi & Lịch sử</button>
    </div>

    <!-- TAB 1: ĐĂNG BÀI & HẸN GIỜ -->
    <div id="tab-publish" class="tab-content active">
        <div class="grid-2">
            <!-- Left: Publish Form -->
            <div class="card">
                <div class="card-header">
                    <h2>📝 Soạn Thảo Video Xuất Bản</h2>
                    <span style="font-size:12px; color:var(--text-muted)">Đa kênh tự động</span>
                </div>
                <form id="publishForm" onsubmit="submitPublish(event)">
                    <div class="form-group">
                        <label>Đường dẫn Video (.mp4) hoặc Link URL (TikTok/Douyin/YouTube):</label>
                        <input type="text" id="p_video_path" class="form-control" placeholder="C:/path/to/video.mp4 hoặc https://vt.tiktok.com/..." required>
                    </div>
                    <div class="form-group">
                        <label>Tiêu đề Video (Title):</label>
                        <input type="text" id="p_title" class="form-control" placeholder="Tiêu đề video ấn tượng #Shorts">
                    </div>
                    <div class="form-group">
                        <label>Mô tả Video (Caption / Description):</label>
                        <textarea id="p_desc" class="form-control" placeholder="Mô tả nội dung, hashtag chuẩn SEO..."></textarea>
                    </div>
                    <div class="form-group">
                        <label>Tags (Phân cách bởi dấu phẩy):</label>
                        <input type="text" id="p_tags" class="form-control" value="shorts, capcut, trending, viral">
                    </div>
                    <div class="form-group">
                        <label>Quyền riêng tư:</label>
                        <select id="p_privacy" class="form-control">
                            <option value="public">Công khai (Public)</option>
                            <option value="unlisted" selected>Không công khai (Unlisted - Khuyên dùng khi test)</option>
                            <option value="private">Riêng tư (Private)</option>
                        </select>
                    </div>

                    <!-- Scheduling section -->
                    <div style="margin-top:20px; padding:16px; border-radius:12px; background:rgba(255,255,255,0.02); border:1px solid var(--border-color);">
                        <label style="font-size:13px; font-weight:700; color:var(--text-main); margin-bottom:10px; display:block;">
                            ⏰ Chọn Thời Gian Xuất Bản:
                        </label>
                        
                        <div class="presets-title">⭐ Khung Giờ Vàng Gợi Ý:</div>
                        <div class="presets-grid">
                            <button type="button" class="preset-btn" onclick="setGoldenHour(0, 11, 30)">🌞 11:30 Trưa Nay</button>
                            <button type="button" class="preset-btn" onclick="setGoldenHour(0, 19, 30)">🌙 19:30 Tối Nay</button>
                            <button type="button" class="preset-btn" onclick="setGoldenHour(0, 21, 0)">✨ 21:00 Đêm Nay</button>
                            <button type="button" class="preset-btn" onclick="setGoldenHour(1, 11, 30)">📅 11:30 Trưa Mai</button>
                        </div>

                        <div class="form-group" style="margin-bottom:0;">
                            <label>Hoặc Hẹn giờ chính xác (Để trống để ĐĂNG NGAY):</label>
                            <input type="datetime-local" id="p_schedule_time" class="form-control">
                        </div>
                    </div>

                    <div style="margin-top: 24px; display:flex; gap:12px;">
                        <button type="submit" class="btn btn-primary" style="flex:1; padding:14px;">
                            🚀 Tiến Hành Xuất Bản / Lên Lịch
                        </button>
                    </div>
                </form>
            </div>

            <!-- Right: Quick Info & Summary -->
            <div class="card">
                <div class="card-header">
                    <h2>🎯 Kênh Tiếp Nhận Xuất Bản</h2>
                </div>
                
                <div class="platform-item">
                    <div class="platform-left">
                        <div class="platform-icon icon-yt">▶</div>
                        <div class="platform-info">
                            <h3>YouTube Shorts / Video</h3>
                            <p id="yt-account-status">
                                {% if yt_connected %}
                                    <span style="color:#4ade80">🟢 Đã kết nối (Kênh: {{ yt_channel }})</span>
                                {% else %}
                                    <span style="color:#f87171">🔴 Chưa kết nối OAuth</span>
                                {% endif %}
                            </p>
                        </div>
                    </div>
                    {% if not yt_connected %}
                        <a href="/api/v1/auth/youtube/login" class="btn btn-primary btn-sm">🔗 Kết nối</a>
                    {% else %}
                        <span class="badge badge-success">Sẵn sàng</span>
                    {% endif %}
                </div>

                <div class="platform-item" style="opacity:0.75">
                    <div class="platform-left">
                        <div class="platform-icon icon-tt">🎵</div>
                        <div class="platform-info">
                            <h3>TikTok Video</h3>
                            <p><span style="color:#fbbf24">⏳ Sẵn sàng nạp Client Key</span></p>
                        </div>
                    </div>
                    <button class="btn btn-outline" onclick="switchTab('tab-oauth')">Cấu hình</button>
                </div>

                <div class="platform-item" style="opacity:0.75">
                    <div class="platform-left">
                        <div class="platform-icon icon-fb">f</div>
                        <div class="platform-info">
                            <h3>Facebook Page & Reels</h3>
                            <p><span style="color:#fbbf24">⏳ Sẵn sàng nạp Page Token</span></p>
                        </div>
                    </div>
                    <button class="btn btn-outline" onclick="switchTab('tab-oauth')">Cấu hình</button>
                </div>

                <div style="margin-top:20px; padding:16px; border-radius:12px; background:rgba(99, 102, 241, 0.08); border:1px solid rgba(99, 102, 241, 0.2);">
                    <h4 style="color:#a5b4fc; font-size:13px; margin-bottom:8px;">💡 Mẹo Đăng Bài Tự Động:</h4>
                    <p style="font-size:12px; color:var(--text-muted); line-height:1.6;">
                        • Hệ thống tự động upload dạng <b>Resumable Stream</b> không ngốn RAM máy.<br>
                        • Tự động làm mới OAuth Token trước mỗi lần đăng bài.<br>
                        • Nếu gửi link TikTok/Douyin, hệ thống tự động tải không logo rồi đẩy thẳng sang YouTube!
                    </p>
                </div>
            </div>
        </div>
    </div>

    <!-- TAB 2: QUẢN LÝ KẾT NỐI OAUTH -->
    <div id="tab-oauth" class="tab-content">
        <div class="grid-2">
            <!-- YouTube OAuth Card -->
            <div class="card">
                <div class="card-header">
                    <h2><span style="color:var(--accent-youtube)">▶</span> Kết nối YouTube Data API v3</h2>
                    {% if yt_connected %}
                        <span class="badge badge-success">Đang hoạt động</span>
                    {% else %}
                        <span class="badge badge-failed">Chưa xác thực</span>
                    {% endif %}
                </div>
                
                <form id="ytConfigForm" onsubmit="saveYtConfig(event)">
                    <div class="form-group">
                        <label>Google Client ID:</label>
                        <input type="text" id="yt_client_id" class="form-control" value="{{ yt_client_id }}" placeholder="876823105226-...apps.googleusercontent.com" required>
                    </div>
                    <div class="form-group">
                        <label>Google Client Secret:</label>
                        <input type="password" id="yt_client_secret" class="form-control" value="{{ yt_client_secret }}" placeholder="GOCSPX-..." required>
                    </div>
                    <div class="form-group">
                        <label>Refresh Token Hiện Tại:</label>
                        <input type="text" class="form-control" value="{{ yt_refresh_token_masked }}" readonly style="background:rgba(0,0,0,0.3); color:#64748b;">
                    </div>

                    <div style="display:flex; gap:10px; margin-top:20px;">
                        <button type="submit" class="btn btn-outline">💾 Lưu Cấu Hình</button>
                        <a href="/api/v1/auth/youtube/login" class="btn btn-primary">🔗 Đăng Nhập & Cấp Quyền Lại</a>
                    </div>
                </form>
            </div>

            <!-- Other Platforms Card -->
            <div class="card">
                <div class="card-header">
                    <h2>⚙️ Các Nền Tảng Khác (TikTok, Meta)</h2>
                </div>
                <p style="font-size:13px; color:var(--text-muted); line-height:1.6; margin-bottom:16px;">
                    Bạn có thể nạp thêm Client Key của TikTok hoặc Page Access Token của Facebook vào để đẩy 1 video lên đồng loạt nhiều nơi cùng lúc.
                </p>
                <div class="form-group">
                    <label>TikTok Client Key / Secret:</label>
                    <input type="text" class="form-control" placeholder="aw_..." style="margin-bottom:8px;">
                </div>
                <div class="form-group">
                    <label>Facebook Page Access Token:</label>
                    <input type="text" class="form-control" placeholder="EAA...">
                </div>
                <button class="btn btn-outline">Lưu Thông Tin</button>
            </div>
        </div>
    </div>

    <!-- TAB 3: HÀNG ĐỢI & LỊCH SỬ ĐĂNG BÀI -->
    <div id="tab-queue" class="tab-content">
        <div class="card">
            <div class="card-header">
                <h2>📋 Danh Sách Bài Đăng & Tiến Độ Hàng Đợi</h2>
                <button class="btn btn-outline btn-sm" onclick="loadJobsTable()">🔄 Làm Mới</button>
            </div>
            
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>Job ID / Thời gian</th>
                            <th>Tiêu đề / Video</th>
                            <th>Nền tảng</th>
                            <th>Trạng thái</th>
                            <th>Kết quả</th>
                        </tr>
                    </thead>
                    <tbody id="jobsTableBody">
                        <tr><td colspan="5" style="text-align:center; padding:30px; color:var(--text-muted);">Đang tải dữ liệu hàng đợi...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<script>
    function switchTab(tabId) {
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        
        event.currentTarget.classList.add('active');
        document.getElementById(tabId).classList.add('active');
        if (tabId === 'tab-queue') loadJobsTable();
    }

    function setGoldenHour(daysOffset, hours, minutes) {
        const now = new Date();
        now.setDate(now.getDate() + daysOffset);
        now.setHours(hours, minutes, 0, 0);

        // Format to YYYY-MM-DDTHH:mm
        const tzOffset = now.getTimezoneOffset() * 60000;
        const localISOTime = (new Date(now - tzOffset)).toISOString().slice(0, 16);
        document.getElementById('p_schedule_time').value = localISOTime;
        alert(`Đã đặt lịch hẹn vào Khung Giờ Vàng: ${hours}:${minutes < 10 ? '0' + minutes : minutes} (${daysOffset === 0 ? 'Hôm nay' : 'Ngày mai'})!`);
    }

    async function submitPublish(e) {
        e.preventDefault();
        const videoInput = document.getElementById('p_video_path').value.trim();
        const title = document.getElementById('p_title').value.trim();
        const desc = document.getElementById('p_desc').value.trim();
        const tags = document.getElementById('p_tags').value.split(',').map(s => s.trim()).filter(Boolean);
        const privacy = document.getElementById('p_privacy').value;
        const scheduleTime = document.getElementById('p_schedule_time').value;

        const isUrl = videoInput.startsWith('http://') || videoInput.startsWith('https://');
        
        const payload = {
            title: title || undefined,
            description: desc || undefined,
            tags: tags,
            privacy_status: privacy,
            platforms: ['youtube']
        };

        if (isUrl) {
            payload.video_url = videoInput;
        } else {
            payload.file_path = videoInput;
        }

        if (scheduleTime) {
            payload.scheduled_at = scheduleTime;
        }

        const endpoint = scheduleTime ? '/api/v1/schedule' : (isUrl ? '/api/v1/publish/pipeline' : '/api/v1/publish');

        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok || data.success) {
                alert(scheduleTime ? `🎉 Đã lên lịch đăng video thành công vào: ${scheduleTime}` : '🚀 Đã tiếp nhận bài đăng thành công!');
                switchTab('tab-queue');
            } else {
                alert('❌ Lỗi: ' + (data.error || JSON.stringify(data)));
            }
        } catch (err) {
            alert('❌ Lỗi kết nối: ' + err.message);
        }
    }

    async function saveYtConfig(e) {
        e.preventDefault();
        const clientId = document.getElementById('yt_client_id').value.trim();
        const clientSecret = document.getElementById('yt_client_secret').value.trim();

        try {
            const res = await fetch('/api/v1/auth/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ youtube: { client_id: clientId, client_secret: clientSecret } })
            });
            const data = await res.json();
            if (data.success) {
                alert('💾 Đã lưu cấu hình Google OAuth thành công!');
                location.reload();
            } else {
                alert('❌ Lỗi lưu: ' + data.error);
            }
        } catch (err) {
            alert('❌ Lỗi kết nối: ' + err.message);
        }
    }

    async function loadJobsTable() {
        const tbody = document.getElementById('jobsTableBody');
        try {
            const [jobsRes, schedRes] = await Promise.all([
                fetch('/api/v1/jobs').then(r => r.json()),
                fetch('/api/v1/schedules').then(r => r.json())
            ]);

            let rows = '';

            // Scheduled posts
            (schedRes.schedules || []).forEach(sch => {
                rows += `
                    <tr>
                        <td>
                            <b>${sch.schedule_id}</b><br>
                            <span style="color:#fbbf24">⏰ Hẹn lúc: ${sch.scheduled_at}</span>
                        </td>
                        <td>${sch.title || 'Video #Shorts'}</td>
                        <td><span class="badge badge-running">YouTube</span></td>
                        <td><span class="badge badge-pending">ĐÃ LÊN LỊCH</span></td>
                        <td><button class="btn btn-danger btn-sm" onclick="cancelSchedule('${sch.schedule_id}')">Hủy lịch</button></td>
                    </tr>
                `;
            });

            // Recent execution jobs
            (jobsRes.jobs || []).forEach(j => {
                const isSuccess = j.status === 'COMPLETED';
                const isFailed = j.status === 'FAILED';
                const badgeClass = isSuccess ? 'badge-success' : (isFailed ? 'badge-failed' : 'badge-running');
                
                let linkHtml = j.message || '-';
                if (j.publish_results && j.publish_results.results && j.publish_results.results.youtube) {
                    const ytRes = j.publish_results.results.youtube;
                    if (ytRes.post_url) {
                        linkHtml = `<a href="${ytRes.post_url}" target="_blank" class="link-ext">🔗 Xem trên YouTube</a>`;
                    }
                }

                rows += `
                    <tr>
                        <td><b>${j.job_id}</b><br><span style="font-size:11px; color:var(--text-muted)">${new Date(j.created_at * 1000).toLocaleString('vi-VN')}</span></td>
                        <td>${j.download_meta ? j.download_meta.title : (j.video_url || j.file_path || '-')}</td>
                        <td><span class="badge badge-running">YouTube</span></td>
                        <td><span class="badge ${badgeClass}">${j.status}</span></td>
                        <td>${linkHtml}</td>
                    </tr>
                `;
            });

            tbody.innerHTML = rows || '<tr><td colspan="5" style="text-align:center; padding:30px; color:var(--text-muted);">Chưa có bài đăng nào trong hàng đợi.</td></tr>';
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:#f87171;">Lỗi tải hàng đợi: ${e.message}</td></tr>`;
        }
    }

    async function cancelSchedule(id) {
        if (!confirm('Bạn có chắc muốn hủy lịch hẹn đăng này?')) return;
        await fetch('/api/v1/schedules/' + id, { method: 'DELETE' });
        loadJobsTable();
    }

    // Initial load
    document.addEventListener('DOMContentLoaded', () => {
        loadJobsTable();
    });
</script>

</body>
</html>
"""


@app.route("/", methods=["GET"])
@app.route("/dashboard", methods=["GET"])
def dashboard():
    """Render Web Dashboard UI"""
    cfg = load_config()
    yt_cfg = cfg.get("social_credentials", {}).get("youtube", {})
    client_id = yt_cfg.get("client_id", "")
    client_secret = yt_cfg.get("client_secret", "")
    refresh_token = yt_cfg.get("refresh_token", "")
    
    yt_connected = bool(refresh_token and client_id)
    yt_refresh_masked = refresh_token[:12] + "..." + refresh_token[-6:] if len(refresh_token) > 18 else (refresh_token or "Chưa có")

    return render_template_string(
        DASHBOARD_HTML,
        port=PORT,
        yt_connected=yt_connected,
        yt_channel="Ty Phạm thi" if yt_connected else "Chưa liên kết",
        yt_client_id=client_id,
        yt_client_secret=client_secret,
        yt_refresh_token_masked=yt_refresh_masked
    )


@app.route("/health", methods=["GET"])
@app.route("/api/v1/status", methods=["GET"])
def health_check():
    """Service health & system status"""
    cfg = load_config()
    creds = cfg.get("social_credentials", {})
    enabled_platforms = get_enabled_platforms()

    return jsonify({
        "service": "CapCutAPI Social Publisher Service & Dashboard",
        "version": "2.1.0",
        "port": PORT,
        "status": "online",
        "timestamp": time.time(),
        "enabled_platforms": enabled_platforms,
        "scheduler_active": SCHEDULER_AVAILABLE,
        "active_jobs_count": len([j for j in BACKGROUND_JOBS.values() if j["status"] in ("DOWNLOADING", "PUBLISHING", "RUNNING")]),
        "scheduled_posts_count": len(SCHEDULED_POSTS)
    })


@app.route("/api/v1/auth/config", methods=["POST"])
def save_auth_config():
    """Save OAuth client ID & secret via UI"""
    data = request.get_json(force=True, silent=True) or {}
    cfg = load_config()
    if "social_credentials" not in cfg:
        cfg["social_credentials"] = {}

    for plat, pcreds in data.items():
        if plat not in cfg["social_credentials"]:
            cfg["social_credentials"][plat] = {}
        for k, v in pcreds.items():
            cfg["social_credentials"][plat][k] = v
        cfg["social_credentials"][plat]["enabled"] = True

    save_config(cfg)
    return jsonify({"success": True, "message": "Đã lưu cấu hình thành công"})


@app.route("/api/v1/auth/youtube/login", methods=["GET"])
def youtube_oauth_login():
    """Redirect to Google OAuth authorization URL with flexible redirect_uri support"""
    import urllib.parse
    cfg = load_config()
    yt_cfg = cfg.get("social_credentials", {}).get("youtube", {})
    client_id = yt_cfg.get("client_id", "").strip()
    if not client_id:
        return jsonify({"success": False, "error": "Chưa cấu hình client_id trong config.json"}), 400

    # Default to exact Postiz redirect URI (port 4200) or requested redirect_uri
    req_redirect = request.args.get("redirect_uri")
    if req_redirect:
        redirect_uri = req_redirect
    else:
        redirect_uri = "http://localhost:4200/integrations/social/youtube"

    scopes = [
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtubepartner",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ]
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "state": redirect_uri,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    
    if request.args.get("json", "0") == "1":
        return jsonify({"success": True, "auth_url": auth_url, "redirect_uri": redirect_uri})
    
    return redirect(auth_url)


@app.route("/callback", methods=["GET"])
@app.route("/api/v1/auth/youtube/callback", methods=["GET"])
def youtube_oauth_callback():
    """Catch OAuth code, exchange for refresh_token, and notify parent window (Postiz style)"""
    import requests
    code = request.args.get("code")
    error = request.args.get("error")
    state_redirect = request.args.get("state")

    if error:
        return f"""
        <html>
        <body style="font-family: system-ui; text-align: center; padding: 40px; background: #09090b; color: #ef4444;">
            <h2>❌ Xác thực Google thất bại: {error}</h2>
            <p style="color:#a1a1aa;">Bạn có thể đóng cửa sổ này và thử lại.</p>
        </body>
        </html>
        """, 400

    if not code:
        return "<h2 style='color:red;'>Không tìm thấy Authorization code</h2>", 400

    cfg = load_config()
    yt_cfg = cfg.get("social_credentials", {}).get("youtube", {})
    client_id = yt_cfg.get("client_id", "").strip()
    client_secret = yt_cfg.get("client_secret", "").strip()

    host = request.host
    redirect_uri = state_redirect or f"http://{host}/api/v1/auth/youtube/callback"

    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    )

    # If first attempt fails with redirect_uri, fallback to localhost:8080/callback
    if token_resp.status_code != 200:
        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": "http://localhost:8080/callback",
                "grant_type": "authorization_code",
            }
        )

    if token_resp.status_code != 200:
        return f"""
        <html>
        <body style="font-family: system-ui; text-align: center; padding: 40px; background: #09090b; color: #ef4444;">
            <h2>❌ Lỗi cấp quyền OAuth: {token_resp.text}</h2>
            <p style="color: #a1a1aa;">Vui lòng kiểm tra Client ID & Client Secret trong config.json</p>
        </body>
        </html>
        """, 400

    tokens = token_resp.json()
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")

    if "social_credentials" not in cfg:
        cfg["social_credentials"] = {}
    if "youtube" not in cfg["social_credentials"]:
        cfg["social_credentials"]["youtube"] = {}

    cfg["social_credentials"]["youtube"]["enabled"] = True
    cfg["social_credentials"]["youtube"]["client_id"] = client_id
    cfg["social_credentials"]["youtube"]["client_secret"] = client_secret
    if refresh_token:
        cfg["social_credentials"]["youtube"]["refresh_token"] = refresh_token
    if access_token:
        cfg["social_credentials"]["youtube"]["access_token"] = access_token

    save_config(cfg)
    logger.info("✅ Đã lưu thành công YouTube Refresh Token và Access Token vào config.json!")

    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Kết Nối YouTube Thành Công</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #09090b; color: #fafafa; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .card { background: #121216; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 32px; text-align: center; max-width: 400px; box-shadow: 0 20px 40px rgba(0,0,0,0.5); }
            h2 { color: #22c55e; margin: 0 0 12px 0; font-size: 20px; }
            p { color: #a1a1aa; font-size: 14px; line-height: 1.5; margin: 0 0 20px 0; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>🎉 Kết Nối YouTube Thành Công!</h2>
            <p>Hệ thống đã cập nhật Token. Cửa sổ này sẽ tự động đóng...</p>
        </div>
        <script>
            try {
                if (window.opener) {
                    window.opener.postMessage({ type: 'OAUTH_YOUTUBE_SUCCESS' }, '*');
                }
            } catch (e) {}
            setTimeout(() => {
                window.close();
            }, 1200);
        </script>
    </body>
    </html>
    """


@app.route("/api/v1/publish", methods=["POST"])
def publish_direct():
    """Publish an existing local video file or accessible URL directly."""
    data = request.get_json(force=True, silent=True) or {}
    res = _execute_publish_job(data)
    status_code = 200 if res.get("success") else 500
    return jsonify(res), status_code


@app.route("/api/v1/publish/pipeline", methods=["POST"])
def publish_from_url_pipeline():
    """Full automated background pipeline"""
    data = request.get_json(force=True, silent=True) or {}
    job_id = f"pub_{uuid.uuid4().hex[:8]}"

    with jobs_lock:
        BACKGROUND_JOBS[job_id] = {
            "job_id": job_id,
            "payload": data,
            "status": "QUEUED",
            "progress": 0,
            "created_at": time.time(),
            "updated_at": time.time(),
            "message": "Đã tiếp nhận yêu cầu tải & đăng video..."
        }

    worker = threading.Thread(target=_run_background_pipeline, args=(job_id, data), daemon=True)
    worker.start()

    return jsonify({
        "success": True,
        "job_id": job_id,
        "message": "Đã tiếp nhận vào hàng đợi xử lý nền",
        "status_url": f"/api/v1/jobs/{job_id}"
    }), 202


@app.route("/api/v1/schedule", methods=["POST"])
def schedule_post():
    """
    Schedule a video post for a future datetime.
    JSON Payload:
    {
        "file_path": "C:/path/to/video.mp4" OR "video_url": "https://...",
        "title": "Tiêu đề video",
        "description": "Mô tả...",
        "scheduled_at": "2026-08-17T19:30:00",
        "platforms": ["youtube"],
        "privacy_status": "public"
    }
    """
    data = request.get_json(force=True, silent=True) or {}
    scheduled_at_str = data.get("scheduled_at")
    if not scheduled_at_str:
        return jsonify({"success": False, "error": "Thiếu tham số 'scheduled_at' (Ví dụ: 2026-08-17T19:30)"}), 400

    schedule_id = f"sch_{uuid.uuid4().hex[:8]}"
    item = {
        "schedule_id": schedule_id,
        "scheduled_at": scheduled_at_str,
        "payload": data,
        "title": data.get("title", "Video #Shorts"),
        "created_at": time.time()
    }
    SCHEDULED_POSTS.append(item)

    # Register in APScheduler if available
    if scheduler:
        try:
            # Parse datetime
            dt = datetime.fromisoformat(scheduled_at_str.replace("Z", ""))
            job_id = f"job_{schedule_id}"
            scheduler.add_job(
                func=_execute_publish_job,
                trigger="date",
                run_date=dt,
                args=[data],
                id=job_id
            )
            logger.info(f"Đã đăng ký APScheduler job {job_id} chạy vào lúc {dt}")
        except Exception as e:
            logger.warning(f"Lỗi parse lịch hẹn APScheduler: {e}")

    return jsonify({
        "success": True,
        "schedule_id": schedule_id,
        "scheduled_at": scheduled_at_str,
        "message": f"Đã lên lịch đăng bài thành công vào lúc {scheduled_at_str}"
    })


@app.route("/api/v1/schedules", methods=["GET"])
def list_schedules():
    """List all scheduled posts"""
    return jsonify({
        "success": True,
        "schedules": SCHEDULED_POSTS
    })


@app.route("/api/v1/schedules/<schedule_id>", methods=["DELETE"])
def cancel_schedule(schedule_id: str):
    """Cancel a scheduled post"""
    global SCHEDULED_POSTS
    SCHEDULED_POSTS = [s for s in SCHEDULED_POSTS if s["schedule_id"] != schedule_id]
    if scheduler:
        try:
            scheduler.remove_job(f"job_{schedule_id}")
        except Exception:
            pass
    return jsonify({"success": True, "message": "Đã hủy lịch đăng bài"})


@app.route("/api/v1/jobs/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    """Get job execution status"""
    with jobs_lock:
        job = BACKGROUND_JOBS.get(job_id)
    if not job:
        return jsonify({"success": False, "error": "Job không tồn tại"}), 404
    return jsonify({"success": True, "job": job})


@app.route("/api/v1/jobs", methods=["GET"])
def list_jobs():
    """List recent background execution jobs"""
    with jobs_lock:
        recent = sorted(list(BACKGROUND_JOBS.values()), key=lambda x: x.get("created_at", 0), reverse=True)[:30]
    return jsonify({"success": True, "jobs": recent})


if __name__ == "__main__":
    logger.info(f"🚀 Khởi động Social Publisher Studio & Dashboard tại http://127.0.0.1:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
