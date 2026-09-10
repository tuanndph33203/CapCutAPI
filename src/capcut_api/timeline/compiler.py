from typing import List
from .models import VideoSegment
from .mapper import map_source_to_target

def compile_timeline(video_segs: List[VideoSegment]) -> List[VideoSegment]:
    """
    Calculates target_start, target_duration, and timeline_src_start sequentially for video segments.
    This is the single source of truth for segment timeline calculations.
    """
    current_tgt = 0
    current_src = 0
    for seg in video_segs:
        effective_source = seg.effective_source_duration
        if seg.speed > 0:
            effective_target = int(round(effective_source / seg.speed))
        else:
            effective_target = effective_source
            
        seg.target_start = current_tgt
        seg.target_duration = effective_target
        seg.timeline_src_start = current_src

        current_tgt += effective_target
        current_src += effective_source
        
    return video_segs

def compile_associated_segments(segs: list, video_segs: List[VideoSegment]) -> list:
    """
    Shared helper to compile subtitles or audio segments against video timeline.
    Duck-types segments to support both SubtitleSegment and AudioSegment.
    """
    import logging
    logger = logging.getLogger("TimelineCompiler")
    
    # Sort video segments by target_start to maintain chronological track sequence
    sorted_video_segs = sorted(video_segs, key=lambda x: x.target_start)
    
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

    # Guard tail overflow against the compiled video end for flush alignment
    if sorted_video_segs:
        max_vid_end = max(vs.target_start + vs.target_duration for vs in sorted_video_segs)
        for seg in segs:
            if seg.target_start + seg.target_duration > max_vid_end:
                if seg.target_start >= max_vid_end:
                    seg.target_start = max(0, max_vid_end - 50_000)
                seg.target_duration = max(50_000, max_vid_end - seg.target_start)

    return segs
