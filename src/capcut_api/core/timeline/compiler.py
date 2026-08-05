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
        effective_source = seg.effective_source_duration
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
    import logging
    logger = logging.getLogger("TimelineCompiler")
    
    # Sort video segments once
    sorted_video_segs = sorted(video_segs, key=lambda x: x.src_start + x.trim_left)
    
    for seg in segs:
        if hasattr(seg, "ocr_source_start") and seg.ocr_source_start is not None:
            src_start = seg.ocr_source_start
            src_duration = getattr(seg, "ocr_source_duration", getattr(seg, "src_duration", 0))
        else:
            src_start = getattr(seg, "src_start", 0)
            src_duration = getattr(seg, "src_duration", 0)

        mapped = map_source_to_target(src_start, sorted_video_segs)

        if hasattr(seg, "speed"):
            # It's an AudioSegment (TTS).
            # The speed is already baked into the audio file by nghitts.
            # We don't need to adjust speed in CapCut, leave it as 1.0.
            seg.speed = 1.0
            new_dur = src_duration
        else:
            # It's a SubtitleSegment.
            new_dur = max(50_000, int(round(src_duration * mapped.ratio)))

        seg.target_start = mapped.target
        seg.target_duration = new_dur
        
        logger.debug(f"Segment {seg.id} Source {src_start} -> VideoSegment {mapped.segment.id if mapped.segment else 'None'} -> Offset {mapped.offset} -> Target {mapped.target}")

    return segs
