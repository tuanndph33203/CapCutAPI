"""CapCut desktop UI automation for export workflows.

This is a CapCut-international variant of ``jianying_controller.py``. It uses
Windows UI Automation where possible and falls back to descriptive text matches
that are visible in recent CapCut desktop builds.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from enum import Enum
from logging.handlers import RotatingFileHandler
from typing import Callable, Literal, Optional

import uiautomation as uia
import win32con
import win32gui
import win32process

from . import exceptions
from .exceptions import AutomationError


logger = logging.getLogger("capcut_controller")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(os.path.join(log_dir, "capcut_controller.log"), backupCount=5, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def capcut_process_ids() -> set[int]:
    try:
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", "Get-Process CapCut -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return {int(line.strip()) for line in output.splitlines() if line.strip().isdigit()}
    except Exception:
        return set()


def capcut_main_hwnd_and_rect() -> tuple[int, tuple[int, int, int, int]] | None:
    pids = capcut_process_ids()
    best: tuple[int, tuple[int, int, int, int], int] | None = None

    def enum_proc(hwnd, _):
        nonlocal best
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid not in pids:
            return
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if "CapCut" not in title or "Qt" not in class_name:
            return
        rect = win32gui.GetWindowRect(hwnd)
        area = max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])
        if area < 400 * 300:
            return
        if best is None or area > best[2]:
            best = (hwnd, rect, area)

    win32gui.EnumWindows(enum_proc, None)
    if best is None:
        return None
    return best[0], best[1]


def activate_capcut_main_window() -> tuple[int, int, int, int] | None:
    found = capcut_main_hwnd_and_rect()
    if found is None:
        return None
    hwnd, rect = found
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    return rect


class ExportResolution(Enum):
    RES_4K = "4K"
    RES_2K = "2K"
    RES_1080P = "1080P"
    RES_720P = "720P"
    RES_480P = "480P"


class ExportFramerate(Enum):
    FR_24 = "24fps"
    FR_25 = "25fps"
    FR_30 = "30fps"
    FR_50 = "50fps"
    FR_60 = "60fps"


class ControlFinder:
    @staticmethod
    def prop(control: uia.Control, prop_id: int) -> str:
        try:
            value = control.GetPropertyValue(prop_id)
            return value if isinstance(value, str) else ""
        except Exception:
            return ""

    @staticmethod
    def text_blob(control: uia.Control) -> str:
        parts = [
            getattr(control, "Name", "") or "",
            getattr(control, "ClassName", "") or "",
            ControlFinder.prop(control, 30159),
            ControlFinder.prop(control, uia.PropertyId.AutomationIdProperty),
        ]
        return " ".join(parts).lower()

    @staticmethod
    def desc_matcher(target_desc: str, depth: int = 2, exact: bool = False) -> Callable[[uia.Control, int], bool]:
        target_desc = target_desc.lower()

        def matcher(control: uia.Control, current_depth: int) -> bool:
            if current_depth != depth:
                return False
            text = ControlFinder.text_blob(control)
            return target_desc == text if exact else target_desc in text

        return matcher

    @staticmethod
    def any_text_matcher(targets: list[str], max_depth: int = 6) -> Callable[[uia.Control, int], bool]:
        needles = [target.lower() for target in targets]

        def matcher(control: uia.Control, current_depth: int) -> bool:
            if current_depth > max_depth:
                return False
            text = ControlFinder.text_blob(control)
            return any(needle in text for needle in needles)

        return matcher


class CapCutController:
    app: uia.WindowControl
    app_status: Literal["home", "edit", "pre_export", "unknown"]

    def __init__(self):
        import ctypes
        try:
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass
        self.export_progress = {"status": "idle", "percent": 0.0, "message": "", "start_time": 0}
        self.get_window()

    def get_export_progress(self) -> dict:
        if self.export_progress["status"] != "idle":
            self.export_progress["elapsed"] = time.time() - self.export_progress["start_time"]
        return self.export_progress

    def get_window(self) -> None:
        activate_capcut_main_window()
        if hasattr(self, "app") and self.app.Exists(0):
            self.app.SetTopmost(False)

        self.app = self.find_main_window()
        if self.app is None or not self.app.Exists(0):
            raise AutomationError("CapCut window not found")

        export_window = self.app.WindowControl(searchDepth=2, Compare=ControlFinder.any_text_matcher(["Export"], max_depth=2))
        if export_window.Exists(0):
            self.app = export_window
            self.app_status = "pre_export"

        self.app.SetActive()
        self.app.SetTopmost()

    def find_main_window(self) -> Optional[uia.WindowControl]:
        candidates = []
        for control in uia.GetRootControl().GetChildren():
            try:
                if self._capcut_window_cmp(control, 1):
                    rect = control.BoundingRectangle
                    candidates.append((rect.width() * rect.height(), control))
            except Exception:
                continue
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _capcut_window_cmp(self, control: uia.WindowControl, depth: int) -> bool:
        if depth != 1:
            return False
        pids = capcut_process_ids()
        if not pids or getattr(control, "ProcessId", 0) not in pids:
            return False
        name = (control.Name or "").lower()
        class_name = (control.ClassName or "").lower()
        if "capcut" not in name and "qt" not in class_name:
            return False
        rect = control.BoundingRectangle
        if rect.width() < 400 or rect.height() < 300:
            return False
        if "homepage" in class_name or "homepage" in name:
            self.app_status = "home"
        elif "main" in class_name or "edit" in class_name:
            self.app_status = "edit"
        else:
            self.app_status = "unknown"
        return True

    def find_first(self, targets: list[str], *, max_depth: int = 8, timeout: float = 0) -> Optional[uia.Control]:
        end = time.time() + timeout
        while True:
            control = self.app.Control(searchDepth=max_depth, Compare=ControlFinder.any_text_matcher(targets, max_depth=max_depth))
            if control.Exists(0):
                return control
            if timeout <= 0 or time.time() >= end:
                return None
            time.sleep(0.5)

    def click_first(self, targets: list[str], *, max_depth: int = 8, timeout: float = 30) -> uia.Control:
        control = self.find_first(targets, max_depth=max_depth, timeout=timeout)
        if control is None:
            raise AutomationError(f"Could not find UI control matching: {targets}")
        control.Click(simulateMove=False)
        return control

    def open_draft(self, draft_name: str, timeout: float = 60) -> None:
        self.get_window()
        if self.find_first(["MainWindowTitleBarExportBtn", "Export"], max_depth=8, timeout=0):
            self.app_status = "edit"
            logger.info("CapCut editor is already open; exporting the current draft.")
            return

        logger.info("Đang tìm dự án đầu tiên...")
        draft_control = self.find_first(
            ["HomePageDraftTitle:"],
            max_depth=15,
            timeout=timeout,
        )
        if draft_control is None:
            logger.warning("Draft '%s' was not visible via UIA; clicking the first project tile fallback.", draft_name)
            if not self.click_first_project_tile_fallback():
                raise exceptions.DraftNotFound(f"No CapCut draft named '{draft_name}' found")
            time.sleep(8)
            self.app_status = "edit"
            return
        parent = draft_control.GetParentControl()
        (parent or draft_control).Click(simulateMove=False)

        start = time.time()
        while time.time() - start < 180:
            self.get_window()
            if self.find_first(["MainWindowTitleBarExportBtn", "Export"], max_depth=8, timeout=0):
                self.app_status = "edit"
                return
            time.sleep(1)
        raise AutomationError("Timed out waiting for CapCut editor")

    def export_draft(
        self,
        draft_name: str,
        output_path: Optional[str] = None,
        *,
        resolution: Optional[ExportResolution] = None,
        framerate: Optional[ExportFramerate] = None,
        timeout: float = 1200,
    ) -> None:
        self.export_progress = {"status": "exporting", "percent": 0.0, "message": "starting export", "start_time": time.time()}
        self.open_draft(draft_name)
        self.export_progress.update({"percent": 15.0, "message": "opening export dialog"})

        self.click_export_button()
        self.wait_for_export_dialog()
        self.export_progress.update({"percent": 20.0, "message": "export dialog ready"})

        export_path = self.read_export_path()
        if resolution is not None:
            try:
                self.select_dropdown(["ExportSharpnessInput", "resolution"], resolution.value)
            except AutomationError as exc:
                logger.warning("Could not set resolution via UIA; keeping current CapCut setting: %s", exc)
        if framerate is not None:
            try:
                self.select_dropdown(["FrameRateInput", "frame rate", "framerate"], framerate.value)
            except AutomationError as exc:
                logger.warning("Could not set framerate via UIA; keeping current CapCut setting: %s", exc)

        self.click_final_export_button()
        self.wait_for_export_finish(timeout=timeout)

        if output_path is not None and export_path and os.path.exists(export_path):
            shutil.move(export_path, output_path)
        self.export_progress.update({"status": "finished", "percent": 100, "message": "export finished"})

    def wait_for_export_dialog(self) -> None:
        start = time.time()
        while time.time() - start < 180:
            self.get_window()
            if self.find_first(["ExportPath", "ExportOkBtn", "Export"], max_depth=8, timeout=0):
                self.app_status = "pre_export"
                return
            time.sleep(1)
            if time.time() - start > 5:
                logger.warning("Export dialog was not visible via UIA; continuing with coordinate fallback.")
                self.app_status = "pre_export"
                return

    def click_first_project_tile_fallback(self) -> bool:
        rect = activate_capcut_main_window()
        if rect is None:
            return False
        left, top, _right, _bottom = rect
        # CapCut 8.8 home grid: first project tile center. This is intentionally
        # a fallback for builds that expose only the root window to UIA.
        x = left + 290
        y = top + 585
        logger.info("Clicking first project tile fallback at (%s, %s).", x, y)
        uia.Click(x, y)
        return True

    def click_export_button(self) -> None:
        control = self.find_first(["MainWindowTitleBarExportBtn", "Export"], max_depth=8, timeout=2)
        if control is not None:
            control.Click(simulateMove=False)
            return
        rect = self.app.BoundingRectangle
        win32_rect = activate_capcut_main_window()
        if win32_rect is not None:
            left, top, right, _bottom = win32_rect
            x = right - 155
            y = top + 18
        else:
            x = rect.right - 155
            y = rect.top + 18
        # CapCut 8.x international: Export button is near the top-right corner,
        # just left of minimize/maximize/close.
        logger.info("UIA export button not found; clicking fallback coordinates (%s, %s).", x, y)
        uia.Click(x, y)
        time.sleep(1)

    def click_final_export_button(self) -> None:
        control = self.find_first(["ExportOkBtn"], max_depth=8, timeout=2)
        if control is not None:
            control.Click(simulateMove=False)
            return
        rect = activate_capcut_main_window()
        if rect is None:
            raise AutomationError("CapCut window not found for final export click")
        _left, _top, right, bottom = rect
        # CapCut 8.8 export dialog: primary Export button is normally near the
        # lower-right corner. This fallback is used when UIA exposes no dialog
        # children.
        x = right - 105
        y = bottom - 55
        logger.info("UIA final export button not found; clicking fallback coordinates (%s, %s).", x, y)
        uia.Click(x, y)
        time.sleep(3)

    def read_export_path(self) -> str:
        export_path_label = self.find_first(["ExportPath"], max_depth=8, timeout=2)
        if not export_path_label:
            return ""
        sibling = export_path_label.GetSiblingControl(lambda ctrl: True)
        return ControlFinder.prop(sibling, 30159) if sibling else ""

    def select_dropdown(self, dropdown_targets: list[str], value: str) -> None:
        dropdown = self.click_first(dropdown_targets, max_depth=8, timeout=10)
        time.sleep(0.5)
        item = self.find_first([value], max_depth=8, timeout=5)
        if item is None:
            dropdown.Click(simulateMove=False)
            raise AutomationError(f"Could not find dropdown option: {value}")
        item.Click(simulateMove=False)
        time.sleep(0.5)

    def wait_for_export_finish(self, timeout: float) -> None:
        start = time.time()
        while time.time() - start < timeout:
            self.get_window()
            close_btn = self.find_first(["ExportSucceedCloseBtn", "Done", "Close"], max_depth=8, timeout=0)
            if close_btn is not None:
                close_btn.Click(simulateMove=False)
                return

            progress_text = self.find_progress_text()
            if progress_text:
                match = re.search(r"(\d+\.?\d*)%", progress_text)
                if match:
                    percent = float(match.group(1))
                    self.export_progress.update({"percent": percent * 0.8 + 20, "message": "exporting"})
            self.export_progress["elapsed"] = time.time() - self.export_progress["start_time"]
            time.sleep(1)
        self.export_progress.update({"status": "error", "message": f"export timed out after {timeout}s"})
        raise AutomationError(f"Export timed out after {timeout}s")

    def find_progress_text(self) -> str:
        for control in self.app.GetChildren():
            text = ControlFinder.text_blob(control)
            if "%" in text:
                return text
        return ""
