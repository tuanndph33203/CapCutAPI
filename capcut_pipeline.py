#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import copy
import uuid
from pathlib import Path

from add_subtitle_impl import add_subtitle_impl
from add_video_track import add_video_track
from save_draft_impl import save_draft_impl


DEFAULT_CAPCUT_DRAFTS = Path(
    os.environ.get(
        "CAPCUT_DRAFTS_DIR",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "CapCut", "User Data", "Projects", "com.lveditor.draft"),
    )
)


def iter_draft_json_files(draft_path: Path) -> list[Path]:
    candidates = [
        draft_path / "draft_content.json",
        draft_path / "draft_info.json",
        *draft_path.glob("template-*.tmp"),
        *draft_path.glob("Timelines/*/draft_content.json"),
        *draft_path.glob("Timelines/*/draft_info.json"),
        *draft_path.glob("Timelines/*/template-*.tmp"),
    ]
    seen = set()
    paths = []
    for path in candidates:
        key = str(path.resolve()).lower()
        if path.exists() and path.is_file() and key not in seen:
            paths.append(path)
            seen.add(key)
    return paths


def capture_effect_timeline_snapshot(draft_path: Path) -> dict | None:
    for content_path in iter_draft_json_files(draft_path):
        try:
            data = json.loads(content_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        video_effects = [
            effect
            for effect in data.get("materials", {}).get("video_effects", [])
            if str(effect.get("name") or "").lower() == "blur"
        ]
        blur_ids = {effect.get("id") for effect in video_effects if effect.get("id")}
        effect_tracks = []
        for track in data.get("tracks", []):
            if track.get("type") != "effect" or not track.get("segments"):
                continue
            segments = [
                segment
                for segment in track.get("segments", [])
                if segment.get("material_id") in blur_ids
            ]
            if segments:
                track_copy = copy.deepcopy(track)
                track_copy["segments"] = segments
                effect_tracks.append(track_copy)

        if video_effects and effect_tracks:
            return {
                "video_effects": copy.deepcopy(video_effects),
                "effect_tracks": copy.deepcopy(effect_tracks),
            }
    return None


def get_video_timeline_duration(data: dict) -> int:
    durations = []
    for track in data.get("tracks", []):
        if track.get("type") != "video":
            continue
        for segment in track.get("segments", []):
            target = segment.get("target_timerange") or {}
            start = int(target.get("start") or 0)
            duration = int(target.get("duration") or 0)
            if duration > 0:
                durations.append(start + duration)
    return max(durations or [int(data.get("duration") or 0)])


def default_blur_effect_snapshot() -> dict:
    effect_id = uuid.uuid4().hex
    return {
        "video_effects": [
            {
                "adjust_params": [
                    {
                        "default_value": 0.5,
                        "max_value": 1.0,
                        "min_value": 0.0,
                        "name": "effects_adjust_blur",
                        "value": 0.5,
                    }
                ],
                "apply_target_type": 2,
                "apply_time_range": None,
                "category_id": "",
                "category_name": "",
                "common_keyframes": [],
                "disable_effect_faces": [],
                "effect_id": "15206412",
                "formula_id": "",
                "id": effect_id,
                "name": "Blur",
                "path": "C:/Users/nguye/AppData/Local/CapCut/User Data/Cache/effect/7399464929830423813/2db7bf49d9349e308ef0f46c39b14abf",
                "platform": "all",
                "render_index": 11000,
                "resource_id": "6739752823140913675",
                "source_platform": 0,
                "time_range": None,
                "track_render_index": 0,
                "type": "video_effect",
                "value": 1.0,
                "version": "",
            }
        ],
        "effect_tracks": [
            {
                "id": str(uuid.uuid4()).upper(),
                "type": "effect",
                "segments": [
                    {
                        "enable_adjust": True,
                        "enable_color_correct_adjust": False,
                        "enable_color_curves": True,
                        "enable_color_match_adjust": False,
                        "enable_color_wheels": True,
                        "enable_lut": True,
                        "enable_smart_color_adjust": False,
                        "last_nonzero_volume": 1.0,
                        "reverse": False,
                        "track_attribute": 4,
                        "track_render_index": 0,
                        "visible": True,
                        "id": uuid.uuid4().hex,
                        "material_id": effect_id,
                        "target_timerange": {"start": 0, "duration": 0},
                        "common_keyframes": [],
                        "keyframe_refs": [],
                    }
                ],
                "flag": 0,
                "attribute": 4,
                "name": "",
                "is_default_name": True,
            }
        ],
    }


def restore_effect_timeline_snapshot(draft_path: Path, snapshot: dict | None, *, ensure_default_blur: bool = False) -> int:
    if not snapshot and ensure_default_blur:
        snapshot = default_blur_effect_snapshot()

    if not snapshot:
        return 0

    patched = 0
    snapshot_effects = snapshot.get("video_effects") or []
    snapshot_tracks = snapshot.get("effect_tracks") or []
    snapshot_effect_ids = {
        effect.get("id")
        for effect in snapshot_effects
        if effect.get("id")
    }

    for content_path in iter_draft_json_files(draft_path):
        try:
            data = json.loads(content_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        duration = get_video_timeline_duration(data)
        if duration <= 0:
            continue

        materials = data.setdefault("materials", {})
        video_effects = materials.setdefault("video_effects", [])
        existing_effect_ids = {effect.get("id") for effect in video_effects if effect.get("id")}
        for effect in snapshot_effects:
            effect_id = effect.get("id")
            if effect_id and effect_id not in existing_effect_ids:
                video_effects.append(copy.deepcopy(effect))
                existing_effect_ids.add(effect_id)

        tracks = data.setdefault("tracks", [])
        kept_tracks = []
        for track in tracks:
            if track.get("type") != "effect":
                kept_tracks.append(track)
                continue
            material_ids = {
                segment.get("material_id")
                for segment in track.get("segments", [])
                if segment.get("material_id")
            }
            if not material_ids.intersection(snapshot_effect_ids):
                kept_tracks.append(track)

        for track in snapshot_tracks:
            restored_track = copy.deepcopy(track)
            restored_track["attribute"] = int(restored_track.get("attribute", 0) or 0) | 4
            for segment in restored_track.get("segments", []):
                target = segment.setdefault("target_timerange", {})
                target["start"] = int(target.get("start") or 0)
                target["duration"] = duration
                segment["track_attribute"] = int(segment.get("track_attribute", 0) or 0) | 4
            kept_tracks.append(restored_track)

        data["tracks"] = kept_tracks
        content_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        patched += 1

    return patched

def brand_overlay_snapshot_path(draft_path: Path) -> Path:
    return Path.cwd() / "brand_overlays" / f"{draft_path.name}.json"


def _is_brand_overlay_material(material: dict) -> bool:
    material_type = str(material.get("type") or "").lower()
    path = str(material.get("path") or material.get("material_name") or "").lower()
    return (
        material_type in {"gif", "photo", "image"}
        or path.endswith((".gif", ".png", ".jpg", ".jpeg", ".webp"))
    )


def capture_brand_overlay_snapshot(draft_path: Path) -> dict | None:
    for content_path in iter_draft_json_files(draft_path):
        try:
            data = json.loads(content_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        materials = data.get("materials") or {}
        videos = materials.get("videos") or []
        video_by_id = {item.get("id"): item for item in videos if item.get("id")}
        overlay_ids = {
            material_id
            for material_id, material in video_by_id.items()
            if _is_brand_overlay_material(material)
        }
        if not overlay_ids:
            continue

        overlay_tracks = []
        referenced_ids_by_key: dict[str, set[str]] = {}
        for track in data.get("tracks") or []:
            if track.get("type") != "video":
                continue
            segments = [
                segment
                for segment in track.get("segments") or []
                if segment.get("material_id") in overlay_ids
            ]
            if not segments:
                continue
            track_copy = copy.deepcopy(track)
            track_copy["segments"] = copy.deepcopy(segments)
            overlay_tracks.append(track_copy)
            for segment in segments:
                for ref_id in segment.get("extra_material_refs") or []:
                    for key, values in materials.items():
                        if not isinstance(values, list):
                            continue
                        if any(item.get("id") == ref_id for item in values if isinstance(item, dict)):
                            referenced_ids_by_key.setdefault(key, set()).add(ref_id)

        if not overlay_tracks:
            continue

        snapshot_materials = {"videos": [copy.deepcopy(video_by_id[item_id]) for item_id in overlay_ids]}
        for key, ids in referenced_ids_by_key.items():
            values = materials.get(key) or []
            snapshot_materials[key] = [
                copy.deepcopy(item)
                for item in values
                if isinstance(item, dict) and item.get("id") in ids
            ]

        return {
            "version": 1,
            "source": str(content_path),
            "materials": snapshot_materials,
            "tracks": overlay_tracks,
        }
    return None


def load_brand_overlay_snapshot(draft_path: Path) -> dict | None:
    path = brand_overlay_snapshot_path(draft_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_brand_overlay_snapshot(draft_path: Path, snapshot: dict | None) -> int:
    if not snapshot:
        return 0
    path = brand_overlay_snapshot_path(draft_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=4), encoding="utf-8")
    return 1


def restore_brand_overlay_snapshot(draft_path: Path, snapshot: dict | None) -> int:
    if not snapshot:
        return 0

    snapshot_materials = snapshot.get("materials") or {}
    snapshot_tracks = snapshot.get("tracks") or []
    overlay_material_ids = {
        material.get("id")
        for material in snapshot_materials.get("videos") or []
        if isinstance(material, dict) and material.get("id")
    }
    if not overlay_material_ids or not snapshot_tracks:
        return 0

    patched = 0
    for content_path in iter_draft_json_files(draft_path):
        try:
            data = json.loads(content_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        duration = get_video_timeline_duration(data)
        if duration <= 0:
            duration = int(data.get("duration") or 0)
        if duration <= 0:
            continue

        materials = data.setdefault("materials", {})
        for key, values in snapshot_materials.items():
            if not isinstance(values, list):
                continue
            target_values = materials.setdefault(key, [])
            existing_ids = {item.get("id") for item in target_values if isinstance(item, dict)}
            for item in values:
                item_id = item.get("id") if isinstance(item, dict) else None
                if item_id and item_id not in existing_ids:
                    target_values.append(copy.deepcopy(item))
                    existing_ids.add(item_id)

        tracks = data.setdefault("tracks", [])
        existing_overlay_ids = {
            segment.get("material_id")
            for track in tracks
            if track.get("type") == "video"
            for segment in track.get("segments") or []
            if segment.get("material_id") in overlay_material_ids
        }
        missing_ids = overlay_material_ids - existing_overlay_ids
        if not missing_ids:
            continue

        for track in snapshot_tracks:
            restored_track = copy.deepcopy(track)
            restored_segments = []
            for segment in restored_track.get("segments") or []:
                if segment.get("material_id") not in missing_ids:
                    continue
                target = segment.setdefault("target_timerange", {})
                target["start"] = int(target.get("start") or 0)
                target["duration"] = duration
                source = segment.setdefault("source_timerange", {})
                source["start"] = int(source.get("start") or 0)
                source["duration"] = duration
                restored_segments.append(segment)
            if restored_segments:
                restored_track["segments"] = restored_segments
                tracks.append(restored_track)

        content_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        patched += 1

    return patched


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
    preserve_blur_effect: bool = False,
    rotation: float = 0.0,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    transform_x: float = 0.0,
    transform_y: float = 0.0,
) -> dict:
    # Clear the in-memory draft cache at the start of each pipeline execution
    from draft_cache import DRAFT_CACHE
    DRAFT_CACHE.clear()

    if not video.exists() or not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")

    existing_capcut_draft = capcut_drafts / draft_id if draft_id else None
    # Blur hardsub is handled by FFmpeg before the video is inserted into CapCut.
    # Do not recreate CapCut Blur effect tracks here; they can cover the whole screen.
    effect_snapshot = None
    brand_snapshot = None
    if existing_capcut_draft and existing_capcut_draft.exists():
        brand_snapshot = capture_brand_overlay_snapshot(existing_capcut_draft)
        if brand_snapshot:
            save_brand_overlay_snapshot(existing_capcut_draft, brand_snapshot)
    if not brand_snapshot and existing_capcut_draft:
        brand_snapshot = load_brand_overlay_snapshot(existing_capcut_draft)

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
        rotation=rotation,
        scale_x=scale_x,
        scale_y=scale_y,
        transform_x=transform_x,
        transform_y=transform_y,
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
    restored_effect_files = 0
    if copy_to_capcut:
        import time
        max_attempts = 10
        for attempt in range(1, max_attempts + 1):
            try:
                if capcut_draft.exists():
                    shutil.rmtree(capcut_draft)
                shutil.copytree(repo_draft, capcut_draft)
                break
            except (PermissionError, OSError) as e:
                if attempt == max_attempts:
                    raise e
                print(f"[{attempt}/{max_attempts}] Không thể copy thư mục nháp sang CapCut vì file bị khóa. "
                      f"Đang force kill CapCut.exe và thử lại sau 1.5s... Chi tiết: {e}")
                subprocess.run(["taskkill", "/F", "/IM", "CapCut.exe"], capture_output=True)
                time.sleep(1.5)
        restore_brand_overlay_snapshot(capcut_draft, brand_snapshot)
        save_brand_overlay_snapshot(capcut_draft, brand_snapshot)

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
        "restored_effect_files": restored_effect_files,
        "restored_brand_files": 1 if brand_snapshot else 0,
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
    parser.add_argument("--preserve-blur-effect", action="store_true", help="Keep or recreate a full-duration Blur effect track.")
    parser.add_argument("--rotation", type=float, default=0.0, help="Rotate video segment in degrees clockwise.")
    parser.add_argument("--scale-x", type=float, default=1.0, help="Scale video segment horizontally.")
    parser.add_argument("--scale-y", type=float, default=1.0, help="Scale video segment vertically.")
    parser.add_argument("--transform-x", type=float, default=0.0, help="Move video segment horizontally.")
    parser.add_argument("--transform-y", type=float, default=0.0, help="Move video segment vertically.")
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
        preserve_blur_effect=args.preserve_blur_effect,
        rotation=args.rotation,
        scale_x=args.scale_x,
        scale_y=args.scale_y,
        transform_x=args.transform_x,
        transform_y=args.transform_y,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
