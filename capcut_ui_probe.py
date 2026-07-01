#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import uiautomation as auto


def prop(control, prop_id):
    try:
        value = control.GetPropertyValue(prop_id)
        return value if isinstance(value, str) else ""
    except Exception:
        return ""


def info(control, depth):
    rect = control.BoundingRectangle
    return {
        "depth": depth,
        "name": control.Name,
        "control_type": control.ControlTypeName,
        "class_name": getattr(control, "ClassName", ""),
        "automation_id": prop(control, auto.PropertyId.AutomationIdProperty),
        "full_description": prop(control, 30159),
        "rect": {
            "left": rect.left,
            "top": rect.top,
            "width": rect.width(),
            "height": rect.height(),
        },
    }


def find_capcut_window():
    pids = capcut_process_ids()
    candidates = []
    for window in auto.GetRootControl().GetChildren():
        if window.ControlType == auto.ControlType.WindowControl and (
            (pids and getattr(window, "ProcessId", 0) in pids)
            or ("capcut" in (window.Name or "").lower() and "chrome" not in (getattr(window, "ClassName", "") or "").lower())
        ):
            rect = window.BoundingRectangle
            if rect.width() >= 400 and rect.height() >= 300:
                candidates.append((rect.width() * rect.height(), window))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


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


def walk(control, max_depth, depth=0):
    node = info(control, depth)
    node["children"] = []
    if depth >= max_depth:
        return node
    try:
        for child in control.GetChildren():
            if child.Exists(0, 0):
                node["children"].append(walk(child, max_depth, depth + 1))
    except Exception as exc:
        node["children_error"] = str(exc)
    return node


def flatten(node):
    out = [node]
    for child in node.get("children", []):
        out.extend(flatten(child))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Dump CapCut UI Automation tree.")
    parser.add_argument("--depth", type=int, default=5)
    parser.add_argument("--out", default="capcut_ui_tree.json")
    parser.add_argument("--filter", default="")
    args = parser.parse_args()

    window = find_capcut_window()
    if not window:
        print(json.dumps({"ok": False, "error": "CapCut window not found"}, ensure_ascii=False))
        return 1

    window.SetActive()
    tree = walk(window, args.depth)
    Path(args.out).write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
    items = flatten(tree)
    needle = args.filter.lower()
    if needle:
        items = [
            item
            for item in items
            if needle in " ".join([item.get("name", ""), item.get("class_name", ""), item.get("automation_id", ""), item.get("full_description", "")]).lower()
        ]
    print(json.dumps({"ok": True, "window": window.Name, "out": args.out, "matches": items[:80]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
