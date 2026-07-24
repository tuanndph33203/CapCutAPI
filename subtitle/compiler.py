from typing import List
from timeline.models import SubtitleSegment, VideoSegment
from timeline.compiler import compile_associated_segments

def compile_subtitles(subtitles: List[SubtitleSegment], video_segs: List[VideoSegment]) -> List[SubtitleSegment]:
    """
    Compiles subtitle segments against the compiled video segments.
    """
    return compile_associated_segments(subtitles, video_segs)
