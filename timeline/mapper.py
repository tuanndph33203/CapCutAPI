from typing import List, Tuple
from .models import VideoSegment

def map_source_to_target(t_src: int, video_segments: List[VideoSegment]) -> Tuple[int, float]:
    """
    Maps a timestamp from source space (original asset timeline) to target space (compiled timeline).
    """
    if not video_segments:
        return max(0, t_src), 1.0

    # Sort video segments by source start time
    sorted_segs = sorted(video_segments, key=lambda x: x.src_start)

    # 1. Before first segment
    v0 = sorted_segs[0]
    played_src_start_0 = v0.src_start + v0.trim_left
    if t_src < played_src_start_0:
        offset = t_src - played_src_start_0
        src_len = v0.src_duration - v0.trim_left - v0.trim_right
        ratio = v0.target_duration / src_len if src_len > 0 else 1.0
        t_tgt = v0.target_start + int(round(offset * ratio))
        return max(0, t_tgt), ratio

    # 2. Within segments or in gaps
    for i in range(len(sorted_segs)):
        vk = sorted_segs[i]
        played_src_start_k = vk.src_start + vk.trim_left
        played_src_end_k = vk.src_start + vk.src_duration - vk.trim_right
        
        if played_src_start_k <= t_src < played_src_end_k:
            offset = t_src - played_src_start_k
            src_len = played_src_end_k - played_src_start_k
            ratio = vk.target_duration / src_len if src_len > 0 else 1.0
            t_tgt = vk.target_start + int(round(offset * ratio))
            return max(0, t_tgt), ratio

        # Falls inside gap between vk and vk+1
        if i + 1 < len(sorted_segs):
            v_next = sorted_segs[i + 1]
            played_src_start_next = v_next.src_start + v_next.trim_left
            if played_src_end_k <= t_src < played_src_start_next:
                # Map to the start of the next segment
                next_src_len = v_next.src_duration - v_next.trim_left - v_next.trim_right
                ratio = v_next.target_duration / next_src_len if next_src_len > 0 else 1.0
                return v_next.target_start, ratio

    # 3. Exceeds end of the last segment
    vn = sorted_segs[-1]
    played_src_end_n = vn.src_start + vn.src_duration - vn.trim_right
    offset = t_src - played_src_end_n
    src_len = vn.src_duration - vn.trim_left - vn.trim_right
    ratio = vn.target_duration / src_len if src_len > 0 else 1.0
    t_tgt = (vn.target_start + vn.target_duration) + int(round(offset * ratio))
    return max(0, t_tgt), ratio


def map_target_to_source(t_tgt: int, video_segments: List[VideoSegment]) -> Tuple[int, float]:
    """
    Maps a timestamp from target space (compiled timeline) back to source space (original asset timeline).
    """
    if not video_segments:
        return max(0, t_tgt), 1.0

    # Sort video segments by target start time
    sorted_segs = sorted(video_segments, key=lambda x: x.target_start)

    # 1. Before first segment
    v0 = sorted_segs[0]
    if t_tgt < v0.target_start:
        offset = t_tgt - v0.target_start
        src_len = v0.src_duration - v0.trim_left - v0.trim_right
        ratio = src_len / v0.target_duration if v0.target_duration > 0 else 1.0
        t_src = (v0.src_start + v0.trim_left) + int(round(offset * ratio))
        return max(0, t_src), ratio

    # 2. Within segments
    for vk in sorted_segs:
        tgt_end_k = vk.target_start + vk.target_duration
        if vk.target_start <= t_tgt < tgt_end_k:
            offset = t_tgt - vk.target_start
            src_len = vk.src_duration - vk.trim_left - vk.trim_right
            ratio = src_len / vk.target_duration if vk.target_duration > 0 else 1.0
            t_src = (vk.src_start + vk.trim_left) + int(round(offset * ratio))
            return max(0, t_src), ratio

    # 3. Exceeds end of the last segment
    vn = sorted_segs[-1]
    tgt_end_n = vn.target_start + vn.target_duration
    offset = t_tgt - tgt_end_n
    src_len = vn.src_duration - vn.trim_left - vn.trim_right
    ratio = src_len / vn.target_duration if vn.target_duration > 0 else 1.0
    t_src = (vn.src_start + vn.src_duration - vn.trim_right) + int(round(offset * ratio))
    return max(0, t_src), ratio
