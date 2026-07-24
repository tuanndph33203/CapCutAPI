import json
import copy
from typing import Dict, List, Any, Tuple, Optional
from .models import VideoSegment, SubtitleSegment, AudioSegment

def _is_main_video_track(track: dict, materials: dict) -> bool:
    if track.get("type") != "video":
        return False
    tr_name = str(track.get("name", "")).lower()
    if any(ext in tr_name for ext in [".gif", ".png", ".jpg", ".jpeg", ".webp", "sticker", "overlay", "logo"]):
        return False
    
    mat_map = {m.get("id"): str(m.get("path") or m.get("material_name") or "").lower() for m in materials.get("videos", []) if isinstance(m, dict)}
    has_valid_video = False
    for seg in track.get("segments", []):
        mat_id = seg.get("material_id")
        path = mat_map.get(mat_id, "").lower()
        if any(path.endswith(ext) or (ext in path) for ext in [".gif", ".png", ".jpg", ".jpeg", ".webp", ".bmp"]):
            return False
        if any(path.endswith(ext) or (ext in path) for ext in [".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".m4v", ".ts"]):
            has_valid_video = True
            
    return has_valid_video

def _get_segment_speed(segment: dict, speed_map: dict) -> Tuple[float, Optional[str]]:
    speed_id = None
    for ref in segment.get("extra_material_refs", []):
        if ref in speed_map:
            speed_id = ref
            break
    if speed_id and speed_id in speed_map:
        return float(speed_map[speed_id].get("speed", 1.0)), speed_id
    return float(segment.get("speed", 1.0)), None

def parse_draft(data: dict) -> Tuple[List[VideoSegment], List[SubtitleSegment], List[AudioSegment]]:
    materials = data.setdefault("materials", {})
    speeds = materials.setdefault("speeds", [])
    speed_map = {s.get("id"): s for s in speeds if isinstance(s, dict)}

    video_segs = []
    subtitle_segs = []
    audio_segs = []

    for track in data.get("tracks", []):
        tr_type = track.get("type")
        tr_name = track.get("name", "")
        
        if _is_main_video_track(track, materials):
            for seg in track.get("segments", []):
                s_src = seg.setdefault("source_timerange", {})
                s_tgt = seg.setdefault("target_timerange", {})
                
                spd, speed_id = _get_segment_speed(seg, speed_map)
                
                # Extract clip flip/scale if exists
                clip = seg.get("clip", {})
                flip = clip.get("flip", {})
                scale = clip.get("scale", {})
                
                flip_h = flip.get("horizontal", False)
                flip_v = flip.get("vertical", False)
                sc_x = scale.get("x", 1.0)
                sc_y = scale.get("y", 1.0)
                
                color_adj = seg.get("color_adjustments", {})
                
                video_segs.append(VideoSegment(
                    id=seg.get("id"),
                    material_id=seg.get("material_id"),
                    src_start=s_src.get("start", 0),
                    src_duration=s_src.get("duration", 0),
                    trim_left=0,
                    trim_right=0,
                    speed=spd,
                    target_start=s_tgt.get("start", 0),
                    target_duration=s_tgt.get("duration", 0),
                    flip_horizontal=flip_h,
                    flip_vertical=flip_v,
                    scale_x=sc_x,
                    scale_y=sc_y,
                    color_adjustments=color_adj,
                    extra_material_refs=seg.get("extra_material_refs", []),
                    speed_id=speed_id,
                    raw_dict=copy.deepcopy(seg)
                ))
                
        elif tr_type == "text":
            for seg in track.get("segments", []):
                s_tgt = seg.setdefault("target_timerange", {})
                
                # Check for cached _ocr_source_start/duration or use current start/duration
                ocr_start = seg.get("_ocr_source_start", s_tgt.get("start", 0))
                ocr_dur = seg.get("_ocr_source_duration", s_tgt.get("duration", 0))
                
                subtitle_segs.append(SubtitleSegment(
                    id=seg.get("id"),
                    ocr_source_start=ocr_start,
                    ocr_source_duration=ocr_dur,
                    target_start=s_tgt.get("start", 0),
                    target_duration=s_tgt.get("duration", 0)
                ))
                
        elif tr_type == "audio" and tr_name != "audio_filtered_vocal":
            for seg in track.get("segments", []):
                s_src = seg.setdefault("source_timerange", {})
                s_tgt = seg.setdefault("target_timerange", {})
                spd, speed_id = _get_segment_speed(seg, speed_map)
                
                ocr_start = seg.get("_ocr_source_start")
                if ocr_start is None:
                    from .mapper import map_target_to_source
                    ocr_start, _ = map_target_to_source(s_tgt.get("start", 0), video_segs)
                
                audio_segs.append(AudioSegment(
                    id=seg.get("id"),
                    material_id=seg.get("material_id"),
                    src_start=s_src.get("start", 0),
                    src_duration=s_src.get("duration", 0),
                    target_start=s_tgt.get("start", 0),
                    target_duration=s_tgt.get("duration", 0),
                    speed=spd,
                    extra_material_refs=seg.get("extra_material_refs", []),
                    speed_id=speed_id,
                    ocr_source_start=ocr_start
                ))

    return video_segs, subtitle_segs, audio_segs
