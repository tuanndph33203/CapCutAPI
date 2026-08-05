from typing import List
import random
from timeline.models import VideoSegment

def apply_scale_crop_dynamic(video_segs: List[VideoSegment], base_ratio: float = 1.07, randomize: bool = True) -> List[VideoSegment]:
    """
    Applies zoom/scale crop adjustments to each video segment.
    """
    for seg in video_segs:
        if randomize:
            seg_scale = round(random.uniform(1.05, 1.10), 3)
        else:
            seg_scale = float(base_ratio)
        seg.scale_x = seg_scale
        seg.scale_y = seg_scale
    return video_segs
