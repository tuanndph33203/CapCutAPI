from typing import List
from .models import VideoSegment
from .mapper import map_source_to_target

def compile_timeline(video_segs: List[VideoSegment]) -> List[VideoSegment]:
    """
    Calculates target_start and target_duration sequentially for video segments.
    This is the single source of truth for segment timeline calculations.
    """
    current = 0
    for seg in video_segs:
        effective_source = seg.src_duration - seg.trim_left - seg.trim_right
        if seg.speed > 0:
            effective_target = int(round(effective_source / seg.speed))
        else:
            effective_target = effective_source
            
        seg.target_start = current
        seg.target_duration = effective_target
        current += effective_target
        
    return video_segs

def compile_associated_segments(segs: list, video_segs: List[VideoSegment]) -> list:
    """
    Shared helper to compile subtitles or audio segments against video timeline.
    Duck-types segments to support both SubtitleSegment and AudioSegment.
    """
    for seg in segs:
        if hasattr(seg, "ocr_source_start") and seg.ocr_source_start is not None:
            src_start = seg.ocr_source_start
            src_duration = getattr(seg, "ocr_source_duration", getattr(seg, "src_duration", 0))
        else:
            src_start = getattr(seg, "src_start", 0)
            src_duration = getattr(seg, "src_duration", 0)

        new_start, ratio = map_source_to_target(src_start, video_segs)

        # Find speed of matching video segment
        matched_spd = 1.0
        for vk in video_segs:
            played_src_start = vk.src_start + vk.trim_left
            played_src_end = vk.src_start + vk.src_duration - vk.trim_right
            if played_src_start <= src_start < played_src_end:
                matched_spd = vk.speed
                break

        pure_speed_ratio = 1.0 / matched_spd if matched_spd > 0 else 1.0
        new_dur = max(50_000, int(round(src_duration * pure_speed_ratio)))

        seg.target_start = new_start
        seg.target_duration = new_dur
    return segs
