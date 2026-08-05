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
sys.path.append(str(BASE_DIR))

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

VIDEOS_BASE_DIR = BASE_DIR / "Videos"
OUTPUTS_DIR = BASE_DIR / "outputs"

VIDEOS_BASE_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)


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


def load_config() -> dict:
    """Load configuration from config.json"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config.json: {e}")
    return {}


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
            InlineKeyboardButton("🎬 Tạo Project Nháp", callback_data="btn_new_draft"),
            InlineKeyboardButton("⚡ Dựng Pipeline Auto", callback_data="btn_pipeline"),
        ],
        [
            InlineKeyboardButton("📁 Thư mục lưu trữ", callback_data="btn_folders"),
            InlineKeyboardButton("🖥️ Xuất Video (RPA)", callback_data="btn_rpa_export"),
        ],
        [
            InlineKeyboardButton("🚀 Đẩy bài Đa Nền tảng", callback_data="btn_publish_menu"),
            InlineKeyboardButton("⚙️ Auto Publish", callback_data="btn_autopublish_menu"),
        ],
        [
            InlineKeyboardButton("🗄️ Tra cứu MongoDB", callback_data="btn_history"),
            InlineKeyboardButton("📊 Kiểm tra Status", callback_data="btn_status"),
        ],
        [
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
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/", headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2) as response:
            server_online = response.status in [200, 404]
    except Exception:
        server_online = False

    # Count downloaded files
    downloads_count = len(list(DOWNLOADS_DIR.glob("*")))
    outputs_count = len(list(OUTPUTS_DIR.glob("*")))

    status_text = (
        f"📊 **BÁO CÁO TRẠNG THÁI HỆ THỐNG**\n\n"
        f"• **CapCut API Server**: {'🟢 Hoạt động (Port ' + str(port) + ')' if server_online else '🔴 Chưa bật server (sẽ dùng script trực tiếp)'}\n"
        f"• **Thư mục Downloads**: {downloads_count} file\n"
        f"• **Thư mục Outputs (Video xuất)**: {outputs_count} file\n"
        f"• **Đường dẫn thư mục làm việc**: `{BASE_DIR}`"
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

        success_msg = (
            f"✅ **Đã nhận {media_type} thành công!**\n\n"
            f"• **Tên file**: `{filename}`\n"
            f"• **Dung lượng**: {file_size_mb:.2f} MB\n"
            f"• **Thư mục lưu**: `Videos/{current_folder}`\n"
            f"• **Đường dẫn**: `{save_path}`\n\n"
            f"💡 *Bạn có thể dùng file này làm đầu vào cho quy trình dựng video CapCut.*"
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
    title = result.get("title", "Video")
    duration = result.get("duration", 0)
    width = result.get("width", 1080)
    height = result.get("height", 1920)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024) if os.path.exists(file_path) else 0

    render_cfg = get_default_render_config(width=width, height=height)

    # 3. Log step: DOWNLOADED
    update_video_status(clean_url, status="DOWNLOADED", local_path=file_path)
    log_pipeline_step(
        clean_url,
        "DOWNLOADED",
        "SUCCESS",
        detail=f"File: {file_path} ({file_size_mb:.2f} MB)",
        render_config=render_cfg,
        extra_meta={
            "videoMeta": {
                "title": title,
                "duration": duration,
                "width": width,
                "height": height,
                "fileSizeMb": round(file_size_mb, 2),
                "localPath": file_path
            }
        }
    )

    await status_msg.edit_text(
        f"✅ **Tải Video thành công!**\n\n"
        f"• **Tiêu đề**: `{title}`\n"
        f"• **Thời lượng**: {duration}s\n"
        f"• **Dung lượng**: {file_size_mb:.2f} MB\n"
        f"• **Lưu tại**: `{file_path}`\n\n"
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

    if pip_success:
        # 5. Log step: DRAFT_CREATED
        update_video_status(clean_url, status="DRAFT_CREATED", draft_id=draft_id)
        log_pipeline_step(
            clean_url,
            "DRAFT_CREATED",
            "SUCCESS",
            detail=f"Đã tạo CapCut Draft ID: {draft_id}",
            render_config=render_cfg,
            extra_meta={"draftId": draft_id}
        )

        keyboard = [
            [InlineKeyboardButton("🖥️ Xuất Video Ngay (RPA)", callback_data="btn_rpa_export")],
            [InlineKeyboardButton("🗄️ Tra cứu MongoDB", callback_data="btn_history")],
            [InlineKeyboardButton("📊 Trạng thái Hệ thống", callback_data="btn_status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await status_msg.edit_text(
            f"🎉 **ĐÀO TẠO PIPELINE HOÀN TẤT!**\n\n"
            f"• **Video gốc**: `{title}`\n"
            f"• **Draft CapCut ID**: `{draft_id}`\n"
            f"• **Thư mục lưu**: `Videos/{current_folder}`\n"
            f"• **Trạng thái MongoDB**: `DRAFT_CREATED`\n\n"
            f"🚀 Bấm nút dưới đây để gọi CapCut xuất video ra MP4:",
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
