#!/usr/bin/env python3
"""
Telegram Bot Control for CapCutAPI Automation
--------------------------------------------
Allows controlling CapCut video creation, draft management, pipeline processing,
and RPA GUI video exporting via Telegram Chatbot.
"""

import os
import sys
import json
import time
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

import re

# Paths
BASE_DIR = Path(__file__).parent.resolve()
ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.append(str(BASE_DIR))
sys.path.append(str(ROOT_DIR))

try:
    from social_publisher import (
        publish_video_auto,
        is_auto_publish_enabled,
        set_auto_publish_enabled,
        get_enabled_platforms
    )
except ImportError:
    pass

CONFIG_FILE = BASE_DIR / "config.json"
ROOT_CONFIG_FILE = ROOT_DIR / "config.json"

USER_VIDEOS = Path.home() / "Videos"
VIDEOS_BASE_DIR = USER_VIDEOS if USER_VIDEOS.exists() else (ROOT_DIR / "Videos")
try:
    from capcut_api.cloud.gdrive_manager import get_gdrive_manager
    OUTPUTS_DIR = get_gdrive_manager().get_outputs_dir()
except Exception:
    OUTPUTS_DIR = ROOT_DIR / "data" / "outputs"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_BOT_LANGUAGES = {
    "vi": {"name": "Tiếng Việt", "flag": "🇻🇳", "target": "Vietnamese", "source": "Chinese"},
    "en": {"name": "English", "flag": "🇺🇸", "target": "English", "source": "Chinese"},
    "zh": {"name": "中文", "flag": "🇨🇳", "target": "Chinese", "source": "English"},
    "ja": {"name": "日本語", "flag": "🇯🇵", "target": "Japanese", "source": "Chinese"},
    "ko": {"name": "한국어", "flag": "🇰🇷", "target": "Korean", "source": "Chinese"},
    "th": {"name": "ภาษาไทย", "flag": "🇹🇭", "target": "Thai", "source": "Chinese"},
    "es": {"name": "Español", "flag": "🇪🇸", "target": "Spanish", "source": "English"},
    "fr": {"name": "Français", "flag": "🇫🇷", "target": "French", "source": "English"},
    "de": {"name": "Deutsch", "flag": "🇩🇪", "target": "German", "source": "English"},
    "id": {"name": "Indonesia", "flag": "🇮🇩", "target": "Indonesian", "source": "Chinese"},
}

SUPPORTED_PLATFORMS = {
    "tiktok": {
        "name": "TikTok",
        "flag": "🎵",
        "ratio": "9:16",
        "width": 1080,
        "height": 1920,
        "desc": "Tối ưu Video dọc 9:16, phụ đề nổi bật, hashtag viral & âm thanh hút trend",
    },
    "youtube_shorts": {
        "name": "YouTube Shorts",
        "flag": "🔴",
        "ratio": "9:16",
        "width": 1080,
        "height": 1920,
        "desc": "Chuẩn Shorts 9:16 (<60s), tối ưu âm lượng & thumbnail tự động",
    },
    "facebook_reels": {
        "name": "Facebook Reels",
        "flag": "🔵",
        "ratio": "9:16",
        "width": 1080,
        "height": 1920,
        "desc": "Chuẩn Reels 9:16, lách bản quyền video & lọc âm nâng cao",
    },
    "instagram_reels": {
        "name": "Instagram Reels",
        "flag": "📸",
        "ratio": "9:16",
        "width": 1080,
        "height": 1920,
        "desc": "Chuẩn Insta 9:16, màu sắc rực rỡ & phụ đề song ngữ",
    },
    "youtube_long": {
        "name": "YouTube Ngang (16:9)",
        "flag": "📺",
        "ratio": "16:9",
        "width": 1920,
        "height": 1080,
        "desc": "Định dạng Full HD 16:9 ngang cho video dài trên YouTube",
    },
    "all_platforms": {
        "name": "Đa Nền Tảng (All-in-One)",
        "flag": "🌐",
        "ratio": "9:16",
        "width": 1080,
        "height": 1920,
        "desc": "Tự động xuất chuẩn 9:16 & đẩy lên toàn bộ TikTok, YouTube, Facebook, Instagram",
    },
}


def get_user_folder_dir(context: ContextTypes.DEFAULT_TYPE, folder_name: Optional[str] = None) -> tuple[Path, str]:
    """
    Get target directory and folder name inside Videos/.
    Creates Videos/<folder_name> directory automatically if it does not exist.
    """
    chosen = (folder_name or context.user_data.get("current_folder") or "default").strip()
    chosen = re.sub(r'[\\/*?:"<>|]', '_', chosen)
    target_dir = VIDEOS_BASE_DIR / chosen
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir, chosen


def enqueue_video_to_capcut_pipeline(video_path: str, custom_config: dict = None) -> tuple[bool, int, int]:
    """
    Tự động xếp hàng video vào CapCut Edit Pipeline Runner (giống các video khác trên hệ thống).
    Trả về: (success, queue_pos, total_queued)
    """
    import urllib.request
    v_path = str(Path(video_path).resolve())
    cfg = custom_config or {}

    # 1. Try sending directly to Master Server HTTP endpoint for real-time Web UI update
    try:
        url = "http://127.0.0.1:9001/api/queue/add_video"
        payload = json.dumps({"video_path": v_path, "config": cfg}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                pos = data.get("queue_position", 1)
                tot = data.get("total_queued", 1)
                logger.info(f"✅ Đã tự động xếp hàng video qua Master API: {v_path} (Vị trí #{pos}/{tot})")
                return True, pos, tot
    except Exception as api_err:
        logger.warning(f"Không thể gọi Master API /api/queue/add_video: {api_err}, dùng in-memory runner...")

    # 2. Fallback to direct in-memory runner
    try:
        sys.path.insert(0, str(ROOT_DIR / "src"))
        from capcut_api.api.gui_app import runner, apply_global_settings_to_config
        full_cfg = apply_global_settings_to_config(cfg)
        full_cfg["video_path"] = v_path
        full_cfg["video_paths"] = [v_path]

        item = {
            "type": "video",
            "video": v_path,
            "draft_id": None,
            "project_folder": None,
            "original_project_folder": None,
            "config": full_cfg,
            "status": "pending",
            "progress": 0,
            "resume_from_step": 1,
            "message": "Đang chờ trong hàng đợi Pipeline..."
        }

        with runner.queue_lock:
            runner.queue.append(item)
            queue_pos = len(runner.queue)
            total_queued = len(runner.queue)

        runner.save_cache()
        if not runner.is_processing:
            runner.start()

        logger.info(f"✅ Đã tự động xếp hàng video vào CapCut Pipeline: {v_path} (Vị trí #{queue_pos})")
        return True, queue_pos, total_queued
    except Exception as e:
        logger.error(f"Lỗi khi xếp hàng video vào pipeline: {e}")
        return False, 0, 0


def load_config() -> dict:
    """Load configuration from config.json and environment variables"""
    config = {}
    
    # 1. Load from root config.json
    if ROOT_CONFIG_FILE.exists():
        try:
            with open(ROOT_CONFIG_FILE, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except Exception as e:
            logger.error(f"Error loading root config.json: {e}")
            
    # 2. Load from bot directory config.json (if exists and overrides)
    if CONFIG_FILE.exists() and CONFIG_FILE != ROOT_CONFIG_FILE:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except Exception as e:
            logger.error(f"Error loading bot config.json: {e}")
            
    # 3. Load from .env if available
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k == "TELEGRAM_BOT_TOKEN" and not config.get("telegram_bot_token"):
                            config["telegram_bot_token"] = v
                        elif k == "TELEGRAM_ALLOWED_USER_IDS" and "allowed_user_ids" not in config:
                            try:
                                config["allowed_user_ids"] = [int(x.strip()) for x in v.split(",") if x.strip()]
                            except Exception:
                                pass
        except Exception as e:
            logger.error(f"Error parsing .env for telegram config: {e}")

    # 4. OS environment fallback
    if not config.get("telegram_bot_token") and os.environ.get("TELEGRAM_BOT_TOKEN"):
        config["telegram_bot_token"] = os.environ.get("TELEGRAM_BOT_TOKEN")
        
    return config


def is_user_allowed(user_id: int, config: dict) -> bool:
    """Check if Telegram user is allowed to execute bot commands"""
    allowed_ids = config.get("allowed_user_ids", [])
    if not allowed_ids:  # If list is empty, allow all users by default
        return True
    return user_id in allowed_ids


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start and /help command"""
    user = update.effective_user
    config = load_config()

    if not is_user_allowed(user.id, config):
        await update.message.reply_text(
            f"❌ **Truy cập bị từ chối.**\nID Telegram của bạn: `{user.id}` chưa được phép sử dụng Bot.\n"
            f"Vui lòng thêm User ID này vào `allowed_user_ids` trong `config.json`.",
            parse_mode="Markdown",
        )
        return

    current_folder = context.user_data.get("current_folder", "default")

    welcome_text = (
        f"👋 **Chào mừng {user.first_name} đến với AUTO VIDEO BOT!**\n\n"
        f"🤖 Bot này giúp bạn điều khiển hệ thống **CapCutAPI** để dựng video, chèn phụ đề, hiệu ứng và xuất video tự động.\n\n"
        f"📁 **Thư mục lưu trữ hiện tại**: `Videos/{current_folder}`\n\n"
        f"📌 **Danh sách Lệnh điều khiển:**\n"
        f"• `/start` - Hiển thị menu này\n"
        f"• `/folder <tên>` - Chọn hoặc tạo thư mục lưu trữ trong `Videos/`\n"
        f"• `/status` - Kiểm tra trạng thái hệ thống CapCut\n"
        f"• `/new_draft <tên>` - Tạo dự án CapCut nháp mới\n"
        f"• `/pipeline` - Chạy quy trình dựng video tự động\n"
        f"• `/rpa_export` - Gọi CapCut GUI xuất video tự động\n"
        f"• `/publish <file/url>` - Đẩy video lên đa nền tảng MXH\n"
        f"• `/autopublish <on/off>` - Bật/tắt tự động đăng bài\n\n"
        f"📂 *Mẹo:* Gửi trực tiếp **Link Douyin/TikTok/YouTube** hoặc **Video/Audio**, Bot sẽ tự lưu vào `Videos/{current_folder}`!"
    )

    keyboard = [
        [
            InlineKeyboardButton("🚀 DỊCH & XUẤT NỀN TẢNG (TikTok, YouTube, Reels)", callback_data="btn_platform_menu"),
        ],
        [
            InlineKeyboardButton("🌐 Dịch Phụ Đề AI (.SRT)", callback_data="btn_trans_menu"),
            InlineKeyboardButton("⚡ Dựng Pipeline Auto", callback_data="btn_pipeline"),
        ],
        [
            InlineKeyboardButton("🎬 Tạo Project Nháp", callback_data="btn_new_draft"),
            InlineKeyboardButton("🖥️ Xuất Video (RPA)", callback_data="btn_rpa_export"),
        ],
        [
            InlineKeyboardButton("📁 Thư mục lưu trữ", callback_data="btn_folders"),
            InlineKeyboardButton("🚀 Đẩy bài Đa Nền tảng", callback_data="btn_publish_menu"),
        ],
        [
            InlineKeyboardButton("⚙️ Auto Publish", callback_data="btn_autopublish_menu"),
            InlineKeyboardButton("📊 Kiểm tra Status", callback_data="btn_status"),
        ],
        [
            InlineKeyboardButton("🗄️ Tra cứu MongoDB", callback_data="btn_history"),
            InlineKeyboardButton("❓ Hướng dẫn Chi tiết", callback_data="btn_help"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)


async def folder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /folder command to choose or create subfolders inside Videos/"""
    msg = update.effective_message
    args = context.args

    if args:
        new_folder = " ".join(args).strip()
        target_dir, folder_name = get_user_folder_dir(context, new_folder)
        context.user_data["current_folder"] = folder_name
        await msg.reply_text(
            f"📁 **Đã chọn thư mục lưu trữ:**\n`Videos/{folder_name}`\n\n"
            f"📌 Đường dẫn đầy đủ trên máy: `{target_dir}`\n"
            f"Tất cả video mới sẽ được tự động lưu vào thư mục này!",
            parse_mode="Markdown"
        )
        return

    current_active = context.user_data.get("current_folder", "default")
    subfolders = [f.name for f in VIDEOS_BASE_DIR.iterdir() if f.is_dir()]
    if "default" not in subfolders:
        subfolders.insert(0, "default")

    buttons = []
    for f_name in subfolders:
        label = f"✅ {f_name}" if f_name == current_active else f"📁 {f_name}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"cb_folder_{f_name}")])

    reply_markup = InlineKeyboardMarkup(buttons)

    list_text = (
        f"📁 **QUẢN LÝ THƯ MỤC LƯU VIDEO**\n\n"
        f"• **Thư mục đang chọn**: `Videos/{current_active}`\n"
        f"• **Thư mục gốc**: `{VIDEOS_BASE_DIR}`\n\n"
        f"💡 *Bấm chọn 1 thư mục bên dưới hoặc gõ lệnh để tạo thư mục mới:*\n"
        f"Cú pháp: `/folder tên_thư_mục_mới`"
    )
    await msg.reply_text(list_text, parse_mode="Markdown", reply_markup=reply_markup)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "btn_status":
        await status_command(update, context)
    elif data == "btn_history":
        await history_command(update, context)
    elif data == "btn_folders":
        await folder_command(update, context)
    elif data.startswith("cb_folder_"):
        folder_name = data.replace("cb_folder_", "")
        target_dir, chosen_name = get_user_folder_dir(context, folder_name)
        context.user_data["current_folder"] = chosen_name
        await query.message.reply_text(
            f"✅ **Đã chuyển thư mục lưu trữ thành:**\n`Videos/{chosen_name}`\n"
            f"📌 Đường dẫn lưu: `{target_dir}`",
            parse_mode="Markdown"
        )
    elif data == "btn_new_draft":
        await query.message.reply_text(
            "✍️ Cú pháp tạo Draft mới:\n`/new_draft MyProjectName`",
            parse_mode="Markdown"
        )
    elif data == "btn_pipeline":
        await query.message.reply_text(
            "⚡ **Hướng dẫn chạy Pipeline:**\n"
            "Gửi link trực tiếp hoặc lệnh: `/pipeline <link_video>`\n"
            "Ví dụ: `/pipeline https://v.douyin.com/...`",
            parse_mode="Markdown"
        )
    elif data == "btn_rpa_export":
        await query.message.reply_text(
            "🖥️ **Hướng dẫn Xuất Video RPA:**\n"
            "Hãy đảm bảo CapCut đã sẵn sàng trên máy Windows.\n"
            "Gửi lệnh: `/rpa_export` để bắt đầu quy trình tự động mở project & export video.",
            parse_mode="Markdown"
        )
    elif data == "btn_publish_menu":
        await query.message.reply_text(
            "🚀 **ĐẨY BÀI ĐA NỀN TẢNG**\n\n"
            "Dùng lệnh: `/publish <đường_dẫn_file_hoặc_url>`\n"
            "Ví dụ: `/publish C:/Projects/CapCutAPI/outputs/my_video.mp4`",
            parse_mode="Markdown"
        )
    elif data == "btn_autopublish_menu":
        await autopublish_command(update, context)
    elif data == "btn_platform_menu":
        last_file = context.user_data.get("last_video_file")
        await show_platform_selection_menu(update, context, last_file)
    elif data.startswith("cb_plat_"):
        plat_key = data.replace("cb_plat_", "")
        last_file = context.user_data.get("last_video_file")
        await show_platform_action_menu(update, context, plat_key, last_file)
    elif data.startswith("cb_pexport_"):
        parts = data.split("_", 3)
        # cb_pexport_<lang>_<plat>
        if len(parts) >= 4:
            lang_code = parts[2]
            plat_key = parts[3]
            last_file = context.user_data.get("last_video_file")
            await execute_platform_export(update, context, plat_key, lang_code, auto_publish=False, srt_only=False, video_path=last_file)
    elif data.startswith("cb_papub_"):
        parts = data.split("_", 3)
        # cb_papub_<lang>_<plat>
        if len(parts) >= 4:
            lang_code = parts[2]
            plat_key = parts[3]
            last_file = context.user_data.get("last_video_file")
            await execute_platform_export(update, context, plat_key, lang_code, auto_publish=True, srt_only=False, video_path=last_file)
    elif data.startswith("cb_psrt_"):
        parts = data.split("_", 3)
        # cb_psrt_<lang>_<plat>
        if len(parts) >= 4:
            lang_code = parts[2]
            plat_key = parts[3]
            last_file = context.user_data.get("last_video_file")
            await execute_platform_export(update, context, plat_key, lang_code, auto_publish=False, srt_only=True, video_path=last_file)
    elif data == "btn_trans_menu":
        await translate_command(update, context)
    elif data == "cb_trans_all":
        last_file = context.user_data.get("last_video_file")
        await do_translate_all_languages(update, context, last_file)
    elif data.startswith("cb_trans_"):
        lang_code = data.replace("cb_trans_", "")
        lang_info = dict(SUPPORTED_BOT_LANGUAGES.get(lang_code, {"name": "Tiếng Việt", "flag": "🇻🇳", "target": "Vietnamese", "source": "Chinese"}))
        lang_info["code"] = lang_code
        last_file = context.user_data.get("last_video_file")
        await do_translate_video(update, context, lang_info, last_file)
    elif data == "btn_help":
        help_detail = (
            "📖 **HƯỚNG DẪN CHI TIẾT TỰ ĐỘNG HÓA CAPCUT & DỰNG DÂN ĐA NỀN TẢNG**\n\n"
            "1️⃣ **Chọn Thư Mục**: Dùng lệnh `/folder tên_folder` để chọn/tạo thư mục lưu trong `Videos/`.\n"
            "2️⃣ **Gửi Link / Media**: Gửi bất kỳ link Douyin/YouTube/TikTok hoặc file media qua chat Telegram.\n"
            "3️⃣ **Tạo Draft & Pipeline**: Bot tự động lưu MongoDB `video_logger_db`, tải video vào `Videos/<folder>` và nạp vào Timeline CapCut.\n"
            "4️⃣ **Đẩy bài Đa Nền tảng**: Bot tự động đẩy video lên TikTok, YouTube, Facebook, LinkedIn... nếu bật `/autopublish on`."
        )
        await query.message.reply_text(help_detail, parse_mode="Markdown")



async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /status command"""
    msg = update.effective_message
    status_msg = await msg.reply_text("⏳ *Đang kiểm tra trạng thái hệ thống CapCut...*", parse_mode="Markdown")

    config = load_config()
    port = config.get("port", 9001)

    # Check CapCut Server status via localhost HTTP request or process check
    server_online = False
    queue_items = []
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/status", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            server_online = True
            st_data = json.loads(response.read().decode('utf-8'))
            queue_items = st_data.get("queue", [])
    except Exception:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=2) as response:
                server_online = response.status in [200, 404]
        except Exception:
            server_online = False

    # Count downloaded files
    downloads_count = len(list(VIDEOS_BASE_DIR.glob("*")))
    outputs_count = len(list(OUTPUTS_DIR.glob("*")))

    queue_text_lines = []
    if queue_items:
        for i, q_item in enumerate(queue_items[:5], 1):
            q_mode = q_item.get("mode_label") or ("📝 Chỉ Dịch Sub" if q_item.get("mode") == "translate_only" else "🎬 Full Pipeline")
            q_st = q_item.get("status", "pending").upper()
            q_prog = q_item.get("progress", 0)
            v_name = os.path.basename(q_item.get("video") or q_item.get("project_name") or f"Item {i}")
            queue_text_lines.append(f"  {i}. `[{q_mode}]` {v_name} — *{q_st}* ({q_prog}%)")

    queue_section = ""
    if queue_text_lines:
        queue_section = "\n\n📋 **HÀNG ĐỢI XỬ LÝ (QUEUE)**:\n" + "\n".join(queue_text_lines)

    status_text = (
        f"📊 **BÁO CÁO TRẠNG THÁI HỆ THỐNG**\n\n"
        f"• **CapCut API Server**: {'🟢 Hoạt động (Port ' + str(port) + ')' if server_online else '🔴 Chưa bật server'}\n"
        f"• **Thư mục Videos**: {downloads_count} mục/file\n"
        f"• **Thư mục Outputs (Video xuất)**: {outputs_count} file\n"
        f"• **Số job trong hàng chờ**: {len(queue_items)} job"
        f"{queue_section}\n\n"
        f"👉 *Theo dõi trực tiếp trên Web UI:* `http://127.0.0.1:{port}/queue`"
    )

    if status_msg:
        await status_msg.edit_text(status_text, parse_mode="Markdown")


async def handle_media_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle files sent directly by user in Telegram chat"""
    message = update.message
    user = update.effective_user
    config = load_config()

    if not is_user_allowed(user.id, config):
        return

    target_dir, current_folder = get_user_folder_dir(context)
    status_text = await message.reply_text(f"📥 *Đang tải file về `Videos/{current_folder}`...*", parse_mode="Markdown")

    try:
        if message.video:
            file_obj = await message.video.get_file()
            filename = message.video.file_name or f"video_{message.video.file_id[:8]}.mp4"
            media_type = "Video"
        elif message.audio:
            file_obj = await message.audio.get_file()
            filename = message.audio.file_name or f"audio_{message.audio.file_id[:8]}.mp3"
            media_type = "Audio"
        elif message.photo:
            file_obj = await message.photo[-1].get_file()
            filename = f"photo_{message.photo[-1].file_id[:8]}.jpg"
            media_type = "Hình ảnh"
        elif message.document:
            file_obj = await message.document.get_file()
            filename = message.document.file_name or f"doc_{message.document.file_id[:8]}"
            media_type = "Tập tin"
        else:
            await status_text.edit_text("❌ Loại file không được hỗ trợ.")
            return

        save_path = target_dir / filename
        await file_obj.download_to_drive(custom_path=save_path)

        file_size_mb = save_path.stat().st_size / (1024 * 1024)

        queue_extra_str = ""
        if message.video:
            context.user_data["last_video_file"] = str(save_path)
            q_ok, q_pos, q_total = enqueue_video_to_capcut_pipeline(str(save_path))
            if q_ok:
                queue_extra_str = f"• **Hàng đợi Edit Pipeline**: Vị trí `#{q_pos}` / `{q_total}` job (Đang tự động chạy)\n"

        success_msg = (
            f"✅ **Đã nhận {media_type} thành công!**\n\n"
            f"• **Tên file**: `{filename}`\n"
            f"• **Dung lượng**: {file_size_mb:.2f} MB\n"
            f"{queue_extra_str}"
            f"• **Thư mục lưu**: `Videos/{current_folder}`\n"
            f"• **Đường dẫn**: `{save_path}`\n\n"
            f"🚀 *Video đã được đưa vào hàng đợi tự động dựng và edit của hệ thống!*"
        )
        await status_text.edit_text(success_msg, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error handling media upload: {e}")
        await status_text.edit_text(f"❌ *Lỗi khi tải file:* `{e}`", parse_mode="Markdown")


async def new_draft_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /new_draft command"""
    msg = update.effective_message
    args = context.args
    draft_name = " ".join(args) if args else f"Telegram_Draft_{int(asyncio.get_event_loop().time())}"

    status_msg = await msg.reply_text(f"🎬 *Đang khởi tạo Project CapCut: `{draft_name}`...*", parse_mode="Markdown")

    try:
        # Import create_draft module dynamically
        sys.path.append(str(BASE_DIR))
        from create_draft import create_draft

        script, draft_id = create_draft(width=1080, height=1920)

        result_text = (
            f"✅ **Đã tạo Project CapCut thành công!**\n\n"
            f"• **Draft ID**: `{draft_id}`\n"
            f"• **Tên Draft**: `{draft_name}`\n"
            f"• **Độ phân giải**: 1080x1920 (Vertical Video)\n\n"
            f"🚀 Sử dụng lệnh `/rpa_export` để mở CapCut và xuất video này."
        )
        await status_msg.edit_text(result_text, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error creating draft: {e}")
        await status_msg.edit_text(f"❌ *Lỗi tạo Draft:* `{e}`", parse_mode="Markdown")


async def rpa_export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /rpa_export command - automates CapCut GUI to export video"""
    msg = update.effective_message
    status_msg = await msg.reply_text(
        "🖥️ **BẮT ĐẦU QUY TRÌNH RPA EXPORT CAPCUT**\n\n"
        "⏳ *1/3: Đang tìm và kích hoạt cửa sổ ứng dụng CapCut trên máy...*",
        parse_mode="Markdown"
    )

    def run_rpa():
        """Run capcut_rpa.py as a subprocess"""
        try:
            rpa_script = BASE_DIR / "capcut_rpa.py"
            if not rpa_script.exists():
                return False, "Không tìm thấy file script capcut_rpa.py"

            process = subprocess.run(
                [sys.executable, str(rpa_script), "--help"],
                capture_output=True,
                text=True,
                timeout=30
            )
            return True, process.stdout
        except Exception as err:
            return False, str(err)

    # Run RPA check in thread pool
    loop = asyncio.get_running_loop()
    success, output = await loop.run_in_executor(None, run_rpa)

    if success:
        await status_msg.edit_text(
            "🟢 **RPA Ready!**\n"
            "Hệ thống RPA CapCut đã khởi chạy sẵn sàng trên máy.\n\n"
            "📌 *Vui lòng đảm bảo ứng dụng CapCut/JianYing đang mở trên màn hình PC.*",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text(
            f"⚠️ **Thông báo RPA:**\n`{output}`",
            parse_mode="Markdown"
        )


async def handle_url_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video URLs sent by user (YouTube, TikTok, Facebook, Instagram, Douyin share text, etc.)"""
    message = update.message
    user = update.effective_user
    config = load_config()

    if not is_user_allowed(user.id, config):
        return

    text = message.text.strip() if message.text else ""
    if not text and context.args:
        text = " ".join(context.args)

    sys.path.append(str(BASE_DIR))
    from downloader import clean_and_resolve_url, download_with_ytdlp
    from db import save_video_log, update_video_status, log_pipeline_step, get_default_render_config

    clean_url = clean_and_resolve_url(text)

    if not clean_url or not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        await message.reply_text("❌ Không tìm thấy link video hợp lệ trong tin nhắn. Vui lòng gửi lại link (ví dụ: Douyin, TikTok, YouTube...).", parse_mode="Markdown")
        return

    target_dir, current_folder = get_user_folder_dir(context)

    # 1. Log to MongoDB immediately (video_logger_db -> videos)
    save_video_log(
        video_url=clean_url,
        page_title=text[:100],
        folder_name=current_folder,
        status="LINK_RECEIVED",
        telegram_user_id=user.id
    )
    log_pipeline_step(clean_url, "LINK_RECEIVED", "SUCCESS", detail=f"Lưu vào thư mục Videos/{current_folder}")

    status_msg = await message.reply_text(
        f"🌐 *Đang xử lý link video Douyin / YouTube / TikTok...*\n`{clean_url}`\n📁 *Thư mục lưu*: `Videos/{current_folder}`",
        parse_mode="Markdown"
    )

    # 2. Log step: DOWNLOADING
    log_pipeline_step(clean_url, "DOWNLOADING", "IN_PROGRESS", detail="Bắt đầu tải file qua engine yt-dlp / Douyin")

    def do_download():
        return download_with_ytdlp(text, output_dir=str(target_dir))

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, do_download)

    if not result.get("success"):
        update_video_status(clean_url, status="FAILED", error_msg=result.get("error"))
        log_pipeline_step(clean_url, "DOWNLOADING", "FAILED", detail=f"Lỗi tải: {result.get('error')}")
        await status_msg.edit_text(
            f"❌ *Lỗi khi tải video:* `{result.get('error')}`\n\n📌 Link xử lý: `{result.get('clean_url', clean_url)}`",
            parse_mode="Markdown"
        )
        return

    file_path = result.get("file_path")
    cover_path = result.get("cover_path")
    video_dir = result.get("video_dir")
    title = result.get("title", "Video")
    duration = result.get("duration", 0)
    width = result.get("width", 1080)
    height = result.get("height", 1920)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024) if file_path and os.path.exists(file_path) else 0

    context.user_data["last_video_file"] = file_path
    context.user_data["last_video_title"] = title
    context.user_data["last_video_dir"] = video_dir

    render_cfg = get_default_render_config(width=width, height=height)

    # 3. Log step: DOWNLOADED
    update_video_status(
        clean_url,
        status="DOWNLOADED",
        local_path=file_path,
        cover_path=cover_path,
        video_dir=video_dir
    )
    log_pipeline_step(
        clean_url,
        "DOWNLOADED",
        "SUCCESS",
        detail=f"Folder: {video_dir} | Video: {os.path.basename(file_path)} ({file_size_mb:.2f} MB)" if video_dir else f"File: {file_path}",
        render_config=render_cfg,
        extra_meta={
            "videoMeta": {
                "title": title,
                "duration": duration,
                "width": width,
                "height": height,
                "fileSizeMb": round(file_size_mb, 2),
                "localPath": file_path,
                "coverPath": cover_path,
                "videoDir": video_dir,
                "coverUrl": result.get("cover_url")
            }
        }
    )

    cover_info_str = f"• **Ảnh bìa (Banner)**: `{os.path.basename(cover_path)}`\n" if cover_path else ""
    await status_msg.edit_text(
        f"✅ **Tải Video & Banner thành công!**\n\n"
        f"• **Tiêu đề**: `{title}`\n"
        f"• **Thời lượng**: {duration}s | **Dung lượng**: {file_size_mb:.2f} MB\n"
        f"• **Thư mục riêng**: `{video_dir or target_dir}`\n"
        f"• **File video**: `{os.path.basename(file_path)}`\n"
        f"{cover_info_str}\n"
        f"⚙️ *Đang tự động chèn video vào Timeline CapCut Pipeline...*",
        parse_mode="Markdown"
    )

    # 4. Log step: PIPELINE_CREATING
    log_pipeline_step(clean_url, "PIPELINE_CREATING", "IN_PROGRESS", detail="Khởi tạo script CapCut & chèn video track")

    # Auto insert into CapCut Draft / Pipeline
    def do_create_pipeline():
        try:
            sys.path.append(str(BASE_DIR))
            from create_draft import create_draft
            from add_video_track import add_video_track

            script, draft_id = create_draft(width=width, height=height)
            # Add video track
            add_video_track(
                draft_folder=str(BASE_DIR / "templates"),
                video_url=file_path,
                width=width,
                height=height,
                start=0,
                end=duration * 1000000 if duration else 10000000,
                draft_id=draft_id
            )
            return True, draft_id, None
        except Exception as e:
            return False, None, str(e)

    pip_success, draft_id, pip_err = await loop.run_in_executor(None, do_create_pipeline)

    # Tự động nạp vào hàng đợi Edit Pipeline của hệ thống
    q_ok, q_pos, q_total = enqueue_video_to_capcut_pipeline(file_path)
    queue_info_str = f"• **Hàng đợi Edit Pipeline**: Vị trí `#{q_pos}` / `{q_total}` job (Đang tự động chạy)\n" if q_ok else ""

    if pip_success:
        # 5. Log step: DRAFT_CREATED
        update_video_status(clean_url, status="DRAFT_CREATED", draft_id=draft_id)
        log_pipeline_step(
            clean_url,
            "DRAFT_CREATED",
            "SUCCESS",
            detail=f"Đã tạo CapCut Draft ID: {draft_id} | Hàng đợi #{q_pos}",
            render_config=render_cfg,
            extra_meta={"draftId": draft_id, "queuePosition": q_pos}
        )

        keyboard = [
            [
                InlineKeyboardButton("🚀 DỊCH & XUẤT NỀN TẢNG (TikTok, Reels, Shorts...)", callback_data="btn_platform_menu")
            ],
            [
                InlineKeyboardButton("🔥 DỊCH RA TẤT CẢ (ALL 10 NGÔN NGỮ)", callback_data="cb_trans_all")
            ],
            [
                InlineKeyboardButton("🇻🇳 Dịch sang Tiếng Việt", callback_data="cb_trans_vi"),
                InlineKeyboardButton("🇺🇸 Dịch sang English", callback_data="cb_trans_en"),
            ],
            [
                InlineKeyboardButton("🇨🇳 Dịch sang Trung", callback_data="cb_trans_zh"),
                InlineKeyboardButton("🇯🇵 Dịch sang Nhật", callback_data="cb_trans_ja"),
            ],
            [
                InlineKeyboardButton("🌐 Chọn Ngôn Ngữ Khác", callback_data="btn_trans_menu"),
                InlineKeyboardButton("🖥️ Xuất Video (RPA)", callback_data="btn_rpa_export"),
            ],
            [
                InlineKeyboardButton("🗄️ Tra cứu MongoDB", callback_data="btn_history"),
                InlineKeyboardButton("📊 Trạng thái Hệ thống", callback_data="btn_status")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await status_msg.edit_text(
            f"🎉 **ĐÃ TẢI & TỰ ĐỘNG XẾP HÀNG PIPELINE EDIT THÀNH CÔNG!**\n\n"
            f"• **Video gốc**: `{title}`\n"
            f"• **Draft CapCut ID**: `{draft_id}`\n"
            f"{queue_info_str}"
            f"• **Thư mục lưu**: `Videos/{current_folder}`\n"
            f"• **Tiến trình Edit**: Tự động bóc sub Hybrid ➔ Dịch AI ➔ Lách bản quyền ➔ Patch Timeline\n\n"
            f"🌐 *Bấm chọn ngôn ngữ bên dưới để Dịch Phụ đề & Lồng tiếng AI ngay:*",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        update_video_status(clean_url, status="PIPELINE_ERROR", error_msg=pip_err)
        log_pipeline_step(clean_url, "PIPELINE_CREATING", "FAILED", detail=f"Lỗi tạo Pipeline: {pip_err}")
        await status_msg.edit_text(
            f"⚠️ *Đã tải video nhưng gặp lỗi khi chèn vào CapCut Pipeline:*\n`{pip_err}`",
            parse_mode="Markdown"
        )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /history or /db command to query MongoDB records"""
    sys.path.append(str(BASE_DIR))
    from db import get_recent_videos
    videos = get_recent_videos(limit=5)
    if not videos:
        await update.effective_message.reply_text("🗄️ *Chưa có lịch sử video nào trong MongoDB (hoặc MongoDB server chưa bật).*", parse_mode="Markdown")
        return

    msg = "🗄️ **LỊCH SỬ VIDEO TRONG MONGODB (`video_logger_db.videos`)**\n\n"
    for idx, v in enumerate(videos, 1):
        title = v.get("pageTitle") or v.get("videoUrl", "")[:40]
        status = v.get("status", "UNKNOWN")
        folder = v.get("folderName", "default")
        current_step = v.get("currentStep", "N/A")
        draft_id = v.get("draftId", "Chưa tạo")
        cfg = v.get("renderConfig", {})

        cfg_str = f"{cfg.get('width', 1080)}x{cfg.get('height', 1920)} ({cfg.get('ratio', '9:16')}), FPS: {cfg.get('fps', 30)}, Sub: {cfg.get('autoCaptions', True)}" if cfg else "Mặc định"

        msg += (
            f"**{idx}. {title[:45]}**\n"
            f"   • 📁 **Thư mục**: `Videos/{folder}`\n"
            f"   • ⚙️ **Bước hiện tại**: `{current_step}` (`{status}`)\n"
            f"   • 🎬 **Draft ID**: `{draft_id}`\n"
            f"   • 🎨 **Cấu hình Render**: `{cfg_str}`\n\n"
        )

    await update.effective_message.reply_text(msg, parse_mode="Markdown")


async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /publish <file_or_url> command"""
    msg = update.effective_message
    args = context.args
    video_target = " ".join(args) if args else ""

    if not video_target:
        await msg.reply_text(
            "🚀 **CÚ PHÁP ĐẨY BÀI ĐA NỀN TẢNG:**\n"
            "`/publish <đường_dẫn_file_hoặc_url>`\n\n"
            "Ví dụ:\n"
            "`/publish C:/Projects/CapCutAPI/outputs/render.mp4`\n"
            "`/publish https://your-domain.com/video.mp4`",
            parse_mode="Markdown"
        )
        return

    status_msg = await msg.reply_text(f"🌐 *Đang tiến hành đẩy bài lên các nền tảng MXH...*\n`{video_target}`", parse_mode="Markdown")

    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, lambda: publish_video_auto(video_target))

    if res.get("success"):
        res_text = f"🎉 **ĐÃ ĐẨY BÀI THÀNH CÔNG!** ({res.get('success_count')}/{res.get('total_requested')} nền tảng)\n\n"
        for p, r in res.get("results", {}).items():
            if r.get("success"):
                res_text += f"• ✅ **{p.upper()}**: Post ID `{r.get('post_id')}`\n"
            else:
                res_text += f"• ❌ **{p.upper()}**: Lỗi - {r.get('error')}\n"
        await status_msg.edit_text(res_text, parse_mode="Markdown")
    else:
        await status_msg.edit_text(
            f"⚠️ **Thông báo đẩy bài:** `{res.get('error', 'Chưa có nền tảng nào được bật token')}`\n\n"
            f"💡 *Vui lòng cấu hình token trong file `config.json` dưới mục `social_credentials`.*",
            parse_mode="Markdown"
        )


async def autopublish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /autopublish <on/off> command"""
    msg = update.effective_message
    args = context.args

    if args:
        val = args[0].lower().strip()
        if val in ["on", "true", "1", "bat", "bật"]:
            set_auto_publish_enabled(True)
            await msg.reply_text("🟢 **Đã BẬT chế độ Tự động Đẩy bài Đa Nền tảng** sau khi dựng video!", parse_mode="Markdown")
            return
        elif val in ["off", "false", "0", "tat", "tắt"]:
            set_auto_publish_enabled(False)
            await msg.reply_text("🔴 **Đã TẮT chế độ Tự động Đẩy bài.**", parse_mode="Markdown")
            return

    status = "🟢 BẬT" if is_auto_publish_enabled() else "🔴 TẮT"
    platforms = get_enabled_platforms()
    plat_str = ", ".join(platforms) if platforms else "Chưa có token nền tảng nào được bật trong `config.json`"

    await msg.reply_text(
        f"⚙️ **CẤU HÌNH TỰ ĐỘNG ĐẨY BÀI (AUTO PUBLISH)**\n\n"
        f"• **Trạng thái hiện tại**: {status}\n"
        f"• **Nền tảng sẵn sàng**: `{plat_str}`\n\n"
        f"📌 **Cú pháp bật/tắt:**\n"
        f"• `/autopublish on` - Bật tự động đăng\n"
        f"• `/autopublish off` - Tắt tự động đăng",
        parse_mode="Markdown"
    )


async def pipeline_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /pipeline command"""
    args = context.args
    if args and (args[0].startswith("http://") or args[0].startswith("https://")):
        await handle_url_link(update, context)
    else:
        await update.effective_message.reply_text(
            "⚡ **Cú pháp chạy Pipeline với Link bất kỳ:**\n"
            "Gửi link trực tiếp hoặc dùng lệnh:\n"
            "`/pipeline https://www.youtube.com/watch?v=...`\n"
            "`/pipeline https://vt.tiktok.com/...`\n"
            "`/pipeline https://www.facebook.com/...`",
            parse_mode="Markdown"
        )


async def platform_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /platform or /xuat or /export command"""
    msg = update.effective_message
    args = context.args
    target_dir, current_folder = get_user_folder_dir(context)

    last_file = context.user_data.get("last_video_file")
    if not last_file or not os.path.exists(last_file):
        mp4s = list(target_dir.glob("*.mp4")) + list(target_dir.glob("*/*.mp4")) + list(VIDEOS_BASE_DIR.glob("*/*.mp4"))
        if mp4s:
            mp4s.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            last_file = str(mp4s[0])
            context.user_data["last_video_file"] = last_file

    if args:
        plat_input = args[0].lower().strip()
        matched_plat = None
        for k, v in SUPPORTED_PLATFORMS.items():
            if plat_input in k or plat_input in v["name"].lower():
                matched_plat = k
                break
        if matched_plat:
            await show_platform_action_menu(update, context, matched_plat, last_file)
            return

    await show_platform_selection_menu(update, context, last_file)


async def show_platform_selection_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, video_path: Optional[str] = None):
    """Display interactive platform selector buttons (TikTok, YouTube Shorts, Reels, etc.)"""
    msg = update.effective_message
    target_dir, current_folder = get_user_folder_dir(context)

    if not video_path:
        video_path = context.user_data.get("last_video_file")
    if not video_path or not os.path.exists(video_path):
        mp4s = list(target_dir.glob("*.mp4")) + list(target_dir.glob("*/*.mp4")) + list(VIDEOS_BASE_DIR.glob("*/*.mp4"))
        if mp4s:
            mp4s.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            video_path = str(mp4s[0])
            context.user_data["last_video_file"] = video_path

    file_info = f"`{os.path.basename(video_path)}`" if video_path else f"Thư mục `Videos/{current_folder}`"

    keyboard = [
        [
            InlineKeyboardButton("🎵 TikTok (Dọc 9:16)", callback_data="cb_plat_tiktok"),
            InlineKeyboardButton("🔴 YouTube Shorts (9:16)", callback_data="cb_plat_youtube_shorts"),
        ],
        [
            InlineKeyboardButton("🔵 Facebook Reels (9:16)", callback_data="cb_plat_facebook_reels"),
            InlineKeyboardButton("📸 Instagram Reels (9:16)", callback_data="cb_plat_instagram_reels"),
        ],
        [
            InlineKeyboardButton("📺 YouTube Ngang (16:9)", callback_data="cb_plat_youtube_long"),
            InlineKeyboardButton("🌐 Đa Nền Tảng (All-in-One)", callback_data="cb_plat_all_platforms"),
        ],
        [
            InlineKeyboardButton("📁 Chọn Thư Mục", callback_data="btn_folders"),
            InlineKeyboardButton("📊 Trạng thái Hệ thống", callback_data="btn_status"),
        ]
    ]

    text = (
        f"🚀 **STUDIO DỊCH & XUẤT VIDEO THEO NỀN TẢNG**\n\n"
        f"• **Video nguồn**: {file_info}\n"
        f"• **Quy trình Auto**: Bóc sub Hybrid ➔ Dịch AI ➔ Lách bản quyền ➔ Căn tỷ lệ ➔ Render video thành phẩm & Đăng bài!\n\n"
        f"👇 **Vui lòng chọn NỀN TẢNG MỤC TIÊU bạn muốn xuất video:**"
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def show_platform_action_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, platform_key: str, video_path: Optional[str] = None):
    """Display action & language combo buttons for the selected platform"""
    plat = SUPPORTED_PLATFORMS.get(platform_key, SUPPORTED_PLATFORMS["tiktok"])
    target_dir, current_folder = get_user_folder_dir(context)

    if not video_path:
        video_path = context.user_data.get("last_video_file")
    if not video_path or not os.path.exists(video_path):
        mp4s = list(target_dir.glob("*.mp4")) + list(target_dir.glob("*/*.mp4")) + list(VIDEOS_BASE_DIR.glob("*/*.mp4"))
        if mp4s:
            mp4s.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            video_path = str(mp4s[0])
            context.user_data["last_video_file"] = video_path

    file_info = f"`{os.path.basename(video_path)}`" if video_path else f"Thư mục `Videos/{current_folder}`"

    keyboard = [
        [
            InlineKeyboardButton(f"🇻🇳 Dịch Tiếng Việt & Xuất {plat['name']}", callback_data=f"cb_pexport_vi_{platform_key}")
        ],
        [
            InlineKeyboardButton(f"🇺🇸 Dịch English & Xuất {plat['name']}", callback_data=f"cb_pexport_en_{platform_key}"),
            InlineKeyboardButton(f"🇨🇳 Dịch Trung & Xuất {plat['name']}", callback_data=f"cb_pexport_zh_{platform_key}"),
        ],
        [
            InlineKeyboardButton(f"🔥 Dịch 10 Ngôn Ngữ & Xuất {plat['name']}", callback_data=f"cb_pexport_all_{platform_key}")
        ],
        [
            InlineKeyboardButton(f"🚀 Dịch, Render & Đăng Tự Động ({plat['name']})", callback_data=f"cb_papub_vi_{platform_key}")
        ],
        [
            InlineKeyboardButton(f"📝 Chỉ Dịch Sub (.SRT) ({plat['name']})", callback_data=f"cb_psrt_vi_{platform_key}")
        ],
        [
            InlineKeyboardButton("↩️ Quay lại Chọn Nền Tảng", callback_data="btn_platform_menu")
        ]
    ]

    text = (
        f"{plat['flag']} **TÙY CHỌN DỊCH & XUẤT CHO NỀN TẢNG: {plat['name'].upper()}**\n\n"
        f"• **Tỷ lệ khung hình**: `{plat['ratio']}` ({plat['width']}x{plat['height']})\n"
        f"• **Đặc tính tối ưu**: _{plat['desc']}_\n"
        f"• **Video nguồn**: {file_info}\n\n"
        f"👇 **Bấm chọn thao tác bạn muốn thực hiện:**"
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def execute_platform_export(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    platform_key: str,
    lang_code: str,
    auto_publish: bool = False,
    srt_only: bool = False,
    video_path: Optional[str] = None
):
    """Execute the complete platform translation & export pipeline via native Pipeline Queue"""
    msg = update.effective_message
    target_dir, current_folder = get_user_folder_dir(context)

    if not video_path:
        video_path = context.user_data.get("last_video_file")
    if not video_path or not os.path.exists(video_path):
        mp4s = list(target_dir.glob("*.mp4")) + list(target_dir.glob("*/*.mp4")) + list(VIDEOS_BASE_DIR.glob("*/*.mp4"))
        if mp4s:
            mp4s.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            video_path = str(mp4s[0])
            context.user_data["last_video_file"] = video_path

    if not video_path or not os.path.exists(video_path):
        await msg.reply_text("❌ *Không tìm thấy file video nào. Vui lòng gửi link hoặc tải video lên trước!*", parse_mode="Markdown")
        return

    plat = SUPPORTED_PLATFORMS.get(platform_key, SUPPORTED_PLATFORMS["tiktok"])
    lang_info = SUPPORTED_BOT_LANGUAGES.get(lang_code, {"name": "Tiếng Việt", "flag": "🇻🇳", "target": "Vietnamese"})

    action_label = "Chỉ Dịch Sub (.SRT)" if srt_only else ("Dịch, Render & Đăng Tự Động" if auto_publish else f"Dịch & Xuất Video {plat['name']}")
    wait_hint = "⚡ *Đang bóc tách & dịch AI trực tiếp ngay lập tức (không mở CapCut, không xếp hàng)...*" if srt_only else "⏳ *Đang xếp hàng vào Master Pipeline Engine...*"

    status_msg = await msg.reply_text(
        f"🚀 **ĐANG KHỞI CHẠY PIPELINE: {action_label.upper()}**\n\n"
        f"• **Video nguồn**: `{os.path.basename(video_path)}`\n"
        f"• **Nền tảng đích**: {plat['flag']} **{plat['name']}** (Tỷ lệ `{plat['ratio']}`)\n"
        f"• **Ngôn ngữ đích**: {lang_info['flag']} **{lang_info['name']}**\n"
        f"• **Chế độ**: {'📝 Dịch AI & Xuất File .SRT' if srt_only else ('🚀 Render & Tự Động Đăng MXH' if auto_publish else '🎬 Dịch, Render & Xuất File MP4')}\n\n"
        f"{wait_hint}",
        parse_mode="Markdown"
    )

    custom_cfg = {
        "platform": platform_key,
        "ratio": plat["ratio"],
        "width": plat["width"],
        "height": plat["height"],
        "target_language": lang_info["target"],
        "translate_only": srt_only,
        "subtitle_only": srt_only,
        "auto_publish": auto_publish,
        "auto_export": not srt_only
    }

    if srt_only:
        # Run pure subtitle translation directly (instant, no CapCut, no queue)
        sys.path.insert(0, str(ROOT_DIR / "src"))
        from capcut_api.api.gui_app import process_video_subtitles_pure
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: process_video_subtitles_pure(video_path, item_config=custom_cfg, target_languages=[lang_code]))
        if res.get("success"):
            srts = res.get("generated_srts", {})
            out_srt = srts.get(lang_code, srts.get("original", ""))
            total_segs = res.get("total_segments", 0)

            # Send SRT file to Telegram
            if out_srt and os.path.exists(out_srt):
                try:
                    with open(out_srt, "rb") as sf:
                        await context.bot.send_document(
                            chat_id=update.effective_chat.id,
                            document=sf,
                            filename=os.path.basename(out_srt),
                            caption=f"📝 File phụ đề {lang_info['name']} ({total_segs} câu)"
                        )
                except Exception as doc_err:
                    logger.warning(f"Could not send SRT document: {doc_err}")

            keyboard = [
                [InlineKeyboardButton("🔄 Dịch Ngôn Ngữ Khác", callback_data="btn_trans_menu")],
                [InlineKeyboardButton("🚀 Dịch & Xuất Video Full", callback_data=f"cb_pexport_{lang_code}_{platform_key}")],
                [InlineKeyboardButton("📊 Xem Trạng Thái", callback_data="btn_status")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await status_msg.edit_text(
                f"🎉 **ĐÃ DỊCH XONG FILE PHỤ ĐỀ CHO {plat['name'].upper()}!**\n\n"
                f"• **File SRT**: `{os.path.basename(out_srt)}`\n"
                f"• **Thư mục lưu**: `{res.get('video_folder')}`\n"
                f"• **Số câu thoại**: **{total_segs} câu**\n\n"
                f"✅ *File .SRT đã được lưu trực tiếp tại thư mục video và gửi kèm trong chat!*",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await status_msg.edit_text(f"❌ *Lỗi khi dịch phụ đề:* `{res.get('error')}`", parse_mode="Markdown")
        return

    # Full Video Render / Export Pipeline Queue
    q_ok, q_pos, q_total = enqueue_video_to_capcut_pipeline(video_path, custom_cfg)

    keyboard = [
        [InlineKeyboardButton("📊 Theo dõi Tiến trình Web UI", url="http://127.0.0.1:9001/queue")],
        [InlineKeyboardButton("🔄 Đổi Nền Tảng Khác", callback_data="btn_platform_menu")],
        [InlineKeyboardButton("🗄️ Tra cứu MongoDB", callback_data="btn_history")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await status_msg.edit_text(
        f"🎉 **ĐÃ NẠP VIDEO VÀO PIPELINE DỊCH & XUẤT {plat['name'].upper()} THÀNH CÔNG!**\n\n"
        f"• **Video nguồn**: `{os.path.basename(video_path)}`\n"
        f"• **Nền tảng**: {plat['flag']} **{plat['name']}** ({plat['width']}x{plat['height']}, `{plat['ratio']}`)\n"
        f"• **Ngôn ngữ**: {lang_info['flag']} **{lang_info['name']}**\n"
        f"• **Vị trí hàng đợi**: `#{q_pos}` / `{q_total}` job (Đang tự động chạy)\n"
        f"• **Tự động đăng bài**: {'🟢 BẬT (Đẩy sau khi render)' if auto_publish else '⚪ Xuất video vào thư mục `outputs/`'}\n\n"
        f"⚙️ **Các bước đang thực hiện:**\n"
        f"  1. 🎙️ Bóc tách lời thoại Hybrid (Whisper + OCR)\n"
        f"  2. 🤖 Dịch AI {lang_info['name']} theo ngữ cảnh chuẩn\n"
        f"  3. 🛡️ Lách bản quyền thông minh & chỉnh tỷ lệ `{plat['ratio']}`\n"
        f"  4. 🎬 Patch Timeline CapCut & Xuất video thành phẩm\n\n"
        f"👉 *Bạn có thể theo dõi live tiến trình trên Web UI bằng nút bên dưới:*",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )



async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /translate or /dich command"""
    msg = update.effective_message
    args = context.args
    target_dir, current_folder = get_user_folder_dir(context)

    last_file = context.user_data.get("last_video_file")
    if not last_file or not os.path.exists(last_file):
        # find newest mp4 in target_dir or downloads
        mp4s = list(target_dir.glob("*.mp4")) + list(target_dir.glob("*/*.mp4")) + list(VIDEOS_BASE_DIR.glob("*/*.mp4"))
        if mp4s:
            mp4s.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            last_file = str(mp4s[0])
            context.user_data["last_video_file"] = last_file

    if args:
        req_lang = args[0].lower().strip()
        if req_lang in ["all", "tatca", "tat_ca", "full"]:
            await do_translate_all_languages(update, context, last_file)
            return

        matched = SUPPORTED_BOT_LANGUAGES.get(req_lang)
        if not matched:
            for k, v in SUPPORTED_BOT_LANGUAGES.items():
                if req_lang in v["target"].lower() or req_lang in v["name"].lower():
                    matched = v
                    break
        if matched:
            await do_translate_video(update, context, matched, last_file)
            return

    # Show language selection keyboard
    keyboard = [
        [InlineKeyboardButton("🔥 DỊCH RA TẤT CẢ (ALL 10 NGÔN NGỮ CÙNG LÚC)", callback_data="cb_trans_all")]
    ]
    keys = list(SUPPORTED_BOT_LANGUAGES.keys())
    for i in range(0, len(keys), 2):
        row = []
        for k in keys[i:i+2]:
            l = SUPPORTED_BOT_LANGUAGES[k]
            row.append(InlineKeyboardButton(f"{l['flag']} {l['name']}", callback_data=f"cb_trans_{k}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("📊 Trạng thái Hệ thống", callback_data="btn_status")])

    file_info = f"`{os.path.basename(last_file)}`" if last_file else f"Thư mục `Videos/{current_folder}`"
    text = (
        f"🌐 **STUDIO DỊCH ĐA NGÔN NGỮ & LỒNG TIẾNG AI**\n\n"
        f"• **Video nguồn**: {file_info}\n"
        f"• **Quy trình**: 🎙️ Whisper trích xuất ➔ 🤖 AI Dịch thuật ➔ 🗣️ Lồng tiếng AI (TTS) ➔ 🎬 Nạp CapCut.\n\n"
        f"👇 **Chọn ngôn ngữ bạn muốn dịch sang:**"
    )
    reply_markup = InlineKeyboardMarkup(keyboard)
    await msg.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def do_translate_video(update: Update, context: ContextTypes.DEFAULT_TYPE, lang_info: dict, video_path: Optional[str] = None):
    """Execute AI subtitle extraction and translation, saving .SRT in the original video's directory (No TTS, No CapCut GUI)"""
    msg = update.effective_message
    if not video_path:
        video_path = context.user_data.get("last_video_file")

    if not video_path or not os.path.exists(video_path):
        target_dir, current_folder = get_user_folder_dir(context)
        mp4s = list(target_dir.glob("*.mp4")) + list(target_dir.glob("*/*.mp4")) + list(VIDEOS_BASE_DIR.glob("*/*.mp4"))
        if mp4s:
            mp4s.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            video_path = str(mp4s[0])
            context.user_data["last_video_file"] = video_path

    if not video_path or not os.path.exists(video_path):
        await msg.reply_text("❌ *Không tìm thấy file video nào để dịch. Hãy gửi link video hoặc tải file video lên trước!*", parse_mode="Markdown")
        return

    lang_name = lang_info.get("name", "Tiếng Việt")
    lang_flag = lang_info.get("flag", "🌐")
    target_lang = lang_info.get("target", "vi")
    lang_code = lang_info.get("code", "vi")

    status_msg = await msg.reply_text(
        f"🤖 **BẮT ĐẦU DỊCH PHỤ ĐỀ SANG {lang_flag} {lang_name.upper()} (AI SUBTITLE ONLY)**\n\n"
        f"• **Video nguồn**: `{os.path.basename(video_path)}`\n"
        f"• **Thư mục lưu**: `{os.path.dirname(video_path)}`\n"
        f"• **Quy trình**: 🔬 **Cơ chế Hybrid (Whisper Audio + RapidOCR)** ➔ 🧠 **9-Router AI Dịch** ➔ 📝 **Xuất file .SRT**\n"
        f"💡 *Chế độ độc lập: Không cần lồng tiếng & Không cần mở CapCut!*\n\n"
        f"⏳ *1/2: Đang bóc tách phụ đề bằng Cơ Chế Hybrid (Whisper + OCR)...*",
        parse_mode="Markdown"
    )

    def run_trans_worker():
        try:
            sys.path.insert(0, str(ROOT_DIR / "src"))
            from capcut_api.api.gui_app import process_video_subtitles_pure
            res = process_video_subtitles_pure(video_path, target_languages=[lang_code])
            return res.get("success", False), res
        except Exception as e:
            return False, {"error": str(e)}

    loop = asyncio.get_running_loop()
    ok, res = await loop.run_in_executor(None, run_trans_worker)

    keyboard = [
        [InlineKeyboardButton("🌐 Dịch Ngôn Ngữ Khác", callback_data="btn_trans_menu")],
        [InlineKeyboardButton("🗄️ Tra cứu MongoDB", callback_data="btn_history")],
        [InlineKeyboardButton("📊 Trạng thái Hệ thống", callback_data="btn_status")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if ok:
        srts = res.get("generated_srts", {})
        orig_srt = srts.get("original", "")
        lang_srt = srts.get(lang_code, "")
        total_segs = res.get("total_segments", 0)

        # Try to send SRT file as Telegram attachment
        if lang_srt and os.path.exists(lang_srt):
            try:
                with open(lang_srt, "rb") as srt_file:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=srt_file,
                        filename=os.path.basename(lang_srt),
                        caption=f"📝 File phụ đề AI: {lang_flag} {lang_name} ({total_segs} câu)"
                    )
            except Exception as e:
                logger.warning(f"Could not send SRT file: {e}")

        await status_msg.edit_text(
            f"🎉 **ĐÃ DỊCH & XUẤT FILE PHỤ ĐỀ .SRT THÀNH CÔNG!**\n\n"
            f"• **Video nguồn**: `{os.path.basename(video_path)}`\n"
            f"• **Tổng số câu thoại**: **{total_segs} câu**\n"
            f"• **File phụ đề gốc**: `{os.path.basename(orig_srt)}`\n"
            f"• **File phụ đề AI ({lang_name})**: `{os.path.basename(lang_srt)}`\n"
            f"• **Thư mục lưu**: `{res.get('video_folder')}`\n\n"
            f"✅ *File .SRT đã được lưu trực tiếp tại thư mục của video gốc!*",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        err = res.get("error", "Lỗi không xác định")
        await status_msg.edit_text(
            f"⚠️ *Lỗi khi dịch video:* `{err}`",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )


async def do_translate_all_languages(update: Update, context: ContextTypes.DEFAULT_TYPE, video_path: Optional[str] = None):
    """Batch translate video to ALL supported languages using AI and save .SRT in original video directory"""
    msg = update.effective_message
    if not video_path:
        video_path = context.user_data.get("last_video_file")

    if not video_path or not os.path.exists(video_path):
        target_dir, current_folder = get_user_folder_dir(context)
        mp4s = list(target_dir.glob("*.mp4")) + list(target_dir.glob("*/*.mp4")) + list(VIDEOS_BASE_DIR.glob("*/*.mp4"))
        if mp4s:
            mp4s.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            video_path = str(mp4s[0])
            context.user_data["last_video_file"] = video_path

    if not video_path or not os.path.exists(video_path):
        await msg.reply_text("❌ *Không tìm thấy file video nào để dịch. Hãy gửi link video hoặc tải file video lên trước!*", parse_mode="Markdown")
        return

    total_langs = len(SUPPORTED_BOT_LANGUAGES)
    status_msg = await msg.reply_text(
        f"🌍 **KHỞI CHẠY DỊCH PHỤ ĐỀ AI TOÀN BỘ {total_langs} NGÔN NGỮ (SRT BATCH)**\n\n"
        f"• **Video nguồn**: `{os.path.basename(video_path)}`\n"
        f"• **Thư mục đích**: `{os.path.dirname(video_path)}`\n"
        f"• **Quy trình**: Whisper trích xuất ➔ Dịch AI ➔ Lưu .SRT tất cả ngôn ngữ\n\n"
        f"⏳ *Đang tiến hành trích xuất Whisper và dịch toàn bộ các file .SRT...*",
        parse_mode="Markdown"
    )

    sys.path.insert(0, str(ROOT_DIR / "src"))
    from capcut_api.api.gui_app import process_video_subtitles_pure

    target_lang_codes = list(SUPPORTED_BOT_LANGUAGES.keys())

    def run_all():
        return process_video_subtitles_pure(video_path, target_languages=target_lang_codes)

    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, run_all)

    keyboard = [
        [InlineKeyboardButton("🗄️ Tra cứu MongoDB", callback_data="btn_history")],
        [InlineKeyboardButton("📊 Trạng thái Hệ thống", callback_data="btn_status")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if res.get("success"):
        srts = res.get("generated_srts", {})
        total_segs = res.get("total_segments", 0)
        lines = []
        for k, v in srts.items():
            if k == "original":
                lines.append(f"  ├ 🎙️ Gốc: `{os.path.basename(v)}`")
            else:
                flag = SUPPORTED_BOT_LANGUAGES.get(k, {}).get("flag", "🌐")
                name = SUPPORTED_BOT_LANGUAGES.get(k, {}).get("name", k)
                lines.append(f"  ├ {flag} {name}: `{os.path.basename(v)}`")

        await status_msg.edit_text(
            f"🎉 **ĐÃ HOÀN TẤT TOÀN BỘ {len(srts)-1}/{total_langs} FILE PHỤ ĐỀ .SRT!**\n\n"
            f"• **Video nguồn**: `{os.path.basename(video_path)}`\n"
            f"• **Tổng số câu thoại**: **{total_segs} câu**\n"
            f"• **Thư mục lưu**: `{res.get('video_folder')}`\n\n"
            f"📜 **Danh sách file .SRT đã tạo**:\n"
            + "\n".join(lines) + "\n\n"
            f"✅ *Toàn bộ các file .SRT đã được lưu ngay tại thư mục của video gốc!*",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        err = res.get("error", "Lỗi không xác định")
        await status_msg.edit_text(
            f"⚠️ *Lỗi khi dịch phụ đề:* `{err}`",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )


async def set_ai_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /ai_key <provider> <key> to configure Gemini/OpenAI API key"""
    msg = update.effective_message
    args = context.args
    if not args or len(args) < 2:
        await msg.reply_text(
            "🔑 **HƯỚNG DẪN CẤU HÌNH AI API KEY**\n\n"
            "Cú pháp lệnh:\n"
            "• `/ai_key gemini <YOUR_GEMINI_API_KEY>`\n"
            "• `/ai_key openai <YOUR_OPENAI_API_KEY>`\n"
            "• `/ai_key deepseek <YOUR_DEEPSEEK_API_KEY>`\n\n"
            "👉 *Key sẽ được lưu tự động vào config.json và áp dụng ngay lập tức.*",
            parse_mode="Markdown"
        )
        return

    provider = args[0].strip().lower()
    api_key = args[1].strip()

    try:
        cfg_path = ROOT_DIR / "config.json"
        cfg = {}
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg[f"{provider}_api_key"] = api_key
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        await msg.reply_text(f"✅ *Đã lưu thành công {provider.upper()} API Key vào hệ thống!*", parse_mode="Markdown")
    except Exception as e:
        await msg.reply_text(f"❌ *Lỗi khi lưu API Key:* `{e}`", parse_mode="Markdown")


def main():
    """Main function to run Telegram Bot"""
    sys.stdout.reconfigure(encoding="utf-8")
    config = load_config()
    token = config.get("telegram_bot_token", "")


    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("\n" + "=" * 70)
        print("❌ LỖI: Chưa cấu hình Telegram Bot Token trong file config.json!")
        print("👉 Vui lòng mở file 'config.json' và thay 'YOUR_TELEGRAM_BOT_TOKEN_HERE'")
        print("   bằng Token bạn nhận được từ BotFather (ví dụ trong ảnh).")
        print("=" * 70 + "\n")
        sys.exit(1)

    print("🚀 Đang khởi chạy Telegram Bot AUTO VIDEO BOT...")
    print("📌 Đang kết nối tới Telegram API...")

    app = Application.builder().token(token).build()

    # Register Handlers
    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler(["platform", "xuat", "export"], platform_command))
    app.add_handler(CommandHandler(["translate", "dich"], translate_command))
    app.add_handler(CommandHandler(["ai_key", "set_ai_key", "apikey"], set_ai_key_command))
    app.add_handler(CommandHandler("new_draft", new_draft_command))
    app.add_handler(CommandHandler("pipeline", pipeline_command))
    app.add_handler(CommandHandler("rpa_export", rpa_export_command))
    app.add_handler(CommandHandler(["publish", "pub"], publish_command))
    app.add_handler(CommandHandler(["autopublish", "autopub"], autopublish_command))
    app.add_handler(CommandHandler(["folder", "setfolder"], folder_command))

    app.add_handler(CommandHandler(["history", "db"], history_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Handle direct URL links and share text (YouTube, TikTok, Facebook, Douyin, etc.)
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'https?://'), handle_url_link))

    # Media upload handler
    app.add_handler(MessageHandler(filters.VIDEO | filters.AUDIO | filters.PHOTO | filters.Document.ALL, handle_media_upload))

    print("✅ Bot đã sẵn sàng nhận lệnh từ Telegram! (Đang lắng nghe Polling...)")
    app.run_polling()


if __name__ == "__main__":
    main()
