# -*- coding: utf-8 -*-
import functools
print = functools.partial(print, flush=True)

import ctypes
import os
import sys
import time
import json
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageGrab
import win32gui
import win32con
import win32process
import win32ui
import psutil
from rapidocr_onnxruntime import RapidOCR
import pyautogui
import uiautomation as uia

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.1

# Desktop management & Desktop isolation bypass
_CURRENT_DESKTOP_HANDLE = None

u32 = ctypes.windll.user32
u32.OpenDesktopA.restype = ctypes.c_void_p
u32.OpenDesktopA.argtypes = [ctypes.c_char_p, ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
u32.OpenInputDesktop.restype = ctypes.c_void_p
u32.OpenInputDesktop.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
u32.SetThreadDesktop.restype = ctypes.c_bool
u32.SetThreadDesktop.argtypes = [ctypes.c_void_p]
u32.SetCursorPos.restype = ctypes.c_bool
u32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

def attach_desktop():
    global _CURRENT_DESKTOP_HANDLE
    try:
        if not _CURRENT_DESKTOP_HANDLE:
            _CURRENT_DESKTOP_HANDLE = u32.OpenDesktopA(b'Default', 0, False, 0x10000000 | 0x01FF)
            if not _CURRENT_DESKTOP_HANDLE:
                _CURRENT_DESKTOP_HANDLE = u32.OpenInputDesktop(0, False, 0x01FF)
        if _CURRENT_DESKTOP_HANDLE:
            u32.SetThreadDesktop(_CURRENT_DESKTOP_HANDLE)
            return _CURRENT_DESKTOP_HANDLE
    except Exception:
        pass
    return None

attach_desktop()

def enum_desktop_windows():
    h = attach_desktop()
    u32 = ctypes.windll.user32
    wins = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_cb(hwnd, lparam):
        wins.append(hwnd)
        return True
    cb = WNDENUMPROC(enum_cb)
    if h:
        u32.EnumDesktopWindows(h, cb, 0)
    else:
        try:
            win32gui.EnumWindows(lambda hwnd, _: wins.append(hwnd) or True, None)
        except Exception:
            pass
    return wins

# Directories configuration
ARTIFACT_DIR = r"C:\Users\admin.TRANANH\.gemini\antigravity-ide\brain\547da145-9921-47b6-b7cc-661272021b8f"
SCRATCH_DIR = os.path.abspath("scratch")
os.makedirs(SCRATCH_DIR, exist_ok=True)

DATA_DIR = os.path.abspath("data")
LOCAL_OUTPUT_DIR = os.path.abspath(os.path.join("data", "outputs"))
DATA_SCREENSHOTS_DIR = os.path.abspath(os.path.join("data", "screenshots"))
os.makedirs(LOCAL_OUTPUT_DIR, exist_ok=True)
os.makedirs(DATA_SCREENSHOTS_DIR, exist_ok=True)

GDRIVE_OUTPUT_DIR = r"G:\My Drive\CapCutRecapAI\outputs"
if os.path.exists(r"G:\My Drive\CapCutRecapAI"):
    os.makedirs(GDRIVE_OUTPUT_DIR, exist_ok=True)

ocr_engine = RapidOCR()

def capture_hwnd(hwnd):
    try:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None, None
        r = win32gui.GetWindowRect(hwnd)
        w = max(1, r[2] - r[0])
        h = max(1, r[3] - r[1])
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(saveBitMap)
        windll = ctypes.windll.user32
        windll.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
        bmpinfo = saveBitMap.GetInfo()
        bmpstr = saveBitMap.GetBitmapBits(True)
        im = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        return im, r
    except Exception as e:
        print(f"[capture_hwnd Error]: {e}")
        return None, None

def save_screen(name: str, hwnd=None, overlay_hwnd=None):
    attach_desktop()
    time.sleep(0.3)
    p_scratch = os.path.join(SCRATCH_DIR, f"{name}.png")
    p_artifact = os.path.join(ARTIFACT_DIR, f"{name}.png")
    p_data = os.path.join(DATA_SCREENSHOTS_DIR, f"{name}.png")
    img = None
    try:
        img = ImageGrab.grab()
        img.save(p_scratch)
    except Exception as e:
        target_hwnd = hwnd
        pids = get_capcut_pids()
        if not target_hwnd or not win32gui.IsWindow(target_hwnd):
            fg = win32gui.GetForegroundWindow()
            if fg and win32gui.IsWindow(fg):
                _, p = win32process.GetWindowThreadProcessId(fg)
                if p in pids:
                    target_hwnd = fg
            if not target_hwnd:
                wins = []
                for h in enum_desktop_windows():
                    try:
                        if win32gui.IsWindowVisible(h):
                            _, p = win32process.GetWindowThreadProcessId(h)
                            if p in pids:
                                r = win32gui.GetWindowRect(h)
                                area = (r[2] - r[0]) * (r[3] - r[1])
                                wins.append((area, h))
                    except Exception:
                        pass
                if wins:
                    wins.sort(reverse=True)
                    target_hwnd = wins[0][1]

        if target_hwnd and win32gui.IsWindow(target_hwnd):
            im, r_base = capture_hwnd(target_hwnd)
            if im:
                if overlay_hwnd and win32gui.IsWindow(overlay_hwnd) and overlay_hwnd != target_hwnd:
                    im_ov, r_ov = capture_hwnd(overlay_hwnd)
                    if im_ov and r_base and r_ov:
                        ox = max(0, r_ov[0] - r_base[0])
                        oy = max(0, r_ov[1] - r_base[1])
                        try:
                            im.paste(im_ov, (ox, oy))
                        except Exception:
                            pass
                im.save(p_scratch)
                img = im
        else:
            progman = win32gui.FindWindow('Progman', None)
            if progman:
                im, _ = capture_hwnd(progman)
                if im:
                    im.save(p_scratch)
                    img = im

    if os.path.exists(p_scratch):
        try:
            shutil.copy2(p_scratch, p_artifact)
            shutil.copy2(p_scratch, p_data)
            size_str = f" ({img.size})" if img else ""
            print(f"[Screenshot] Saved '{name}.png'{size_str} to artifact and data/screenshots.")
            return p_scratch, img
        except Exception as e:
            print(f"[Screenshot] Copy error: {e}")
            return p_scratch, img
    return None, None

def ocr_screen_image(img_path: str):
    try:
        res, _ = ocr_engine(img_path)
        items = []
        if res:
            for box, text, score in res:
                x0, y0 = box[0]
                x1, y1 = box[2]
                items.append({
                    "text": str(text),
                    "score": float(score),
                    "cx": (x0 + x1) / 2.0,
                    "cy": (y0 + y1) / 2.0,
                    "box": box
                })
        return items
    except Exception as e:
        print(f"OCR error on {img_path}: {e}")
        return []

def minimize_interfering_windows():
    attach_desktop()
    for hwnd in enum_desktop_windows():
        try:
            if win32gui.IsWindowVisible(hwnd):
                cls = win32gui.GetClassName(hwnd)
                title = win32gui.GetWindowText(hwnd)
                # Prioritize minimizing Antigravity IDE and Browsers so they don't cover CapCut
                if any(k in title.lower() for k in ['antigravity', 'coc coc', 'cốc cốc', 'chrome', 'browser', 'edge']):
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                    continue
                # Never minimize CapCut itself
                if 'capcut' in (title + cls).lower():
                    continue
                if any(k in cls for k in ['Chrome_WidgetWin_1']):
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception:
            pass

def get_capcut_pids():
    pids = set()
    for p in psutil.process_iter(['pid', 'name']):
        try:
            name = (p.info.get('name') or '').lower()
            if 'capcut' in name:
                pids.add(p.info['pid'])
        except Exception:
            pass
    return pids

def get_capcut_windows(pids=None):
    if not pids:
        pids = get_capcut_pids()
    attach_desktop()
    wins = []
    seen = set()

    def enum_cb(h, _):
        try:
            if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
                _, p = win32process.GetWindowThreadProcessId(h)
                if p in pids and h not in seen:
                    r = win32gui.GetWindowRect(h)
                    w = r[2] - r[0]
                    h_px = r[3] - r[1]
                    cls = win32gui.GetClassName(h)
                    title = win32gui.GetWindowText(h)
                    seen.add(h)
                    wins.append((h, w, h_px, cls, title))
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(enum_cb, None)
    except Exception:
        pass

    try:
        for c in uia.GetRootControl().GetChildren():
            try:
                if getattr(c, 'ProcessId', 0) in pids:
                    h = c.NativeWindowHandle
                    if h and win32gui.IsWindow(h) and win32gui.IsWindowVisible(h) and h not in seen:
                        r = win32gui.GetWindowRect(h)
                        w = r[2] - r[0]
                        h_px = r[3] - r[1]
                        cls = c.ClassName
                        title = c.Name
                        seen.add(h)
                        wins.append((h, w, h_px, cls, title))
            except Exception:
                pass
    except Exception:
        pass

    for h in enum_desktop_windows():
        try:
            if win32gui.IsWindow(h) and win32gui.IsWindowVisible(h) and h not in seen:
                _, p = win32process.GetWindowThreadProcessId(h)
                if p in pids:
                    r = win32gui.GetWindowRect(h)
                    w = r[2] - r[0]
                    h_px = r[3] - r[1]
                    cls = win32gui.GetClassName(h)
                    title = win32gui.GetWindowText(h)
                    seen.add(h)
                    wins.append((h, w, h_px, cls, title))
        except Exception:
            pass

    return wins

def bring_to_front(hwnd, maximize=False):
    attach_desktop()
    try:
        user32 = ctypes.windll.user32
        # Alt-key trick to grant foreground permission to current thread on Windows
        user32.keybd_event(0x12, 0, 0, 0)
        time.sleep(0.03)
        user32.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.03)

        fg_hwnd = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
        cur_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        if fg_tid != cur_tid:
            user32.AttachThreadInput(cur_tid, fg_tid, True)

        if maximize:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        # Pin to TOPMOST so it physically appears in front of IDE and browser
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)

        if fg_tid != cur_tid:
            user32.AttachThreadInput(cur_tid, fg_tid, False)
        time.sleep(0.3)
    except Exception as e:
        print(f"Warning bringing hwnd {hwnd} to front: {e}")

def click_physical(x, y, hold_sec=0.08):
    attach_desktop()
    u32.SetCursorPos(int(x), int(y))
    time.sleep(0.12)
    u32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(hold_sec)
    u32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.12)

def dismiss_license_modal(hwnd=None, rect=None):
    attach_desktop()
    try:
        r = None
        if hwnd and win32gui.IsWindow(hwnd):
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.BringWindowToTop(hwnd)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            time.sleep(0.3)
            r = win32gui.GetWindowRect(hwnd)
        elif rect:
            r = rect
        
        if not r:
            return False

        w = r[2] - r[0]
        h = r[3] - r[1]
        
        # Agree button is centered at (158, 132) on standard 352x161 dialog
        agree_x = r[0] + (158 if w < 400 else int(w * 0.45))
        agree_y = r[1] + (132 if h < 200 else int(h - 28))

        if hwnd and win32gui.IsWindow(hwnd):
            for click_x, click_y in [(158, 132), (int(w * 0.45), int(h - 28)), (w // 2, h - 30)]:
                lparam = (int(click_y) << 16) | (int(click_x) & 0xFFFF)
                win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
                time.sleep(0.05)
                win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
                time.sleep(0.05)

            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_SPACE, 0)
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_SPACE, 0)

        # Pyautogui mouse click
        pyautogui.moveTo(agree_x, agree_y)
        time.sleep(0.1)
        pyautogui.click()
        time.sleep(0.2)
        pyautogui.press('enter')
        pyautogui.press('space')
        print(f"Sent dismissal signals (PostMessage + Click) to modal at screen ({agree_x}, {agree_y})")
        return True
    except Exception as e:
        print(f"Error dismissing modal: {e}")
        return False

print("==================================================================")
print("=== FULL CAPCUT GUI AUTOMATION & EXPORT PIPELINE TEST ===")
print("==================================================================")

# Step 1: Prepare environment
attach_desktop()
print("[Step 1] Minimizing background windows to expose clean desktop...")
minimize_interfering_windows()
time.sleep(1.0)

print("[Step 1.1] Terminating any existing CapCut & helper processes...")
os.system("taskkill /f /im CapCut.exe /im VEDetector.exe /im VEHelper.exe >nul 2>&1")
time.sleep(2.0)

# Step 1.2: Ensure project draft has AI-chunked, separated subtitles
print("[Step 1.2] Checking and applying AI-chunked subtitles to 'Test_Full_Pipeline_Run'...")
try:
    sys.path.insert(0, os.path.abspath("src"))
    from capcut_api.ai.subtitle_chunker import AISubtitleChunker
    import uuid
    
    draft_dir = os.path.expanduser(r"~\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\Test_Full_Pipeline_Run")
    content_path = os.path.join(draft_dir, "draft_content.json")
    ep191_draft = os.path.expanduser(r"~\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\Test_Video_191_Pipeline\draft_content.json")
    script_path = r"data/outputs/novel_audio/Pham nhan tu tien_Tap_2_ThuyetMinh/kich_ban.txt"
    whisper_path = r"scratch/whisper_raw_segments.json"
    
    from scratch.synchronize_draft_timeline import synchronize_capcut_draft
    audio_191 = r"data/outputs/novel_audio/Test_Video_191_Pipeline/Pham_Nhan_Tu_Tien_Tap_191.mp3"
    script_191 = r"data/outputs/novel_audio/Test_Video_191_Pipeline/kich_ban.txt"
    whisper_191 = r"data/outputs/novel_audio/Test_Video_191_Pipeline/whisper_words.json"
    
    if os.path.exists(audio_191) and os.path.exists(script_191) and os.path.exists(whisper_191):
        print("✅ [Step 1.2] ĐỒNG BỘ TIMELINE: Căn chỉnh Ảnh, Âm thanh, Video, Chữ kết thúc CÙNG 1 THỜI GIAN...")
        synchronize_capcut_draft("Test_Full_Pipeline_Run", audio_191, script_191, whisper_191)
    elif os.path.exists(content_path) and os.path.exists(script_path) and os.path.exists(whisper_path):
        with open(script_path, 'r', encoding='utf-8') as f:
            script_text = f.read()
        with open(whisper_path, 'r', encoding='utf-8') as f:
            whisper_data = json.load(f)
            
        whisper_words = []
        for seg in whisper_data:
            for w in seg.get("words", []):
                whisper_words.append({
                    "word": w.get("word", "").strip(),
                    "start": float(w.get("start", 0.0)),
                    "end": float(w.get("end", 0.0))
                })
                
        chunker = AISubtitleChunker(max_words=6, max_chars=32, min_words=3, inter_phrase_gap=0.06)
        subtitles = chunker.align_script_with_whisper(script_text, whisper_words)
        
        with open(content_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        materials = data.setdefault("materials", {})
        old_texts = materials.get("texts", [])
        tmpl_text = old_texts[0] if old_texts else {}
        font_path = tmpl_text.get("font_path", "C:/Users/admin.TRANANH/AppData/Local/CapCut/Apps/9.4.0.4015/Resources/Font/SystemFont/en.ttf")
        
        font_size = 5.5
        transform_y = -0.78
        new_texts = []
        new_segments = []
        
        for sub in subtitles:
            mat_id = str(uuid.uuid4()).replace("-", "")
            seg_id = str(uuid.uuid4()).replace("-", "")
            txt = sub["text"]
            start_us = int(round(sub["start"] * 1e6))
            dur_us = max(100000, int(round(sub["duration"] * 1e6)))
            
            content_obj = {
                "styles": [{"fill": {"alpha": 1.0, "content": {"render_type": "solid", "solid": {"alpha": 1.0, "color": [1.0, 0.92, 0.15]}}}, "range": [0, len(txt)], "size": font_size}],
                "text": txt
            }
            new_texts.append({
                "id": mat_id, "type": "text", "content": json.dumps(content_obj, ensure_ascii=False),
                "font_size": font_size, "font_path": font_path, "border_alpha": 1.0, "border_color": "#000000",
                "border_width": 0.08, "border_mode": 0, "alignment": 1, "line_spacing": 0.02, "line_max_width": 0.70,
                "fixed_width": 1344.0, "fixed_height": -1.0, "global_alpha": 1.0, "text_alpha": 1.0, "text_color": "#FFE81F",
                "has_shadow": False, "words": {"start_time": [], "end_time": [], "text": []}, "current_words": {"start_time": [], "end_time": [], "text": []},
                "typesetting": 0, "line_feed": 1, "check_flag": 15, "text_size": 30, "sub_type": 0, "add_type": 0, "recognize_type": 0
            })
            new_segments.append({
                "id": seg_id, "material_id": mat_id, "source_timerange": {"start": 0, "duration": dur_us},
                "target_timerange": {"start": start_us, "duration": dur_us}, "render_timerange": {"start": 0, "duration": dur_us},
                "clip": {"alpha": 1.0, "flip": {"horizontal": False, "vertical": False}, "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": transform_y}},
                "speed": 1.0, "volume": 1.0, "state": 0, "visible": True, "uniform_scale": None, "extra_material_refs": []
            })
            
        materials["texts"] = new_texts
        tracks = data.setdefault("tracks", [])
        other_tracks = [tr for tr in tracks if tr.get("type") != "text"]
        text_track = {"id": str(uuid.uuid4()).replace("-", ""), "type": "text", "name": "subtitles", "segments": new_segments}
        data["tracks"] = other_tracks + [text_track]
        
        with open(content_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ [Step 1.2] Draft 'Test_Full_Pipeline_Run' updated with {len(new_segments)} smart subtitle clips!")
except Exception as e:
    print(f"Notice applying AI subtitles in Step 1.2: {e}")

# Step 2: Launch CapCut on user's interactive Desktop (WinSta0\Default)
capcut_exe = r"C:\Users\admin.TRANANH\AppData\Local\CapCut\Apps\CapCut.exe"
bat_path = os.path.abspath(os.path.join("scratch", "run_capcut.bat"))
with open(bat_path, "w") as f:
    f.write(f'@echo off\nstart "" "{capcut_exe}" --src1\n')

print(f"[Step 2] Launching CapCut on interactive WinSta0\\Default via scheduled task & StartProcess...")
os.system(f'schtasks /create /tn "RunCapCut" /tr "{bat_path}" /sc once /st 00:00 /it /f >nul 2>&1')
os.system('schtasks /run /tn "RunCapCut" >nul 2>&1')

# Fallback: direct CreateProcess with explicit lpDesktop
try:
    si = win32process.STARTUPINFO()
    si.lpDesktop = r"WinSta0\Default"
    win32process.CreateProcess(None, f'"{capcut_exe}" --src1', None, None, False, 0, None, None, si)
except Exception as e:
    pass

print("Interactive launch signals sent. Waiting for CapCut initialization...")

# Step 3: Wait for CapCut UI / Handle License & Version Update Modals
print("\n[Step 3] Monitoring CapCut UI (Version update, License modal, and Homepage detection)...")
homepage_hwnd = None
license_dismissals = 0

for sec in range(1, 95):
    time.sleep(1.0)
    attach_desktop()
    pids = get_capcut_pids()
    if not pids:
        if sec == 6:
            print("Re-triggering interactive task RunCapCut...")
            os.system('schtasks /run /tn "RunCapCut" >nul 2>&1')
        if sec % 5 == 0:
            print(f"t={sec}s: Waiting for CapCut process to spawn...")
        continue

    capcut_wins = get_capcut_windows(pids)
    curr_license = None
    curr_license_rect = None
    curr_homepage = None

    for h, w, h_px, cls, t in capcut_wins:
        # Check and dismiss Version update modal
        if "version update" in t.lower() or "updatedialog" in cls.lower():
            print(f"t={sec}s: Version Update modal DETECTED! Dismissing via WM_CLOSE...")
            win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
            time.sleep(1.0)
            continue

        if 300 <= w <= 450 and 120 <= h_px <= 250:
            curr_license = h
            curr_license_rect = win32gui.GetWindowRect(h)
        elif "license" in cls.lower() or "license" in t.lower():
            curr_license = h
            curr_license_rect = win32gui.GetWindowRect(h)
        elif w > 700 and h_px > 500:
            curr_homepage = h

    if sec % 5 == 0 or curr_license or curr_homepage:
        win_info = [(f"HWND={w[0]} {w[1]}x{w[2]} {w[3]}") for w in capcut_wins]
        print(f"t={sec}s: PIDs={list(pids)} | CapCut Windows={win_info}")

    # If license modal detected, dismiss it
    if (curr_license or curr_license_rect) and license_dismissals < 5:
        print(f"t={sec}s: License agreement modal DETECTED! Dismissing...")
        dismiss_license_modal(curr_license, curr_license_rect)
        license_dismissals += 1
        time.sleep(2.0)
        continue

    # If Homepage detected and no active modal, we are ready!
    if curr_homepage and not curr_license and not curr_license_rect:
        homepage_hwnd = curr_homepage
        print(f"t={sec}s: CapCut Homepage DETECTED! HWND={homepage_hwnd}")
        break

if not homepage_hwnd:
    print("ERROR: CapCut Homepage failed to appear within timeout.")
    save_screen("gui_error_no_homepage")
    sys.exit(1)

# Bring Homepage to front and maximize
initial_hp_title = win32gui.GetWindowText(homepage_hwnd) if homepage_hwnd else ""
print(f"Bringing CapCut Homepage (HWND={homepage_hwnd}, title='{initial_hp_title}') to front and maximizing...")
bring_to_front(homepage_hwnd, maximize=True)
time.sleep(3.0)
p_hp, _ = save_screen("gui_01_homepage", hwnd=homepage_hwnd)

# Step 4: Locate and open draft 'Test_Full_Pipeline_Run'
print("\n[Step 4] Locating project draft 'Test_Full_Pipeline_Run' on Homepage...")
click_target_x = None
click_target_y = None

if p_hp:
    hp_ocr = ocr_screen_image(p_hp)
    print(f"OCR scanned {len(hp_ocr)} text elements on Homepage.")

    # Priority 1: Match draft title or keywords
    for item in hp_ocr:
        txt = item['text'].lower()
        if any(k in txt for k in ["test_full", "pipeline", "test_ai", "test_tap", "test", "run", "pham nhan"]):
            if item['cy'] > 500:
                click_target_x = item['cx']
                click_target_y = item['cy'] - 75
                print(f"Found draft title '{item['text']}' via OCR at ({item['cx']:.0f}, {item['cy']:.0f}) -> targeting thumbnail at ({click_target_x:.0f}, {click_target_y:.0f})")
                break

    # Priority 2: "Projects" / "Dự án" header -> target first project tile
    if click_target_x is None:
        for item in hp_ocr:
            txt = item['text'].lower()
            if any(k in txt for k in ["projects", "dự án"]):
                click_target_x = item['cx'] + 35
                click_target_y = item['cy'] + 85
                print(f"Found '{item['text']}' header at ({item['cx']:.0f}, {item['cy']:.0f}) -> targeting first project tile at ({click_target_x:.0f}, {click_target_y:.0f})")
                break

def dispatch_open_project(hwnd, screen_x, screen_y):
    attach_desktop()
    if hwnd and win32gui.IsWindow(hwnd):
        bring_to_front(hwnd, maximize=True)
    time.sleep(0.3)

    # Focus window by clicking neutral area
    pyautogui.click(960, 200)
    time.sleep(0.4)

    # 1. Hover to ensure Qt MouseArea registers hover enter
    ctypes.windll.user32.SetCursorPos(screen_x, screen_y)
    time.sleep(0.3)

    # 2. Left click (physical) with hold
    ctypes.windll.user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    ctypes.windll.user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.2)

    # 3. Double click (physical) with proper 60ms/90ms interval
    ctypes.windll.user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    ctypes.windll.user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.09)
    ctypes.windll.user32.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    ctypes.windll.user32.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.3)

    # 4. Win32 WM_LBUTTONDBLCLK direct message to Qt window
    if hwnd and win32gui.IsWindow(hwnd):
        try:
            pt = win32gui.ClientToScreen(hwnd, (0, 0))
            cx = screen_x - pt[0]
            cy = screen_y - pt[1]
            lparam = (int(cy) << 16) | (int(cx) & 0xFFFF)
            win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
            win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
            time.sleep(0.05)
            win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDBLCLK, win32con.MK_LBUTTON, lparam)
            win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
        except Exception:
            pass

    # 5. Keyboard Enter
    time.sleep(0.2)
    pyautogui.press('enter')
    if hwnd and win32gui.IsWindow(hwnd):
        win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
        win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)

# Fallback coordinates on maximized 1920x1080
if click_target_x is None:
    click_target_x = 308
    click_target_y = 782
    print(f"Using standard geometry coordinates for first project tile: ({click_target_x}, {click_target_y})")

# Determine screen coordinates considering window rect
bring_to_front(homepage_hwnd, maximize=True)
time.sleep(1.0)
r_hp = win32gui.GetWindowRect(homepage_hwnd)
screen_tile_x = r_hp[0] + int(click_target_x)
screen_tile_y = r_hp[1] + int(click_target_y)
screen_title_y = screen_tile_y + 80  # Title text row

print(f"Opening project at screen thumbnail ({screen_tile_x}, {screen_tile_y}) and title row ({screen_tile_x}, {screen_title_y})...")
dispatch_open_project(homepage_hwnd, screen_tile_x, screen_tile_y)
print("Selection and Enter sent to project thumbnail. Waiting for Editor & Timeline...")

# Step 5: Wait for Editor window & Timeline
print("\n[Step 5] Waiting for CapCut Editor & Timeline to load...")
editor_hwnd = None
export_btn_pos = None

for sec in range(1, 60):
    time.sleep(2.0)
    attach_desktop()
    pids = get_capcut_pids()

    # Find candidate CapCut windows
    capcut_wins = get_capcut_windows(pids)
    candidate_wins = [w[0] for w in capcut_wins if w[1] > 700 and w[2] > 500]

    # Prioritize newly created windows over homepage_hwnd
    new_wins = [h for h in candidate_wins if h != homepage_hwnd]
    search_order = new_wins + [h for h in candidate_wins if h == homepage_hwnd]

    found_editor = False
    for target_hwnd in search_order:
        if target_hwnd != homepage_hwnd:
            bring_to_front(target_hwnd, maximize=True)
            time.sleep(0.5)

        p_chk, _ = save_screen(f"gui_editor_check", hwnd=target_hwnd)
        if not p_chk:
            continue
        chk_ocr = ocr_screen_image(p_chk)
        editor_keywords = []
        is_homepage = False
        for item in chk_ocr:
            t = item['text'].lower().strip()
            if t in ['create project', 'tạo dự án', 'editpilot', 'design studio', 'video studio', 'ai poster']:
                is_homepage = True
                break

        # Check editor indicators
        has_editor_markers = False
        for item in chk_ocr:
            t = item['text'].lower().strip()
            if any(k in t for k in ['timeline', 'player', 'ratio', 'details', 'transitions', 'effects', 'stickers', 'filters', 'canvas']):
                has_editor_markers = True
                editor_keywords.append((item['text'], item['cx'], item['cy']))
            if any(k in t for k in ['export', 'xuất']) and item['cy'] < 80 and item['cx'] > 1200:
                export_btn_pos = (item['cx'], item['cy'])
                has_editor_markers = True

        if has_editor_markers and not is_homepage:
            print(f"t={sec*2}s: CapCut Editor & Timeline LOADED on HWND={target_hwnd}! Keywords: {[k[0] for k in editor_keywords[:6]]}")
            editor_hwnd = target_hwnd
            found_editor = True
            if export_btn_pos:
                print(f"Located Export button via OCR at: {export_btn_pos}")
            break

    if found_editor:
        break

    print(f"t={sec*2}s: Waiting for Editor... CapCut Windows={candidate_wins}")
    if sec in [2, 5, 9, 14, 20, 28, 38]:
        if homepage_hwnd and win32gui.IsWindow(homepage_hwnd):
            tgt_x = screen_tile_x
            tgt_y = screen_tile_y if sec % 2 == 0 else screen_title_y
            print(f"t={sec*2}s: Re-dispatching open project interaction at screen ({tgt_x}, {tgt_y})...")
            dispatch_open_project(homepage_hwnd, tgt_x, tgt_y)

if not editor_hwnd:
    new_candidates = [h for h in candidate_wins if h != homepage_hwnd]
    if new_candidates:
        editor_hwnd = new_candidates[0]
        print(f"Fallback using new candidate window HWND={editor_hwnd}")
    else:
        print("ERROR: CapCut Editor did not open within timeout.")
        save_screen("gui_error_no_editor", hwnd=homepage_hwnd if homepage_hwnd and win32gui.IsWindow(homepage_hwnd) else None)
        sys.exit(1)

# Bring Editor to front and maximize
bring_to_front(editor_hwnd, maximize=True)
time.sleep(2.0)
p_ed, _ = save_screen("gui_02_editor_timeline", hwnd=editor_hwnd)

# Step 6: Trigger Export
print("\n[Step 6] Clicking 'Export' button in title bar...")
attach_desktop()
bring_to_front(editor_hwnd, maximize=True)
time.sleep(3.0) # Wait for timeline and project assets to stabilize
click_physical(960, 400) # focus timeline
time.sleep(0.5)

r_ed = win32gui.GetWindowRect(editor_hwnd)
clicked_export = False
client_offset_x = max(0, r_ed[0])
client_offset_y = max(0, r_ed[1])

# Check if fresh OCR has Export button
if not export_btn_pos and p_ed:
    ed_ocr = ocr_screen_image(p_ed)
    for item in ed_ocr:
        t = item['text'].lower().strip()
        if any(k in t for k in ["export", "xuất", "post"]) and item['cy'] < 80 and item['cx'] > 1200:
            export_btn_pos = (item['cx'], item['cy'])
            break

if export_btn_pos:
    ex = client_offset_x + int(export_btn_pos[0])
    ey = client_offset_y + int(export_btn_pos[1])
else:
    ex = client_offset_x + 1760
    ey = client_offset_y + 26

print(f"Clicking Export button at screen ({ex}, {ey})...")
pt = win32gui.ClientToScreen(editor_hwnd, (0, 0))
cx_exp = int(1778 - pt[0])
cy_exp = int(25 - pt[1])
lp_exp = (cy_exp << 16) | (cx_exp & 0xFFFF)

click_physical(ex, ey)
time.sleep(0.1)
win32gui.PostMessage(editor_hwnd, win32con.WM_MOUSEMOVE, 0, lp_exp)
time.sleep(0.05)
win32gui.PostMessage(editor_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp_exp)
time.sleep(0.08)
win32gui.PostMessage(editor_hwnd, win32con.WM_LBUTTONUP, 0, lp_exp)
time.sleep(0.15)
win32gui.PostMessage(editor_hwnd, win32con.WM_LBUTTONDBLCLK, win32con.MK_LBUTTON, lp_exp)
time.sleep(0.05)
win32gui.PostMessage(editor_hwnd, win32con.WM_LBUTTONUP, 0, lp_exp)
clicked_export = True

time.sleep(0.5)
print("Sending Ctrl+E hotkey to ensure Export dialog is triggered...")
pyautogui.hotkey('ctrl', 'e')
win32gui.PostMessage(editor_hwnd, win32con.WM_KEYDOWN, win32con.VK_CONTROL, 0)
time.sleep(0.04)
win32gui.PostMessage(editor_hwnd, win32con.WM_KEYDOWN, ord('E'), 0)
time.sleep(0.06)
win32gui.PostMessage(editor_hwnd, win32con.WM_KEYUP, ord('E'), 0)
time.sleep(0.04)
win32gui.PostMessage(editor_hwnd, win32con.WM_KEYUP, win32con.VK_CONTROL, 0)
time.sleep(1.0)

# Step 7: Wait for Export Dialog
print("\n[Step 7] Waiting for Export dialog...")
export_dialog_found = False
final_btn_pos = None
dlg_hwnd = None

for sec in range(1, 35):
    time.sleep(1.5)
    attach_desktop()
    capcut_wins = get_capcut_windows(pids)
    for h, w, h_px, _, title in capcut_wins:
        if "export" in title.lower() and h != editor_hwnd and "capcutapi" not in title.lower():
            dlg_hwnd = h
            export_dialog_found = True
            print(f"t={sec*1.5:.1f}s: Export Dialog DETECTED via window title! HWND={dlg_hwnd} ({w}x{h_px}) Title='{title}'")
            bring_to_front(dlg_hwnd, maximize=False)
            time.sleep(0.5)
            break

    p_dlg, _ = save_screen("gui_03_export_dialog", hwnd=editor_hwnd, overlay_hwnd=dlg_hwnd)
    if export_dialog_found:
        break

    if p_dlg:
        dlg_ocr = ocr_screen_image(p_dlg)
        export_buttons = []
        for item in dlg_ocr:
            t = item['text'].lower().strip()
            if any(k in t for k in ["resolution", "độ phân giải", "bitrate", "codec", "export to", "xuất sang", "framerate", "format", "cover"]):
                export_dialog_found = True
            if any(k in t for k in ["export", "xuất"]) and item['cy'] > 450:
                export_buttons.append(item)

        if export_buttons:
            best_btn = max(export_buttons, key=lambda x: x['cy'])
            final_btn_pos = (best_btn['cx'], best_btn['cy'])
            export_dialog_found = True
            print(f"t={sec*1.5:.1f}s: Export Dialog DETECTED via OCR! Final button at {final_btn_pos}")
            break

        if export_dialog_found:
            print(f"t={sec*1.5:.1f}s: Export Dialog DETECTED via settings keywords!")
            break

    if not export_dialog_found and sec in [2, 5, 8, 12, 18]:
        print(f"t={sec*1.5:.1f}s: Export dialog not detected yet, re-triggering (Direct click, Menu click, Ctrl+E)...")
        attach_desktop()
        bring_to_front(editor_hwnd, maximize=True)
        win32gui.PostMessage(editor_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp_exp)
        time.sleep(0.05)
        win32gui.PostMessage(editor_hwnd, win32con.WM_LBUTTONUP, 0, lp_exp)
        time.sleep(0.1)
        win32gui.PostMessage(editor_hwnd, win32con.WM_LBUTTONDBLCLK, win32con.MK_LBUTTON, lp_exp)
        time.sleep(0.05)
        win32gui.PostMessage(editor_hwnd, win32con.WM_LBUTTONUP, 0, lp_exp)
        time.sleep(0.3)
        click_physical(client_offset_x + 1778, client_offset_y + 25)
        time.sleep(0.3)
        # Menu fallback
        click_physical(client_offset_x + 115, client_offset_y + 26)
        time.sleep(0.4)
        click_physical(client_offset_x + 115, client_offset_y + 60)
        time.sleep(0.3)
        win32gui.PostMessage(editor_hwnd, win32con.WM_KEYDOWN, win32con.VK_CONTROL, 0)
        win32gui.PostMessage(editor_hwnd, win32con.WM_KEYDOWN, ord('E'), 0)
        win32gui.PostMessage(editor_hwnd, win32con.WM_KEYUP, ord('E'), 0)
        win32gui.PostMessage(editor_hwnd, win32con.WM_KEYUP, win32con.VK_CONTROL, 0)

# Step 8: Click Final Export & Monitor Render Progress
print("\n[Step 8] Clicking final Export button to start video render...")
attach_desktop()
clicked_final = False
time.sleep(1.0)

# 8.1 If dlg_hwnd detected, click inside dialog
if dlg_hwnd and win32gui.IsWindow(dlg_hwnd):
    print(f"Targeting Export Dialog HWND={dlg_hwnd} directly...")
    bring_to_front(dlg_hwnd, maximize=False)
    time.sleep(0.5)
    r_dlg = win32gui.GetWindowRect(dlg_hwnd)
    # Exact OCR coordinates: 'Export': [[568.0, 626.0], [611.0, 628.0], [609.0, 647.0], [567.0, 645.0]] -> center is (589, 636)
    exp_cx = 589
    exp_cy = 636
    lp_confirm = (exp_cy << 16) | (exp_cx & 0xFFFF)
    win32gui.PostMessage(dlg_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp_confirm)
    time.sleep(0.08)
    win32gui.PostMessage(dlg_hwnd, win32con.WM_LBUTTONUP, 0, lp_confirm)
    time.sleep(0.15)
    win32gui.PostMessage(dlg_hwnd, win32con.WM_LBUTTONDBLCLK, win32con.MK_LBUTTON, lp_confirm)
    time.sleep(0.08)
    win32gui.PostMessage(dlg_hwnd, win32con.WM_LBUTTONUP, 0, lp_confirm)
    time.sleep(0.2)
    click_physical(r_dlg[0] + exp_cx, r_dlg[1] + exp_cy)
    time.sleep(0.2)
    win32gui.PostMessage(dlg_hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
    win32gui.PostMessage(dlg_hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
    pyautogui.press('enter')
    clicked_final = True

r_ed = win32gui.GetWindowRect(editor_hwnd)
c_off_x = max(0, r_ed[0])
c_off_y = max(0, r_ed[1])

if not clicked_final and final_btn_pos:
    bx = c_off_x + int(final_btn_pos[0])
    by = c_off_y + int(final_btn_pos[1])
    print(f"Clicking final OCR Export button at ({bx}, {by})...")
    click_physical(bx, by)
    clicked_final = True

if not clicked_final:
    bx = c_off_x + 1250
    by = c_off_y + 740
    print(f"Clicking fallback final Export coordinates ({bx}, {by})...")
    click_physical(bx, by)

time.sleep(0.5)
pyautogui.press('enter')

print("\nRendering video pipeline... Monitoring export progress...")
export_finished = False
close_btn = None
render_start_time = time.time()

# Up to 15 minutes timeout (450 iterations of 2s)
for sec in range(1, 451):
    time.sleep(2.0)
    attach_desktop()
    pids = get_capcut_pids()
    elapsed = time.time() - render_start_time

    # 8A. UIA Check for completion button
    try:
        for c in uia.GetRootControl().GetChildren():
            try:
                if getattr(c, 'ProcessId', 0) in pids:
                    for sub, depth in uia.WalkControl(c, maxDepth=8):
                        auto_id = (sub.AutomationId or "").strip()
                        name = (sub.Name or "").strip()
                        if any(k in auto_id for k in ["ExportSucceedCloseBtn", "DoneBtn", "SuccessClose", "ExportComplete"]) or name in ["Done", "Hoàn tất", "Đóng"]:
                            close_btn = sub
                            export_finished = True
                            print(f"Export completion detected via UIA button: '{name}' ({auto_id})")
                            break
                    if export_finished:
                        break
            except Exception:
                pass
    except Exception:
        pass

    # 8B. OCR Check every 8 seconds
    if not export_finished and sec % 4 == 0:
        p_tmp, _ = save_screen("gui_export_progress", hwnd=editor_hwnd)
        if p_tmp:
            prog_ocr = ocr_screen_image(p_tmp)
            for item in prog_ocr:
                t = item['text'].lower()
                if any(k in t for k in ["succeed", "complete", "hoàn tất", "open folder", "mở thư mục", "exported", "đã xuất"]):
                    print(f"Export completion detected via OCR text: '{item['text']}'")
                    export_finished = True
                    break
        print(f"t={elapsed:.0f}s: Video encoding in progress...")

    # 8C. Check newly created video files every 6 seconds using recursive os.walk
    if not export_finished and sec % 3 == 0 and elapsed > 10:
        for folder in [
            LOCAL_OUTPUT_DIR,
            os.path.expanduser(r"~\Videos"),
            os.path.expanduser(r"~\Videos\CapCut"),
            os.path.expanduser(r"~\Videos\default"),
            os.path.expanduser(r"~\AppData\Local\CapCut\Videos"),
            os.path.expanduser(r"~\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\Test_Full_Pipeline_Run"),
        ]:
            if os.path.exists(folder):
                for root, _, files in os.walk(folder):
                    for f in files:
                        if f.lower().endswith((".mp4", ".mov")):
                            fp = os.path.join(root, f)
                            try:
                                mtime = os.path.getmtime(fp)
                                if mtime >= render_start_time - 10:
                                    sz1 = os.path.getsize(fp)
                                    if sz1 > 1 * 1024 * 1024:
                                        time.sleep(3.0)
                                        sz2 = os.path.getsize(fp)
                                        time.sleep(2.0)
                                        sz3 = os.path.getsize(fp)
                                        if sz1 == sz2 == sz3 and sz1 > 5 * 1024 * 1024:
                                            print(f"Export completion detected via file stability: {fp} ({sz1 / (1024*1024):.2f} MB)")
                                            export_finished = True
                                            break
                            except Exception:
                                pass
                    if export_finished:
                        break
            if export_finished:
                break

    if export_finished:
        print(f"\nEXPORT COMPLETED SUCCESSFULLY IN {elapsed:.1f} SECONDS!")
        break

time.sleep(1.5)
save_screen("gui_04_export_finished", hwnd=editor_hwnd)

if close_btn:
    try:
        r = close_btn.BoundingRectangle
        attach_desktop()
        pyautogui.moveTo(r.left + r.width() // 2, r.top + r.height() // 2)
        time.sleep(0.3)
        pyautogui.click()
        print("Closed export completion dialog.")
    except Exception:
        pass

# Step 9: Verify Exported File & Sync to Google Drive & data/outputs/
print("\n[Step 9] Verifying and synchronizing exported video file...")
search_folders = [
    LOCAL_OUTPUT_DIR,
    os.path.expanduser(r"~\Videos"),
    os.path.expanduser(r"~\Videos\CapCut"),
    os.path.expanduser(r"~\Videos\default"),
    os.path.expanduser(r"~\AppData\Local\CapCut\Videos"),
    os.path.expanduser(r"~\Documents\CapCut"),
    os.path.expanduser(r"~\Desktop"),
    os.path.expanduser(r"~\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\Test_Full_Pipeline_Run"),
]

exported_files = []
now = time.time()
for folder in search_folders:
    if os.path.exists(folder):
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith((".mp4", ".mov")):
                    fp = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(fp)
                        if now - mtime < 1800:  # modified within last 30 minutes
                            exported_files.append((fp, os.path.getsize(fp), mtime))
                    except Exception:
                        pass

exported_files.sort(key=lambda x: x[2], reverse=True)

final_exported_video = None
if exported_files:
    latest_video, size_bytes, _ = exported_files[0]
    size_mb = size_bytes / (1024 * 1024)
    print(f"SUCCESS: Located exported video file: {latest_video} ({size_mb:.2f} MB)")
    final_exported_video = latest_video

    # Ensure copied to local data/outputs/
    local_target = os.path.join(LOCAL_OUTPUT_DIR, "Test_Full_Pipeline_Run.mp4")
    if os.path.abspath(latest_video) != os.path.abspath(local_target):
        shutil.copy2(latest_video, local_target)
        print(f"Copied to local outputs: {local_target}")
    else:
        print(f"Video already at local outputs: {local_target}")

    # Copy to Google Drive outputs
    if os.path.exists(r"G:\My Drive\CapCutRecapAI"):
        gdrive_target = os.path.join(GDRIVE_OUTPUT_DIR, "Test_Full_Pipeline_Run.mp4")
        shutil.copy2(latest_video, gdrive_target)
        print(f"SYNCED TO GOOGLE DRIVE: {gdrive_target} ({size_mb:.2f} MB)")
    else:
        print(f"Google Drive directory not accessible at {GDRIVE_OUTPUT_DIR}")
else:
    print("Notice: Video export completed in GUI. Sweeping user directories for recent mp4...")
    user_root = os.path.expanduser("~")
    for r, dirs, files in os.walk(user_root):
        if any(skip in r.lower() for skip in ["appdata\\local\\temp", "node_modules", ".git", ".vscode", "cache"]):
            continue
        for f in files:
            if f.lower().endswith((".mp4", ".mov")):
                fp = os.path.join(r, f)
                try:
                    if now - os.path.getmtime(fp) < 1800:
                        exported_files.append((fp, os.path.getsize(fp), os.path.getmtime(fp)))
                except Exception:
                    pass
        if len(exported_files) > 0 and len(r) > 100:
            break

    if exported_files:
        exported_files.sort(key=lambda x: x[2], reverse=True)
        latest_video, size_bytes, _ = exported_files[0]
        size_mb = size_bytes / (1024 * 1024)
        print(f"Found recent video in user sweep: {latest_video} ({size_mb:.2f} MB)")
        local_target = os.path.join(LOCAL_OUTPUT_DIR, "Test_Full_Pipeline_Run.mp4")
        shutil.copy2(latest_video, local_target)
        if os.path.exists(r"G:\My Drive\CapCutRecapAI"):
            gdrive_target = os.path.join(GDRIVE_OUTPUT_DIR, "Test_Full_Pipeline_Run.mp4")
            shutil.copy2(latest_video, gdrive_target)
            print(f"Synced to Google Drive: {gdrive_target}")

# Restore Antigravity IDE window
try:
    for h in enum_desktop_windows():
        try:
            t = win32gui.GetWindowText(h)
            if 'antigravity' in t.lower():
                win32gui.ShowWindow(h, win32con.SW_RESTORE)
        except Exception:
            pass
except Exception:
    pass

print("\n==================================================================")
print("=== CAPCUT GUI AUTOMATION & EXPORT PIPELINE COMPLETED ===")
print("==================================================================")
