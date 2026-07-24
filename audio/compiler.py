from typing import List
from timeline.models import AudioSegment, VideoSegment
from timeline.compiler import compile_associated_segments

def compile_audio(audios: List[AudioSegment], video_segs: List[VideoSegment]) -> List[AudioSegment]:
    """
    Compiles audio segments against the compiled video segments.
    """
    return compile_associated_segments(audios, video_segs)
