#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from add_subtitle_impl import add_subtitle_impl
from add_video_track import add_video_track
from save_draft_impl import save_draft_impl


DEFAULT_CAPCUT_DRAFTS = Path(
    r"C:\Users\PC\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft"
)


def probe_duration(path: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    return float(completed.stdout.strip())


def read_srt(path: Path | None, fallback_duration: float) -> str:
    if path:
        return path.read_text(encoding="utf-8-sig")
    end_second = max(1, int(min(fallback_duration, 3)))
    return (
        "1\n"
        "00:00:00,000 --> 00:00:01,200\n"
        "Pipeline test CapCutAPI.\n\n"
        "2\n"
        f"00:00:01,200 --> 00:00:{end_second:02d},000\n"
        "Patch subtitle + speed 1.17 bang command.\n"
    )


def run_pipeline(
    video: Path,
    capcut_drafts: Path,
    srt: Path | None,
    width: int,
    height: int,
    speed: float,
    clip_seconds: float | None,
    font: str,
    font_size: float,
    copy_to_capcut: bool,
    draft_id: str | None = None,
    volume: float = 1.0,
) -> dict:
    # Clear the in-memory draft cache at the start of each pipeline execution
    from draft_cache import DRAFT_CACHE
    DRAFT_CACHE.clear()

    if not video.exists() or not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")

    source_duration = probe_duration(video)
    clip_duration = min(clip_seconds or source_duration, source_duration)
    if clip_duration <= 0:
        raise ValueError(f"Invalid clip duration: {clip_duration}")

    video_result = add_video_track(
        video_url=str(video),
        draft_folder=str(capcut_drafts),
        width=width,
        height=height,
        start=0,
        end=clip_duration,
        duration=source_duration,
        speed=speed,
        track_name="main",
        draft_id=draft_id,
        volume=volume,
    )
    draft_id = video_result["draft_id"]

    if srt:
        add_subtitle_impl(
            srt_path=read_srt(srt, clip_duration),
            draft_id=draft_id,
            track_name="subtitle_vi",
            font=font,
            font_size=font_size,
            font_color="#FFFFFF",
            border_width=0.08,
            border_color="#000000",
            vertical=False,
            alpha=1.0,
            width=width,
            height=height,
        )

    save_result = save_draft_impl(draft_id, str(capcut_drafts))

    repo_draft = Path.cwd() / draft_id
    capcut_draft = capcut_drafts / draft_id
    if copy_to_capcut:
        if capcut_draft.exists():
            shutil.rmtree(capcut_draft)
        shutil.copytree(repo_draft, capcut_draft)

    draft_info = repo_draft / "draft_info.json"
    draft_text = draft_info.read_text(encoding="utf-8") if draft_info.exists() else ""

    return {
        "ok": True,
        "draft_id": draft_id,
        "video": str(video),
        "source_duration": source_duration,
        "clip_duration": clip_duration,
        "repo_draft": str(repo_draft),
        "capcut_draft": str(capcut_draft) if copy_to_capcut else None,
        "has_bad_windows_path": "C:Users" in draft_text,
        "has_speed": f'"speed": {speed}' in draft_text,
        "has_subtitle_track": '"name": "subtitle_vi"' in draft_text,
        "save_result": save_result,
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Create a CapCut draft with video, patched subtitle, and speed.")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--srt", type=Path, help="Vietnamese SRT to patch into draft. If omitted, uses test captions.")
    parser.add_argument("--draft-folder", type=Path, default=DEFAULT_CAPCUT_DRAFTS)
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--speed", type=float, default=1.17)
    parser.add_argument("--clip-seconds", type=float, default=3.0)
    parser.add_argument("--font", default="HarmonyOS_Sans_SC_Regular")
    parser.add_argument("--font-size", type=float, default=8.0)
    parser.add_argument("--no-copy-to-capcut", action="store_true")
    parser.add_argument("--draft-id", help="Draft ID or name to use instead of generating a random one.")
    parser.add_argument("--volume", type=float, default=1.0, help="Volume level (linear float, e.g. 1.0 is 100%, 0.168 is -15.5dB).")
    parser.add_argument("--volume-db", type=float, help="Volume in decibels (dB), e.g. -15.5. Overrides --volume if specified.")
    args = parser.parse_args()

    volume = args.volume
    if args.volume_db is not None:
        volume = 10.0 ** (args.volume_db / 20.0)

    result = run_pipeline(
        video=args.video,
        capcut_drafts=args.draft_folder,
        srt=args.srt,
        width=args.width,
        height=args.height,
        speed=args.speed,
        clip_seconds=args.clip_seconds,
        font=args.font,
        font_size=args.font_size,
        copy_to_capcut=not args.no_copy_to_capcut,
        draft_id=args.draft_id,
        volume=volume,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
