from typing import List
import random
from timeline.models import VideoSegment

def apply_color_adjustments_dynamic(video_segs: List[VideoSegment], randomize: bool = True) -> List[VideoSegment]:
    """
    Applies color adjustments (brightness, contrast, saturation) to each video segment.
    """
    for seg in video_segs:
        b = round(random.uniform(0.02, 0.05), 3) if randomize else 0.03
        c = round(random.uniform(0.03, 0.06), 3) if randomize else 0.04
        s = round(random.uniform(0.01, 0.03), 3) if randomize else 0.02
        seg.color_adjustments = {"brightness": b, "contrast": c, "saturation": s}
    return video_segs
