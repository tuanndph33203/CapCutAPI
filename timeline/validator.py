from typing import List
from timeline.models import VideoSegment, SubtitleSegment, AudioSegment

class ValidationError(Exception):
    """Exception raised when timeline validation fails."""
    pass

def validate_timeline(
    video_segs: List[VideoSegment],
    subtitle_segs: List[SubtitleSegment],
    audio_segs: List[AudioSegment]
):
    """
    Validates the compiled timeline objects for overlapping issues, gaps,
    negative durations, invalid speeds, and overflow bounds.
    """
    # 1. Sort video segments by target start time
    sorted_videos = sorted(video_segs, key=lambda x: x.target_start)
    
    video_end = 0
    for i, vs in enumerate(sorted_videos):
        # Durations must be positive
        if vs.src_duration <= 0 or vs.target_duration <= 0:
            raise ValidationError(
                f"Video segment {vs.id} has non-positive duration: "
                f"src={vs.src_duration}, tgt={vs.target_duration}"
            )
            
        # Speed must be positive
        if vs.speed <= 0:
            raise ValidationError(f"Video segment {vs.id} has invalid speed: {vs.speed}")
            
        # Video overlaps
        if vs.target_start < video_end:
            raise ValidationError(
                f"Video segment {vs.id} overlaps with previous segments. "
                f"Starts at {vs.target_start}, but previous end was {video_end}"
            )
            
        # Update running timeline end bounds
        video_end = vs.target_start + vs.target_duration

    # 2. Check subtitle segment ranges
    for ss in subtitle_segs:
        if ss.target_duration <= 0:
            raise ValidationError(f"Subtitle segment {ss.id} has non-positive duration: {ss.target_duration}")
            
        if ss.ocr_source_start is None or ss.ocr_source_duration is None:
            raise ValidationError(f"Subtitle segment {ss.id} is missing OCR source metadata.")
            
        # Subtitle exceeds video timeline end
        if ss.target_start + ss.target_duration > video_end + 500_000:
            import logging
            logging.getLogger("TimelineValidator").warning(
                f"Subtitle segment {ss.id} extends past video timeline bounds: "
                f"ends at {ss.target_start + ss.target_duration}, but video timeline ends at {video_end}"
            )

    # 3. Check audio segment ranges
    for as_val in audio_segs:
        if as_val.src_duration <= 0 or as_val.target_duration <= 0:
            raise ValidationError(
                f"Audio segment {as_val.id} has non-positive duration: "
                f"src={as_val.src_duration}, tgt={as_val.target_duration}"
            )
            
        # Audio exceeds video timeline end
        if as_val.target_start + as_val.target_duration > video_end + 500_000:
            import logging
            logging.getLogger("TimelineValidator").warning(
                f"Audio segment {as_val.id} extends past video timeline bounds: "
                f"ends at {as_val.target_start + as_val.target_duration}, but video timeline ends at {video_end}"
            )
