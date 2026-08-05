from typing import List, Tuple
from .models import VideoSegment, MappingResult

def map_source_to_target(t_src: int, sorted_segs: List[VideoSegment]) -> MappingResult:
    """
    Maps a timestamp from source space (original asset timeline) to target space (compiled timeline).
    Assumes sorted_segs is already sorted by (src_start + trim_left).
    """
    if not sorted_segs:
        return MappingResult(target=max(0, t_src), source=t_src, ratio=1.0, offset=0, segment=None)

    # 1. Before first segment
    v0 = sorted_segs[0]
    played_src_start_0 = v0.src_start + v0.trim_left
    if t_src < played_src_start_0:
        offset = t_src - played_src_start_0
        ratio = v0.effective_ratio
        t_tgt = v0.target_start + int(round(offset * ratio))
        return MappingResult(target=max(0, t_tgt), source=t_src, ratio=ratio, offset=offset, segment=v0)

    # 2. Within segments or in gaps
    for i in range(len(sorted_segs)):
        vk = sorted_segs[i]
        played_src_start_k = vk.src_start + vk.trim_left
        played_src_end_k = vk.src_start + vk.src_duration - vk.trim_right
        
        if played_src_start_k <= t_src < played_src_end_k:
            offset = t_src - played_src_start_k
            ratio = vk.effective_ratio
            t_tgt = vk.target_start + int(round(offset * ratio))
            return MappingResult(target=max(0, t_tgt), source=t_src, ratio=ratio, offset=offset, segment=vk)

        # Falls inside gap between vk and vk+1
        if i + 1 < len(sorted_segs):
            v_next = sorted_segs[i + 1]
            played_src_start_next = v_next.src_start + v_next.trim_left
            if played_src_end_k <= t_src < played_src_start_next:
                # Map to the start of the next segment
                offset = t_src - played_src_start_next
                ratio = v_next.effective_ratio
                return MappingResult(target=v_next.target_start, source=t_src, ratio=ratio, offset=offset, segment=v_next)

    # 3. Exceeds end of the last segment
    vn = sorted_segs[-1]
    played_src_end_n = vn.src_start + vn.src_duration - vn.trim_right
    offset = t_src - played_src_end_n
    ratio = vn.effective_ratio
    t_tgt = (vn.target_start + vn.target_duration) + int(round(offset * ratio))
    return MappingResult(target=max(0, t_tgt), source=t_src, ratio=ratio, offset=offset, segment=vn)


def map_target_to_source(t_tgt: int, sorted_segs: List[VideoSegment]) -> MappingResult:
    """
    Maps a timestamp from target space (compiled timeline) back to source space (original asset timeline).
    Assumes sorted_segs is already sorted by target_start.
    """
    if not sorted_segs:
        return MappingResult(target=t_tgt, source=max(0, t_tgt), ratio=1.0, offset=0, segment=None)

    # 1. Before first segment
    v0 = sorted_segs[0]
    if t_tgt < v0.target_start:
        offset = t_tgt - v0.target_start
        ratio = 1.0 / v0.effective_ratio if v0.effective_ratio > 0 else 1.0
        t_src = (v0.src_start + v0.trim_left) + int(round(offset * ratio))
        return MappingResult(target=t_tgt, source=max(0, t_src), ratio=ratio, offset=offset, segment=v0)

    # 2. Within segments
    for vk in sorted_segs:
        tgt_end_k = vk.target_start + vk.target_duration
        if vk.target_start <= t_tgt < tgt_end_k:
            offset = t_tgt - vk.target_start
            ratio = 1.0 / vk.effective_ratio if vk.effective_ratio > 0 else 1.0
            t_src = (vk.src_start + vk.trim_left) + int(round(offset * ratio))
            return MappingResult(target=t_tgt, source=max(0, t_src), ratio=ratio, offset=offset, segment=vk)

    # 3. Exceeds end of the last segment
    vn = sorted_segs[-1]
    tgt_end_n = vn.target_start + vn.target_duration
    offset = t_tgt - tgt_end_n
    ratio = 1.0 / vn.effective_ratio if vn.effective_ratio > 0 else 1.0
    t_src = (vn.src_start + vn.src_duration - vn.trim_right) + int(round(offset * ratio))
    return MappingResult(target=t_tgt, source=max(0, t_src), ratio=ratio, offset=offset, segment=vn)
