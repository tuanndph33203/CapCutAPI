#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pyautogui
from PIL import ImageGrab


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Capture a small template image around the mouse cursor.")
    parser.add_argument("name", help="Template file name, for example captions_tab.png")
    parser.add_argument("--width", type=int, default=96)
    parser.add_argument("--height", type=int, default=56)
    parser.add_argument("--delay", type=float, default=15.0)
    parser.add_argument("--out-dir", type=Path, default=Path("rpa_templates"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    output = args.out_dir / args.name
    if output.suffix.lower() != ".png":
        output = output.with_suffix(".png")

    print(f"Hover chuột lên nút cần chụp. Sẽ chụp sau {args.delay:.1f}s...")
    time.sleep(args.delay)
    x, y = pyautogui.position()
    left = int(x - args.width / 2)
    top = int(y - args.height / 2)
    right = left + args.width
    bottom = top + args.height
    image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    image.save(output)
    print(f"saved: {output.resolve()}")
    print(f"mouse: x={x}, y={y}, crop=({left},{top},{right},{bottom})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
