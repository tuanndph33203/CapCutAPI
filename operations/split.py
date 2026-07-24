from typing import List
import copy
import uuid
from timeline.models import VideoSegment

def split_video_segments(video_segs: List[VideoSegment], cut_points: List[int], micro_trim_us: int = 200000) -> List[VideoSegment]:
    """
    Splits video segments at the specified cut points, applying a trim to the right side
    of each split segment (except the last one).
    """
    sorted_cuts = sorted(list(set(cut_points)))
    result = []
    
    for seg in video_segs:
        seg_start = seg.src_start
        seg_end = seg.src_start + seg.src_duration
        
        # Find all cut points that fall strictly inside this segment
        cuts_in_seg = [c for c in sorted_cuts if seg_start < c < seg_end]
        
        if not cuts_in_seg:
            result.append(seg)
            continue
            
        # Split the segment
        curr_start = seg_start
        for cp in cuts_in_seg:
            seg_len = cp - curr_start
            trim_r = micro_trim_us if seg_len > micro_trim_us else 0
            
            new_seg = copy.deepcopy(seg)
            new_seg.id = str(uuid.uuid4()).upper()
            new_seg.src_start = curr_start
            new_seg.src_duration = seg_len
            new_seg.trim_right = trim_r
            result.append(new_seg)
            
            curr_start = cp
            
        # Add the remaining part of the segment
        remaining_len = seg_end - curr_start
        if remaining_len > 0:
            new_seg = copy.deepcopy(seg)
            new_seg.id = str(uuid.uuid4()).upper()
            new_seg.src_start = curr_start
            new_seg.src_duration = remaining_len
            new_seg.trim_right = 0
            result.append(new_seg)
            
    return result
