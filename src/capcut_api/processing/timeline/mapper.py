from typing import List, Tuple
from .models import VideoSegment, MappingResult

def _is_single_continuous_asset(sorted_segs: List[VideoSegment]) -> bool:
    return (
        len(sorted_segs) > 1
        and all(s.material_id == sorted_segs[0].material_id for s in sorted_segs)
        and all(sorted_segs[i].src_start <= sorted_segs[i+1].src_start for i in range(len(sorted_segs)-1))
        and sorted_segs[-1].src_start > 0
    )

def map_source_to_target(t_src: int, sorted_segs: List[VideoSegment]) -> MappingResult:
    """
    Maps a timestamp from source space (original asset timeline) to target space (compiled timeline).
    """
    if not sorted_segs:
        return MappingResult(target=max(0, t_src), source=t_src, ratio=1.0, offset=0, segment=None)

    is_single = _is_single_continuous_asset(sorted_segs)
    if is_single:
        def get_played_range(s):
            return s.src_start + s.trim_left, s.src_start + s.src_duration - s.trim_right
    else:
        def get_played_range(s):
            return s.timeline_src_start, s.timeline_src_start + s.effective_source_duration

    # 1. Before first segment
    v0 = sorted_segs[0]
    p_start_0, _ = get_played_range(v0)
    if t_src < p_start_0:
        offset = t_src - p_start_0
        ratio = v0.effective_ratio
        t_tgt = v0.target_start + int(round(offset * ratio))
        return MappingResult(target=max(0, t_tgt), source=t_src, ratio=ratio, offset=offset, segment=v0)

    # 2. Within segments or in gaps
    for i in range(len(sorted_segs)):
        vk = sorted_segs[i]
        p_start_k, p_end_k = get_played_range(vk)
        
        if p_start_k <= t_src < p_end_k:
            offset = t_src - p_start_k
            ratio = vk.effective_ratio
            t_tgt = vk.target_start + int(round(offset * ratio))
            return MappingResult(target=max(0, t_tgt), source=t_src, ratio=ratio, offset=offset, segment=vk)

        # Falls inside gap between vk and vk+1
        if i + 1 < len(sorted_segs):
            v_next = sorted_segs[i + 1]
            p_start_next, _ = get_played_range(v_next)
            if p_end_k <= t_src < p_start_next:
                offset = t_src - p_start_next
                ratio = v_next.effective_ratio
                return MappingResult(target=v_next.target_start, source=t_src, ratio=ratio, offset=offset, segment=v_next)

    # 3. Exceeds end of the last segment
    vn = sorted_segs[-1]
    _, p_end_n = get_played_range(vn)
    offset = t_src - p_end_n
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

    is_single = _is_single_continuous_asset(sorted_segs)
    if is_single:
        def get_played_src_start(s):
            return s.src_start + s.trim_left
        def get_played_src_end(s):
            return s.src_start + s.src_duration - s.trim_right
    else:
        def get_played_src_start(s):
            return s.timeline_src_start
        def get_played_src_end(s):
            return s.timeline_src_start + s.effective_source_duration

    # 1. Before first segment
    v0 = sorted_segs[0]
    if t_tgt < v0.target_start:
        offset = t_tgt - v0.target_start
        ratio = 1.0 / v0.effective_ratio if v0.effective_ratio > 0 else 1.0
        t_src = get_played_src_start(v0) + int(round(offset * ratio))
        return MappingResult(target=t_tgt, source=max(0, t_src), ratio=ratio, offset=offset, segment=v0)

    # 2. Within segments
    for vk in sorted_segs:
        tgt_end_k = vk.target_start + vk.target_duration
        if vk.target_start <= t_tgt < tgt_end_k:
            offset = t_tgt - vk.target_start
            ratio = 1.0 / vk.effective_ratio if vk.effective_ratio > 0 else 1.0
            t_src = get_played_src_start(vk) + int(round(offset * ratio))
            return MappingResult(target=t_tgt, source=max(0, t_src), ratio=ratio, offset=offset, segment=vk)

    # 3. Exceeds end of the last segment
    vn = sorted_segs[-1]
    tgt_end_n = vn.target_start + vn.target_duration
    offset = t_tgt - tgt_end_n
    ratio = 1.0 / vn.effective_ratio if vn.effective_ratio > 0 else 1.0
    t_src = get_played_src_end(vn) + int(round(offset * ratio))
    return MappingResult(target=t_tgt, source=max(0, t_src), ratio=ratio, offset=offset, segment=vn)
