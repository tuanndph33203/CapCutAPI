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
import shutil
import socket
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response
import psutil

# Add current dir to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import uiautomation as auto
import pyautogui

from pyJianYingDraft.capcut_controller import CapCutController, ExportResolution, ExportFramerate, capcut_process_ids, capcut_main_hwnd_and_rect
from pyJianYingDraft.exceptions import AutomationError
from settings import (
    TRANSLATION_ULTRA_SHORT_PROMPT_TEMPLATE,
    TRANSLATION_SYSTEM_PROMPT_TEMPLATE,
    FULL_CONTEXT_PROMPT
)

def load_env_file():
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        os.environ[key] = val
        except Exception as e:
            print(f"Error loading .env file: {e}")

load_env_file()

def resolve_env_value(val, fallback_env_names=None):
    val = (val or "").strip()
    if val.startswith("env:"):
        var_name = val[4:].strip()
        return os.environ.get(var_name, "")
    if not val and fallback_env_names:
        for env_name in fallback_env_names:
            env_val = os.environ.get(env_name)
            if env_val:
                return env_val
    return val

def write_key_to_env_file(key_name, key_value):
    env_path = Path(__file__).resolve().parent / ".env"
    lines = []
    found = False
    
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"Error reading .env file: {e}")
            
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key_name}="):
            new_lines.append(f"{key_name}={key_value}\n")
            found = True
        else:
            new_lines.append(line)
            
    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"{key_name}={key_value}\n")
        
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"Error writing key to .env file: {e}")
        
    os.environ[key_name] = key_value

def delete_key_from_env_file(key_name):
    """Remove a key from .env file and os.environ."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = [line for line in lines if not line.strip().startswith(f"{key_name}=")]
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"Error deleting key from .env file: {e}")
    os.environ.pop(key_name, None)

DEFAULT_CAPCUT_DRAFTS = os.environ.get(
    "CAPCUT_DRAFTS_DIR",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "CapCut", "User Data", "Projects", "com.lveditor.draft"),
)
QUEUE_CACHE_PATH = Path(__file__).with_name("queue_cache.json")
FIRST_PROJECT_FALLBACK_X = 285
FIRST_PROJECT_FALLBACK_Y = 583
PROJECT_TITLE_MARKER_TEMPLATE = Path(__file__).with_name("rpa_templates") / "project_title_marker.png"
PROJECT_TITLE_MARKER_CLICK_ABOVE_CM = 1.0
PROJECT_TITLE_MARKER_DPI = 96.0
CAPCUT_SHORTCUT_CANDIDATES = [
    os.environ.get("CAPCUT_SHORTCUT", ""),
    os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "CapCut", "CapCut.lnk"),
    os.path.join(os.environ.get("USERPROFILE", ""), "Desktop", "CapCut.lnk"),
    r"C:\Users\PC\Desktop\CapCut.lnk",
]
GLOBAL_SETTINGS_PATH = Path(__file__).resolve().parent / "settings" / "global_pipeline_settings.json"

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
try:
    file_handler = logging.FileHandler(Path(__file__).with_name("capcut_gui_app.log"), encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception:
    pass

# Create Flask Application
app = Flask(__name__, template_folder="templates")

# Disable default flask access logs in SSE stream to avoid cluttering
log_werkzeug = logging.getLogger('werkzeug')
log_werkzeug.setLevel(logging.WARNING)

def ensure_control_overlay_running():
    if str(os.environ.get("CAPCUT_DISABLE_OVERLAY", "")).lower() in {"1", "true", "yes", "on"}:
        return
    try:
        script_path = Path(__file__).resolve().parent / "tools" / "pipeline_control_overlay.py"
        if not script_path.exists():
            return
        for proc in psutil.process_iter(["name", "cmdline"]):
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if "pipeline_control_overlay.py" in cmdline:
                return
        subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(Path(__file__).resolve().parent),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        logger.info("Đã bật overlay điều khiển pipeline.")
    except Exception as exc:
        logger.warning(f"Không bật được overlay điều khiển pipeline: {exc}")

# --- Helper RPA Functions ---

def run_image_workflow(config_name, label, attempts=3, retry_delay=3):
    """Run an OpenCV/PyAutoGUI workflow from JSON."""
    from capcut_rpa import run_workflow

    workflow_path = Path(__file__).resolve().parent / config_name
    attempts = max(1, int(attempts or 1))
    last_exc = None

    for attempt in range(1, attempts + 1):
        logger.info(
            f"Chạy workflow nhận diện ảnh: {label} ({workflow_path.name}) "
            f"lần {attempt}/{attempts}"
        )
        try:
            logger.info(f"Bắt đầu run_workflow: {workflow_path}")
            result = run_workflow(workflow_path, dry_run=False)
            logger.info(f"run_workflow hoàn tất: {workflow_path.name}")
            break
        except BaseException as exc:
            last_exc = exc
            logger.warning(
                f"Workflow ảnh {label} lỗi lần {attempt}/{attempts}: "
                f"{type(exc).__name__}: {exc}"
            )
            try:
                debug_path = Path(__file__).with_name(f"debug_{workflow_path.stem}_attempt_{attempt}.png")
                from capcut_rpa import find_capcut_window, screenshot_window
                import cv2

                window = find_capcut_window()
                cv2.imwrite(str(debug_path), screenshot_window(window))
                logger.info(f"Đã lưu ảnh debug workflow lỗi: {debug_path}")
            except Exception as debug_exc:
                logger.warning(f"Không lưu được ảnh debug workflow lỗi: {debug_exc}")
            if attempt < attempts:
                logger.info(f"Đợi {retry_delay}s rồi nhận diện lại workflow {label}...")
                time.sleep(retry_delay)
                continue
            logger.exception(
                f"Workflow ảnh {label} thất bại sau {attempts} lần; "
                "đánh dấu item hiện tại lỗi rồi chuyển item kế tiếp."
            )
            raise last_exc

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

VIDEO_EXPORT_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}

def get_export_scan_dirs(video_path=None, item_config=None):
    """Return likely folders where CapCut may write exported videos."""
    dirs = []
    item_config = item_config or {}

    for configured in [
        item_config.get("export_scan_dir"),
        item_config.get("export_dir"),
        os.environ.get("CAPCUT_EXPORT_SCAN_DIRS", ""),
    ]:
        if not configured:
            continue
        for part in str(configured).split(";"):
            if part.strip():
                dirs.append(Path(part.strip()))

    user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    dirs.extend([
        user_profile / "Videos",
    ])

    seen = set()
    result = []
    for d in dirs:
        try:
            resolved = d.expanduser().resolve()
        except Exception:
            continue
        if resolved in seen or not resolved.exists() or not resolved.is_dir():
            continue
        seen.add(resolved)
        result.append(resolved)
    return result

def snapshot_video_files(scan_dirs):
    snapshot = {}
    for folder in scan_dirs:
        try:
            candidates = list(folder.iterdir())
        except Exception:
            continue
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXPORT_EXTENSIONS:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            snapshot[str(path.resolve()).lower()] = (stat.st_mtime, stat.st_size)
    return snapshot

def wait_until_file_stable(path, stable_checks=3, interval=2, timeout=120):
    deadline = time.time() + timeout
    last_size = None
    stable_count = 0
    while time.time() < deadline:
        try:
            size = path.stat().st_size
        except OSError:
            time.sleep(interval)
            continue
        if size > 0 and size == last_size:
            stable_count += 1
            if stable_count >= stable_checks:
                return True
        else:
            stable_count = 0
            last_size = size
        time.sleep(interval)
    return False

def unique_output_path(folder, stem, suffix=".mp4"):
    candidate = folder / f"{stem}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = folder / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate

def safe_ascii_stem(value, fallback="export"):
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or ""))
    ascii_name = re.sub(r"_+", "_", ascii_name).strip("._-")
    return ascii_name or fallback

def has_non_ascii(value):
    return any(ord(ch) > 127 for ch in str(value or ""))

def replace_file_with_retry(source, target, attempts=8, interval=2):
    last_error = None
    expected_size = source.stat().st_size
    for attempt in range(1, attempts + 1):
        try:
            os.replace(str(source), str(target))
            if not target.exists() or target.stat().st_size != expected_size:
                raise OSError(f"Move xong nhưng file đích không hợp lệ: {target}")
            return True
        except OSError as exc:
            last_error = exc
            if attempt == attempts:
                break
            logger.warning(
                f"Chưa chuyển được file export do Windows còn giữ file "
                f"(lần {attempt}/{attempts}): {exc}. Đợi {interval}s rồi thử lại..."
            )
            time.sleep(interval)
    logger.warning(f"Không move được file export sau {attempts} lần, thử copy thay vì move: {last_error}")
    shutil.copy2(str(source), str(target))
    if target.exists() and target.stat().st_size == expected_size:
        try:
            source.unlink()
        except OSError as exc:
            logger.warning(f"Đã copy export sang đích nhưng chưa xóa được file gốc '{source}': {exc}")
        return True
    raise OSError(
        f"Copy export không hợp lệ: source={source} size={expected_size}, "
        f"target={target} exists={target.exists()} size={target.stat().st_size if target.exists() else 0}"
    )

def move_latest_export_to_source_folder(video_path, before_snapshot, item_config=None, timeout=180, cancel_check=None):
    if not video_path:
        logger.warning("Không có video_path nên không thể xác định folder xuất theo video gốc.")
        return None

    source_video = Path(video_path)
    output_dir = Path(item_config.get("export_dir") or source_video.parent)
    output_dir.mkdir(parents=True, exist_ok=True)

    scan_dirs = get_export_scan_dirs(video_path, item_config)
    deadline = time.time() + timeout
    newest = None

    while time.time() < deadline:
        if cancel_check:
            cancel_check()
        after_snapshot = snapshot_video_files(scan_dirs)
        changed = []
        for key, value in after_snapshot.items():
            old = before_snapshot.get(key)
            if old is None or old != value:
                changed.append((key, value))

        if changed:
            newest_key, _ = max(changed, key=lambda item: item[1][0])
            newest = Path(newest_key)
            break
        time.sleep(2)

    if not newest:
        logger.warning("Không tìm thấy file video export mới để chuyển về folder video gốc.")
        return None

    if not wait_until_file_stable(newest):
        logger.warning(f"File export chưa ổn định kích thước sau khi chờ: {newest}")
        return None

    suffix = newest.suffix.lower() if newest.suffix.lower() in VIDEO_EXPORT_EXTENSIONS else ".mp4"
    template = str(item_config.get("export_filename_template") or "{source_stem}_vi")
    stem = template.format(
        source_stem=source_video.stem,
        project=item_config.get("project_name") or source_video.stem,
        date=time.strftime("%Y%m%d"),
        time=time.strftime("%H%M%S"),
    )
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .") or f"{source_video.stem}_vi"
    target = unique_output_path(output_dir, stem, suffix)
    logger.info(f"File export mới phát hiện: {newest} ({newest.stat().st_size} bytes). Đích yêu cầu: {target}")

    if newest.resolve() == target.resolve():
        if target.exists() and target.parent.resolve() == output_dir.resolve() and target.stat().st_size > 0:
            logger.info(f"File export đã nằm đúng vị trí: {target}")
            return str(target)
        raise RuntimeError(f"File export trùng đường dẫn đích nhưng không hợp lệ: {target}")

    try:
        replace_file_with_retry(newest, target)
        if not target.exists() or target.parent.resolve() != output_dir.resolve():
            raise RuntimeError(f"Không xác minh được file đích sau move/copy: {target}")
        logger.info(f"Đã chuyển file export về folder video gốc: {target} ({target.stat().st_size} bytes)")
        return str(target)
    except OSError as exc:
        raise RuntimeError(
            f"Không thể move/copy file export sang thư mục video gốc '{output_dir}' với tên '{target.name}': {exc}. "
            f"File CapCut đã xuất vẫn nằm tại: {newest}. "
            "Hãy Allow app python.exe trong Windows Security > Protected folder access rồi bấm Thử lại."
        )

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

def launch_capcut(connect_ui=True, cancel_check=None):
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
            if cancel_check:
                cancel_check()
            time.sleep(0.5)
            if capcut_main_hwnd_and_rect() is not None:
                break

    if not connect_ui:
        hwnd_and_rect = capcut_main_hwnd_and_rect()
        if hwnd_and_rect is None:
            raise Exception("Không tìm thấy cửa sổ CapCut sau khi khởi động.")
        try:
            import win32gui
            hwnd, _ = hwnd_and_rect
            win32gui.ShowWindow(hwnd, 5)
            win32gui.SetForegroundWindow(hwnd)
        except Exception as e:
            logger.warning(f"Không activate được cửa sổ CapCut bằng Win32, workflow ảnh vẫn sẽ tự tìm cửa sổ: {e}")
        logger.info("Đã sẵn sàng cửa sổ CapCut cho workflow nhận diện ảnh.")
        return None

    # Wait for window and connect controller
    logger.info("Đang kết nối với cửa sổ CapCut...")
    for i in range(25):
        if cancel_check:
            cancel_check()
        try:
            controller = CapCutController()
            if controller.app and controller.app.Exists(0):
                logger.info(f"Đã kết nối thành công tới cửa sổ CapCut (Trạng thái: {controller.app_status})")
                return controller
        except Exception as e:
            logger.warning(f"Lần thử {i+1}/25 kết nối với CapCut thất bại: {str(e)}")
        time.sleep(1)
    raise Exception("Không thể kết nối với cửa sổ CapCut. Vui lòng mở CapCut thủ công trước.")

def activate_capcut_for_image_workflow():
    hwnd_and_rect = capcut_main_hwnd_and_rect()
    if hwnd_and_rect is None:
        return False

    hwnd, _ = hwnd_and_rect
    try:
        import win32con
        import win32gui
        import win32process

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    f"$ws=New-Object -ComObject WScript.Shell; $null=$ws.AppActivate({int(pid)})",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except Exception:
            pass

        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
        )
        time.sleep(0.15)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception as e:
            logger.warning(f"Không SetForegroundWindow được cho CapCut, vẫn giữ TOPMOST để workflow ảnh thấy cửa sổ: {e}")
        time.sleep(0.5)
        return True
    except Exception as e:
        logger.warning(f"Không đưa được CapCut lên foreground bằng Win32/AppActivate: {e}")
        return False

def is_project_editor_visible(controller, project_name):
    if controller is None:
        return False
    try:
        controller.app.SetActive()
        controller.app.SetTopmost()
    except Exception:
        pass
    try:
        controller.get_window()
        if getattr(controller, "app_status", "") in ("edit", "pre_export"):
            logger.info("CapCut dang o man hinh editor, bo qua buoc tim/click project tren home.")
            return True
    except Exception:
        pass
    try:
        project_label = find_element_by_name(controller.app, str(project_name))
        export_btn = find_element_by_name(controller.app, "Export") or find_element_by_name(controller.app, "Xuất")
        if project_label and export_btn:
            logger.info(f"CapCut da mo dung project '{project_name}' trong editor.")
            return True
    except Exception:
        pass
    return False



def capcut_window_title_contains(project_name):
    try:
        from capcut_rpa import find_capcut_window

        window = find_capcut_window()
        return str(project_name).lower() in (window.title or "").lower()
    except Exception:
        return False

def open_project_in_gui(controller, project_name, cancel_check=None):
    logger.info(f"Opening CapCut project '{project_name}'...")
    if is_project_editor_visible(controller, project_name):
        return controller
    if controller is not None:
        try:
            controller.app.SetActive()
            controller.app.SetTopmost()
            controller.get_window()
            if getattr(controller, "app_status", "") in ("edit", "pre_export"):
                logger.info("CapCut đã ở màn hình editor, bỏ qua bước tìm/click project trên home.")
                return controller
            export_btn = find_element_by_name(controller.app, "Export") or find_element_by_name(controller.app, "Xuất")
            if export_btn:
                logger.info("CapCut đang mở sẵn dự án khác. Đóng CapCut để về màn hình chính...")
                kill_capcut()
                controller = launch_capcut(cancel_check=cancel_check)
                time.sleep(2)
        except Exception as e:
            logger.warning(f"UIAutomation project check failed; using image workflow: {e}")

    try:
        from capcut_rpa import click_template

        click_above_px = -int(PROJECT_TITLE_MARKER_CLICK_ABOVE_CM / 2.54 * PROJECT_TITLE_MARKER_DPI)
        logger.info(
            f"Đang dùng ảnh {PROJECT_TITLE_MARKER_TEMPLATE.name} để mở dự án, "
            f"click lên trên {PROJECT_TITLE_MARKER_CLICK_ABOVE_CM}cm ở giữa ảnh..."
        )
        click_result = click_template(
            PROJECT_TITLE_MARKER_TEMPLATE,
            threshold=0.82,
            dry_run=False,
            timeout=90,
            click_offset_y=click_above_px,
            search_region=[0.0, 0.12, 1.0, 0.85],
        )
        logger.info(
            f"Đã thấy template project marker score={click_result['score']:.4f} "
            f"và click tại ({click_result['x']}, {click_result['y']})."
        )
    except Exception as e:
        if is_project_editor_visible(controller, project_name) or capcut_window_title_contains(project_name):
            logger.warning(
                f"Template project marker khong match, nhung project '{project_name}' dang mo trong editor; tiep tuc workflow."
            )
            return controller
        raise Exception(
            f"Khong mo duoc project '{project_name}' bang template anh {PROJECT_TITLE_MARKER_TEMPLATE}. "
            f"Da chan fallback sang project dau tien. Chi tiet: {str(e)}."
        ) from e

    logger.info("Clicked project marker. Continue workflow.")
    return controller

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

DEFAULT_SUBTITLE_FONT_PATH = "C:/Users/nguye/AppData/Local/CapCut/Apps/8.9.1.3802/Resources/Font/SystemFont/en.ttf"
DEFAULT_SUBTITLE_COLOR_HEX = "#f0ff00"
DEFAULT_SUBTITLE_COLOR_RGB = (0.9411764740943909, 1.0, 0.0)
DEFAULT_SUBTITLE_STROKE_RGB = (0.0, 0.0, 0.0)
DEFAULT_SUBTITLE_BORDER_WIDTH = 0.08
DEFAULT_SUBTITLE_STROKE_WIDTH = 0.05999999865889549

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
        root / "draft_info.json",
        *root.glob("template-*.tmp"),
        *root.glob("Timelines/*/draft_content.json"),
        *root.glob("Timelines/*/draft_info.json"),
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

def count_subtitle_text_items_in_json(draft_path):
    text_materials = 0
    text_segments = 0
    scanned_files = 0
    for content_path in draft_json_paths(draft_path):
        try:
            data = json.loads(Path(content_path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        scanned_files += 1
        materials = data.get("materials") or {}
        texts = materials.get("texts") or []
        if isinstance(texts, list):
            text_materials += sum(1 for item in texts if isinstance(item, dict))
        for track in data.get("tracks") or []:
            if not isinstance(track, dict) or track.get("type") != "text":
                continue
            segments = track.get("segments") or []
            if isinstance(segments, list):
                text_segments += sum(1 for item in segments if isinstance(item, dict))
    return {
        "materials": text_materials,
        "segments": text_segments,
        "total": text_materials + text_segments,
        "files": scanned_files,
    }

def config_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}

def should_use_local_whisper(item_config):
    if "use_local_whisper" in item_config:
        return config_bool(item_config.get("use_local_whisper"), True)
    if "use_whisper_captions" in item_config:
        return config_bool(item_config.get("use_whisper_captions"), True)
    return config_bool(os.environ.get("CAPCUT_USE_LOCAL_WHISPER"), True)

def run_local_whisper_captions_for_draft(draft_full_path, draft_id, video_path, item_config, font_name, font_size, font_color_hex):
    from local_whisper_captions import patch_draft_with_local_whisper

    language = (
        item_config.get("whisper_language")
        or item_config.get("source_language_code")
        or item_config.get("source_lang")
        or "zh"
    )
    logger.info(
        f"Chạy local faster-whisper GPU để tạo phụ đề: draft={draft_id}, "
        f"language={language}, video={video_path}"
    )
    result = patch_draft_with_local_whisper(
        draft_path=draft_full_path,
        draft_id=draft_id,
        video_path=video_path,
        repo_root=Path(__file__).resolve().parent,
        language=language,
        speed=float(item_config.get("speed", 1.0) or 1.0),
        font=normalize_draft_font_name(font_name),
        font_size=font_size,
        font_color=font_color_hex,
        width=int(item_config.get("canvas_width", item_config.get("width", 1920))),
        height=int(item_config.get("canvas_height", item_config.get("height", 1080))),
        progress_callback=lambda message: logger.info(f"Whisper local: {message}"),
    )
    logger.info(
        f"Đã patch phụ đề Whisper local vào draft: segments={result['segments']}, "
        f"added_texts={result['added_texts']}, srt={result['srt_path']}"
    )
    return result

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

KNOWN_SOURCE_TERM_REPLACEMENTS = {
    "阁下": "các hạ",
    "阁 下": "các hạ",
    "赤岳城": "thành Xích Nhạc",
    "赤岳": "Xích Nhạc",
    "道友": "đạo hữu",
    "师尊": "sư tôn",
    "师父": "sư phụ",
    "师傅": "sư phụ",
    "师兄": "sư huynh",
    "师姐": "sư tỷ",
    "师弟": "sư đệ",
    "师妹": "sư muội",
    "宗门": "tông môn",
    "长老": "trưởng lão",
    "城主": "thành chủ",
    "一路过关斩将": "một đường vượt ải chém tướng",
    "过关斩将": "vượt ải chém tướng",
}

def repair_known_source_terms(text):
    repaired = str(text or "")
    for source, target in sorted(KNOWN_SOURCE_TERM_REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True):
        repaired = repaired.replace(source, target)
    repaired = re.sub(r"阁\s*hạ", "các hạ", repaired, flags=re.IGNORECASE)
    return repaired

def extract_subtitle_text(text_mat):
    content_str = text_mat.get("content")
    if not content_str:
        return None
    content_json = json.loads(content_str)
    return content_json.get("text", "")

def resolve_font_path(font_name=None):
    if not font_name:
        return DEFAULT_SUBTITLE_FONT_PATH
    font_name = str(font_name).strip()
    if "/" in font_name or "\\" in font_name or font_name.lower().endswith(".ttf"):
        return font_name.replace("\\", "/")
    return DEFAULT_SUBTITLE_FONT_PATH

def normalize_draft_font_name(font_name=None):
    if not font_name:
        return "HarmonyOS_Sans_SC_Regular"
    font_value = str(font_name).strip()
    if not font_value:
        return "HarmonyOS_Sans_SC_Regular"
    if "/" in font_value or "\\" in font_value or font_value.lower().endswith((".ttf", ".otf")):
        return "HarmonyOS_Sans_SC_Regular"
    return font_value

def apply_default_text_style_to_content(content_json, translated, font_size=None, font_color=None, font_name=None):
    if "styles" not in content_json or not content_json["styles"]:
        content_json["styles"] = [{}]

    style = content_json["styles"][0]
    style["range"] = [0, len(translated)]
    if font_size is not None:
        style["size"] = font_size
    style["font"] = {
        "id": "",
        "path": resolve_font_path(font_name),
    }

    fill_color = list(font_color if font_color is not None else DEFAULT_SUBTITLE_COLOR_RGB)
    style["fill"] = {
        "alpha": 1.0,
        "content": {
            "render_type": "solid",
            "solid": {
                "alpha": 1.0,
                "color": fill_color,
            },
        },
    }
    style["strokes"] = [{
        "alpha": 1.0,
        "content": {
            "render_type": "solid",
            "solid": {
                "alpha": 1.0,
                "color": list(DEFAULT_SUBTITLE_STROKE_RGB),
            },
        },
        "width": DEFAULT_SUBTITLE_STROKE_WIDTH,
    }]
    style["useLetterColor"] = True
    return content_json

def sync_text_material_fields(text_mat, content_json, translated, font_size=None, font_color=None, font_name=None):
    content_json["text"] = translated
    apply_default_text_style_to_content(content_json, translated, font_size, font_color, font_name)

    text_mat["content"] = json.dumps(content_json, ensure_ascii=False)
    text_mat["recognize_text"] = translated
    text_mat["text_color"] = DEFAULT_SUBTITLE_COLOR_HEX
    text_mat["font_size"] = font_size
    text_mat["font_path"] = resolve_font_path(font_name)
    text_mat["font_name"] = ""
    text_mat["border_color"] = "#000000"
    text_mat["border_alpha"] = 1.0
    text_mat["border_width"] = DEFAULT_SUBTITLE_BORDER_WIDTH
    text_mat["border_mode"] = 0
    text_mat["has_shadow"] = False
    text_mat["background_color"] = "#000000"
    text_mat["background_style"] = 0

    base_content_str = text_mat.get("base_content")
    if base_content_str:
        try:
            base_content = json.loads(base_content_str)
            base_content["text"] = translated
            apply_default_text_style_to_content(base_content, translated, font_size, font_color, font_name)
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
    extra_info = data.get("extra_info") or {}
    fragments = extra_info.get("subtitle_fragment_info_list") or []
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

def normalize_ai_base_url(base_url):
    base_url = (base_url or "").strip().rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    if base_url.endswith("/messages"):
        base_url = base_url[: -len("/messages")]
    return base_url

def default_global_settings():
    default_profile = {
        "id": "gemma-default",
        "label": "GEMMA",
        "provider": "openai",
        "api_key": "env:GEMMA_API_KEY",
        "model": "google/gemma-4-31b-it",
        "base_url": "https://integrate.api.nvidia.com/v1",
    }
    return {
        "ai_provider": default_profile["provider"],
        "ai_api_key": default_profile["api_key"],
        "ai_model": default_profile["model"],
        "ai_base_url": default_profile["base_url"],
        "ai_profiles": [default_profile],
        "default_translation_ai_profile_id": default_profile["id"],
        "default_context_ai_profile_id": default_profile["id"],
        "openreel_api_key": "",
        "openreel_reference_keys": "",
    }

def default_ai_model_for_provider(provider):
    provider = (provider or "openai").strip().lower()
    if provider == "gemini":
        return "gemini-1.5-flash"
    if provider == "anthropic":
        return "claude-3-5-haiku-20241022"
    return "gpt-4o-mini"

def default_ai_base_url_for_provider(provider):
    provider = (provider or "openai").strip().lower()
    if provider == "gemini":
        return "https://generativelanguage.googleapis.com/v1beta/interactions"
    if provider == "anthropic":
        return "https://api.anthropic.com/v1"
    return "https://api.openai.com/v1"

def slugify_profile_id(value, fallback="custom-ai"):
    raw = str(value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or fallback

def sanitize_ai_profile(profile, fallback_index=0):
    source = profile if isinstance(profile, dict) else {}
    provider = (source.get("provider") or source.get("ai_provider") or "openai").strip().lower()
    model = (source.get("model") or source.get("ai_model") or default_ai_model_for_provider(provider)).strip()
    base_url = normalize_ai_base_url(
        source.get("base_url") or source.get("ai_base_url") or default_ai_base_url_for_provider(provider)
    )
    label = (
        source.get("label")
        or source.get("name")
        or source.get("title")
        or f"{provider.title()} {fallback_index + 1}"
    ).strip()
    profile_id = slugify_profile_id(
        source.get("id") or source.get("key") or source.get("slug") or label,
        fallback=f"custom-ai-{fallback_index + 1}",
    )
    return {
        "id": profile_id,
        "label": label,
        "provider": provider,
        "api_key": str(source.get("api_key") or source.get("ai_api_key") or "").strip(),
        "model": model,
        "base_url": base_url,
    }

def normalize_ai_profiles(raw_profiles, legacy_settings=None):
    legacy_settings = legacy_settings or {}
    profiles = []
    seen_ids = set()

    if isinstance(raw_profiles, list):
        for index, profile in enumerate(raw_profiles):
            sanitized = sanitize_ai_profile(profile, fallback_index=index)
            base_id = sanitized["id"]
            dedup_id = base_id
            suffix = 2
            while dedup_id in seen_ids:
                dedup_id = f"{base_id}-{suffix}"
                suffix += 1
            sanitized["id"] = dedup_id
            seen_ids.add(dedup_id)
            profiles.append(sanitized)

    if not profiles:
        profiles.append(
            sanitize_ai_profile(
                {
                    "id": "openai-default",
                    "label": "OpenAI Default",
                    "provider": legacy_settings.get("ai_provider") or "openai",
                    "api_key": legacy_settings.get("ai_api_key") or "",
                    "model": legacy_settings.get("ai_model") or "",
                    "base_url": legacy_settings.get("ai_base_url") or "",
                }
            )
        )

    return profiles

def sync_legacy_ai_settings(settings):
    profiles = settings.get("ai_profiles") or []
    default_translation_id = settings.get("default_translation_ai_profile_id")
    default_context_id = settings.get("default_context_ai_profile_id")

    profile_map = {profile["id"]: profile for profile in profiles if isinstance(profile, dict) and profile.get("id")}
    default_translation = profile_map.get(default_translation_id) or (profiles[0] if profiles else {})
    default_context = profile_map.get(default_context_id) or default_translation

    if default_translation:
        settings["ai_provider"] = default_translation.get("provider", "openai")
        settings["ai_api_key"] = default_translation.get("api_key", "")
        settings["ai_model"] = default_translation.get("model", default_ai_model_for_provider(settings["ai_provider"]))
        settings["ai_base_url"] = normalize_ai_base_url(
            default_translation.get("base_url", default_ai_base_url_for_provider(settings["ai_provider"]))
        )

    if profiles:
        settings["default_translation_ai_profile_id"] = (
            default_translation.get("id") or profiles[0].get("id")
        )
        settings["default_context_ai_profile_id"] = (
            default_context.get("id") or settings["default_translation_ai_profile_id"]
        )

    return settings

def load_global_settings():
    defaults = default_global_settings()
    try:
        GLOBAL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if GLOBAL_SETTINGS_PATH.exists():
            with open(GLOBAL_SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    defaults.update(saved)
    except Exception as e:
        logger.warning(f"Không thể đọc global settings: {str(e)}")

    defaults["ai_profiles"] = normalize_ai_profiles(defaults.get("ai_profiles"), legacy_settings=defaults)
    defaults["ai_base_url"] = normalize_ai_base_url(defaults.get("ai_base_url"))
    return sync_legacy_ai_settings(defaults)

def save_global_settings(data):
    settings = default_global_settings()
    payload = data or {}
    
    # 1. Process OpenReel API Key
    openreel_key = payload.get("openreel_api_key", "").strip()
    if openreel_key and not openreel_key.startswith("env:"):
        write_key_to_env_file("OPENREEL_API_KEY", openreel_key)
        openreel_key = "env:OPENREEL_API_KEY"
    elif not openreel_key:
        openreel_key = settings["openreel_api_key"]
        
    settings.update({
        "openreel_api_key": openreel_key,
        "openreel_reference_keys": payload.get("openreel_reference_keys", settings["openreel_reference_keys"]),
    })
    
    # 2. Process AI Profiles
    # Check for duplicate labels (case-insensitive) on raw payload BEFORE normalize
    raw_profiles = payload.get("ai_profiles") or []
    labels_seen = set()
    for profile in raw_profiles:
        p_label = (profile.get("label") or profile.get("id") or "").strip()
        if p_label:
            p_label_lower = p_label.lower()
            if p_label_lower in labels_seen:
                raise ValueError(f"Tên hiển thị (Label) '{p_label}' bị trùng lặp. Vui lòng đặt tên hiển thị duy nhất.")
            labels_seen.add(p_label_lower)

    ai_profiles = normalize_ai_profiles(raw_profiles, legacy_settings=payload or settings)

    for profile in ai_profiles:
        api_key = profile.get("api_key", "").strip()
        if api_key and not api_key.startswith("env:"):
            # Determine appropriate variable name
            p_label = profile.get("label", "").strip()
            p_id = profile.get("id", "").strip()
            p_provider = profile.get("provider", "").strip()
            
            if p_label:
                label_clean = re.sub(r"[^a-zA-Z0-9]", "_", p_label).strip("_").upper()
                env_name = f"{label_clean}_API_KEY"
            elif p_id:
                env_name = f"{p_id.replace('-', '_').upper()}_API_KEY"
            else:
                env_name = f"{p_provider.upper()}_API_KEY"
                
            write_key_to_env_file(env_name, api_key)
            profile["api_key"] = f"env:{env_name}"
            
    settings["ai_profiles"] = ai_profiles

    # 3. Clean up env keys for deleted profiles
    try:
        existing_saved = load_global_settings()
        existing_profiles = existing_saved.get("ai_profiles") or []
        new_profile_ids = {p["id"] for p in ai_profiles}
        for old_profile in existing_profiles:
            if old_profile.get("id") not in new_profile_ids:
                old_key_ref = old_profile.get("api_key", "")
                if old_key_ref.startswith("env:"):
                    env_var = old_key_ref[4:].strip()
                    # Only delete if no remaining profile still uses this env var
                    still_in_use = any(
                        p.get("api_key", "") == old_key_ref
                        for p in ai_profiles
                    )
                    if not still_in_use:
                        delete_key_from_env_file(env_var)
                        logger.info(f"Đã xóa env key '{env_var}' do profile '{old_profile.get('label', old_profile.get('id'))}' bị xóa.")
    except Exception as e:
        logger.warning(f"Không thể dọn env keys sau khi xóa profile: {e}")

    
    profile_ids = [profile["id"] for profile in settings["ai_profiles"]]
    default_translation_id = payload.get("default_translation_ai_profile_id") or settings["default_translation_ai_profile_id"]
    default_context_id = payload.get("default_context_ai_profile_id") or settings["default_context_ai_profile_id"]
    settings["default_translation_ai_profile_id"] = (
        default_translation_id if default_translation_id in profile_ids else profile_ids[0]
    )
    settings["default_context_ai_profile_id"] = (
        default_context_id if default_context_id in profile_ids else settings["default_translation_ai_profile_id"]
    )
    settings = sync_legacy_ai_settings(settings)
    GLOBAL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GLOBAL_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)
    return settings

def apply_global_settings_to_config(config):
    global_settings = load_global_settings()
    merged = {
        "openreel_api_key": global_settings.get("openreel_api_key", ""),
        "openreel_reference_keys": global_settings.get("openreel_reference_keys", ""),
        "available_ai_profiles": global_settings.get("ai_profiles", []),
        "default_translation_ai_profile_id": global_settings.get("default_translation_ai_profile_id"),
        "default_context_ai_profile_id": global_settings.get("default_context_ai_profile_id"),
        "translation_ai_profile_id": global_settings.get("default_translation_ai_profile_id"),
        "context_ai_profile_id": global_settings.get("default_context_ai_profile_id"),
    }
    if config:
        merged.update(config)
    merged["available_ai_profiles"] = normalize_ai_profiles(
        merged.get("available_ai_profiles") or global_settings.get("ai_profiles"),
        legacy_settings=global_settings,
    )
    merged["ai_base_url"] = normalize_ai_base_url(merged.get("ai_base_url"))
    return merged

def resolve_ai_profile(settings, profile_id=None):
    profiles = normalize_ai_profiles((settings or {}).get("ai_profiles"), legacy_settings=settings or {})
    profile_map = {profile["id"]: profile for profile in profiles}
    default_profile = profile_map.get((settings or {}).get("default_translation_ai_profile_id")) or profiles[0]
    if profile_id and profile_id in profile_map:
        return profile_map[profile_id]
    return default_profile

def build_ai_translation_config(item_config=None, purpose="translation"):
    item_config = item_config or {}
    global_settings = load_global_settings()
    method = (
        item_config.get("translation_method")
        or item_config.get("translationMethod")
        or "google"
    ).lower()

    profile_key = "context_ai_profile_id" if purpose == "context" else "translation_ai_profile_id"
    default_profile_key = "default_context_ai_profile_id" if purpose == "context" else "default_translation_ai_profile_id"
    selected_profile_id = (
        item_config.get(profile_key)
        or item_config.get("contextAiProfileId" if purpose == "context" else "translationAiProfileId")
        or global_settings.get(default_profile_key)
    )
    profile = resolve_ai_profile(global_settings, selected_profile_id)

    provider = (profile.get("provider") or "openai").lower()
    api_key = profile.get("api_key") or ""
    model = profile.get("model") or default_ai_model_for_provider(provider)
    base_url = normalize_ai_base_url(profile.get("base_url") or default_ai_base_url_for_provider(provider))
    fallback_model = (
        item_config.get("ai_fallback_model")
        or item_config.get("aiFallbackModel")
        or profile.get("fallback_model")
        or "google/gemma-4-31b-it"
    )

    if not item_config.get(profile_key) and not item_config.get("contextAiProfileId" if purpose == "context" else "translationAiProfileId"):
        provider = (item_config.get("ai_provider") or item_config.get("aiProvider") or provider).lower()
        api_key = item_config.get("ai_api_key") or item_config.get("apiKey") or api_key
        model = item_config.get("ai_model") or item_config.get("aiModel") or model or default_ai_model_for_provider(provider)
        base_url = normalize_ai_base_url(
            item_config.get("ai_base_url") or item_config.get("aiBaseUrl") or base_url or default_ai_base_url_for_provider(provider)
        )

    glossary = item_config.get("ai_glossary") or item_config.get("glossary") or {}
    if isinstance(glossary, str):
        parsed_glossary = {}
        for line in glossary.splitlines():
            if "=>" in line:
                key, value = line.split("=>", 1)
            elif ":" in line:
                key, value = line.split(":", 1)
            else:
                continue
            key = key.strip().strip('"')
            value = value.strip().strip('"')
            if key and value:
                parsed_glossary[key] = value
        glossary = parsed_glossary
    if not isinstance(glossary, dict):
        glossary = {}

    is_mimo = (
        "xiaomimimo.com" in (base_url or "").lower()
        or "mimo" in (model or "").lower()
    )

    fallback_envs = []
    
    # 1. Fallback based on profile ID (e.g. openai-default -> OPENAI_DEFAULT_API_KEY)
    p_id = profile.get("id")
    if p_id:
        id_env = f"{p_id.replace('-', '_').upper()}_API_KEY"
        if id_env not in fallback_envs:
            fallback_envs.append(id_env)
            
    # 2. Fallback based on profile label (e.g. GEMMA -> GEMMA_API_KEY)
    p_label = profile.get("label")
    if p_label:
        label_clean = re.sub(r"[^a-zA-Z0-9]", "_", p_label).strip("_")
        if label_clean:
            label_env = f"{label_clean.upper()}_API_KEY"
            if label_env not in fallback_envs:
                fallback_envs.append(label_env)

    # 3. Fallback based on provider (e.g. openai -> OPENAI_API_KEY)
    if provider == "openai":
        fallback_envs.append("OPENAI_API_KEY")
    elif provider == "gemini":
        fallback_envs.append("GEMINI_API_KEY")
    elif provider == "anthropic":
        fallback_envs.append("ANTHROPIC_API_KEY")
    else:
        prov_env = f"{provider.upper()}_API_KEY"
        if prov_env not in fallback_envs:
            fallback_envs.append(prov_env)

    # 4. General fallbacks
    for gen_env in ["NVIDIA_API_KEY", "AI_API_KEY", "API_KEY"]:
        if gen_env not in fallback_envs:
            fallback_envs.append(gen_env)

    resolved_api_key = resolve_env_value(api_key, fallback_envs)

    return {
        "enabled": (method == "ai" if purpose == "translation" else True) and bool(resolved_api_key),
        "purpose": purpose,
        "profile_id": profile.get("id"),
        "profile_label": profile.get("label"),
        "method": method,
        "provider": provider,
        "api_key": resolved_api_key,
        "model": model,
        "fallback_model": fallback_model,
        "base_url": base_url,
        "is_mimo": is_mimo,
        "source_language": item_config.get("source_language") or item_config.get("sourceLanguage") or "Chinese",
        "target_language": item_config.get("target_language") or item_config.get("targetLanguage") or "Vietnamese",
        "tone": item_config.get("ai_tone") or item_config.get("aiTone") or "natural and fluent",
        "video_context": item_config.get("video_context") or item_config.get("videoContext") or "N/A",
        "video_terms": item_config.get("video_terms") or item_config.get("videoTerms") or "N/A",
        "temperature": float(item_config.get("ai_temperature", item_config.get("aiTemperature", 0.0)) or 0.0),
        "glossary": glossary,
        "translation_branch": item_config.get("translation_branch") or item_config.get("translationBranch"),
    }

def build_ai_translation_prompt(config, ultra_short=False):
    if ultra_short:
        return TRANSLATION_ULTRA_SHORT_PROMPT_TEMPLATE.format(
            source_language=config['source_language'],
            target_language=config['target_language']
        )

    glossary_rule = ""
    if config.get("glossary"):
        glossary_rule = "\nUser glossary mappings take absolute priority."

    return TRANSLATION_SYSTEM_PROMPT_TEMPLATE.format(
        source_language=config['source_language'],
        target_language=config['target_language'],
        context=config.get('video_context', 'N/A'),
        terms=config.get('video_terms', 'N/A'),
        glossary_rule=glossary_rule
    ).strip()

def build_ai_batch_payload(config, lines, previous_context=None, next_context=None):
    return {
        "source_language": config["source_language"],
        "target_language": config["target_language"],
        "previous_context": previous_context or None,
        "lines": [line["text"] for line in lines],
        "next_context": next_context or None,
        "translation_branch": config.get("translation_branch"),
    }

def repair_with_glossary(text, glossary=None):
    if not glossary:
        return text
    repaired = text
    for key in sorted(glossary.keys(), key=len, reverse=True):
        value = glossary.get(key)
        if key and value:
            repaired = re.sub(re.escape(key), str(value), repaired, flags=re.IGNORECASE)
    return repaired

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
                        out.append(repair_known_source_terms(str(item).strip()))
                    else:
                        out.append("")
                return out
        except Exception:
            continue

    raise ValueError(f"Không parse được JSON dịch AI: {text[:180]}")

def validate_ai_translation_result(lines, translations, source_language):
    if len(translations) != len(lines):
        raise ValueError(f"Count mismatch: expected {len(lines)}, got {len(translations)}")
    for idx, (line, translated) in enumerate(zip(lines, translations), start=1):
        translated = (translated or "").strip()
        translated = repair_known_source_terms(translated)
        if not translated:
            raise ValueError(f"Dòng {idx} rỗng trong kết quả AI")
        if has_source_chars(translated, source_language):
            raise ValueError(f"Dòng {idx} còn ký tự nguồn: {translated}")
        if translated == line["text"].strip() and has_source_chars(line["text"], source_language):
            raise ValueError(f"Dòng {idx} giống nguyên văn nguồn: {translated}")


def build_ai_request_payload(config, user_payload, system_prompt, line_count):
    model = config["model"]
    provider = config["provider"]
    temperature = float(config.get("temperature", 0.0) or 0.0)
    user_content = json.dumps(user_payload, ensure_ascii=False) if isinstance(user_payload, dict) else str(user_payload)
    max_tokens = max(1024, min(8192, int(line_count or 1) * 120))
    is_reasoning = model.startswith(("o1", "o3")) or config.get("is_mimo")

    if provider == "anthropic":
        return {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
            "stream": False,
        }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "top_p": 1,
        "stream": False,
        "max_completion_tokens" if is_reasoning else "max_tokens": max_tokens,
    }
    if not is_reasoning:
        payload["response_format"] = {"type": "json_object"}
    else:
        payload["reasoning_effort"] = "low"
    return payload

def call_ai_json_object(config, system_prompt, user_payload, line_count=20):
    import requests

    provider = config["provider"]
    url_lower = (config.get("base_url") or "").lower()
    is_interactions = "interactions" in url_lower or provider == "gemini"

    if provider == "anthropic":
        url = f"{config['base_url']}/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": config["api_key"],
            "anthropic-version": "2023-06-01",
        }
    elif is_interactions:
        url = config["base_url"]
        headers = {
            "content-type": "application/json",
            "x-goog-api-key": config["api_key"],
        }
    else:
        url = f"{config['base_url']}/chat/completions"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {config['api_key']}",
        }

    if is_interactions:
        user_payload_str = json.dumps(user_payload, ensure_ascii=False) if isinstance(user_payload, dict) else str(user_payload)
        payload = {
            "model": config.get("model") or "gemma-4-31b-it",
            "input": [
                {
                    "type": "text",
                    "text": system_prompt
                },
                {
                    "type": "text",
                    "text": user_payload_str
                }
            ],
        }
    else:
        payload = build_ai_request_payload(config, user_payload, system_prompt, line_count)

    response = None
    last_err = None
    for attempt in range(1, 4):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            if response.ok:
                break
            last_err = f"HTTP {response.status_code}: {response.text[:500]}"
        except Exception as e:
            last_err = str(e)
        logger.warning(f"Thử gọi AI JSON lần {attempt}/3 thất bại: {last_err}. Đang thử lại...")
        time.sleep(2)

    if response is None or not response.ok:
        raise RuntimeError(f"AI JSON call thất bại sau 3 lần thử: {last_err}")

    data = response.json()
    if provider == "anthropic":
        raw = "".join(part.get("text", "") for part in data.get("content", []) if isinstance(part, dict))
    elif is_interactions:
        extracted_text = None
        for step in data.get("steps", []):
            if isinstance(step, dict) and step.get("type") == "model_output":
                content_list = step.get("content", [])
                extracted_text = "".join(item.get("text", "") for item in content_list if isinstance(item, dict))
                if extracted_text:
                    break
        if not extracted_text:
            extracted_text = next((item.get("text", "") for item in data.get("input", []) if isinstance(item, dict) and item.get("type") == "model_output"), None)

        if extracted_text is not None:
            raw = extracted_text
        elif "candidates" in data:
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
        elif "choices" in data:
            raw = data["choices"][0]["message"]["content"]
        else:
            raw = str(data)
    else:
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    text = (raw or "").strip()
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start:end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    raise ValueError(f"Không parse được JSON object từ AI: {text[:180]}")

def normalize_full_subtitles(raw_texts):
    return [{"id": index + 1, "text": text} for index, text in enumerate(raw_texts)]

def as_list(value):
    if isinstance(value, list):
        return value
    return [value]

def call_ai_translation_once(lines, config, previous_context=None, next_context=None, ultra_short=False):
    import requests

    system_prompt = build_ai_translation_prompt(config, ultra_short=ultra_short)
    user_payload = build_ai_batch_payload(config, lines, previous_context, next_context)

    provider = config["provider"]
    url_lower = (config.get("base_url") or "").lower()
    is_interactions = "interactions" in url_lower or provider == "gemini"

    if provider == "anthropic":
        url = f"{config['base_url']}/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": config["api_key"],
            "anthropic-version": "2023-06-01",
        }
    elif is_interactions:
        url = config["base_url"]
        headers = {
            "content-type": "application/json",
            "x-goog-api-key": config["api_key"],
        }
    else:
        url = f"{config['base_url']}/chat/completions"
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {config['api_key']}",
        }

    if is_interactions:
        user_payload_str = json.dumps(user_payload, ensure_ascii=False) if isinstance(user_payload, dict) else str(user_payload)
        payload = {
            "model": config.get("model") or "gemma-4-31b-it",
            "input": [
                {
                    "type": "text",
                    "text": system_prompt
                },
                {
                    "type": "text",
                    "text": user_payload_str
                }
            ],
        }
    else:
        payload = build_ai_request_payload(config, user_payload, system_prompt, len(lines))

    try:
        debug_dir = Path(__file__).with_name("scratch") / "ai_translation_payloads"
        debug_dir.mkdir(parents=True, exist_ok=True)
        safe_model = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(config.get("model") or "model")).strip("_") or "model"
        debug_path = debug_dir / f"{int(time.time())}_{safe_model}_{len(lines)}lines.json"
        debug_headers = dict(headers)
        for key in list(debug_headers.keys()):
            if key.lower() in {"authorization", "x-goog-api-key", "x-api-key"}:
                value = str(debug_headers[key] or "")
                debug_headers[key] = f"{value[:6]}...{value[-4:]}" if len(value) > 12 else "***"
        debug_payload = {
            "url": url,
            "headers": debug_headers,
            "payload": payload,
            "provider": provider,
            "model": config.get("model"),
            "line_count": len(lines),
            "ultra_short": ultra_short,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        debug_path.write_text(json.dumps(debug_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Saved AI translation payload for Postman: {debug_path}")
    except Exception as exc:
        logger.warning(f"Could not save AI translation payload debug file: {exc}")

    response = None
    last_error = None
    for attempt in range(1, 4):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=90)
            if response.ok:
                break
            last_error = f"HTTP {response.status_code}: {response.text[:500]}"
            if response.status_code < 500:
                break
        except Exception as exc:
            last_error = str(exc)
        logger.warning(f"AI translation request failed attempt {attempt}/3: {last_error}")
        time.sleep(2 * attempt)

    if response is None or not response.ok:
        status = response.status_code if response is not None else "no_response"
        text = response.text[:500] if response is not None else str(last_error)
        raise RuntimeError(f"AI translation HTTP {status}: {text}")

    data = response.json()
    if provider == "anthropic":
        raw = "".join(part.get("text", "") for part in data.get("content", []) if isinstance(part, dict))
    elif is_interactions:
        extracted_text = None
        for step in data.get("steps", []):
            if isinstance(step, dict) and step.get("type") == "model_output":
                content_list = step.get("content", [])
                extracted_text = "".join(item.get("text", "") for item in content_list if isinstance(item, dict))
                if extracted_text:
                    break
        if not extracted_text:
            extracted_text = next((item.get("text", "") for item in data.get("input", []) if isinstance(item, dict) and item.get("type") == "model_output"), None)

        if extracted_text is not None:
            raw = extracted_text
        elif "candidates" in data:
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
        elif "choices" in data:
            raw = data["choices"][0]["message"]["content"]
        else:
            raw = str(data)
    else:
        raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    translations = parse_ai_translation_response(raw, len(lines))
    validate_ai_translation_result(lines, translations, config["source_language"])
    return translations

def config_with_model(config, model):
    updated = dict(config)
    updated["model"] = model
    updated["is_mimo"] = (
        "xiaomimimo.com" in (updated.get("base_url") or "").lower()
        or "mimo" in (model or "").lower()
    )
    return updated

def call_ai_translation_with_fallback(lines, config, previous_context=None, next_context=None, ultra_short=False):
    try:
        return call_ai_translation_once(lines, config, previous_context, next_context, ultra_short=ultra_short)
    except Exception as primary_error:
        fallback_model = (config.get("fallback_model") or "").strip()
        if not fallback_model or fallback_model == config.get("model"):
            raise
        fallback_config = config_with_model(config, fallback_model)
        logger.warning(
            f"Model chính {config.get('model')} dịch thất bại, chuyển sang fallback "
            f"{fallback_model}: {str(primary_error)}"
        )
        return call_ai_translation_once(
            lines,
            fallback_config,
            previous_context,
            next_context,
            ultra_short=ultra_short,
        )

def translate_ai_batch_recursive(lines, config, previous_context=None, next_context=None, item_config=None):
    if not lines:
        return []

    for ultra_short in (False, True):
        try:
            if len(lines) <= 10:
                return call_ai_translation_with_fallback(lines, config, previous_context, next_context, ultra_short=ultra_short)
            return call_ai_translation_once(lines, config, previous_context, next_context, ultra_short=ultra_short)
        except Exception as e:
            logger.warning(f"Dịch AI batch {len(lines)} dòng thất bại (ultra_short={ultra_short}): {str(e)}")

    if len(lines) == 1:
        raw_text = lines[0]["text"]
        logger.warning(f"Dịch AI dòng đơn thất bại hoàn toàn, thử repair dòng đơn: {raw_text}")
        try:
            return [repair_single_translation(
                raw_text,
                item_config=item_config,
                previous_context=previous_context,
                next_context=next_context,
            )]
        except Exception as e:
            logger.warning(f"Repair dòng đơn thất bại, dùng glossary repair cuối cùng: {str(e)}")
            repaired = repair_with_glossary(raw_text, config.get("glossary"))
            repaired = repair_known_source_terms(repaired)
            if has_source_chars(repaired, config["source_language"]):
                raise ValueError(f"Dòng đơn vẫn còn ký tự nguồn sau mọi retry: {repaired}")
            return [repaired]

    mid = len(lines) // 2
    left = translate_ai_batch_recursive(lines[:mid], config, previous_context, next_context, item_config=item_config)
    right_context = (previous_context or []) + left
    right_context = right_context[-5:]
    right = translate_ai_batch_recursive(lines[mid:], config, right_context, next_context, item_config=item_config)
    return left + right

def translate_texts_with_ai(raw_texts, item_config=None):
    config = build_ai_translation_config(item_config, purpose="translation")
    if not config["enabled"]:
        raise RuntimeError(
            "AI translation is disabled or missing API key. Set translation_method='ai' and configure a valid translation AI profile."
        )

    logger.info(f"Dịch AI bằng {config['provider']} model {config['model']} theo batch 20 dòng...")
    batch_size = int((item_config or {}).get("ai_batch_size", 20) or 20)
    context_window = 2
    translated = [None] * len(raw_texts)

    for start in range(0, len(raw_texts), batch_size):
        end = min(len(raw_texts), start + batch_size)
        batch = [{"id": str(i), "text": raw_texts[i]} for i in range(start, end)]
        prev_context = raw_texts[max(0, start - context_window):start]
        next_context = raw_texts[end:min(len(raw_texts), end + context_window)]
        batch_translations = translate_ai_batch_recursive(batch, config, prev_context, next_context, item_config=item_config)
        for offset, value in enumerate(batch_translations):
            translated[start + offset] = value
        logger.info(f"Dịch AI batch {start // batch_size + 1}: OK ({len(batch_translations)}/{len(batch)})")

    return translated

def repair_single_translation(raw_text, item_config=None, previous_context=None, next_context=None):
    config = build_ai_translation_config(item_config)
    if config["enabled"]:
        line = [{"id": "0", "text": raw_text}]
        for ultra_short in (False, True):
            try:
                repaired = call_ai_translation_with_fallback(
                    line,
                    config,
                    previous_context=previous_context,
                    next_context=next_context,
                    ultra_short=ultra_short,
                )[0]
                repaired = repair_known_source_terms(repaired)
                if repaired and not has_source_chars(repaired, config["source_language"]):
                    return repaired
                logger.warning(f"Dịch lại dòng đơn vẫn còn ký tự nguồn: {raw_text} -> {repaired}")
            except Exception as e:
                logger.warning(f"Dịch lại dòng đơn thất bại (ultra_short={ultra_short}): {str(e)}")

    raise ValueError(f"AI repair failed; stop pipeline before Google fallback. Source line: {raw_text}")

def patch_subtitles_file(content_path, font_size=5.0, font_color=DEFAULT_SUBTITLE_COLOR_RGB, font_name=DEFAULT_SUBTITLE_FONT_PATH, item_config=None, translation_cache=None):
    translation_cache = translation_cache if translation_cache is not None else {}
    if item_config is not None and not item_config.get("draft_path"):
        try:
            item_config["draft_path"] = str(Path(content_path).parent)
        except Exception:
            pass

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

    # Extract video context and terms before translation
    if item_config is not None and not item_config.get("_full_context_generated") and raw_texts:
        try:
            logger.info(f"Đang dùng AI lấy video_context và asr_text từ {len(raw_texts)} dòng phụ đề...")
            config = build_ai_translation_config(item_config, purpose="context")
            if config.get("enabled"):
                subtitles_block = "\n".join(raw_texts[: min(len(raw_texts), 220)])
                payload = {"subtitles": subtitles_block}
                result = call_ai_json_object(config, FULL_CONTEXT_PROMPT, payload, line_count=len(raw_texts))
                context_val = result.get("context", "")
                if isinstance(context_val, (dict, list)):
                    context_val = json.dumps(context_val, ensure_ascii=False)
                context = str(context_val or "").strip()

                terms_val = result.get("terms", "")
                if isinstance(terms_val, (dict, list)):
                    terms_val = json.dumps(terms_val, ensure_ascii=False)
                terms = str(terms_val or "").strip()
                
                if context or terms:
                    item_config["video_context"] = context or "N/A"
                    item_config["video_terms"] = terms or "N/A"
                    item_config["_full_context_generated"] = True
                    logger.info(f"AI context extracted successfully: Context: {context[:100]} | Terms: {terms[:100]}")
        except Exception as e:
            item_config["_full_context_generated"] = True
            logger.warning(f"Lấy context/terms thất bại, tiếp tục với bối cảnh hiện có: {e}")


    source_indices = [index for index, raw_text in enumerate(raw_texts) if has_source_chars(raw_text, "Chinese")]
    source_raw_texts = [raw_texts[index] for index in source_indices]
    missing_source_texts = []
    seen_missing = set()
    for raw_text in source_raw_texts:
        if raw_text in translation_cache or raw_text in seen_missing:
            continue
        missing_source_texts.append(raw_text)
        seen_missing.add(raw_text)

    cached_count = len(source_raw_texts) - len(missing_source_texts)
    logger.info(
        f"Đang dịch {len(missing_source_texts)}/{len(source_raw_texts)} dòng phụ đề tiếng Trung chưa có cache "
        f"(dùng lại cache {cached_count} dòng) sang tiếng Việt..."
    )
    try:
        source_ai_translations = translate_texts_with_ai(missing_source_texts, item_config=item_config)
        if source_ai_translations:
            for offset, translated in enumerate(source_ai_translations):
                raw_text = missing_source_texts[offset]
                if translated:
                    translation_cache[raw_text] = translated
    except Exception as e:
        logger.error(f"AI translation failed; stop pipeline without Google fallback: {str(e)}")
        raise

    failed_translations = []
    translated_count = 0
    translated_samples = []
    translated_texts = []
    for index, (text_mat, content_json, raw_text) in enumerate(parsed_items):
        try:
            if not has_source_chars(raw_text, "Chinese"):
                translated = raw_text
            elif raw_text in translation_cache:
                translated = translation_cache[raw_text]
            else:
                translated = translate_google(raw_text, "zh-CN", "vi")
            translated = repair_known_source_terms(translated)
            translation_cache[raw_text] = translated

            if has_source_chars(translated, "Chinese"):
                logger.warning(f"Bản dịch vẫn còn chữ Trung, thử dịch lại riêng dòng: {raw_text} -> {translated}")
                previous_context = raw_texts[max(0, index - 2):index]
                next_context = raw_texts[index + 1:index + 3]
                translated = repair_single_translation(
                    raw_text,
                    item_config=item_config,
                    previous_context=previous_context,
                    next_context=next_context,
                )
                translated = repair_known_source_terms(translated)
                translation_cache[raw_text] = translated

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
    extra_info = data.get("extra_info") or {}
    remaining_source.extend(collect_source_strings(extra_info.get("subtitle_fragment_info_list") or [], "Chinese"))

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

def patch_subtitles_in_json(draft_path, font_size=5.0, font_color=DEFAULT_SUBTITLE_COLOR_RGB, font_name=DEFAULT_SUBTITLE_FONT_PATH, item_config=None):
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
    if track_types is not None:
        track_types = set(track_types)

    total_updated = 0
    patched_files = 0
    lock_bit = 4
    for content_path in draft_json_paths(draft_path):
        with open(content_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        updated_count = 0
        for track in data.get("tracks", []):
            if track_types is not None and track.get("type") not in track_types:
                continue

            current_attr = int(track.get("attribute", 0) or 0)
            new_attr = (current_attr | lock_bit) if locked else (current_attr & ~lock_bit)
            if new_attr != current_attr:
                track["attribute"] = new_attr
                updated_count += 1

            for segment in track.get("segments", []):
                current_seg_attr = int(segment.get("track_attribute", 0) or 0)
                new_seg_attr = (current_seg_attr | lock_bit) if locked else (current_seg_attr & ~lock_bit)
                if new_seg_attr != current_seg_attr:
                    segment["track_attribute"] = new_seg_attr
                    updated_count += 1

        if updated_count:
            with open(content_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            patched_files += 1
            total_updated += updated_count

    action = "khóa" if locked else "mở khóa"
    target = ", ".join(track_types) if track_types else "tất cả track"
    logger.info(f"Đã {action} {total_updated} track/segment ({target}) trên {patched_files} file draft.")
    return total_updated

def patch_canvas_config_in_json(draft_path, ratio="16:9", width=1920, height=1080):
    target_canvas = {
        "ratio": ratio,
        "width": int(width),
        "height": int(height),
        "background": None,
    }
    patched_files = 0

    for content_path in draft_json_paths(draft_path):
        with open(content_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        current = data.get("canvas_config") or {}
        new_canvas = dict(current)
        new_canvas.update(target_canvas)
        if new_canvas == current:
            continue

        data["canvas_config"] = new_canvas
        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        patched_files += 1

    logger.info(f"Đã chỉnh canvas {ratio} ({width}x{height}) trên {patched_files} file draft.")
    return patched_files

def patch_video_mirror_in_json(draft_path, mirror_horizontal=True):
    patched_segments = 0
    patched_files = 0

    for content_path in draft_json_paths(draft_path):
        with open(content_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        updated_count = 0
        for track in data.get("tracks", []):
            if track.get("type") != "video":
                continue
            for segment in track.get("segments", []):
                clip = segment.setdefault("clip", {})
                flip = clip.setdefault("flip", {})
                current = bool(flip.get("horizontal", False))
                if current != bool(mirror_horizontal):
                    flip["horizontal"] = bool(mirror_horizontal)
                    updated_count += 1
                if "vertical" not in flip:
                    flip["vertical"] = False

        if updated_count:
            with open(content_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            patched_files += 1
            patched_segments += updated_count

    state = "bật" if mirror_horizontal else "tắt"
    logger.info(f"Đã {state} mirror ngang video trên {patched_segments} segment / {patched_files} file draft.")
    return patched_segments

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

def wait_for_new_audio_assets(draft_path, before_count, interval=5, timeout=600, cancel_check=None):
    last_count = before_count
    start = time.time()

    while True:
        if cancel_check:
            cancel_check()
        current_count = count_audio_assets_in_json(draft_path)
        last_count = current_count
        logger.info(
            f"Kiểm tra audio TTS: audio_segments={current_count['segments']}, "
            f"audio_materials={current_count['materials']}, files={current_count.get('files', 0)}."
        )
        if current_count["total"] > before_count["total"]:
            return True, current_count
        if timeout and time.time() - start >= timeout:
            logger.warning(
                f"Hết thời gian chờ audio TTS sau {int(timeout)}s "
                f"(trước={before_count}, sau={current_count})."
            )
            return False, current_count
        time.sleep(interval)

def parse_video_paths(value):
    if not value:
        return []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\r\n;]+", str(value))
    return [item.strip().strip('"') for item in raw_items if item and item.strip()]

def get_machine_aliases():
    aliases = []
    for raw in [
        os.environ.get("CAPCUT_MACHINE_NAME"),
        os.environ.get("COMPUTERNAME"),
        os.environ.get("HOSTNAME"),
        socket.gethostname(),
    ]:
        value = str(raw or "").strip().lower()
        if value and value not in aliases:
            aliases.append(value)
    return aliases

def resolve_existing_video_source(item_config):
    item_config = item_config or {}
    aliases = get_machine_aliases()
    candidates = []

    override_map = item_config.get("video_path_overrides") or item_config.get("videoPathOverrides") or {}
    if isinstance(override_map, dict):
        for alias in aliases:
            override_value = override_map.get(alias)
            if override_value:
                candidates.extend(parse_video_paths(override_value))

    candidates.extend(parse_video_paths(item_config.get("video_path") or item_config.get("videoPath")))
    candidates.extend(parse_video_paths(item_config.get("video_paths") or item_config.get("videoPaths")))

    seen = set()
    normalized = []
    for candidate in candidates:
        key = candidate.strip().lower()
        if key and key not in seen:
            seen.add(key)
            normalized.append(candidate)

    missing = []
    for candidate in normalized:
        path = Path(candidate).expanduser()
        if path.exists() and path.is_file():
            return str(path), normalized, missing
        missing.append(str(path))

    return None, normalized, missing

def probe_video_metadata(video_path):
    completed = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    info = json.loads(completed.stdout or "{}")
    stream = (info.get("streams") or [{}])[0]
    duration = float(stream.get("duration") or info.get("format", {}).get("duration") or 0)
    return {
        "duration_us": int(round(duration * 1_000_000)),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
    }

def build_atempo_filter(speed):
    factors = []
    remaining = float(speed)
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    factors.append(remaining)
    return ",".join(f"atempo={factor:.8g}" for factor in factors)

def render_speed_adjusted_video(source, output_path, speed):
    source = Path(source)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(".tmp.mp4")
    if temp_path.exists():
        temp_path.unlink()

    command = [
        "ffmpeg",
        "-y",
        "-i", str(source),
        "-filter_complex",
        f"[0:v]setpts={1 / float(speed):.12g}*PTS[v];[0:a]{build_atempo_filter(speed)}[a]",
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(temp_path),
    ]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0:
        if temp_path.exists():
            temp_path.unlink()
        raise RuntimeError(f"ffmpeg speed render failed: {completed.stderr[-1200:]}")
    os.replace(temp_path, output_path)
    return output_path

def ensure_video_track_in_draft(draft_path, video_path, speed=1.0, volume=1.0):
    root = Path(draft_path)
    source = Path(video_path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Source video not found for draft patch: {source}")

    speed = float(speed or 1.0)
    if speed <= 0:
        raise ValueError("Video speed must be greater than 0")

    original_meta = probe_video_metadata(source)
    original_duration = int(original_meta["duration_us"])
    if original_duration <= 0:
        raise ValueError(f"Invalid source video duration: {source}")

    asset_dir = root / "assets" / "video"
    asset_dir.mkdir(parents=True, exist_ok=True)
    if abs(speed - 1.0) > 0.0001:
        material_name = f"video_{uuid.uuid5(uuid.NAMESPACE_URL, str(source.resolve()) + f':speed:{speed}').hex}_speed_{speed:.4g}.mp4"
    else:
        material_name = f"video_{uuid.uuid5(uuid.NAMESPACE_URL, str(source.resolve())).hex}.mp4"
    asset_path = asset_dir / material_name
    if abs(speed - 1.0) > 0.0001:
        if not asset_path.exists() or asset_path.stat().st_size <= 0:
            logger.info(f"Đang render video đã làm chậm thật bằng ffmpeg: speed={speed}, output={asset_path}")
            render_speed_adjusted_video(source, asset_path, speed)
    else:
        if not asset_path.exists() or asset_path.stat().st_size != source.stat().st_size:
            shutil.copy2(source, asset_path)

    meta = probe_video_metadata(asset_path)
    source_duration = int(meta["duration_us"])
    if source_duration <= 0:
        source_duration = int(round(original_duration / speed))
    target_duration = source_duration
    draft_speed = 1.0

    material_id = uuid.uuid5(uuid.NAMESPACE_URL, str(asset_path.resolve())).hex
    speed_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{asset_path.resolve()}:speed:1").hex
    segment_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{asset_path.resolve()}:segment").hex
    track_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{root.resolve()}:main-video")).upper()

    video_material = {
        "audio_fade": None,
        "category_id": "",
        "category_name": "local",
        "check_flag": 63487,
        "crop": {
            "upper_left_x": 0.0,
            "upper_left_y": 0.0,
            "upper_right_x": 1.0,
            "upper_right_y": 0.0,
            "lower_left_x": 0.0,
            "lower_left_y": 1.0,
            "lower_right_x": 1.0,
            "lower_right_y": 1.0,
        },
        "crop_ratio": "free",
        "crop_scale": 1.0,
        "duration": source_duration,
        "height": meta["height"],
        "id": material_id,
        "local_material_id": "",
        "material_id": material_id,
        "material_name": material_name,
        "media_path": "",
        "path": str(asset_path),
        "remote_url": str(source),
        "type": "video",
        "width": meta["width"],
    }
    speed_material = {
        "curve_speed": None,
        "id": speed_id,
        "mode": 0,
        "speed": draft_speed,
        "type": "speed",
    }
    video_segment = {
        "enable_adjust": True,
        "enable_color_correct_adjust": False,
        "enable_color_curves": True,
        "enable_color_match_adjust": False,
        "enable_color_wheels": True,
        "enable_lut": True,
        "enable_smart_color_adjust": False,
        "last_nonzero_volume": volume,
        "reverse": False,
        "track_attribute": 0,
        "track_render_index": 0,
        "visible": True,
        "id": segment_id,
        "material_id": material_id,
        "target_timerange": {"start": 0, "duration": target_duration},
        "common_keyframes": [],
        "keyframe_refs": [],
        "source_timerange": {"start": 0, "duration": source_duration},
        "speed": draft_speed,
        "volume": volume,
        "extra_material_refs": [speed_id],
        "clip": {
            "alpha": 1.0,
            "flip": {"horizontal": False, "vertical": False},
            "rotation": 0.0,
            "scale": {"x": 1.0, "y": 1.0},
            "transform": {"x": 0.0, "y": 0.0},
        },
        "uniform_scale": {"on": True, "value": 1.0},
        "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
        "render_index": 0,
    }
    video_track = {
        "attribute": 0,
        "flag": 0,
        "id": track_id,
        "is_default_name": False,
        "name": "main",
        "segments": [video_segment],
        "type": "video",
    }

    patched = 0
    for content_path in [
        root / "draft_content.json",
        root / "draft_info.json",
        root / "template-2.tmp",
        root / "template.tmp",
        *root.glob("Timelines/*/draft_content.json"),
        *root.glob("Timelines/*/draft_info.json"),
        *root.glob("Timelines/*/template-*.tmp"),
    ]:
        if not content_path.exists() or not content_path.is_file():
            continue
        try:
            data = json.loads(content_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        materials = data.setdefault("materials", {})
        videos = materials.setdefault("videos", [])
        videos[:] = [item for item in videos if item.get("id") != material_id and item.get("material_id") != material_id]
        videos.append(video_material.copy())

        speeds = materials.setdefault("speeds", [])
        speeds[:] = [item for item in speeds if item.get("id") != speed_id]
        speeds.append(speed_material.copy())

        tracks = data.setdefault("tracks", [])
        non_video_tracks = [track for track in tracks if track.get("type") != "video"]
        existing_video = next((track for track in tracks if track.get("type") == "video"), None)
        merged_track = dict(existing_video or video_track)
        merged_track.update({
            "attribute": int(merged_track.get("attribute", 0) or 0),
            "flag": int(merged_track.get("flag", 0) or 0),
            "id": merged_track.get("id") or track_id,
            "is_default_name": False,
            "name": merged_track.get("name") or "main",
            "segments": [video_segment.copy()],
            "type": "video",
        })
        data["tracks"] = [merged_track] + non_video_tracks
        data["duration"] = max(int(data.get("duration") or 0), target_duration)
        content_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        patched += 1

    logger.info(
        f"Đã patch video track vào draft: files={patched}, source_duration={source_duration}, "
        f"target_duration={target_duration}, speed={speed}, asset={asset_path}"
    )
    return patched

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

class PipelineCancelled(RuntimeError):
    pass

class QueueRunner:
    def __init__(self):
        self.queue = []
        self.is_processing = False
        self.is_paused = False
        self.current_index = -1
        self.pause_requested = False
        self.thread = None
        self.config = {}
        self.load_cache()

    def _check_cancel(self, item):
        if item.get("cancel_requested"):
            raise PipelineCancelled("__PIPELINE_CANCELLED__")

    def load_cache(self):
        if not QUEUE_CACHE_PATH.exists():
            return
        try:
            data = json.loads(QUEUE_CACHE_PATH.read_text(encoding="utf-8"))
            cached_queue = data.get("queue", [])
            if isinstance(cached_queue, list):
                self.queue = cached_queue
                for item in self.queue:
                    if item.get("status") == "running":
                        item["status"] = "failed"
                        item["message"] = "Lỗi: Pipeline bị gián đoạn khi server/máy tính tắt. Bấm Thử lại nếu muốn chạy lại mục này."
                    item.pop("cancel_requested", None)
            cached_config = data.get("config", {})
            if isinstance(cached_config, dict):
                self.config = cached_config
            logger.info(f"Đã khôi phục {len(self.queue)} item hàng chờ từ cache.")
        except Exception as e:
            logger.warning(f"Không thể đọc queue cache: {str(e)}")

    def save_cache(self):
        try:
            payload = {
                "queue": self.queue,
                "config": self.config,
                "saved_at": int(time.time()),
            }
            tmp_path = QUEUE_CACHE_PATH.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(QUEUE_CACHE_PATH)
        except Exception as e:
            logger.warning(f"Không thể lưu queue cache: {str(e)}")

    def repair_runtime_state(self):
        thread_alive = bool(self.thread and self.thread.is_alive())
        invalid_running_state = (
            self.is_processing
            and not thread_alive
        )
        invalid_index_state = (
            self.is_processing
            and self.current_index < 0
            and not thread_alive
            and not any(item.get("status") == "running" for item in self.queue)
        )
        if not (invalid_running_state or invalid_index_state):
            return False

        logger.warning(
            "Phát hiện trạng thái pipeline bị kẹt "
            f"(is_processing={self.is_processing}, current_index={self.current_index}, "
            f"thread_alive={thread_alive}). Tự reset runtime state."
        )
        self.is_processing = False
        self.is_paused = False
        self.pause_requested = False
        self.current_index = -1
        changed = False
        for item in self.queue:
            if item.get("status") == "running":
                item["status"] = "failed"
                item["message"] = "Lỗi: Pipeline bị gián đoạn. Bấm Chạy/Thử lại để chạy lại từ bước 1."
                changed = True
        if changed:
            self.save_cache()
        return True

    def get_state(self):
        self.repair_runtime_state()
        if not self.is_processing:
            changed = False
            for item in self.queue:
                if item.get("status") == "running":
                    item["status"] = "failed"
                    item["message"] = "Lỗi: Pipeline đã dừng khi mục này đang chạy. Bấm Thử lại để chạy lại."
                    changed = True
            if changed:
                self.save_cache()
        return {
            "queue": self.queue,
            "is_processing": self.is_processing,
            "is_paused": self.is_paused,
            "pause_requested": self.pause_requested,
            "current_index": self.current_index,
            "auto_shutdown": bool(self.config.get("auto_shutdown", False)),
        }

    def reset_item_for_fresh_run(self, item, message=None):
        item["status"] = "pending"
        item["progress"] = 0
        item["resume_from_step"] = 1
        item["message"] = message or "Đang chờ..."
        item.pop("cancel_requested", None)
        item.pop("stopped_after_patch", None)
        item.pop("paused_at", None)
        item.pop("exported_path", None)

    def set_queue(self, videos):
        self.repair_runtime_state()
        if self.is_processing:
            return
        self.queue = []
        for video in videos:
            item = {"video": video}
            self.reset_item_for_fresh_run(item)
            self.queue.append(item)
        self.save_cache()

    def start(self, config):
        self.repair_runtime_state()
        if self.is_processing:
            return
        self.config = dict(config or {})
        self.config.setdefault("auto_shutdown", False)
        self.config["auto_shutdown"] = bool(self.config.get("auto_shutdown"))
        restart_all = bool(
            self.config.get("restart_all")
            or self.config.get("fresh")
            or self.config.get("start_from_step_1")
        )
        for item in self.queue:
            if restart_all:
                self.reset_item_for_fresh_run(item)
                continue
            if item.get("status") == "running":
                item["status"] = "failed"
                item["message"] = "Lỗi: Pipeline bị gián đoạn trước đó. Bấm Thử lại nếu muốn chạy lại mục này."
            elif item.get("status") == "pending":
                item["progress"] = int(item.get("progress", 0) or 0)
                item.setdefault("message", "Đang chờ...")
                item["resume_from_step"] = int(item.get("resume_from_step", 1) or 1)
                item.pop("stopped_after_patch", None)
            elif item.get("status") in ("success", "failed", "cancelled"):
                item.pop("cancel_requested", None)
                continue
            else:
                item["status"] = "pending"
                item["progress"] = 0
                item["message"] = "Đang chờ..."
            item.pop("cancel_requested", None)
            if item.get("status") != "paused":
                item["resume_from_step"] = int(item.get("resume_from_step", 1) or 1)
        self.pause_requested = False
        self.is_paused = False
        self.is_processing = True
        self.save_cache()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def pause(self):
        self.repair_runtime_state()
        if not self.is_processing:
            self.pause_requested = False
            self.is_paused = False
            return
        self.pause_requested = True

    def cancel_item(self, idx):
        if idx is None or idx < 0 or idx >= len(self.queue):
            raise IndexError("Invalid index")
        item = self.queue[idx]
        item["cancel_requested"] = True
        video = item.get("video")
        was_running = item.get("status") == "running" or idx == self.current_index
        self.queue.pop(idx)
        if was_running:
            logger.info(f"Đã hủy và xóa item đang chạy khỏi hàng chờ: {video}")
            kill_capcut()
        else:
            logger.info(f"Đã xóa item khỏi hàng chờ: {video}")
        if self.current_index == idx:
            self.current_index = -1
        elif self.current_index > idx:
            self.current_index -= 1
        self.save_cache()
        return item

    def resume(self, config=None):
        self.repair_runtime_state()
        if self.is_processing:
            return
        if config:
            self.config.update(config)
            if "auto_shutdown" in config:
                self.config["auto_shutdown"] = bool(config.get("auto_shutdown"))
            self.save_cache()
        has_resumable = any(item.get("status") in ("paused", "pending") for item in self.queue)
        if not has_resumable:
            return
        self.pause_requested = False
        self.is_paused = False
        self.is_processing = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def set_auto_shutdown(self, enabled):
        self.config["auto_shutdown"] = bool(enabled)
        self.save_cache()
        return self.config["auto_shutdown"]

    def clear(self):
        if self.is_processing:
            return
        self.queue = []
        self.current_index = -1
        self.is_paused = False
        self.save_cache()

    def _pause_item(self, item, next_step, progress, message):
        item["status"] = "paused"
        item["progress"] = progress
        item["resume_from_step"] = next_step
        item["message"] = message
        item["paused_at"] = int(time.time())
        self.is_paused = True
        self.pause_requested = False
        raise RuntimeError("__PIPELINE_PAUSED__")

    def _checkpoint_pause(self, item, next_step, progress):
        if not self.pause_requested:
            return
        self._pause_item(
            item,
            next_step=next_step,
            progress=progress,
            message=f"Tạm dừng. Tiếp tục sẽ chạy từ Bước {next_step}."
        )

    def _run_loop(self):

        uia_initializer = None

        com_initialized = False

        try:

            uia_initializer = auto.UIAutomationInitializerInThread()

            uia_initializer.__enter__()

            logger.info("Đã khởi tạo UIAutomation cho thread pipeline.")

        except Exception as init_error:

            import ctypes

            logger.warning(f"UIAutomationInitializerInThread thất bại, fallback CoInitialize: {init_error}")

            ctypes.windll.ole32.CoInitialize(None)

            com_initialized = True
        logger.info("Bắt đầu xử lý hàng chờ video...")
        try:
            while True:
                if self.pause_requested:
                    self.is_paused = True
                    logger.info("Đã tạm dừng hàng chờ video.")
                    break

                # Find the first paused or pending item
                pending_item = None
                pending_idx = -1
                for i, item in enumerate(self.queue):
                    if item["status"] in ("paused", "pending"):
                        pending_item = item
                        pending_idx = i
                        break

                if pending_item is None:
                    if self.config.get("auto_shutdown"):
                        logger.info("Tất cả video trong hàng chờ đã xử lý xong. Hệ thống sẽ tự động tắt máy sau 10 giây (lệnh: shutdown /s /f /t 10)...")
                        result = subprocess.run(
                            ["shutdown.exe", "/s", "/f", "/t", "10"],
                            capture_output=True,
                            text=True,
                            errors="replace",
                        )
                        if result.returncode == 0:
                            logger.info("Đã gửi lệnh shutdown thành công cho Windows.")
                        else:
                            logger.error(
                                f"Lệnh shutdown thất bại, code={result.returncode}: "
                                f"{(result.stderr or result.stdout or '').strip()}"
                            )
                    else:
                        logger.info("Tất cả video trong hàng chờ đã xử lý xong. Không tắt máy vì người dùng không bật tùy chọn tự tắt.")
                    break

                self.current_index = pending_idx
                pending_item["status"] = "running"
                pending_item["progress"] = max(5, int(pending_item.get("progress", 0) or 0))
                resume_from_step = int(pending_item.get("resume_from_step", 1) or 1)
                pending_item["message"] = (
                    f"Đang tiếp tục từ Bước {resume_from_step}..."
                    if resume_from_step > 1
                    else "Đang xử lý..."
                )
                self.save_cache()

                try:
                    self._process_item(pending_item)
                    if pending_item.get("cancel_requested"):
                        logger.info(f"Dự án '{pending_item.get('video')}' đã bị hủy, bỏ qua cập nhật trạng thái hoàn thành.")
                    else:
                        pending_item["status"] = "success"
                        pending_item["progress"] = 100
                        pending_item["message"] = "Hoàn thành!"
                        pending_item["resume_from_step"] = None
                        self.save_cache()
                except PipelineCancelled:
                    logger.info(f"Dự án '{pending_item.get('video')}' đã bị hủy, chuyển sang item kế tiếp.")
                    kill_capcut()
                    self.save_cache()
                    continue
                except RuntimeError as e:
                    if str(e) == "__PIPELINE_PAUSED__":
                        logger.info(f"Đã tạm dừng dự án '{pending_item.get('video')}' tại checkpoint an toàn.")
                        break
                    if pending_item.get("cancel_requested"):
                        logger.info(f"Dự án '{pending_item.get('video')}' đã bị hủy.")
                        self.save_cache()
                        continue
                    logger.error(f"Lỗi khi tự động hóa video '{pending_item['video']}': {str(e)}")
                    pending_item["status"] = "failed"
                    pending_item["message"] = f"Lỗi: {str(e)}"
                    self.save_cache()
                except Exception as e:
                    if pending_item.get("cancel_requested"):
                        logger.info(f"Dự án '{pending_item.get('video')}' đã bị hủy.")
                        self.save_cache()
                        continue
                    logger.error(f"Lỗi khi tự động hóa video '{pending_item['video']}': {str(e)}")
                    pending_item["status"] = "failed"
                    pending_item["message"] = f"Lỗi: {str(e)}"
                    self.save_cache()
                except BaseException as e:
                    logger.exception(f"Lỗi nghiêm trọng ngoài Exception khi tự động hóa video '{pending_item.get('video')}': {e}")
                    pending_item["status"] = "failed"
                    pending_item["message"] = f"Lỗi nghiêm trọng: {type(e).__name__}: {e}"
                    self.save_cache()
        finally:
            self.is_processing = False
            self.current_index = -1
            self.save_cache()
            if uia_initializer is not None:
                try:
                    uia_initializer.__exit__(None, None, None)
                except Exception as exit_error:
                    logger.warning(f"Không giải phóng được UIAutomation initializer: {exit_error}")
            elif com_initialized:
                import ctypes
                ctypes.windll.ole32.CoUninitialize()
            logger.info("Quá trình chạy hàng chờ hoàn tất.")

    def _process_item(self, item):
        is_existing_project = item.get("type") == "project"
        draft_id = item.get("draft_id")
        resume_from_step = int(item.get("resume_from_step", 1) or 1)

        # Determine config for this item (either item-specific or runner global config)
        item_config = apply_global_settings_to_config(item.get("config") or self.config or {})

        speed = float(item_config.get("speed", 0.77))
        volume_db = float(item_config.get("volume_db", -15.5))
        tts_speed = float(item_config.get("tts_speed", 1.17))
        font_size = float(item_config.get("font_size", 5.0))
        font_color_hex = item_config.get("font_color", DEFAULT_SUBTITLE_COLOR_HEX)
        font_name = item_config.get("font_name", DEFAULT_SUBTITLE_FONT_PATH)
        video_name = os.path.basename(str(item.get("video") or draft_id or "project"))

        configured_video_path, configured_candidates, missing_candidates = resolve_existing_video_source(item_config)
        if configured_video_path:
            item["video"] = configured_video_path
            is_existing_project = False
            logger.info(
                f"Project has reusable source video; forcing Step 1 video patch into draft {draft_id}: "
                f"{configured_video_path}"
            )
        elif item_config.get("video_path") or item_config.get("video_paths") or item_config.get("video_path_overrides"):
            if item.get("type") == "project":
                logger.warning(
                    "Không tìm thấy source video hợp lệ trên máy hiện tại. "
                    f"Sẽ dùng draft sẵn có và bỏ qua Step 1. Candidates: {configured_candidates or missing_candidates}"
                )
            else:
                raise FileNotFoundError(
                    "Không tìm thấy source video hợp lệ để tạo project mới. "
                    f"Candidates đã thử: {configured_candidates or missing_candidates}"
                )

        # Convert hex color to RGB normalized float tuple (R, G, B)
        try:
            hex_val = font_color_hex.lstrip('#')
            r = int(hex_val[0:2], 16) / 255.0
            g = int(hex_val[2:4], 16) / 255.0
            b = int(hex_val[4:6], 16) / 255.0
            font_color_rgb = (r, g, b)
        except Exception:
            font_color_rgb = DEFAULT_SUBTITLE_COLOR_RGB

        if resume_from_step <= 1 and is_existing_project:
            self._check_cancel(item)
            logger.info(f"=== BẮT ĐẦU AUTOMATION CHO DỰ ÁN CÓ SẴN: {video_name} ({draft_id}) ===")
            clean_name = "".join([c if c.isalnum() else "_" for c in video_name])

            # Step 1 is skipped
            item["progress"] = 15
            item["message"] = "Bước 1: Bỏ qua (Dự án đã tồn tại)..."
            time.sleep(1)
            item["resume_from_step"] = 2
            self._checkpoint_pause(item, next_step=2, progress=15)
        elif resume_from_step <= 1:
            self._check_cancel(item)
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
            pipeline_font_name = normalize_draft_font_name(font_name)
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
                font=pipeline_font_name,
                font_size=font_size,
                copy_to_capcut=True,
                draft_id=draft_id,
                volume=1.0,
                preserve_blur_effect=bool(item_config.get("preserve_blur_effect", True)),
            )
            self._check_cancel(item)

            # Save pipeline_config.json inside the newly created project folder
            try:
                new_project_folder = os.path.join(DEFAULT_CAPCUT_DRAFTS, draft_id)
                os.makedirs(new_project_folder, exist_ok=True)
                config_path = os.path.join(new_project_folder, "pipeline_config.json")
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(item_config, f, ensure_ascii=False, indent=4)
            except Exception as e:
                logger.warning(f"Không thể lưu pipeline_config cho dự án mới: {str(e)}")
            item["resume_from_step"] = 2
            self._checkpoint_pause(item, next_step=2, progress=20)

        draft_full_path = os.path.join(DEFAULT_CAPCUT_DRAFTS, draft_id)
        video_source_for_patch = configured_video_path or (item.get("video") if item.get("video") and Path(str(item.get("video"))).is_file() else None)
        if video_source_for_patch:
            self._check_cancel(item)
            ensure_video_track_in_draft(
                draft_full_path,
                video_source_for_patch,
                speed=speed,
                volume=1.0,
            )
        project_opened_this_run = False
        if resume_from_step <= 2:
            self._check_cancel(item)
            item["progress"] = 25
            prefer_local_whisper = should_use_local_whisper(item_config)
            item["message"] = (
                "Bước 2: Patch cấu hình draft trước khi chạy Whisper..."
                if prefer_local_whisper
                else "Bước 2: Mở dự án trong CapCut..."
            )
            try:
                patch_canvas_config_in_json(
                    draft_full_path,
                    ratio=item_config.get("canvas_ratio", "16:9"),
                    width=int(item_config.get("canvas_width", 1920)),
                    height=int(item_config.get("canvas_height", 1080)),
                )
                patch_video_mirror_in_json(
                    draft_full_path,
                    mirror_horizontal=bool(item_config.get("mirror_video", True)),
                )
                patch_track_lock_in_json(draft_full_path, track_types=["video", "effect"], locked=True)
                patch_track_lock_in_json(draft_full_path, track_types=["text", "audio"], locked=False)
            except Exception as e:
                logger.warning(f"Không thể chỉnh trạng thái khóa track trước khi mở dự án: {str(e)}")

            if prefer_local_whisper:
                logger.info("Dùng local Whisper nên chưa mở CapCut ở bước 2. Sẽ mở sau khi dịch/patch xong.")
            else:
                controller = launch_capcut()
                open_project_in_gui(controller, draft_id)
                self._check_cancel(item)
                project_opened_this_run = True
            item["resume_from_step"] = 3
            self._checkpoint_pause(item, next_step=3, progress=30)

        if resume_from_step <= 3:
            self._check_cancel(item)
            item["progress"] = 45
            use_local_whisper = should_use_local_whisper(item_config)
            local_whisper_video = item.get("video")
            if use_local_whisper and not (local_whisper_video and Path(str(local_whisper_video)).is_file()):
                logger.warning(
                    f"Không có file video thật để chạy local Whisper ({local_whisper_video}). "
                    "Fallback sang Auto Captions bằng CapCut."
                )
                use_local_whisper = False
            item["message"] = (
                "Bước 3: Đang tạo phụ đề bằng local Whisper GPU..."
                if use_local_whisper
                else "Bước 3: Đang tự động tạo phụ đề (Auto Captions)..."
            )
            existing_subtitles = count_subtitle_text_items_in_json(draft_full_path)
            if existing_subtitles["total"] > 0:
                logger.info(
                    f"Draft đã có subtitle/text trước bước tạo phụ đề "
                    f"(materials={existing_subtitles['materials']}, segments={existing_subtitles['segments']}). "
                    "Bỏ qua bước tạo phụ đề và đi tiếp."
                )
            elif use_local_whisper:
                if project_opened_this_run:
                    kill_capcut()
                    project_opened_this_run = False
                    time.sleep(1)
                run_local_whisper_captions_for_draft(
                    draft_full_path,
                    draft_id,
                    local_whisper_video,
                    item_config,
                    font_name,
                    font_size,
                    font_color_hex,
                )
            else:
                if not project_opened_this_run:
                    controller = launch_capcut(cancel_check=lambda: self._check_cancel(item))
                    open_project_in_gui(controller, draft_id, cancel_check=lambda: self._check_cancel(item))
                    project_opened_this_run = True
                run_image_workflow("rpa_auto_captions.sample.json", "Auto Captions", attempts=4, retry_delay=5)
            self._check_cancel(item)
            item["resume_from_step"] = 4
            self._checkpoint_pause(item, next_step=4, progress=50)

        if resume_from_step <= 4:
            self._check_cancel(item)
            item["progress"] = 60
            item["message"] = "Bước 4 & 5: Đang dịch phụ đề và chỉnh âm lượng trong draft..."
            if project_opened_this_run:
                logger.info("Đóng CapCut để flush draft trước khi dịch/patch.")
                kill_capcut()
                project_opened_this_run = False
                time.sleep(1)
            else:
                logger.info("CapCut chưa được mở trong luồng Whisper local, patch draft trực tiếp.")

            patch_subtitles_in_json(
                draft_full_path,
                font_size=font_size,
                font_color=font_color_rgb,
                font_name=font_name,
                item_config=item_config
            )
            patch_track_volume_in_json(draft_full_path, volume_db=volume_db, track_types=["video"])
            self._check_cancel(item)

            if item_config.get("stop_after_patch"):
                item["progress"] = 70
                item["message"] = "Đã patch bản dịch/âm lượng xong và dừng để kiểm tra draft."
                item["stopped_after_patch"] = True
                logger.info(
                    f"Đã dừng pipeline sau bước patch theo cấu hình stop_after_patch=true. "
                    f"Draft: {draft_full_path}"
                )
                return

            item["resume_from_step"] = 5
            self._checkpoint_pause(item, next_step=5, progress=68)

        if resume_from_step <= 5:
            self._check_cancel(item)
            logger.info("Đợi 1 giây sau khi patch âm lượng trước khi mở lại CapCut...")
            time.sleep(1)
            item["message"] = "Bước 5.5: Đang mở lại dự án sau khi patch bản dịch và âm lượng..."
            controller = launch_capcut(cancel_check=lambda: self._check_cancel(item))
            open_project_in_gui(controller, draft_id, cancel_check=lambda: self._check_cancel(item))
            project_opened_this_run = True
            item["resume_from_step"] = 6
            self._checkpoint_pause(item, next_step=6, progress=72)

        if resume_from_step <= 6:
            self._check_cancel(item)
            item["progress"] = 75
            item["message"] = "Bước 6: Đang tạo giọng nói (TTS) cho sub trên dự án đang mở..."
            if not project_opened_this_run:
                controller = launch_capcut(cancel_check=lambda: self._check_cancel(item))
                open_project_in_gui(controller, draft_id, cancel_check=lambda: self._check_cancel(item))
                project_opened_this_run = True
            tts_audio_before = count_audio_assets_in_json(draft_full_path)
            logger.info(f"Trước TTS: audio_segments={tts_audio_before['segments']}, audio_materials={tts_audio_before['materials']}.")

            max_tts_attempts = int(item_config.get("tts_attempts", 3))
            tts_ready = False
            tts_audio_after = tts_audio_before

            for attempt in range(1, max_tts_attempts + 1):
                item["message"] = f"Bước 6: Đang tạo giọng nói TTS, lần {attempt}/{max_tts_attempts}..."
                logger.info(f"Chạy TTS lần {attempt}/{max_tts_attempts}...")
                if attempt == 1:
                    run_image_workflow("rpa_tts.sample.json", "Text to speech", attempts=4, retry_delay=5)
                else:
                    run_image_workflow("rpa_tts_retry.sample.json", "Text to speech retry", attempts=4, retry_delay=5)
                self._check_cancel(item)

                tts_ready, tts_audio_after = wait_for_new_audio_assets(
                    draft_full_path,
                    tts_audio_before,
                    interval=int(item_config.get("tts_audio_wait_interval", 5)),
                    timeout=int(item_config.get("tts_audio_wait_timeout", 600)),
                    cancel_check=lambda: self._check_cancel(item),
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

            item["resume_from_step"] = 7
            self._checkpoint_pause(item, next_step=7, progress=82)

        if resume_from_step <= 7:
            self._check_cancel(item)
            item["progress"] = 85
            item["message"] = f"Bước 7: Đang tăng tốc độ giọng đọc lên {tts_speed}..."
            patch_audio_speed_in_json(draft_full_path, target_speed=tts_speed)
            item["resume_from_step"] = 8
            self._checkpoint_pause(item, next_step=8, progress=88)

        if resume_from_step <= 8:
            self._check_cancel(item)
            item["progress"] = 90
            item["message"] = "Bước 8: Đang xuất video thành phẩm..."
            export_source_video = item_config.get("video_path") or item.get("video")
            export_scan_dirs = get_export_scan_dirs(export_source_video, item_config)
            export_before_snapshot = snapshot_video_files(export_scan_dirs)
            logger.info(
                "Theo dõi file export trong các thư mục: "
                + ", ".join(str(path) for path in export_scan_dirs)
            )
            controller = launch_capcut(cancel_check=lambda: self._check_cancel(item))
            open_project_in_gui(controller, draft_id, cancel_check=lambda: self._check_cancel(item))
            run_image_workflow("rpa_export.sample.json", "Export", attempts=1, retry_delay=5)
            self._check_cancel(item)
            logger.info("Đóng CapCut để nhả file export trước khi đổi tên và chuyển thư mục...")
            kill_capcut()
            time.sleep(1)
            exported_path = move_latest_export_to_source_folder(
                export_source_video,
                export_before_snapshot,
                item_config=item_config,
                timeout=int(item_config.get("export_detect_timeout", 180)),
                cancel_check=lambda: self._check_cancel(item),
            )
            if exported_path:
                item["exported_path"] = exported_path
            item["resume_from_step"] = 9
            self._checkpoint_pause(item, next_step=9, progress=96)

        item["progress"] = 98
        item["message"] = "Bước 9: Hoàn tất dự án..."
        logger.info(f"=== ĐÃ XỬ LÝ XONG: {video_name} ===")

# Instantiate global runner
runner = QueueRunner()

# --- Flask Server Routes ---

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/api/settings/global', methods=['GET', 'POST'])
def global_settings():
    if request.method == 'POST':
        try:
            data = request.get_json() or {}
            settings = save_global_settings(data)
            return jsonify({"ok": True, "settings": settings})
        except Exception as e:
            logger.error(f"Failed to save global settings: {str(e)}")
            return jsonify({"error": str(e)}), 500
    return jsonify(load_global_settings())

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
    data.setdefault("restart_all", True)
    runner.start(data)
    state = runner.get_state()
    state["ok"] = True
    return jsonify(state)

@app.route('/api/auto_shutdown', methods=['POST'])
def set_auto_shutdown():
    data = request.get_json() or {}
    enabled = runner.set_auto_shutdown(bool(data.get("auto_shutdown", False)))
    logger.info(f"Tự tắt máy sau pipeline đã được {'BẬT' if enabled else 'TẮT'} trên server.")
    return jsonify({"ok": True, "auto_shutdown": enabled})

@app.route('/api/pause', methods=['POST'])
def pause_runner():
    runner.pause()
    return jsonify(runner.get_state())

@app.route('/api/resume', methods=['POST'])
def resume_runner():
    data = request.get_json() or {}
    runner.resume(data)
    state = runner.get_state()
    state["ok"] = True
    return jsonify(state)

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
            if data.get("ai_base_url"):
                data["ai_base_url"] = normalize_ai_base_url(data.get("ai_base_url"))
            # Keep values clean
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        global_settings = load_global_settings()
        default_config = apply_global_settings_to_config({
            "speed": 0.77,
            "volume_db": -15.5,
            "tts_speed": 1.17,
            "font_size": 5.0,
            "font_color": DEFAULT_SUBTITLE_COLOR_HEX,
            "font_name": DEFAULT_SUBTITLE_FONT_PATH,
            "mirror_video": True,
            "translation_method": "ai",
            "translation_ai_profile_id": global_settings.get("default_translation_ai_profile_id"),
            "context_ai_profile_id": global_settings.get("default_context_ai_profile_id"),
            "source_language": "Chinese",
            "target_language": "Vietnamese",
            "ai_tone": "natural and fluent",
            "video_context": "Short fantasy game online videos, MMORPG gameplay review, PvP server war",
            "ai_temperature": 0.0,
            "ai_glossary": {},
            "translation_branch": "A",
            "auto_asr_context": True,
            "asr_suggested_fixes": [],
            "video_path": ""
        })
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    saved_config = json.load(f)
                    default_config.update(saved_config)
                    default_config = apply_global_settings_to_config(default_config)
            except Exception:
                pass
        return jsonify(default_config)

@app.route('/api/projects/create', methods=['POST'])
def create_project():
    try:
        data = request.get_json() or {}
        video_path = data.get("video_path")
        project_name = data.get("project_name")
        global_settings = load_global_settings()

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
            "font_color": data.get("font_color", DEFAULT_SUBTITLE_COLOR_HEX),
            "font_name": data.get("font_name", DEFAULT_SUBTITLE_FONT_PATH),
            "mirror_video": bool(data.get("mirror_video", True)),
            "translation_method": data.get("translation_method", "ai"),
            "translation_ai_profile_id": data.get(
                "translation_ai_profile_id",
                global_settings.get("default_translation_ai_profile_id"),
            ),
            "context_ai_profile_id": data.get(
                "context_ai_profile_id",
                global_settings.get("default_context_ai_profile_id"),
            ),
            "source_language": data.get("source_language", "Chinese"),
            "target_language": data.get("target_language", "Vietnamese"),
            "ai_tone": data.get("ai_tone", "natural and fluent"),
            "video_context": data.get("video_context", "Short fantasy game online videos, MMORPG gameplay review, PvP server war"),
            "ai_temperature": float(data.get("ai_temperature", 0.0)),
            "ai_glossary": data.get("ai_glossary", {}),
            "translation_branch": data.get("translation_branch", "A"),
            "auto_asr_context": bool(data.get("auto_asr_context", True)),
            "asr_suggested_fixes": data.get("asr_suggested_fixes", []),
            "openreel_api_key": data.get("openreel_api_key", global_settings.get("openreel_api_key", "")),
            "openreel_reference_keys": data.get("openreel_reference_keys", global_settings.get("openreel_reference_keys", "")),
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
        config = apply_global_settings_to_config(config)

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
                "resume_from_step": 1,
                "message": "Đang chờ..."
            }

            if len(video_paths) > 1:
                item["message"] = f"Đang chờ ({index}/{len(video_paths)})..."

            runner.queue.append(item)
        runner.save_cache()
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
            runner.cancel_item(int(idx))
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
            item["resume_from_step"] = 1
            item.pop("cancel_requested", None)
            item.pop("stopped_after_patch", None)
            runner.save_cache()

            # Start queue runner if it's currently idle
            if not runner.is_processing:
                runner.start(data)
            return jsonify(runner.get_state())
        return jsonify({"error": "Invalid index"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/queue/delete', methods=['POST'])
def delete_queue_item():
    try:
        data = request.get_json() or {}
        idx = data.get("index")
        if idx is None:
            return jsonify({"error": "Index is required"}), 400
        if 0 <= idx < len(runner.queue):
            item = runner.queue[idx]
            if item.get("status") == "running":
                return jsonify({"error": "Không thể xóa item đang chạy. Hãy bấm Hủy trước."}), 400
            runner.queue.pop(idx)
            runner.save_cache()
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
    ensure_control_overlay_running()
    debug_enabled = str(os.environ.get("CAPCUT_DEBUG", "")).lower() in {"1", "true", "yes", "on"}
    app.run(host="127.0.0.1", port=5000, debug=debug_enabled, use_reloader=False)
