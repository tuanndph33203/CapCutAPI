#!/usr/bin/env python3
import os
import sys
import json
import time
import queue
import logging
import threading
import subprocess
import re
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response

# Add current dir to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import uiautomation as auto
import pyautogui

from pyJianYingDraft.capcut_controller import CapCutController, ExportResolution, ExportFramerate, capcut_process_ids, capcut_main_hwnd_and_rect
from pyJianYingDraft.exceptions import AutomationError

DEFAULT_CAPCUT_DRAFTS = os.environ.get(
    "CAPCUT_DRAFTS_DIR",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "CapCut", "User Data", "Projects", "com.lveditor.draft"),
)
FIRST_PROJECT_FALLBACK_X = 285
FIRST_PROJECT_FALLBACK_Y = 583
CAPCUT_SHORTCUT_CANDIDATES = [
    os.environ.get("CAPCUT_SHORTCUT", ""),
    os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "CapCut", "CapCut.lnk"),
    os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", "CapCut.lnk"),
    r"C:\Users\PC\Desktop\CapCut.lnk",
]

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
    for step in result.get("steps", []):
        template_name = os.path.basename(step.get("template", "")) if step.get("template") else ""
        if step.get("skipped"):
            logger.warning(
                f"RPA step {step.get('step')}: {step.get('action')} {template_name} bị bỏ qua: {step.get('error')}"
            )
        elif step.get("action") == "click_template":
            logger.info(
                f"RPA step {step.get('step')}: clicked {template_name} "
                f"score={step.get('score'):.4f} at ({step.get('x')}, {step.get('y')})"
            )
        elif step.get("action") == "sleep":
            logger.info(f"RPA step {step.get('step')}: sleep {step.get('seconds')}s")
        else:
            logger.info(f"RPA step {step.get('step')}: {step.get('action')}")
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
        shortcut = next((path for path in CAPCUT_SHORTCUT_CANDIDATES if path and os.path.exists(path)), None)
        if shortcut:
            logger.info(f"Khởi chạy CapCut từ shortcut: {shortcut}")
            subprocess.Popen(["explorer.exe", shortcut])
        else:
            logger.info("Không tìm thấy shortcut CapCut. Thử khởi chạy bằng App Execution Alias/URI...")
            try:
                subprocess.Popen(["CapCut.exe"])
            except Exception:
                subprocess.Popen(["powershell", "-NoProfile", "-Command", "Start-Process 'capcut://'"])
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
        
    try:
        from capcut_ocr_projects import click_text_above

        logger.info(f"Đang dùng OCR tìm chữ dự án '{project_name}' rồi click lên trên 0.5cm...")
        click_result = click_text_above(
            text=str(project_name),
            min_score=0.35,
            click_above_cm=0.5,
            debug_image=Path("scratch/capcut_projects_ocr_crop.png"),
            full_debug_image=Path("scratch/capcut_projects_ocr_full.png"),
        )
        logger.info(
            f"OCR đã thấy '{click_result['text']}' "
            f"(score={click_result['score']}) và click tại ({click_result['x']}, {click_result['y']})."
        )
    except Exception as e:
        logger.warning(f"OCR không mở được dự án '{project_name}': {str(e)}. Fallback click tọa độ project đầu tiên.")
        pyautogui.click(FIRST_PROJECT_FALLBACK_X, FIRST_PROJECT_FALLBACK_Y)

    logger.info("Waiting 5 seconds after project click before continuing pipeline...")
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
            return controller
            
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

def draft_json_path(draft_path):
    content_path = os.path.join(draft_path, "draft_content.json")
    if os.path.exists(content_path):
        return content_path

    info_path = os.path.join(draft_path, "draft_info.json")
    if os.path.exists(info_path):
        return info_path

    raise FileNotFoundError(f"Không tìm thấy draft_content.json hoặc draft_info.json tại {draft_path}")


def draft_json_paths(draft_path):
    root = Path(draft_path)
    candidates = []
    for path in [
        root / "draft_content.json",
        *root.glob("template-*.tmp"),
        *root.glob("Timelines/*/draft_content.json"),
        *root.glob("Timelines/*/template-*.tmp"),
    ]:
        if not path.exists() or not path.is_file():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if path not in candidates:
            candidates.append(path)

    if candidates:
        return [str(path) for path in candidates]

    return [draft_json_path(draft_path)]

def translate_google(text: str, source_lang: str = "zh-CN", target_lang: str = "vi") -> str:
    import requests

    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": source_lang,
        "tl": target_lang,
        "dt": "t",
        "q": text,
    }
    last_error = None
    for attempt in range(1, 4):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            res = r.json()
            translated = "".join(sentence[0] for sentence in res[0] if sentence and sentence[0]).strip()
            if not translated:
                raise ValueError("Google trả về bản dịch rỗng")
            if translated == text or has_source_chars(translated, source_lang):
                raise ValueError(f"Google trả về bản gốc hoặc còn ký tự nguồn: {translated}")
            return translated
        except Exception as e:
            last_error = e
            logger.warning(f"Dịch Google lần {attempt}/3 thất bại cho đoạn chữ: '{text}': {str(e)}")
            time.sleep(1.5 * attempt)

    raise RuntimeError(f"Dịch Google thất bại sau 3 lần cho đoạn chữ: '{text}': {last_error}")

def has_source_chars(text, source_lang="Chinese"):
    lang = (source_lang or "").lower()
    if "chinese" in lang or lang in {"zh", "zh-cn", "cn"}:
        return any("\u3400" <= ch <= "\u9fff" for ch in text)
    return False


def extract_subtitle_text(text_mat):
    content_str = text_mat.get("content")
    if not content_str:
        return None
    content_json = json.loads(content_str)
    return content_json.get("text", "")


def sync_text_material_fields(text_mat, content_json, translated, font_size=None, font_color=None, font_name=None):
    content_json["text"] = translated

    if "styles" in content_json and len(content_json["styles"]) > 0:
        style = content_json["styles"][0]
        style["range"] = [0, len(translated)]
        if font_size is not None:
            style["size"] = font_size

        if font_color is not None:
            if "fill" not in style:
                style["fill"] = {}
            if "content" not in style["fill"]:
                style["fill"]["content"] = {}
            style["fill"]["content"]["render_type"] = "solid"
            style["fill"]["content"]["solid"] = {
                "alpha": 1.0,
                "color": list(font_color)
            }

        if font_name:
            style["font"] = {
                "id": "system_font",
                "path": f"C:/{font_name}.ttf"
            }

    text_mat["content"] = json.dumps(content_json, ensure_ascii=False)
    text_mat["recognize_text"] = translated

    base_content_str = text_mat.get("base_content")
    if base_content_str:
        try:
            base_content = json.loads(base_content_str)
            base_content["text"] = translated
            if "styles" in base_content and len(base_content["styles"]) > 0:
                base_style = base_content["styles"][0]
                base_style["range"] = [0, len(translated)]
                if font_size is not None:
                    base_style["size"] = font_size
                if font_color is not None:
                    if "fill" not in base_style:
                        base_style["fill"] = {}
                    if "content" not in base_style["fill"]:
                        base_style["fill"]["content"] = {}
                    base_style["fill"]["content"]["render_type"] = "solid"
                    base_style["fill"]["content"]["solid"] = {
                        "alpha": 1.0,
                        "color": list(font_color)
                    }
                if font_name:
                    base_style["font"] = {
                        "id": "system_font",
                        "path": f"C:/{font_name}.ttf"
                    }
            text_mat["base_content"] = json.dumps(base_content, ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            logger.warning(f"Không parse được base_content để đồng bộ text: {str(e)}")

    words = text_mat.get("words")
    if isinstance(words, dict):
        start_times = words.get("start_time") or [0]
        end_times = words.get("end_time") or start_times
        words["start_time"] = [start_times[0]]
        words["end_time"] = [end_times[-1]]
        words["text"] = [translated]


def collect_source_strings(obj, source_lang="Chinese"):
    found = []
    if isinstance(obj, dict):
        for value in obj.values():
            found.extend(collect_source_strings(value, source_lang))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(collect_source_strings(value, source_lang))
    elif isinstance(obj, str) and has_source_chars(obj, source_lang):
        found.append(obj)
    return found


def sync_subtitle_cache_info(data, translated_texts):
    fragments = data.get("extra_info", {}).get("subtitle_fragment_info_list", [])
    text_index = 0
    updated_count = 0

    for fragment in fragments:
        cache_str = fragment.get("subtitle_cache_info")
        if not cache_str:
            continue
        try:
            cache = json.loads(cache_str)
        except Exception:
            continue

        sentence_list = cache.get("sentence_list")
        if not isinstance(sentence_list, list) or not sentence_list:
            continue

        changed = False
        for sentence in sentence_list:
            if text_index >= len(translated_texts):
                break
            translated = translated_texts[text_index]
            if not translated:
                text_index += 1
                continue

            sentence["text"] = translated
            sentence["translation_text"] = translated
            sentence["language_user_select"] = "vi"
            sentence["words"] = [{
                "start_time": sentence.get("start_time", 0),
                "end_time": sentence.get("end_time", 0),
                "text": translated,
            }]
            text_index += 1
            changed = True

        if changed:
            fragment["subtitle_cache_info"] = json.dumps(cache, ensure_ascii=False, separators=(",", ":"))
            updated_count += 1

    return updated_count


def build_ai_translation_config(item_config=None):
    item_config = item_config or {}
    method = (
        item_config.get("translation_method")
        or item_config.get("translationMethod")
        or "google"
    ).lower()

    provider = (
        item_config.get("ai_provider")
        or item_config.get("aiProvider")
        or "openai"
    ).lower()

    api_key = (
        item_config.get("ai_api_key")
        or item_config.get("apiKey")
    )

    model = (
        item_config.get("ai_model")
        or item_config.get("aiModel")
    )
    if not model:
        if provider == "gemini":
            model = "gemini-1.5-flash"
        elif provider == "anthropic":
            model = "claude-3-5-haiku-20241022"
        else:
            model = "gpt-4o-mini"

    base_url = (
        item_config.get("ai_base_url")
        or item_config.get("aiBaseUrl")
    )
    if not base_url:
        if provider == "gemini":
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        elif provider == "anthropic":
            base_url = "https://api.anthropic.com/v1"
        else:
            base_url = "https://api.openai.com/v1"

    return {
        "enabled": method == "ai" and bool(api_key),
        "method": method,
        "provider": provider,
        "api_key": api_key,
        "model": model,
        "base_url": base_url.rstrip("/"),
        "source_language": item_config.get("source_language") or item_config.get("sourceLanguage") or "Chinese",
        "target_language": item_config.get("target_language") or item_config.get("targetLanguage") or "Vietnamese",
        "tone": item_config.get("ai_tone") or item_config.get("aiTone") or "natural and fluent",
        "topic": item_config.get("video_context") or item_config.get("videoContext") or "Short fantasy game online videos, MMORPG gameplay review, PvP server war",
        "temperature": float(item_config.get("ai_temperature", item_config.get("aiTemperature", 0.0)) or 0.0),
    }


def build_ai_translation_prompt(config, ultra_short=False):
    if ultra_short:
        return (
            f"Translate given lines from {config['source_language']} to {config['target_language']}.\n"
            "Rules:\n"
            '- Output MUST be valid JSON: {"translations": ["translation_1", "translation_2", ...]}\n'
            "- The array length MUST exactly match the input line count.\n"
            "- Do not merge, omit, explain, or use markdown."
        )

    return f"""You are an expert subtitle translator from {config['source_language']} to {config['target_language']}.
Tone: {config['tone']}. Topic: {config['topic']}.

Task: Translate the given subtitle lines.
Rules:
- Output MUST be valid JSON containing an array of strings under key "translations": {{"translations": ["translation_1", "translation_2", ...]}}
- CRITICAL: The returned array length MUST exactly match the input line count.
- Keep one-to-one correspondence in the exact same order. Do NOT combine, merge, split, or omit lines.
- Translate naturally, not word-by-word.
- For Vietnamese, write pure, grammatical Vietnamese. Do not leave Chinese characters, pinyin, or unrelated English.
- Preserve names naturally; for Chinese character/location names, use natural Sino-Vietnamese when appropriate.
- No explanations, no markdown, no extra text.""".strip()


def format_ai_translation_user_message(lines, previous_context=None, next_context=None):
    prev = f"--- PREVIOUS CONTEXT ---\n{chr(10).join(previous_context)}\n\n" if previous_context else ""
    next_part = f"\n\n--- NEXT CONTEXT ---\n{chr(10).join(next_context)}" if next_context else ""
    body = "\n".join([f"Line {idx + 1}: {line['text']}" for idx, line in enumerate(lines)])
    return f"{prev}--- LINES TO TRANSLATE ---\n{body}{next_part}"


def parse_ai_translation_response(raw_text, expected_count):
    text = (raw_text or "").strip()
    candidates = [text]

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start:end + 1])

    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        candidates.append(text[start:end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                arr = parsed.get("translations")
                if not isinstance(arr, list):
                    arr = next((v for v in parsed.values() if isinstance(v, list)), None)
            elif isinstance(parsed, list):
                arr = parsed
            else:
                arr = None

            if isinstance(arr, list):
                out = []
                for i in range(expected_count):
                    if i < len(arr):
                        item = arr[i]
                        if isinstance(item, dict):
                            item = item.get("text", "")
                        out.append(str(item).strip())
                    else:
                        out.append("")
                return out
        except Exception:
            continue

    raise ValueError(f"Không parse được JSON dịch AI: {text[:180]}")


def call_ai_translation_once(lines, config, previous_context=None, next_context=None, ultra_short=False):
    import requests

    system_prompt = build_ai_translation_prompt(config, ultra_short=ultra_short)
    user_message = format_ai_translation_user_message(lines, previous_context, next_context)

    provider = config["provider"]
    if provider == "anthropic":
        url = f"{config['base_url']}/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": config["api_key"],
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": config["model"],
            "max_tokens": 8000,
            "temperature": config["temperature"],
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }
    else:
        url = f"{config['base_url']}/chat/completions"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {config['api_key']}",
        }
        payload = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": config["temperature"],
            "max_tokens": 8000,
            "stream": False,
        }

    response = requests.post(url, headers=headers, json=payload, timeout=90)
    if not response.ok:
        raise RuntimeError(f"AI translation HTTP {response.status_code}: {response.text[:500]}")

    data = response.json()
    if provider == "anthropic":
        raw = "".join(part.get("text", "") for part in data.get("content", []) if isinstance(part, dict))
    else:
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    translations = parse_ai_translation_response(raw, len(lines))
    for idx, translated in enumerate(translations):
        if not translated:
            raise ValueError(f"Dòng {idx + 1} rỗng trong kết quả AI")
        if has_source_chars(translated, config["source_language"]):
            raise ValueError(f"Dòng {idx + 1} còn ký tự nguồn: {translated}")

    return translations


def translate_ai_batch_recursive(lines, config, previous_context=None, next_context=None):
    if not lines:
        return []

    for ultra_short in (False, True):
        try:
            return call_ai_translation_once(lines, config, previous_context, next_context, ultra_short=ultra_short)
        except Exception as e:
            logger.warning(f"Dịch AI batch {len(lines)} dòng thất bại (ultra_short={ultra_short}): {str(e)}")

    if len(lines) == 1:
        logger.warning(f"Dịch AI dòng đơn thất bại, fallback Google: {lines[0]['text']}")
        return [translate_google(lines[0]["text"], "zh-CN", "vi")]

    mid = len(lines) // 2
    left = translate_ai_batch_recursive(lines[:mid], config, previous_context, next_context)
    right_context = (previous_context or []) + left
    right_context = right_context[-5:]
    right = translate_ai_batch_recursive(lines[mid:], config, right_context, next_context)
    return left + right


def translate_texts_with_ai(raw_texts, item_config=None):
    config = build_ai_translation_config(item_config)
    if not config["enabled"]:
        return None

    logger.info(f"Dịch AI bằng {config['provider']} model {config['model']} theo batch 20 dòng...")
    batch_size = 20
    context_window = 5
    translated = [None] * len(raw_texts)

    for start in range(0, len(raw_texts), batch_size):
        end = min(len(raw_texts), start + batch_size)
        batch = [{"id": str(i), "text": raw_texts[i]} for i in range(start, end)]
        prev_context = raw_texts[max(0, start - context_window):start]
        next_context = raw_texts[end:min(len(raw_texts), end + context_window)]
        batch_translations = translate_ai_batch_recursive(batch, config, prev_context, next_context)
        for offset, value in enumerate(batch_translations):
            translated[start + offset] = value
        logger.info(f"Dịch AI batch {start // batch_size + 1}: OK ({len(batch_translations)}/{len(batch)})")

    return translated


def patch_subtitles_file(content_path, font_size=5.0, font_color=(1.0, 1.0, 0.0), font_name="HarmonyOS_Sans_SC_Regular", item_config=None, translation_cache=None):
    translation_cache = translation_cache if translation_cache is not None else {}

    logger.info(f"Đang đọc {content_path} để dịch và cập nhật font/màu sắc...")
    with open(content_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    texts = data.get("materials", {}).get("texts", [])
    if not texts:
        logger.warning("Không tìm thấy phụ đề nào trong bản nháp.")
        return False
        
    parsed_items = []
    raw_texts = []
    for text_mat in texts:
        content_str = text_mat.get("content")
        if not content_str:
            continue
        try:
            content_json = json.loads(content_str)
            raw_text = content_json.get("text", "")
            if not raw_text:
                continue
            parsed_items.append((text_mat, content_json, raw_text))
            raw_texts.append(raw_text)
        except Exception as e:
            logger.error(f"Lỗi đọc text phụ đề trước khi dịch: {str(e)}")

    source_indices = [index for index, raw_text in enumerate(raw_texts) if has_source_chars(raw_text, "Chinese")]
    source_raw_texts = [raw_texts[index] for index in source_indices]
    logger.info(f"Đang dịch {len(source_raw_texts)}/{len(raw_texts)} dòng phụ đề còn tiếng Trung sang tiếng Việt...")
    ai_translations = None
    try:
        source_ai_translations = translate_texts_with_ai(source_raw_texts, item_config=item_config)
        if source_ai_translations:
            ai_translations = {}
            for offset, translated in enumerate(source_ai_translations):
                ai_translations[source_indices[offset]] = translated
    except Exception as e:
        logger.error(f"Dịch AI thất bại, fallback Google từng dòng: {str(e)}")

    failed_translations = []
    translated_count = 0
    translated_samples = []
    translated_texts = []
    for index, (text_mat, content_json, raw_text) in enumerate(parsed_items):
        try:
            if not has_source_chars(raw_text, "Chinese"):
                translated = raw_text
            elif ai_translations and index in ai_translations and ai_translations[index]:
                translated = ai_translations[index]
            elif raw_text not in translation_cache:
                translated = translate_google(raw_text, "zh-CN", "vi")
                translation_cache[raw_text] = translated
            else:
                translated = translation_cache[raw_text]

            if has_source_chars(translated, "Chinese"):
                raise ValueError(f"Bản dịch vẫn còn chữ Trung: {translated}")

            if len(translated_samples) < 3:
                translated_samples.append((raw_text, translated))
            translated_count += 1
            translated_texts.append(translated)
            sync_text_material_fields(
                text_mat,
                content_json,
                translated,
                font_size=font_size,
                font_color=font_color,
                font_name=font_name,
            )
        except Exception as e:
            logger.error(f"Lỗi xử lý dịch: {str(e)}")
            failed_translations.append(raw_text)

    if failed_translations:
        preview = ", ".join(failed_translations[:3])
        raise RuntimeError(
            f"Dừng patch phụ đề vì {len(failed_translations)} dòng chưa dịch được, tránh ghi tiếng gốc vào draft. Ví dụ: {preview}"
        )

    cache_updated = sync_subtitle_cache_info(data, translated_texts)

    remaining_source = []
    remaining_source.extend(collect_source_strings(data.get("materials", {}).get("texts", []), "Chinese"))
    remaining_source.extend(collect_source_strings(data.get("extra_info", {}).get("subtitle_fragment_info_list", []), "Chinese"))

    if remaining_source:
        preview = ", ".join(remaining_source[:3])
        raise RuntimeError(
            f"Dừng patch phụ đề vì draft vẫn còn {len(remaining_source)} dòng tiếng Trung sau dịch. Ví dụ: {preview}"
        )
            
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    for raw_sample, translated_sample in translated_samples:
        logger.info(f"Mẫu dịch: '{raw_sample}' -> '{translated_sample}'")
    logger.info(
        f"Đã dịch {translated_count}/{len(parsed_items)} dòng phụ đề, "
        f"đồng bộ {cache_updated} subtitle cache và định dạng màu vàng cỡ chữ 5 thành công."
    )
    return True


def patch_subtitles_in_json(draft_path, font_size=5.0, font_color=(1.0, 1.0, 0.0), font_name="HarmonyOS_Sans_SC_Regular", item_config=None):
    content_paths = draft_json_paths(draft_path)
    translation_cache = {}
    patched_count = 0

    for content_path in content_paths:
        patched = patch_subtitles_file(
            content_path,
            font_size=font_size,
            font_color=font_color,
            font_name=font_name,
            item_config=item_config,
            translation_cache=translation_cache,
        )
        if patched:
            patched_count += 1

    logger.info(f"Đã patch phụ đề trên {patched_count}/{len(content_paths)} file draft/timeline.")
    return patched_count > 0

def patch_track_lock_in_json(draft_path, track_types=None, locked=True):
    content_path = draft_json_path(draft_path)

    if track_types is not None:
        track_types = set(track_types)

    with open(content_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated_count = 0
    lock_bit = 4
    for track in data.get("tracks", []):
        if track_types is not None and track.get("type") not in track_types:
            continue

        current_attr = int(track.get("attribute", 0) or 0)
        new_attr = (current_attr | lock_bit) if locked else (current_attr & ~lock_bit)
        if new_attr != current_attr:
            track["attribute"] = new_attr
            updated_count += 1

    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    action = "khóa" if locked else "mở khóa"
    target = ", ".join(track_types) if track_types else "tất cả track"
    logger.info(f"Đã {action} {updated_count} track ({target}) bằng draft_content.json.")
    return updated_count

# --- Audio JSON speed processing ---

def patch_track_volume_in_json(draft_path, volume_db=-15.5, track_types=None):
    if track_types is None:
        track_types = {"video"}
    else:
        track_types = set(track_types)

    volume = 10.0 ** (float(volume_db) / 20.0)

    logger.info(f"Đang chỉnh âm lượng track {', '.join(track_types)} về {volume_db} dB ({volume:.4f})...")
    total_updated = 0
    patched_files = 0

    for content_path in draft_json_paths(draft_path):
        with open(content_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        updated_count = 0
        for track in data.get("tracks", []):
            if track.get("type") not in track_types:
                continue
            for seg in track.get("segments", []):
                seg["volume"] = volume
                seg["last_nonzero_volume"] = volume
                updated_count += 1

        if updated_count:
            with open(content_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            patched_files += 1
            total_updated += updated_count
            logger.info(f"Đã chỉnh âm lượng {updated_count} đoạn trong {content_path}.")

    logger.info(f"Đã chỉnh âm lượng tổng {total_updated} đoạn trên {patched_files} file về {volume_db} dB.")
    return total_updated


def count_audio_assets_in_json(draft_path):
    audio_segments = 0
    audio_material_ids = set()
    scanned_files = 0

    for content_path in draft_json_paths(draft_path):
        with open(content_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        scanned_files += 1

        for track in data.get("tracks", []):
            if track.get("type") == "audio":
                audio_segments += len(track.get("segments", []))

        for audio in data.get("materials", {}).get("audios", []):
            audio_id = audio.get("id") or audio.get("material_id") or json.dumps(audio, ensure_ascii=False, sort_keys=True)
            audio_material_ids.add(audio_id)

    audio_materials = len(audio_material_ids)
    return {
        "segments": audio_segments,
        "materials": audio_materials,
        "total": audio_segments + audio_materials,
        "files": scanned_files,
    }


def wait_for_new_audio_assets(draft_path, before_count, interval=5):
    last_count = before_count

    while True:
        current_count = count_audio_assets_in_json(draft_path)
        last_count = current_count
        logger.info(
            f"Kiểm tra audio TTS: audio_segments={current_count['segments']}, "
            f"audio_materials={current_count['materials']}, files={current_count.get('files', 0)}."
        )
        if current_count["total"] > before_count["total"]:
            return True, current_count
        time.sleep(interval)


def parse_video_paths(value):
    if not value:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\r\n;]+", str(value))
    return [item.strip().strip('"') for item in raw_items if item and item.strip()]


def wait_for_draft_files_unlocked(draft_path, timeout=20):
    root = Path(draft_path)
    if not root.exists():
        return True

    deadline = time.time() + timeout
    probe_files = []
    for pattern in ("assets/video/*", "draft_content.json", "Timelines/*/draft_content.json"):
        probe_files.extend([path for path in root.glob(pattern) if path.is_file()])

    while time.time() <= deadline:
        locked = []
        for path in probe_files:
            try:
                with open(path, "ab"):
                    pass
            except OSError as e:
                if getattr(e, "winerror", None) == 32:
                    locked.append(path)
        if not locked:
            return True
        logger.info(f"Đang chờ CapCut nhả khóa {len(locked)} file draft...")
        time.sleep(1)

    return False


def run_pipeline_with_file_lock_retry(run_pipeline_func, draft_full_path, max_attempts=3, **kwargs):
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            kill_capcut()
            wait_for_draft_files_unlocked(draft_full_path, timeout=20)
            if attempt > 1:
                logger.info(f"Thử patch video lại lần {attempt}/{max_attempts} sau khi nhả khóa file...")
            return run_pipeline_func(**kwargs)
        except OSError as e:
            last_error = e
            if getattr(e, "winerror", None) != 32 or attempt >= max_attempts:
                raise
            logger.warning(f"Patch video gặp WinError 32 do file đang bị khóa. Đóng CapCut và thử lại...")
            kill_capcut()
            time.sleep(3)
    raise last_error


def patch_audio_speed_in_json(draft_path, target_speed=1.17):
    logger.info(f"Đang tăng tốc độ audio TTS lên {target_speed} trên tất cả file draft/timeline...")
    total_updated = 0
    patched_files = 0

    for content_path in draft_json_paths(draft_path):
        with open(content_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        speeds = data.get("materials", {}).get("speeds", [])
        updated_count = 0
        audio_speed_ids = set()

        for track in data.get("tracks", []):
            if track.get("type") != "audio":
                continue
            for seg in track.get("segments", []):
                seg["speed"] = target_speed

                target_tr = seg.get("target_timerange", {})
                source_tr = seg.get("source_timerange", {})
                orig_duration = source_tr.get("duration", target_tr.get("duration", 0))
                if orig_duration:
                    target_tr["duration"] = int(orig_duration / target_speed)

                for ref in seg.get("extra_material_refs", []):
                    audio_speed_ids.add(ref)
                updated_count += 1

        updated_speed_objs = 0
        for speed_obj in speeds:
            if speed_obj.get("id") in audio_speed_ids:
                speed_obj["speed"] = target_speed
                updated_speed_objs += 1

        if updated_count:
            with open(content_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            patched_files += 1
            total_updated += updated_count
            logger.info(
                f"Đã tăng tốc {updated_count} đoạn audio trong {content_path} "
                f"(speed materials={updated_speed_objs})."
            )

    if total_updated == 0:
        logger.warning("Không tìm thấy audio track để tăng tốc trên các file draft/timeline.")
        return False

    logger.info(f"Đã hoàn thành tăng tốc audio TTS lên {target_speed}: {total_updated} đoạn trên {patched_files} file.")
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
                    if pending_item.get("cancel_requested"):
                        logger.info(f"Dự án '{pending_item.get('video')}' đã bị hủy, bỏ qua cập nhật trạng thái hoàn thành.")
                    else:
                        pending_item["status"] = "success"
                        pending_item["progress"] = 100
                        pending_item["message"] = "Hoàn thành!"
                except Exception as e:
                    if pending_item.get("cancel_requested"):
                        logger.info(f"Dự án '{pending_item.get('video')}' đã bị hủy.")
                        continue
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
            
            from capcut_pipeline import run_pipeline
            
            logger.info(f"Chạy pipeline ngầm để tạo draft '{draft_id}'...")
            draft_full_path = os.path.join(DEFAULT_CAPCUT_DRAFTS, draft_id)
            run_pipeline_with_file_lock_retry(
                run_pipeline,
                draft_full_path,
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
                volume=1.0
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
        draft_full_path = os.path.join(DEFAULT_CAPCUT_DRAFTS, draft_id)
        try:
            patch_track_lock_in_json(draft_full_path, track_types=["video"], locked=True)
            patch_track_lock_in_json(draft_full_path, track_types=["text", "audio"], locked=False)
        except Exception as e:
            logger.warning(f"Không thể chỉnh trạng thái khóa track trước khi mở dự án: {str(e)}")

        controller = launch_capcut()
        open_project_in_gui(controller, draft_id)
        
        # Step 3: Auto Captions
        item["progress"] = 45
        item["message"] = "Bước 3: Đang tự động tạo phụ đề (Auto Captions)..."
        run_image_workflow("rpa_auto_captions.sample.json", "Auto Captions")
        
        # Step 4 & 5: Close project, then translate Chinese -> Vietnamese and patch volume on disk
        item["progress"] = 60
        item["message"] = "Bước 4 & 5: Đang đóng CapCut để lưu draft, sau đó dịch phụ đề và chỉnh âm lượng..."
        kill_capcut()
        time.sleep(1)
        
        patch_subtitles_in_json(
            draft_full_path,
            font_size=font_size,
            font_color=font_color_rgb,
            font_name=font_name,
            item_config=item_config
        )
        patch_track_volume_in_json(draft_full_path, volume_db=volume_db, track_types=["video"])

        if item_config.get("stop_after_patch"):
            item["progress"] = 70
            item["message"] = "Đã patch bản dịch/âm lượng xong và dừng để kiểm tra draft."
            item["stopped_after_patch"] = True
            logger.info(
                f"Đã dừng pipeline sau bước patch theo cấu hình stop_after_patch=true. "
                f"Draft: {draft_full_path}"
            )
            return

        logger.info("Đợi 1 giây sau khi patch âm lượng trước khi mở lại CapCut...")
        time.sleep(1)

        item["message"] = "Bước 5.5: Đang mở lại dự án sau khi patch bản dịch và âm lượng..."
        controller = launch_capcut()
        open_project_in_gui(controller, draft_id)
        
        # Step 6: Text to speech on the currently open project
        item["progress"] = 75
        item["message"] = "Bước 6: Đang tạo giọng nói (TTS) cho sub trên dự án đang mở..."
        tts_audio_before = count_audio_assets_in_json(draft_full_path)
        logger.info(f"Trước TTS: audio_segments={tts_audio_before['segments']}, audio_materials={tts_audio_before['materials']}.")

        max_tts_attempts = int(item_config.get("tts_attempts", 3))
        tts_ready = False
        tts_audio_after = tts_audio_before

        for attempt in range(1, max_tts_attempts + 1):
            item["message"] = f"Bước 6: Đang tạo giọng nói TTS, lần {attempt}/{max_tts_attempts}..."
            logger.info(f"Chạy TTS lần {attempt}/{max_tts_attempts}...")
            if attempt == 1:
                run_image_workflow("rpa_tts.sample.json", "Text to speech")
            else:
                run_image_workflow("rpa_tts_retry.sample.json", "Text to speech retry")

            tts_ready, tts_audio_after = wait_for_new_audio_assets(
                draft_full_path,
                tts_audio_before,
                interval=int(item_config.get("tts_audio_wait_interval", 5)),
            )

            if tts_ready:
                logger.info("Đã xác nhận draft có audio TTS mới.")
                break

            if attempt < max_tts_attempts:
                logger.warning("Chưa thấy audio TTS trong draft. Giữ nguyên dự án đang mở và bấm Generate speech lần nữa...")

        if not tts_ready:
            logger.warning("Chưa thấy audio khi project đang mở. Đóng CapCut một lần để flush draft rồi kiểm tra lại...")
            kill_capcut()
            time.sleep(1)
            tts_audio_after = count_audio_assets_in_json(draft_full_path)
            logger.info(
                f"Sau khi flush draft: audio_segments={tts_audio_after['segments']}, "
                f"audio_materials={tts_audio_after['materials']}."
            )
            if tts_audio_after["total"] > tts_audio_before["total"]:
                logger.info("Đã xác nhận draft có audio TTS mới sau khi flush.")
                tts_ready = True
            else:
                raise Exception(
                    f"Không thấy audio TTS sau {max_tts_attempts} lần Generate speech "
                    f"(trước={tts_audio_before}, sau={tts_audio_after})."
                )
        else:
            logger.info("Đóng CapCut để flush draft sau khi xác nhận TTS...")
            kill_capcut()
            time.sleep(1)
        
        # Step 7: Close, Set audio speed
        item["progress"] = 85
        item["message"] = f"Bước 7: Đang tăng tốc độ giọng đọc lên {tts_speed}..."
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
            "translation_method": "google",
            "ai_provider": "openai",
            "ai_api_key": "",
            "ai_model": "gpt-4o-mini",
            "ai_base_url": "https://api.openai.com/v1",
            "source_language": "Chinese",
            "target_language": "Vietnamese",
            "ai_tone": "natural and fluent",
            "video_context": "Short fantasy game online videos, MMORPG gameplay review, PvP server war",
            "ai_temperature": 0.0,
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
            "translation_method": data.get("translation_method", "google"),
            "ai_provider": data.get("ai_provider", "openai"),
            "ai_api_key": data.get("ai_api_key", ""),
            "ai_model": data.get("ai_model", "gpt-4o-mini"),
            "ai_base_url": data.get("ai_base_url", "https://api.openai.com/v1"),
            "source_language": data.get("source_language", "Chinese"),
            "target_language": data.get("target_language", "Vietnamese"),
            "ai_tone": data.get("ai_tone", "natural and fluent"),
            "video_context": data.get("video_context", "Short fantasy game online videos, MMORPG gameplay review, PvP server war"),
            "ai_temperature": float(data.get("ai_temperature", 0.0)),
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
                
        video_paths = parse_video_paths(config.get("video_paths") or config.get("video_path"))
        if not video_paths:
            video_paths = [None]

        for index, video_path in enumerate(video_paths, start=1):
            item_config = dict(config)
            if video_path:
                item_config["video_path"] = video_path

            item = {
                "type": "project",
                "video": video_path or name,
                "draft_id": folder,
                "project_folder": folder,
                "config": item_config,
                "status": "pending",
                "progress": 0,
                "message": "Đang chờ..."
            }

            if len(video_paths) > 1:
                item["message"] = f"Đang chờ ({index}/{len(video_paths)})..."

            runner.queue.append(item)
        logger.info(f"Đã thêm {len(video_paths)} job vào hàng chờ cho dự án {folder}.")
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
                item["cancel_requested"] = True
                # Kill CapCut to break the active pyautogui RPA process
                kill_capcut()
                runner.pause_requested = True
                runner.is_processing = False
                runner.current_index = -1
            runner.queue.pop(idx)
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




