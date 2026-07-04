#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import psutil
import pyautogui
import win32gui
import win32process
from PIL import ImageGrab

try:
    from pyJianYingDraft.capcut_controller import capcut_main_hwnd_and_rect
except Exception:
    capcut_main_hwnd_and_rect = None


pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05
FAILSAFE_EDGE_MARGIN = 8


@dataclass
class WindowBox:
    hwnd: int
    title: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


def list_window_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def enum_window(hwnd: int, _: Any) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = max(0, right - left)
        height = max(0, bottom - top)
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            process_name = proc.name()
            process_path = proc.exe()
        except Exception as exc:
            pid = -1
            process_name = ""
            process_path = f"<error: {exc}>"
        haystack = f"{title} {class_name} {process_name} {process_path}".lower()
        if "capcut" not in haystack:
            return
        candidates.append({
            "hwnd": hwnd,
            "pid": pid,
            "title": title,
            "class_name": class_name,
            "process_name": process_name,
            "process_path": process_path,
            "rect": [left, top, right, bottom],
            "width": width,
            "height": height,
            "area": width * height,
        })

    win32gui.EnumWindows(enum_window, None)
    candidates.sort(key=lambda item: item["area"], reverse=True)
    return candidates


def write_window_debug_report(debug_report: Path, *, selected: WindowBox | None = None, reason: str | None = None) -> None:
    debug_report.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "reason": reason,
        "selected": None,
        "candidates": list_window_candidates(),
    }
    if selected is not None:
        payload["selected"] = {
            "hwnd": selected.hwnd,
            "title": selected.title,
            "rect": [selected.left, selected.top, selected.right, selected.bottom],
            "width": selected.width,
            "height": selected.height,
        }
    debug_report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def find_capcut_window(debug_report: Path | None = None) -> WindowBox:
    if capcut_main_hwnd_and_rect is not None:
        try:
            found = capcut_main_hwnd_and_rect()
            if found is not None:
                hwnd, rect = found
                title = win32gui.GetWindowText(hwnd) or "CapCut"
                selected = WindowBox(hwnd, title, rect[0], rect[1], rect[2], rect[3])
                if debug_report:
                    write_window_debug_report(debug_report, selected=selected, reason="selected via capcut_main_hwnd_and_rect")
                return selected
        except Exception:
            pass

    matches: list[WindowBox] = []

    def enum_window(hwnd: int, _: Any) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            process_name = proc.name().lower()
            process_path = (proc.exe() or "").lower()
            if process_name != "capcut.exe" and not process_path.endswith("\\capcut.exe"):
                return
        except Exception:
            return
        if "CapCut" not in title:
            return
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if right - left < 600 or bottom - top < 400:
            return
        matches.append(WindowBox(hwnd, title or "CapCut", left, top, right, bottom))

    win32gui.EnumWindows(enum_window, None)
    if not matches:
        if debug_report:
            write_window_debug_report(debug_report, reason="no matching CapCut.exe window found")
        raise RuntimeError("CapCut window not found")
    selected = sorted(matches, key=lambda box: box.width * box.height, reverse=True)[0]
    if debug_report:
        write_window_debug_report(debug_report, selected=selected, reason="selected via win32 enumeration fallback")
    return selected


def activate_window(window: WindowBox) -> None:
    try:
        win32gui.ShowWindow(window.hwnd, 5)
        win32gui.SetForegroundWindow(window.hwnd)
    except Exception:
        pass
    time.sleep(0.25)


def screenshot_window(window: WindowBox) -> np.ndarray:
    image = ImageGrab.grab(bbox=(window.left, window.top, window.right, window.bottom), all_screens=True)
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def ensure_cursor_safe(window: WindowBox | None = None) -> None:
    x, y = pyautogui.position()
    screen_w, screen_h = pyautogui.size()
    near_edge = (
        x <= FAILSAFE_EDGE_MARGIN
        or y <= FAILSAFE_EDGE_MARGIN
        or x >= screen_w - 1 - FAILSAFE_EDGE_MARGIN
        or y >= screen_h - 1 - FAILSAFE_EDGE_MARGIN
    )
    if not near_edge:
        return

    if window is not None:
        target_x = max(window.left + 80, min(window.right - 80, window.left + window.width // 2))
        target_y = max(window.top + 80, min(window.bottom - 80, window.top + window.height // 2))
    else:
        target_x = screen_w // 2
        target_y = screen_h // 2

    # Temporarily disable PyAutoGUI's failsafe only while nudging the cursor
    # away from the screen corner that would otherwise abort all automation.
    previous_failsafe = pyautogui.FAILSAFE
    pyautogui.FAILSAFE = False
    try:
        pyautogui.moveTo(target_x, target_y, duration=0.1)
    finally:
        pyautogui.FAILSAFE = previous_failsafe


def click_abs(x: int, y: int, dry_run: bool) -> dict[str, Any]:
    if not dry_run:
        ensure_cursor_safe()
        pyautogui.click(x, y)
    return {"x": x, "y": y, "dry_run": dry_run}


def select_all_timeline(
    dry_run: bool,
    click_x_ratio: float = 0.5,
    click_y_from_bottom: int = 150,
    pause_after_click: float = 0.5,
    pause_after_hotkey: float = 1.0,
) -> dict[str, Any]:
    window = find_capcut_window()
    activate_window(window)
    x = int(window.left + window.width * click_x_ratio)
    y = int(window.bottom - click_y_from_bottom)

    if not dry_run:
        ensure_cursor_safe(window)
        pyautogui.click(x, y)
        time.sleep(pause_after_click)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(pause_after_hotkey)

    return {
        "action": "select_all_timeline",
        "window": window.title,
        "window_rect": [window.left, window.top, window.right, window.bottom],
        "x": x,
        "y": y,
        "click_x_ratio": click_x_ratio,
        "click_y_from_bottom": click_y_from_bottom,
        "dry_run": dry_run,
    }


def click_template(
    template_path: Path,
    threshold: float,
    dry_run: bool,
    timeout: float,
    click_offset_x: int = 0,
    click_offset_y: int = 0,
    search_region: list[float] | None = None,
) -> dict[str, Any]:
    start = time.time()
    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        raise FileNotFoundError(f"template not found or unreadable: {template_path}")

    while True:
        window = find_capcut_window()
        activate_window(window)
        screen = screenshot_window(window)
        crop_left = 0
        crop_top = 0
        search_screen = screen
        if search_region:
            sh, sw = screen.shape[:2]
            x1 = max(0, min(sw - 1, int(sw * search_region[0])))
            y1 = max(0, min(sh - 1, int(sh * search_region[1])))
            x2 = max(x1 + 1, min(sw, int(sw * search_region[2])))
            y2 = max(y1 + 1, min(sh, int(sh * search_region[3])))
            search_screen = screen[y1:y2, x1:x2]
            crop_left = x1
            crop_top = y1

        result = cv2.matchTemplate(search_screen, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, max_loc = cv2.minMaxLoc(result)
        if score >= threshold:
            h, w = template.shape[:2]
            x = window.left + crop_left + max_loc[0] + w // 2 + click_offset_x
            y = window.top + crop_top + max_loc[1] + h // 2 + click_offset_y
            clicked = click_abs(x, y, dry_run)
            return {
                "action": "click_template",
                "template": str(template_path),
                "score": float(score),
                "window": window.title,
                "search_region": search_region,
                **clicked,
            }
        if time.time() - start > timeout:
            raise TimeoutError(f"template not found above threshold {threshold}: {template_path}, last score={score:.4f}")
        time.sleep(0.3)


def best_template_score(template_path: Path) -> dict[str, Any]:
    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        raise FileNotFoundError(f"template not found or unreadable: {template_path}")
    window = find_capcut_window()
    screen = screenshot_window(window)
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, max_loc = cv2.minMaxLoc(result)
    h, w = template.shape[:2]
    return {
        "score": float(score),
        "x": window.left + max_loc[0] + w // 2,
        "y": window.top + max_loc[1] + h // 2,
        "window": window.title,
    }


def wait_action(
    timeout: float,
    template_path: Path | None = None,
    threshold: float = 0.82,
    mode: str = "present",
    interval: float = 0.5,
    dry_run: bool = False,
    require_seen: bool = False,
) -> dict[str, Any]:
    start = time.time()
    last_score: float | None = None
    seen_once = False

    if template_path is None:
        if not dry_run:
            time.sleep(timeout)
        return {"action": "wait", "mode": "sleep", "seconds": timeout, "dry_run": dry_run}

    if mode not in {"present", "gone"}:
        raise ValueError("wait mode must be 'present' or 'gone'")

    while True:
        match = best_template_score(template_path)
        last_score = float(match["score"])
        found = last_score >= threshold
        if found:
            seen_once = True

        if (mode == "present" and found) or (mode == "gone" and not found and (not require_seen or seen_once)):
            return {
                "action": "wait",
                "mode": mode,
                "template": str(template_path),
                "threshold": threshold,
                "score": last_score,
                "elapsed": round(time.time() - start, 3),
                "dry_run": dry_run,
                "require_seen": require_seen,
                "seen_once": seen_once,
            }

        if timeout > 0 and time.time() - start > timeout:
            raise TimeoutError(
                f"wait timeout: mode={mode}, template={template_path}, threshold={threshold}, last score={last_score:.4f}, seen_once={seen_once}"
            )

        if dry_run:
            return {
                "action": "wait",
                "mode": mode,
                "template": str(template_path),
                "threshold": threshold,
                "score": last_score,
                "dry_run": dry_run,
                "require_seen": require_seen,
                "seen_once": seen_once,
            }

        time.sleep(interval)

def detect_first_project_card(
    min_area: int = 1500,
    dry_run: bool = False,
    debug_image: Path | None = None,
) -> dict[str, Any]:
    window = find_capcut_window()
    activate_window(window)
    screen = screenshot_window(window)
    h, w = screen.shape[:2]

    # CapCut Home has project cards in the lower central area. This crop is
    # relative to the CapCut window, so it survives resizing and multi-monitor.
    crop_x1 = int(w * 0.10)
    crop_y1 = int(h * 0.42)
    crop_x2 = int(w * 0.96)
    crop_y2 = int(h * 0.86)
    crop = screen[crop_y1:crop_y2, crop_x1:crop_x2]

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    # Project thumbnails are brighter / more textured than the dark background.
    _, mask = cv2.threshold(gray, 24, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cards: list[tuple[int, int, int, int, int]] = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        area = cw * ch
        if area < min_area:
            continue
        if cw < 45 or ch < 45:
            continue
        if cw > w * 0.20 or ch > h * 0.25:
            continue
        cards.append((x, y, cw, ch, area))

    if not cards:
        if debug_image:
            cv2.imwrite(str(debug_image), crop)
        raise RuntimeError("No project card detected. Open CapCut Home with Projects visible.")

    # Choose the top row first, then the left-most card in that row.
    cards.sort(key=lambda item: (item[1], item[0]))
    first = cards[0]
    x, y, cw, ch, area = first
    abs_x = window.left + crop_x1 + x + cw // 2
    abs_y = window.top + crop_y1 + y + ch // 2

    if debug_image:
        debug = crop.copy()
        for bx, by, bw, bh, _ in cards[:20]:
            cv2.rectangle(debug, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)
        cv2.rectangle(debug, (x, y), (x + cw, y + ch), (0, 0, 255), 3)
        cv2.imwrite(str(debug_image), debug)

    clicked = click_abs(abs_x, abs_y, dry_run)
    return {
        "action": "open_first_project",
        "window": window.title,
        "window_rect": [window.left, window.top, window.right, window.bottom],
        "crop": [crop_x1, crop_y1, crop_x2, crop_y2],
        "detected_cards": len(cards),
        "card": {"x": x, "y": y, "width": cw, "height": ch, "area": area},
        **clicked,
    }


def run_workflow(config_path: Path, dry_run: bool) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    base = config_path.parent
    steps = []
    for index, step in enumerate(config.get("steps", []), start=1):
        action = step["action"]
        if action == "open_first_project":
            result = detect_first_project_card(
                min_area=int(step.get("min_area", 1500)),
                dry_run=dry_run,
                debug_image=Path(step["debug_image"]) if step.get("debug_image") else None,
            )
        elif action == "select_all_timeline":
            result = select_all_timeline(
                dry_run=dry_run,
                click_x_ratio=float(step.get("click_x_ratio", 0.5)),
                click_y_from_bottom=int(step.get("click_y_from_bottom", 150)),
                pause_after_click=float(step.get("pause_after_click", 0.5)),
                pause_after_hotkey=float(step.get("pause_after_hotkey", 1.0)),
            )
        elif action == "click_template":
            template = Path(step["template"])
            if not template.is_absolute():
                template = base / template
            try:
                result = click_template(
                    template,
                    threshold=float(step.get("threshold", 0.82)),
                    dry_run=dry_run,
                    timeout=float(step.get("timeout", 20)),
                    click_offset_x=int(step.get("click_offset_x", 0)),
                    click_offset_y=int(step.get("click_offset_y", 0)),
                    search_region=step.get("search_region"),
                )
            except Exception as exc:
                if not bool(step.get("optional", False)):
                    raise
                result = {
                    "action": "click_template",
                    "template": str(template),
                    "optional": True,
                    "skipped": True,
                    "error": str(exc),
                    "dry_run": dry_run,
                }
        elif action == "wait":
            template = step.get("template")
            template_path = None
            if template:
                template_path = Path(template)
                if not template_path.is_absolute():
                    template_path = base / template_path
            result = wait_action(
                timeout=float(step.get("timeout", step.get("seconds", 1))),
                template_path=template_path,
                threshold=float(step.get("threshold", 0.82)),
                mode=str(step.get("mode", "present")),
                interval=float(step.get("interval", 0.5)),
                dry_run=dry_run,
                require_seen=bool(step.get("require_seen", False)),
            )
        elif action == "sleep":
            seconds = float(step.get("seconds", 1))
            if not dry_run:
                time.sleep(seconds)
            result = {"action": "sleep", "seconds": seconds, "dry_run": dry_run}
        else:
            raise ValueError(f"Unsupported action: {action}")
        result["step"] = index
        steps.append(result)
    return {"ok": True, "steps": steps}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="CapCut OpenCV/PyAutoGUI RPA helper.")
    sub = parser.add_subparsers(dest="command", required=True)

    open_first = sub.add_parser("open-first-project", help="Detect and click the first project card on CapCut Home.")
    open_first.add_argument("--dry-run", action="store_true")
    open_first.add_argument("--debug-image", type=Path)
    open_first.add_argument("--min-area", type=int, default=1500)

    click = sub.add_parser("click-template", help="Click an image template inside the CapCut window.")
    click.add_argument("template", type=Path)
    click.add_argument("--threshold", type=float, default=0.82)
    click.add_argument("--timeout", type=float, default=20)
    click.add_argument("--dry-run", action="store_true")

    workflow = sub.add_parser("workflow", help="Run JSON workflow.")
    workflow.add_argument("config", type=Path)
    workflow.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if args.command == "open-first-project":
        result = detect_first_project_card(args.min_area, args.dry_run, args.debug_image)
    elif args.command == "click-template":
        result = click_template(args.template, args.threshold, args.dry_run, args.timeout)
    else:
        result = run_workflow(args.config, args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



