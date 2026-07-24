import os
import json
from typing import List
from timeline.models import VideoSegment, SubtitleSegment, AudioSegment

def dump_stage_timeline(filename: str, video_segs: List[VideoSegment]):
    """
    Dumps the state of video segments for debugging.
    """
    serialized = []
    for vs in video_segs:
        serialized.append({
            "id": vs.id,
            "material_id": vs.material_id,
            "source": {
                "start": vs.src_start,
                "duration": vs.src_duration
            },
            "trim": {
                "left": vs.trim_left,
                "right": vs.trim_right
            },
            "speed": vs.speed,
            "target": {
                "start": vs.target_start,
                "duration": vs.target_duration
            },
            "flip": {
                "horizontal": vs.flip_horizontal,
                "vertical": vs.flip_vertical
            },
            "scale": {
                "x": vs.scale_x,
                "y": vs.scale_y
            },
            "color_adjustments": vs.color_adjustments
        })
        
    os.makedirs("debug", exist_ok=True)
    filepath = os.path.join("debug", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(serialized, f, ensure_ascii=False, indent=4)

def dump_subtitle_debug(filename: str, subtitle_segs: List[SubtitleSegment]):
    """
    Dumps the state of subtitle segments for debugging.
    """
    serialized = []
    for ss in subtitle_segs:
        serialized.append({
            "id": ss.id,
            "ocr_source": {
                "start": ss.ocr_source_start,
                "duration": ss.ocr_source_duration
            },
            "target": {
                "start": ss.target_start,
                "duration": ss.target_duration
            }
        })
    os.makedirs("debug", exist_ok=True)
    filepath = os.path.join("debug", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(serialized, f, ensure_ascii=False, indent=4)

def dump_audio_debug(filename: str, audio_segs: List[AudioSegment]):
    """
    Dumps the state of audio segments for debugging.
    """
    serialized = []
    for as_val in audio_segs:
        serialized.append({
            "id": as_val.id,
            "material_id": as_val.material_id,
            "source": {
                "start": as_val.src_start,
                "duration": as_val.src_duration
            },
            "target": {
                "start": as_val.target_start,
                "duration": as_val.target_duration
            },
            "speed": as_val.speed
        })
    os.makedirs("debug", exist_ok=True)
    filepath = os.path.join("debug", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(serialized, f, ensure_ascii=False, indent=4)
