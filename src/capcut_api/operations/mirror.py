from typing import List
from timeline.models import VideoSegment

def apply_mirror(video_segs: List[VideoSegment], mirror_horizontal: bool = True) -> List[VideoSegment]:
    """
    Applies mirror/flip properties to each video segment.
    """
    for seg in video_segs:
        seg.flip_horizontal = mirror_horizontal
    return video_segs
