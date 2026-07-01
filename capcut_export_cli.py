#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from pyJianYingDraft.capcut_controller import CapCutController, ExportFramerate, ExportResolution


def enum_by_value(enum_cls, value):
    if not value:
        return None
    for item in enum_cls:
        if item.value.lower() == value.lower():
            return item
    raise SystemExit(f"Unsupported value {value}. Choices: {', '.join(item.value for item in enum_cls)}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Export a CapCut desktop draft via Windows UI Automation.")
    parser.add_argument("draft_name")
    parser.add_argument("--out")
    parser.add_argument("--resolution", choices=[item.value for item in ExportResolution])
    parser.add_argument("--framerate", choices=[item.value for item in ExportFramerate])
    parser.add_argument("--timeout", type=float, default=1200)
    parser.add_argument("--probe", action="store_true", help="Only find the CapCut window and print status.")
    args = parser.parse_args()

    controller = CapCutController()
    if args.probe:
        print(json.dumps({"ok": True, "status": controller.app_status, "window": controller.app.Name}, ensure_ascii=False, indent=2))
        return 0

    controller.export_draft(
        args.draft_name,
        args.out,
        resolution=enum_by_value(ExportResolution, args.resolution),
        framerate=enum_by_value(ExportFramerate, args.framerate),
        timeout=args.timeout,
    )
    print(json.dumps({"ok": True, "progress": controller.get_export_progress()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
