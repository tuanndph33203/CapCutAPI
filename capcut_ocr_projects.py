#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import pyautogui
from rapidocr_onnxruntime import RapidOCR

from capcut_rpa import activate_window, find_capcut_window, screenshot_window


def crop_project_area(image, ratios: tuple[float, float, float, float]):
    height, width = image.shape[:2]
    left = max(0, min(width, int(width * ratios[0])))
    top = max(0, min(height, int(height * ratios[1])))
    right = max(left + 1, min(width, int(width * ratios[2])))
    bottom = max(top + 1, min(height, int(height * ratios[3])))
    return image[top:bottom, left:right], {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": right - left,
        "height": bottom - top,
    }


def parse_ocr_results(results: list[list[Any]] | None, min_score: float, crop_rect: dict[str, int]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not results:
        return items

    for item in results:
        if len(item) < 3:
            continue
        box, text, score = item[0], str(item[1]).strip(), float(item[2])
        if not text or score < min_score:
            continue
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        items.append({
            "text": text,
            "score": round(score, 4),
            "box": {
                "left": int(min(xs)),
                "top": int(min(ys)),
                "right": int(max(xs)),
                "bottom": int(max(ys)),
            },
            "abs_box": {
                "left": crop_rect["left"] + int(min(xs)),
                "top": crop_rect["top"] + int(min(ys)),
                "right": crop_rect["left"] + int(max(xs)),
                "bottom": crop_rect["top"] + int(max(ys)),
            },
        })

    items.sort(key=lambda value: (value["box"]["top"], value["box"]["left"]))
    return items


def read_visible_texts(
    min_score: float = 0.45,
    crop: str = "0.10,0.36,0.96,0.88",
    debug_image: Path | None = None,
    full_debug_image: Path | None = None,
) -> dict[str, Any]:
    ratios = tuple(float(part.strip()) for part in crop.split(","))
    if len(ratios) != 4:
        raise ValueError("crop must have four comma-separated ratios")

    window = find_capcut_window()
    activate_window(window)
    image = screenshot_window(window)
    cropped_image, crop_rect = crop_project_area(image, ratios)

    if debug_image:
        debug_image.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_image), cropped_image)
    if full_debug_image:
        full_debug_image.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(full_debug_image), image)

    ocr = RapidOCR()
    results, _ = ocr(cropped_image)
    items = parse_ocr_results(results, min_score, crop_rect)

    return {
        "window": window,
        "crop_rect": crop_rect,
        "texts": items,
    }


def click_text_above(
    text: str,
    min_score: float = 0.45,
    click_above_cm: float = 0.5,
    dpi: float = 96.0,
    crop: str = "0.10,0.36,0.96,0.88",
    dry_run: bool = False,
    debug_image: Path | None = None,
    full_debug_image: Path | None = None,
) -> dict[str, Any]:
    ocr_data = read_visible_texts(
        min_score=min_score,
        crop=crop,
        debug_image=debug_image,
        full_debug_image=full_debug_image,
    )
    needle = text.lower()
    match = next((item for item in ocr_data["texts"] if needle in item["text"].lower()), None)
    if not match:
        raise RuntimeError(f"OCR text not found: {text}")

    window = ocr_data["window"]
    abs_box = match["abs_box"]
    offset_px = int(click_above_cm / 2.54 * dpi)
    click_x = window.left + int((abs_box["left"] + abs_box["right"]) / 2)
    click_y = window.top + int((abs_box["top"] + abs_box["bottom"]) / 2) - offset_px
    if not dry_run:
        pyautogui.click(click_x, click_y)

    return {
        "text": match["text"],
        "score": match["score"],
        "x": click_x,
        "y": click_y,
        "offset_px": offset_px,
        "dry_run": dry_run,
        "window_rect": [window.left, window.top, window.right, window.bottom],
        "crop_rect": ocr_data["crop_rect"],
        "texts": ocr_data["texts"],
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Read visible CapCut project names with OCR.")
    parser.add_argument("--min-score", type=float, default=0.45)
    parser.add_argument("--debug-image", type=Path, default=Path("scratch/capcut_projects_ocr_crop.png"))
    parser.add_argument("--full-debug-image", type=Path, default=Path("scratch/capcut_projects_ocr_full.png"))
    parser.add_argument("--crop", default="0.10,0.36,0.96,0.88", help="left,top,right,bottom ratios inside the CapCut window")
    parser.add_argument("--click-text", default="", help="Click the first OCR text containing this value")
    parser.add_argument("--click-above-cm", type=float, default=0.5, help="Click this many centimeters above the OCR text center")
    parser.add_argument("--dpi", type=float, default=96.0, help="Pixel density used to convert centimeters to pixels")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    clicked = None
    if args.click_text:
        clicked = click_text_above(
            text=args.click_text,
            min_score=args.min_score,
            click_above_cm=args.click_above_cm,
            dpi=args.dpi,
            crop=args.crop,
            dry_run=args.dry_run,
            debug_image=args.debug_image,
            full_debug_image=args.full_debug_image,
        )
        items = clicked["texts"]
        window_rect = clicked["window_rect"]
        crop_rect = clicked["crop_rect"]
    else:
        ocr_data = read_visible_texts(
            min_score=args.min_score,
            crop=args.crop,
            debug_image=args.debug_image,
            full_debug_image=args.full_debug_image,
        )
        window = ocr_data["window"]
        window_rect = [window.left, window.top, window.right, window.bottom]
        crop_rect = ocr_data["crop_rect"]
        items = ocr_data["texts"]

    print(json.dumps({
        "ok": True,
        "window": "CapCut",
        "window_rect": window_rect,
        "crop_rect": crop_rect,
        "debug_image": str(args.debug_image),
        "full_debug_image": str(args.full_debug_image),
        "clicked": clicked,
        "texts": items,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
