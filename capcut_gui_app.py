#!/usr/bin/env python3
import os
import sys
import json
import time
import queue
import logging
import threading
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response

# Add current dir to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import uiautomation as auto
import pyautogui

from pyJianYingDraft.capcut_controller import CapCutController, ExportResolution, ExportFramerate, capcut_process_ids, capcut_main_hwnd_and_rect
from pyJianYingDraft.exceptions import AutomationError

DEFAULT_CAPCUT_DRAFTS = r"C:\Users\PC\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft"
FIRST_PROJECT_FALLBACK_X = 285
FIRST_PROJECT_FALLBACK_Y = 583

# Configure logging
logger = logging.getLogger("flask_video_generator")
logger.setLevel(logging.INFO)

# Log Queue for SSE Stream
sse_log_queue = queue.Queue()

class SSELogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        level = "info"
        if record.levelno >= logging.ERROR:
            level = "error"
        elif record.levelno >= logging.WARNING:
            level = "warning"
        elif record.levelno >= logging.INFO:
            if any(w in log_entry.lower() for w in ["thành công", "hoàn thành", "success", "finished"]):
                level = "success"
            else:
                level = "info"
        sse_log_queue.put({"message": log_entry, "level": level})

# Attach SSE log handler
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
sse_handler = SSELogHandler()
sse_handler.setFormatter(formatter)
logger.addHandler(sse_handler)

# Create Flask Application
app = Flask(__name__, template_folder="templates")

# Disable default flask access logs in SSE stream to avoid cluttering
log_werkzeug = logging.getLogger('werkzeug')
log_werkzeug.setLevel(logging.WARNING)

# --- Helper RPA Functions ---

def run_image_workflow(config_name, label):
    """Run an OpenCV/PyAutoGUI workflow from JSON."""
    from capcut_rpa import run_workflow

    workflow_path = Path(__file__).resolve().parent / config_name
    logger.info(f"Chạy workflow nhận diện ảnh: {label} ({workflow_path.name})")
    result = run_workflow(workflow_path, dry_run=False)
    logger.info(json.dumps(result, ensure_ascii=False))
    return result

def find_element_by_name(root, target_name, depth=0, max_depth=10):
    if not root or depth > max_depth:
        return None
    name = (root.Name or "").strip()
    if target_name.lower() in name.lower():
        return root
    try:
        for child in root.GetChildren():
            res = find_element_by_name(child, target_name, depth + 1, max_depth)
            if res:
                return res
    except Exception:
        pass
    return None

def launch_capcut():
    logger.info("Đang kiểm tra và khởi động CapCut...")
    hwnd_and_rect = capcut_main_hwnd_and_rect()
    if hwnd_and_rect is None:
        logger.info("Không tìm thấy cửa sổ CapCut GUI đang mở. Dọn dẹp tiến trình ngầm cũ...")
        kill_capcut()
        time.sleep(1)
        logger.info("Khởi chạy CapCut từ shortcut Desktop...")
        # Use explorer to run desktop link interactively inside user session
        subprocess.Popen(["explorer.exe", r"C:\Users\PC\Desktop\CapCut.lnk"])
        for _ in range(30):
            time.sleep(0.5)
            if capcut_main_hwnd_and_rect() is not None:
                break
                
    # Wait for window and connect controller
    logger.info("Đang kết nối với cửa sổ CapCut...")
    for i in range(25):
        try:
            controller = CapCutController()
            if controller.app and controller.app.Exists(0):
                logger.info(f"Đã kết nối thành công tới cửa sổ CapCut (Trạng thái: {controller.app_status})")
                return controller
        except Exception as e:
            logger.warning(f"Lần thử {i+1}/25 kết nối với CapCut thất bại: {str(e)}")
        time.sleep(1)
    raise Exception("Không thể kết nối với cửa sổ CapCut. Vui lòng mở CapCut thủ công trước.")

def open_project_in_gui(controller, project_name):
    logger.info(f"Đang tìm và mở dự án '{project_name}' trên màn hình CapCut...")
    controller.app.SetActive()
    controller.app.SetTopmost()
    
    # Refresh window state
    controller.get_window()
    
    # If we are already in the editor panel (Export button exists), close active draft first
    export_btn = find_element_by_name(controller.app, "Export") or find_element_by_name(controller.app, "Xuất")
    if export_btn:
        logger.info("CapCut đang mở sẵn dự án khác. Tiến hành đóng dự án cũ để về màn hình chính...")
        # Click close project button (usually "Back" arrow or X in the top left)
        # We can also just taskkill and launch CapCut clean to ensure we start on home screen!
        kill_capcut()
        controller = launch_capcut()
        controller.app.SetActive()
        controller.app.SetTopmost()
        time.sleep(2)
        
    logger.info("Clicking first project by fixed coordinate only; skipping OpenCV and UIA...")
    pyautogui.click(FIRST_PROJECT_FALLBACK_X, FIRST_PROJECT_FALLBACK_Y)
    logger.info("Waiting 5 seconds after first-project click before continuing pipeline...")
    time.sleep(5)
    return controller
    # Wait up to 30 seconds for editor window to open
    logger.info("Đang đợi chế độ chỉnh sửa tải xong...")
    for _ in range(30):
        time.sleep(1)
        controller.get_window()
        export_btn = find_element_by_name(controller.app, "Export") or find_element_by_name(controller.app, "Xuất")
        if export_btn:
            logger.info("Đã mở dự án thành công.")
            return True
            
    raise Exception("Đợi mở dự án bị quá giờ (Timeout).")

def run_auto_captions(controller):
    logger.info("Tiến hành tự động nhận diện phụ đề (Auto Captions)...")
    
    # 1. Click Text tab on top-left menu
    text_tab = find_element_by_name(controller.app, "Text") or find_element_by_name(controller.app, "Văn bản")
    if not text_tab:
        text_tab = auto.ButtonControl(searchDepth=6, Name="Text") or auto.ButtonControl(searchDepth=6, Name="Văn bản")
    if not text_tab:
        raise Exception("Không tìm thấy Tab 'Text'/'Văn bản' ở góc trên bên trái!")
    logger.info("Nhấp chọn tab 'Text'...")
    text_tab.Click()
    time.sleep(1)
    
    # 2. Click Auto captions tab on left sub-menu
    captions_tab = find_element_by_name(controller.app, "Auto captions") or find_element_by_name(controller.app, "Chú thích tự động")
    if not captions_tab:
        captions_tab = auto.ButtonControl(searchDepth=8, Name="Auto captions") or auto.ButtonControl(searchDepth=8, Name="Chú thích tự động")
    if not captions_tab:
        raise Exception("Không tìm thấy tiểu mục 'Auto captions'/'Chú thích tự động'!")
    logger.info("Nhấp chọn 'Auto captions'...")
    captions_tab.Click()
    time.sleep(1.5)
    
    # 3. Click Generate button
    gen_btn = find_element_by_name(controller.app, "Generate") or find_element_by_name(controller.app, "Bắt đầu") or find_element_by_name(controller.app, "Create")
    if not gen_btn:
        gen_btn = auto.ButtonControl(searchDepth=8, Name="Generate") or auto.ButtonControl(searchDepth=8, Name="Bắt đầu")
    if not gen_btn:
        raise Exception("Không tìm thấy nút 'Generate' / 'Bắt đầu' nhận diện phụ đề!")
    logger.info("Nhấp chọn nút 'Generate' / 'Bắt đầu'...")
    gen_btn.Click()
    
    # 4. Wait for captions dialog to complete
    logger.info("Đang nhận diện giọng nói tạo chữ (Auto Captions)... Vui lòng đợi...")
    time.sleep(5)
    for i in range(120):
        time.sleep(2)
        controller.get_window()
        export_btn = find_element_by_name(controller.app, "Export") or find_element_by_name(controller.app, "Xuất")
        if export_btn and not find_element_by_name(controller.app, "Creating"):
            logger.info("Nhận diện phụ đề hoàn thành.")
            return True
    raise Exception("Quá thời gian nhận diện phụ đề (Timeout).")

def run_text_to_speech(controller):
    logger.info("Tiến hành tạo giọng đọc cho phụ đề (Text-to-speech)...")
    
    # 1. Click timeline to select subtitle clips
    rect = controller.app.BoundingRectangle
    timeline_x = int(rect.left + rect.width() / 2)
    timeline_y = int(rect.bottom - 150)
    
    logger.info("Focus vào vùng timeline...")
    pyautogui.click(timeline_x, timeline_y)
    time.sleep(0.5)
    
    logger.info("Nhấn chọn tất cả các clip sub (Ctrl+A)...")
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(1)
    
    # 2. Click Text-to-speech tab on top-right properties panel
    tts_tab = find_element_by_name(controller.app, "Text-to-speech") or find_element_by_name(controller.app, "Đọc văn bản")
    if not tts_tab:
        tts_tab = auto.ButtonControl(searchDepth=10, Name="Text-to-speech") or auto.ButtonControl(searchDepth=10, Name="Đọc văn bản")
    if not tts_tab:
        raise Exception("Không tìm thấy Tab 'Text-to-speech' / 'Đọc văn bản' ở bảng thuộc tính bên phải!")
    logger.info("Nhấp chọn tab 'Text-to-speech'...")
    tts_tab.Click()
    time.sleep(1.5)
    
    # 3. Choose Favorites tab (Star icon)
    fav_btn = find_element_by_name(controller.app, "Favorites") or find_element_by_name(controller.app, "Yêu thích")
    if not fav_btn:
        fav_btn = auto.ButtonControl(searchDepth=12, Name="Favorites") or auto.ButtonControl(searchDepth=12, Name="Yêu thích")
    if fav_btn:
        logger.info("Nhấp chọn mục Yêu thích (Star)...")
        fav_btn.Click()
        time.sleep(1)
        
    # 4. Click the first voice item card
    # Offset coordinates from fav_btn
    if fav_btn:
        fav_rect = fav_btn.BoundingRectangle
        click_x = int(fav_rect.left + 35)
        click_y = int(fav_rect.bottom + 45)
    else:
        tab_rect = tts_tab.BoundingRectangle
        click_x = int(tab_rect.left + 50)
        click_y = int(tab_rect.bottom + 110)
        
    logger.info("Nhấp chọn giọng đọc đầu tiên (Giọng bé đã sao)...")
    pyautogui.click(click_x, click_y)
    time.sleep(1)
    
    # 5. Click Start reading button
    read_btn = find_element_by_name(controller.app, "Start reading") or find_element_by_name(controller.app, "Bắt đầu đọc") or find_element_by_name(controller.app, "Generate")
    if not read_btn:
        read_btn = auto.ButtonControl(searchDepth=12, Name="Start reading") or auto.ButtonControl(searchDepth=12, Name="Bắt đầu đọc")
    if not read_btn:
        raise Exception("Không tìm thấy nút 'Start reading'/'Bắt đầu đọc'!")
    logger.info("Nhấp nút 'Bắt đầu đọc'...")
    read_btn.Click()
    
    # 6. Wait for TTS generation to finish
    logger.info("Đang chuyển đổi văn bản thành giọng nói... Vui lòng đợi...")
    time.sleep(5)
    for i in range(90):
        time.sleep(1.5)
        controller.get_window()
        export_btn = find_element_by_name(controller.app, "Export") or find_element_by_name(controller.app, "Xuất")
        if export_btn and not find_element_by_name(controller.app, "speech"):
            logger.info("Tạo giọng đọc hoàn thành.")
            return True
    raise Exception("Quá thời gian tạo giọng đọc TTS (Timeout).")

def kill_capcut():
    logger.info("Đang đóng cưỡng bức CapCut để lưu cấu hình bản nháp...")
    os.system("taskkill /f /im CapCut.exe")
    time.sleep(2.5)

# --- Subtitle JSON processing ---

def translate_google(text: str, source_lang: str = "zh-CN", target_lang: str = "vi") -> str:
    try:
        import urllib.parse
        import requests
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={source_lang}&tl={target_lang}&dt=t&q={urllib.parse.quote(text)}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            res = r.json()
            translated = "".join([sentence[0] for sentence in res[0]])
            return translated
    except Exception as e:
        logger.error(f"Dịch Google thất bại cho đoạn chữ: '{text}': {str(e)}")
    return text

def patch_subtitles_in_json(draft_path, font_size=5.0, font_color=(1.0, 1.0, 0.0), font_name="HarmonyOS_Sans_SC_Regular"):
    content_path = os.path.join(draft_path, "draft_content.json")
    if not os.path.exists(content_path):
        raise FileNotFoundError(f"Không tìm thấy file draft_content.json tại {draft_path}")
        
    logger.info("Đang đọc draft_content.json để dịch và cập nhật font/màu sắc...")
    with open(content_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    texts = data.get("materials", {}).get("texts", [])
    if not texts:
        logger.warning("Không tìm thấy phụ đề nào trong bản nháp.")
        return False
        
    logger.info(f"Đang dịch {len(texts)} dòng phụ đề từ tiếng Trung sang tiếng Việt...")
    translation_cache = {}
    
    for text_mat in texts:
        content_str = text_mat.get("content")
        if not content_str:
            continue
        try:
            content_json = json.loads(content_str)
            raw_text = content_json.get("text", "")
            if not raw_text:
                continue
                
            if raw_text not in translation_cache:
                translated = translate_google(raw_text, "zh-CN", "vi")
                translation_cache[raw_text] = translated
            else:
                translated = translation_cache[raw_text]
                
            content_json["text"] = translated
            
            # Styles update
            if "styles" in content_json and len(content_json["styles"]) > 0:
                style = content_json["styles"][0]
                style["range"] = [0, len(translated)]
                style["size"] = font_size
                
                # Fill color
                if "fill" not in style:
                    style["fill"] = {}
                if "content" not in style["fill"]:
                    style["fill"]["content"] = {}
                style["fill"]["content"]["render_type"] = "solid"
                style["fill"]["content"]["solid"] = {
                    "alpha": 1.0,
                    "color": list(font_color)
                }
                
                # Font path
                style["font"] = {
                    "id": "system_font",
                    "path": f"C:/{font_name}.ttf"
                }
                
            text_mat["content"] = json.dumps(content_json, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Lỗi xử lý dịch: {str(e)}")
            
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    logger.info("Đã dịch phụ đề và định dạng màu vàng cỡ chữ 5 thành công.")
    return True

# --- Audio JSON speed processing ---

def patch_audio_speed_in_json(draft_path, target_speed=1.17):
    content_path = os.path.join(draft_path, "draft_content.json")
    if not os.path.exists(content_path):
        raise FileNotFoundError(f"Không tìm thấy file draft_content.json tại {draft_path}")
        
    logger.info("Đang đọc draft_content.json để tăng tốc độ âm thanh...")
    with open(content_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    tracks = data.get("tracks", [])
    speeds = data.get("materials", {}).get("speeds", [])
    
    updated_count = 0
    audio_speed_ids = set()
    
    for track in tracks:
        if track.get("type") == "audio":
            segments = track.get("segments", [])
            for seg in segments:
                seg["speed"] = target_speed
                
                # Adjust time-range duration of clip
                target_tr = seg.get("target_timerange", {})
                source_tr = seg.get("source_timerange", {})
                
                orig_duration = source_tr.get("duration", target_tr.get("duration", 0))
                new_duration = int(orig_duration / target_speed)
                
                target_tr["duration"] = new_duration
                
                for ref in seg.get("extra_material_refs", []):
                    audio_speed_ids.add(ref)
                updated_count += 1
                
    if updated_count == 0:
        logger.warning("Không tìm thấy tệp âm thanh nào trong audio track để tăng tốc.")
        return False
        
    # Update Speed materials
    updated_speed_objs = 0
    for speed_obj in speeds:
        if speed_obj.get("id") in audio_speed_ids:
            speed_obj["speed"] = target_speed
            updated_speed_objs += 1
            
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    logger.info(f"Đã hoàn thành tăng tốc độ giọng đọc TTS lên {target_speed} ({updated_count} đoạn).")
    return True

# --- Background Task Queue Thread-safe Processor ---

class QueueRunner:
    def __init__(self):
        self.queue = []
        self.is_processing = False
        self.current_index = -1
        self.pause_requested = False
        self.thread = None
        self.config = {}

    def get_state(self):
        return {
            "queue": self.queue,
            "is_processing": self.is_processing,
            "current_index": self.current_index
        }

    def set_queue(self, videos):
        if self.is_processing:
            return
        self.queue = [{"video": v, "status": "pending", "progress": 0, "message": "Đang chờ..."} for v in videos]

    def start(self, config):
        if self.is_processing:
            return
        self.config = config
        for item in self.queue:
            if item["status"] != "success":
                item["status"] = "pending"
                item["progress"] = 0
                item["message"] = "Đang chờ..."
        self.pause_requested = False
        self.is_processing = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def pause(self):
        self.pause_requested = True

    def clear(self):
        if self.is_processing:
            return
        self.queue = []
        self.current_index = -1

    def _run_loop(self):
        import ctypes
        ctypes.windll.ole32.CoInitialize(None)
        logger.info("Bắt đầu xử lý hàng chờ video...")
        try:
            while True:
                if self.pause_requested:
                    logger.info("Đã tạm dừng hàng chờ video.")
                    break
                    
                # Find the first pending item
                pending_item = None
                pending_idx = -1
                for i, item in enumerate(self.queue):
                    if item["status"] == "pending":
                        pending_item = item
                        pending_idx = i
                        break
                
                if pending_item is None:
                    break
                    
                self.current_index = pending_idx
                pending_item["status"] = "running"
                pending_item["progress"] = 5
                pending_item["message"] = "Đang xử lý..."
                
                try:
                    self._process_item(pending_item)
                    pending_item["status"] = "success"
                    pending_item["progress"] = 100
                    pending_item["message"] = "Hoàn thành!"
                except Exception as e:
                    logger.error(f"Lỗi khi tự động hóa video '{pending_item['video']}': {str(e)}")
                    pending_item["status"] = "failed"
                    pending_item["message"] = f"Lỗi: {str(e)}"
        finally:
            self.is_processing = False
            self.current_index = -1
            ctypes.windll.ole32.CoUninitialize()
            logger.info("Quá trình chạy hàng chờ hoàn tất.")

    def _process_item(self, item):
        is_existing_project = item.get("type") == "project"
        draft_id = item.get("draft_id")
        
        # Determine config for this item (either item-specific or runner global config)
        item_config = item.get("config") or self.config or {}
        
        speed = float(item_config.get("speed", 0.77))
        volume_db = float(item_config.get("volume_db", -15.5))
        tts_speed = float(item_config.get("tts_speed", 1.17))
        font_size = float(item_config.get("font_size", 5.0))
        font_color_hex = item_config.get("font_color", "#FFFF00")
        font_name = item_config.get("font_name", "HarmonyOS_Sans_SC_Regular")

        configured_video_path = item_config.get("video_path")
        if configured_video_path:
            item["video"] = configured_video_path
            is_existing_project = False
            logger.info(f"Project has video_path config; forcing Step 1 video patch into draft {draft_id}: {configured_video_path}")
        
        # Convert hex color to RGB normalized float tuple (R, G, B)
        try:
            hex_val = font_color_hex.lstrip('#')
            r = int(hex_val[0:2], 16) / 255.0
            g = int(hex_val[2:4], 16) / 255.0
            b = int(hex_val[4:6], 16) / 255.0
            font_color_rgb = (r, g, b)
        except Exception:
            font_color_rgb = (1.0, 1.0, 0.0) # default yellow
            
        if is_existing_project:
            video_name = item["video"]
            logger.info(f"=== BẮT ĐẦU AUTOMATION CHO DỰ ÁN CÓ SẴN: {video_name} ({draft_id}) ===")
            clean_name = "".join([c if c.isalnum() else "_" for c in video_name])
            
            # Step 1 is skipped
            item["progress"] = 15
            item["message"] = "Bước 1: Bỏ qua (Dự án đã tồn tại)..."
            time.sleep(1)
        else:
            video_path = item["video"]
            logger.info(f"=== BẮT ĐẦU AUTOMATION TẠO DỰ ÁN MỚI CHO VIDEO: {video_path} ===")
            
            # Step 1: Run background pipeline to load video
            item["progress"] = 10
            item["message"] = "Bước 1: Khởi tạo dự án & load video..."
            
            video_name = os.path.basename(video_path)
            clean_name = "".join([c if c.isalnum() else "_" for c in os.path.splitext(video_name)[0]])
            if not draft_id:
                draft_id = f"auto_{clean_name[:20]}"
                item["draft_id"] = draft_id
            
            volume = 10.0 ** (volume_db / 20.0)
            
            from capcut_pipeline import run_pipeline
            
            logger.info(f"Chạy pipeline ngầm để tạo draft '{draft_id}'...")
            run_pipeline(
                video=Path(video_path),
                capcut_drafts=Path(DEFAULT_CAPCUT_DRAFTS),
                srt=None,
                width=int(item_config.get("width", 1080)),
                height=int(item_config.get("height", 1920)),
                speed=speed,
                clip_seconds=None, # Process FULL video
                font=font_name,
                font_size=font_size,
                copy_to_capcut=True,
                draft_id=draft_id,
                volume=volume
            )
            
            # Save pipeline_config.json inside the newly created project folder
            try:
                new_project_folder = os.path.join(DEFAULT_CAPCUT_DRAFTS, draft_id)
                os.makedirs(new_project_folder, exist_ok=True)
                config_path = os.path.join(new_project_folder, "pipeline_config.json")
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(item_config, f, ensure_ascii=False, indent=4)
            except Exception as e:
                logger.warning(f"Không thể lưu pipeline_config cho dự án mới: {str(e)}")

        # Step 2: Open CapCut & Open Project
        item["progress"] = 25
        item["message"] = "Bước 2: Mở dự án trong CapCut..."
        controller = launch_capcut()
        open_project_in_gui(controller, draft_id)
        
        # Step 3: Auto Captions
        item["progress"] = 45
        item["message"] = "Bước 3: Đang tự động tạo phụ đề (Auto Captions)..."
        run_image_workflow("rpa_auto_captions.sample.json", "Auto Captions")
        
        # Step 4 & 5: Translate Chinese -> Vietnamese, style without closing CapCut
        item["progress"] = 60
        item["message"] = "Bước 4 & 5: Đang dịch phụ đề sang tiếng Việt, patch thẳng khi CapCut đang mở..."
        
        draft_full_path = os.path.join(DEFAULT_CAPCUT_DRAFTS, draft_id)
        patch_subtitles_in_json(
            draft_full_path,
            font_size=font_size,
            font_color=font_color_rgb,
            font_name=font_name
        )
        
        # Step 6: Text to speech on the currently open project
        item["progress"] = 75
        item["message"] = "Bước 6: Đang tạo giọng nói (TTS) cho sub trên dự án đang mở..."
        run_image_workflow("rpa_tts.sample.json", "Text to speech")
        
        # Step 7: Close, Set audio speed
        item["progress"] = 85
        item["message"] = f"Bước 7: Đang tăng tốc độ giọng đọc lên {tts_speed}..."
        kill_capcut()
        patch_audio_speed_in_json(draft_full_path, target_speed=tts_speed)
        
        # Step 8: Reopen, Export
        item["progress"] = 90
        item["message"] = "Bước 8: Đang xuất video thành phẩm..."
        controller = launch_capcut()
        open_project_in_gui(controller, draft_id)
        run_image_workflow("rpa_export.sample.json", "Export")
        
        # Step 9: Close CapCut / Done
        item["progress"] = 98
        item["message"] = "Bước 9: Đang đóng CapCut hoàn tất dự án..."
        kill_capcut()
        logger.info(f"=== ĐÃ XỬ LÝ XONG: {video_name} ===")

# Instantiate global runner
runner = QueueRunner()

# --- Flask Server Routes ---

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify(runner.get_state())

@app.route('/api/queue', methods=['POST'])
def set_queue():
    data = request.get_json() or {}
    videos = data.get("videos", [])
    runner.set_queue(videos)
    return jsonify(runner.get_state())

@app.route('/api/start', methods=['POST'])
def start_runner():
    data = request.get_json() or {}
    if "videos" in data:
        runner.set_queue(data["videos"])
    runner.start(data)
    return jsonify({"ok": True})

@app.route('/api/pause', methods=['POST'])
def pause_runner():
    runner.pause()
    return jsonify({"ok": True})

@app.route('/api/clear', methods=['POST'])
def clear_runner():
    runner.clear()
    return jsonify(runner.get_state())

@app.route('/api/select_files', methods=['POST'])
def select_files():
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        
        file_paths = filedialog.askopenfilenames(
            title="Chọn các file video",
            filetypes=[("Video files", "*.mp4 *.avi *.mkv *.mov *.flv *.ts"), ("All files", "*.*")]
        )
        root.destroy()
        return jsonify({"files": list(file_paths)})
    except Exception as e:
        logger.error(f"Lỗi khi chọn file: {str(e)}")
        return jsonify({"files": []})

@app.route('/api/select_folder', methods=['POST'])
def select_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes('-topmost', 1)
        
        folder_path = filedialog.askdirectory(title="Chọn thư mục chứa video")
        root.destroy()
        
        video_files = []
        if folder_path:
            for r, d, files in os.walk(folder_path):
                for f in files:
                    if f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.flv', '.ts')):
                        video_files.append(os.path.join(r, f))
        return jsonify({"files": video_files})
    except Exception as e:
        logger.error(f"Lỗi khi chọn thư mục: {str(e)}")
        return jsonify({"files": []})

def get_dir_size(path):
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    total += entry.stat().st_size
                elif entry.is_dir():
                    total += get_dir_size(entry.path)
    except Exception:
        pass
    return total

def format_size(size_bytes):
    if size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.1f}G"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / (1024**2):.1f}M"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f}K"
    else:
        return f"{size_bytes}B"

@app.route('/api/projects', methods=['GET'])
def list_projects():
    try:
        projects = []
        if os.path.exists(DEFAULT_CAPCUT_DRAFTS):
            for entry in os.scandir(DEFAULT_CAPCUT_DRAFTS):
                if entry.is_dir():
                    meta_path = os.path.join(entry.path, "draft_meta_info.json")
                    config_path = os.path.join(entry.path, "pipeline_config.json")
                    
                    name = entry.name
                    updated_at = 0
                    duration_str = "00:00"
                    
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, "r", encoding="utf-8") as f:
                                meta_data = json.load(f)
                                name = meta_data.get("draft_name", entry.name)
                                updated_at = meta_data.get("tm_draft_modified", 0)
                                tm_duration = meta_data.get("tm_duration", 0)
                                duration_sec = tm_duration / 1e6
                                if duration_sec >= 3600:
                                    duration_str = f"{int(duration_sec // 3600):02d}:{int((duration_sec % 3600) // 60):02d}:{int(duration_sec % 60):02d}"
                                else:
                                    duration_str = f"{int(duration_sec // 60):02d}:{int(duration_sec % 60):02d}"
                        except Exception as json_err:
                            logger.warning(f"Error reading meta for {entry.name}: {str(json_err)}")
                    
                    if updated_at == 0:
                        try:
                            updated_at = int(os.path.getmtime(entry.path) * 1000000)
                        except Exception:
                            updated_at = 0

                    has_config = os.path.exists(config_path)
                    dir_size = get_dir_size(entry.path)
                    size_str = format_size(dir_size)

                    projects.append({
                        "name": name,
                        "folder": entry.name,
                        "updated_at": updated_at,
                        "duration": duration_str,
                        "size": size_str,
                        "has_config": has_config
                    })
            
            projects.sort(key=lambda x: x["updated_at"], reverse=True)
        return jsonify({"projects": projects})
    except Exception as e:
        logger.error(f"Failed to list CapCut projects: {str(e)}")
        return jsonify({"projects": []}), 500

@app.route('/api/projects/<folder>/cover')
def get_project_cover(folder):
    folder_path = os.path.join(DEFAULT_CAPCUT_DRAFTS, folder)
    cover_path = os.path.join(folder_path, "draft_cover.jpg")
    if os.path.exists(cover_path):
        from flask import send_file
        return send_file(cover_path, mimetype='image/jpeg')
    return "", 404

@app.route('/api/projects/<folder>/config', methods=['GET', 'POST'])
def project_config(folder):
    folder_path = os.path.join(DEFAULT_CAPCUT_DRAFTS, folder)
    config_path = os.path.join(folder_path, "pipeline_config.json")
    
    if not os.path.exists(folder_path):
        return jsonify({"error": "Project folder not found"}), 404
        
    if request.method == 'POST':
        try:
            data = request.get_json() or {}
            # Keep values clean
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        default_config = {
            "speed": 0.77,
            "volume_db": -15.5,
            "tts_speed": 1.17,
            "font_size": 5.0,
            "font_color": "#FFFF00",
            "font_name": "HarmonyOS_Sans_SC_Regular",
            "video_path": ""
        }
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    saved_config = json.load(f)
                    default_config.update(saved_config)
            except Exception:
                pass
        return jsonify(default_config)

@app.route('/api/projects/create', methods=['POST'])
def create_project():
    try:
        data = request.get_json() or {}
        video_path = data.get("video_path")
        project_name = data.get("project_name")
        
        if not video_path:
            return jsonify({"error": "Video path is required"}), 400
            
        if not project_name:
            project_name = os.path.splitext(os.path.basename(video_path))[0]
            
        clean_name = "".join([c if c.isalnum() else "_" for c in project_name])
        draft_id = f"auto_{clean_name[:20]}_{int(time.time())}"
        
        project_folder = os.path.join(DEFAULT_CAPCUT_DRAFTS, draft_id)
        os.makedirs(project_folder, exist_ok=True)
        
        config_data = {
            "speed": float(data.get("speed", 0.77)),
            "volume_db": float(data.get("volume_db", -15.5)),
            "tts_speed": float(data.get("tts_speed", 1.17)),
            "font_size": float(data.get("font_size", 5.0)),
            "font_color": data.get("font_color", "#FFFF00"),
            "font_name": data.get("font_name", "HarmonyOS_Sans_SC_Regular"),
            "video_path": video_path
        }
        with open(os.path.join(project_folder, "pipeline_config.json"), "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
            
        meta_data = {
            "draft_name": project_name,
            "draft_id": draft_id,
            "tm_draft_create": int(time.time() * 1000000),
            "tm_draft_modified": int(time.time() * 1000000),
            "tm_duration": 0,
            "draft_cover": "draft_cover.jpg"
        }
        with open(os.path.join(project_folder, "draft_meta_info.json"), "w", encoding="utf-8") as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=4)
            
        return jsonify({"ok": True, "project": {
            "name": project_name,
            "folder": draft_id,
            "updated_at": meta_data["tm_draft_modified"],
            "duration": "00:00",
            "size": "0.0K",
            "has_config": True
        }})
    except Exception as e:
        logger.error(f"Failed to create project: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/queue/add', methods=['POST'])
def add_to_queue():
    try:
        data = request.get_json() or {}
        folder = data.get("folder")
        if not folder:
            return jsonify({"error": "Folder is required"}), 400
            
        folder_path = os.path.join(DEFAULT_CAPCUT_DRAFTS, folder)
        meta_path = os.path.join(folder_path, "draft_meta_info.json")
        config_path = os.path.join(folder_path, "pipeline_config.json")
        
        name = folder
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                name = json.load(f).get("draft_name", folder)
                
        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                
        item = {
            "type": "project",
            "video": name,
            "draft_id": folder,
            "project_folder": folder,
            "config": config,
            "status": "pending",
            "progress": 0,
            "message": "Đang chờ..."
        }
        
        if config.get("video_path"):
            item["type"] = "video"
            item["video"] = config.get("video_path")
            
        runner.queue.append(item)
        return jsonify(runner.get_state())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/api/test_dump')
def test_dump_uia():
    try:
        from pyJianYingDraft.capcut_controller import CapCutController
        controller = CapCutController()
        out_path = os.path.join(os.path.dirname(__file__), "scratch", "uia_tree.txt")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        
        # Use uiautomation's WalkControl instead of GetChildren
        import uiautomation as uia
        with open(out_path, "w", encoding="utf-8") as f:
            for control, depth in uia.WalkControl(controller.app, maxDepth=16):
                name = control.Name or ""
                class_name = control.ClassName or ""
                control_type = control.ControlTypeName or ""
                auto_id = control.AutomationId or ""
                rect = control.BoundingRectangle
                f.write(f"{'  '*depth}Name: '{name}' | Class: '{class_name}' | Type: '{control_type}' | AutoId: '{auto_id}' | Rect: {rect}\n")
                
        return jsonify({"ok": True, "path": out_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/test_find')
def test_find_uia():
    try:
        from pyJianYingDraft.capcut_controller import CapCutController
        controller = CapCutController()
        
        import uiautomation as uia
        results = []
        
        # Strategy 1: Walk the tree manually using WalkControl and look for '0602' or any project name
        for ctrl, depth in uia.WalkControl(controller.app, maxDepth=16):
            name = ctrl.Name or ""
            auto_id = ctrl.AutomationId or ""
            if "0602" in name or "0602" in auto_id:
                results.append({
                    "strategy": "WalkControl",
                    "depth": depth,
                    "name": name,
                    "class": ctrl.ClassName,
                    "type": ctrl.ControlTypeName,
                    "auto_id": auto_id,
                    "rect": str(ctrl.BoundingRectangle)
                })
                
        # Strategy 2: Use Native TextControl lookup
        tc = controller.app.TextControl(searchDepth=15, Name="0602")
        if tc.Exists(1):
            results.append({
                "strategy": "TextControl",
                "name": tc.Name,
                "class": tc.ClassName,
                "type": tc.ControlTypeName,
                "rect": str(tc.BoundingRectangle)
            })
            
        # Strategy 3: General Control lookup
        c = controller.app.Control(searchDepth=15, Compare=lambda ctrl, depth: "0602" in (ctrl.Name or ""))
        if c.Exists(1):
            results.append({
                "strategy": "CompareControl",
                "name": c.Name,
                "class": c.ClassName,
                "type": c.ControlTypeName,
                "rect": str(c.BoundingRectangle)
            })
            
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/api/queue/cancel', methods=['POST'])
def cancel_queue_item():
    try:
        data = request.get_json() or {}
        idx = data.get("index")
        if idx is None:
            return jsonify({"error": "Index is required"}), 400
        if 0 <= idx < len(runner.queue):
            item = runner.queue[idx]
            if item["status"] == "running":
                # Kill CapCut to break the active pyautogui RPA process
                kill_capcut()
                item["status"] = "failed"
                item["message"] = "Bị hủy bởi người dùng."
            elif item["status"] == "pending":
                item["status"] = "failed"
                item["message"] = "Đã hủy."
            return jsonify(runner.get_state())
        return jsonify({"error": "Invalid index"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/queue/retry', methods=['POST'])
def retry_queue_item():
    try:
        data = request.get_json() or {}
        idx = data.get("index")
        if idx is None:
            return jsonify({"error": "Index is required"}), 400
        if 0 <= idx < len(runner.queue):
            item = runner.queue[idx]
            item["status"] = "pending"
            item["progress"] = 0
            item["message"] = "Đang chờ..."
            
            # Start queue runner if it's currently idle
            if not runner.is_processing:
                runner.start(data)
            return jsonify(runner.get_state())
        return jsonify({"error": "Invalid index"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/test_connection', methods=['POST'])
def test_connection():
    try:
        controller = launch_capcut()
        return jsonify({
            "ok": True,
            "window": controller.app.Name,
            "status": controller.app_status
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route('/api/logs')
def get_logs():
    def log_stream():
        # Clear log queue before start
        while not sse_log_queue.empty():
            try:
                sse_log_queue.get_nowait()
            except queue.Empty:
                break
                
        while True:
            try:
                log_data = sse_log_queue.get(timeout=30)
                yield f"data: {json.dumps(log_data)}\n\n"
            except queue.Empty:
                # Keep connection alive
                yield ": keepalive\n\n"
            except Exception:
                break
    return Response(log_stream(), mimetype="text/event-stream")

if __name__ == "__main__":
    # Ensure port 5000 is used
    logger.info("Khởi động server CapCut Automation Studio tại http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)




