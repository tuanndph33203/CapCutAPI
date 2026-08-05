from typing import List
import random
from timeline.models import VideoSegment

def apply_speed_dynamic(video_segs: List[VideoSegment], base_speed: float = 1.05, randomize: bool = True) -> List[VideoSegment]:
    """
    Applies speed modifications to each video segment.
    """
    for seg in video_segs:
        if randomize:
            spd = round(base_speed + random.uniform(-0.02, 0.02), 3)
        else:
            spd = float(base_speed)
        seg.speed = spd
    return video_segs
