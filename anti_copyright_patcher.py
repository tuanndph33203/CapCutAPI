import os
import json
import logging
import random
from typing import Dict, List, Any, Optional

logger = logging.getLogger("AntiCopyrightPatcher")
if not logger.handlers:
    import sys
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s][%(levelname)s][AntiCopyright] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def find_draft_content_paths(draft_path: str) -> List[str]:
    """Tìm tất cả các file draft_content.json hoặc file timeline trong thư mục draft."""
    paths = []
    if not os.path.exists(draft_path):
        return paths
        
    for root, _, files in os.walk(draft_path):
        for file in files:
            if file in ("draft_content.json", "draft_info.json") or file.endswith(".tmp"):
                file_path = os.path.join(root, file)
                if file_path not in paths:
                    paths.append(file_path)
                    
    # Sắp xếp ưu tiên draft_content.json
    paths.sort(key=lambda p: (0 if ("draft_content.json" in p or p.endswith(".tmp")) else 1, p))
    return paths

def _is_main_video_track(track: dict, materials: dict) -> bool:
    """Kiểm tra track có phải là Video chính hay không (loại trừ logo, sticker, overlay GIF/PNG)."""
    if track.get("type") != "video":
        return False
    tr_name = str(track.get("name", "")).lower()
    if any(ext in tr_name for ext in [".gif", ".png", ".jpg", "sticker", "overlay", "logo"]):
        return False
    
    mat_map = {m.get("id"): str(m.get("path", "")).lower() for m in materials.get("videos", []) if isinstance(m, dict)}
    for seg in track.get("segments", []):
        mat_id = seg.get("material_id")
        path = mat_map.get(mat_id, "")
        if path and any(path.endswith(ext) for ext in [".gif", ".png", ".jpg", ".jpeg", ".webp"]):
            return False
            
    return True

def patch_video_mirror(draft_path: str, mirror_horizontal: bool = True) -> int:
    """1. Lật ngang toàn bộ video chính (Horizontal Flip / Mirror)."""
    patched_count = 0
    for content_path in find_draft_content_paths(draft_path):
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            materials = data.setdefault("materials", {})
            updated = False
            for track in data.get("tracks", []):
                if not _is_main_video_track(track, materials):
                    continue
                for segment in track.get("segments", []):
                    clip = segment.get("clip")
                    if not isinstance(clip, dict):
                        clip = {}
                        segment["clip"] = clip
                    flip = clip.get("flip")
                    if not isinstance(flip, dict):
                        flip = {}
                        clip["flip"] = flip
                    if flip.get("horizontal") != mirror_horizontal:
                        flip["horizontal"] = bool(mirror_horizontal)
                        flip["vertical"] = False
                        updated = True
                        patched_count += 1
                        
            if updated:
                with open(content_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Lỗi patch_video_mirror tại {content_path}: {e}")
            
    logger.info(f"Da lat ngang video tren {patched_count} phan doan.")
    return patched_count

def patch_video_scale_crop_dynamic(draft_path: str, base_ratio: float = 1.07, randomize: bool = True) -> int:
    """2. Zoom & Crop ĐỘNG: Phóng to ngẫu nhiên (1.05 - 1.10) theo từng segment để triệt tiêu pattern nhận diện."""
    patched_count = 0
    for content_path in find_draft_content_paths(draft_path):
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            materials = data.setdefault("materials", {})
            updated = False
            for track in data.get("tracks", []):
                if not _is_main_video_track(track, materials):
                    continue
                for segment in track.get("segments", []):
                    # Tính tỷ lệ Zoom động từng segment
                    if randomize:
                        seg_scale = round(random.uniform(1.05, 1.10), 3)
                    else:
                        seg_scale = float(base_ratio)
                        
                    clip = segment.get("clip")
                    if not isinstance(clip, dict):
                        clip = {}
                        segment["clip"] = clip
                    scale = clip.get("scale")
                    if not isinstance(scale, dict):
                        scale = {}
                        clip["scale"] = scale
                    scale["x"] = seg_scale
                    scale["y"] = seg_scale
                    updated = True
                    patched_count += 1
                    
            if updated:
                with open(content_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Loi patch_video_scale_crop_dynamic tai {content_path}: {e}")
            
    logger.info(f"Da Zoom & Crop DONG tren {patched_count} phan doan video.")
    return patched_count

def patch_video_speed_dynamic(draft_path: str, base_speed: float = 1.05, randomize: bool = True) -> int:
    """3. Chỉnh tốc độ ĐỘNG (1.04x - 1.08x) ngẫu nhiên làm lệch mốc thời gian Content ID."""
    if base_speed <= 0:
        return 0
    patched_count = 0
    for content_path in find_draft_content_paths(draft_path):
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            updated = False
            materials = data.setdefault("materials", {})
            speeds = materials.setdefault("speeds", [])
            speed_map = {s.get("id"): s for s in speeds if isinstance(s, dict)}
            
            for track in data.get("tracks", []):
                if not _is_main_video_track(track, materials):
                    continue
                    
                current_time = 0
                for segment in track.get("segments", []):
                    spd = round(random.uniform(1.04, 1.07), 3) if randomize else float(base_speed)
                    
                    seg_speed_id = None
                    extra_refs = segment.get("extra_material_refs", [])
                    for ref in extra_refs:
                        if ref in speed_map:
                            seg_speed_id = ref
                            break
                            
                    if seg_speed_id and seg_speed_id in speed_map:
                        speed_map[seg_speed_id]["speed"] = spd
                    else:
                        segment["speed"] = spd
                        
                    source = segment.get("source_timerange", {})
                    target = segment.get("target_timerange", {})
                    if source and source.get("duration", 0) > 0:
                        new_duration = int(round(source["duration"] / spd))
                        target["start"] = current_time
                        target["duration"] = new_duration
                        current_time += new_duration
                    elif target and target.get("duration", 0) > 0:
                        new_duration = int(round(target["duration"] / spd))
                        target["start"] = current_time
                        target["duration"] = new_duration
                        current_time += new_duration
                        
                    updated = True
                    patched_count += 1
                    
            if updated:
                with open(content_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Loi patch_video_speed_dynamic tai {content_path}: {e}")
            
    logger.info(f"Da dieu chinh Toc do DONG tren {patched_count} phan doan video.")
    return patched_count

def patch_video_color_adjustments_dynamic(draft_path: str, randomize: bool = True) -> int:
    """4. Bộ lọc màu sắc ĐỘNG (Contrast, Brightness, Saturation ngẫu nhiên nhẹ)."""
    patched_count = 0
    for content_path in find_draft_content_paths(draft_path):
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            materials = data.setdefault("materials", {})
            updated = False
            for track in data.get("tracks", []):
                if not _is_main_video_track(track, materials):
                    continue
                for segment in track.get("segments", []):
                    b = round(random.uniform(0.02, 0.05), 3) if randomize else 0.03
                    c = round(random.uniform(0.03, 0.06), 3) if randomize else 0.04
                    s = round(random.uniform(0.01, 0.03), 3) if randomize else 0.02
                    
                    adj_dict = {"brightness": b, "contrast": c, "saturation": s}
                    segment["color_adjustments"] = adj_dict
                    updated = True
                    patched_count += 1
                    
            if updated:
                with open(content_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Loi patch_video_color_adjustments_dynamic tai {content_path}: {e}")
            
    logger.info(f"Da phu Bo loc mau sac DONG tren {patched_count} phan doan.")
    return patched_count

def patch_smart_subtitle_gaps(draft_path: str, target_interval_sec: float = 30.0, micro_trim_ms: int = 200) -> int:
    """
    5. THUẬT TOÁN CẮT THÔNG MINH BẰNG KHOẢNG NGHỈ PHỤ ĐỀ (Subtitle Gap Splitter):
       - Tìm các khoảng im lặng (Gap) giữa 2 câu phụ đề gần mốc 30 giây nhất.
       - Cắt video tại mốc khoảng nghỉ và xén nhẹ micro_trim_ms (150-250ms).
       - Tự động lùi giảm gối timestamp phụ đề phía sau để giữ chuẩn 100% đồng bộ giọng lồng và thoại.
    """
    patched_count = 0
    target_interval_us = int(target_interval_sec * 1_000_000)
    micro_trim_us = int(micro_trim_ms * 1_000)
    
    for content_path in find_draft_content_paths(draft_path):
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            materials = data.setdefault("materials", {})
            tracks = data.get("tracks", [])
            text_tracks = [t for t in tracks if t.get("type") == "text"]
            video_tracks = [t for t in tracks if _is_main_video_track(t, materials)]
            
            if not text_tracks or not video_tracks:
                continue
                
            # Lấy danh sách phụ đề có mốc thời gian
            sub_segments = []
            for tr in text_tracks:
                for seg in tr.get("segments", []):
                    trange = seg.get("target_timerange", {})
                    start = trange.get("start", 0)
                    dur = trange.get("duration", 0)
                    if dur > 0:
                        sub_segments.append({
                            "segment": seg,
                            "start": start,
                            "end": start + dur,
                            "duration": dur
                        })
                        
            sub_segments.sort(key=lambda x: x["start"])
            if not sub_segments:
                logger.warning("[AntiCopyright] [Buc 5/5 Cat Thong Minh] Khong tim thay phu de hop le trong draft.")
                continue
                
            logger.info(f"[AntiCopyright] [Buc 5/5 Cat Thong Minh] Da quet {len(sub_segments)} cau phu de. Dang tim diem cat nghi im lang...")
            
            # Tìm mốc khoảng trống không thoại (Gaps) gần mỗi 30s
            cut_points = []
            last_cut_time = 0
            
            for i in range(len(sub_segments) - 1):
                cur_end = sub_segments[i]["end"]
                next_start = sub_segments[i+1]["start"]
                gap = next_start - cur_end
                
                # Khoảng trống không thoại lớn hơn 150ms
                if gap >= 150_000:
                    current_duration = next_start - last_cut_time
                    if current_duration >= target_interval_us:
                        cut_point = cur_end + (gap // 2)
                        cut_points.append(cut_point)
                        last_cut_time = cut_point
                        
            # Fallback nới lỏng mốc 20s nếu mốc 30s chưa tìm thấy điểm cắt
            if not cut_points:
                fallback_interval_us = int(20.0 * 1_000_000)
                last_cut_time = 0
                for i in range(len(sub_segments) - 1):
                    cur_end = sub_segments[i]["end"]
                    next_start = sub_segments[i+1]["start"]
                    gap = next_start - cur_end
                    if gap >= 80_000:
                        current_duration = next_start - last_cut_time
                        if current_duration >= fallback_interval_us:
                            cut_point = cur_end + (gap // 2)
                            cut_points.append(cut_point)
                            last_cut_time = cut_point

            if not cut_points:
                logger.info(f"[AntiCopyright] [Buc 5/5 Cat Thong Minh] Khong phat hien khoang im lang du dieu kien. Giu nguyen video 1 phan doan.")
                continue
                
            logger.info(f"[AntiCopyright] [Buc 5/5 Cat Thong Minh] Phat hien {len(cut_points)} diem im lang -> CAN CAT VIDEO THANH {len(cut_points) + 1} PHAN DOAN!")
            
            # Cắt các video segment theo cut_points
            updated = False
            for vtrack in video_tracks:
                orig_segs = vtrack.get("segments", [])
                new_vsegs = []
                cum_trimmed = 0
                
                for seg in orig_segs:
                    v_start = seg.get("target_timerange", {}).get("start", 0)
                    v_dur = seg.get("target_timerange", {}).get("duration", 0)
                    v_end = v_start + v_dur
                    
                    current_sub_start = v_start
                    for cp in cut_points:
                        if v_start <= cp < v_end:
                            sub_dur = cp - current_sub_start
                            if sub_dur > 100_000:
                                sub_seg = json.loads(json.dumps(seg))
                                trimmed_dur = sub_dur - micro_trim_us if sub_dur > micro_trim_us else sub_dur
                                sub_seg["target_timerange"] = {
                                    "start": current_sub_start - cum_trimmed,
                                    "duration": max(100_000, trimmed_dur)
                                }
                                new_vsegs.append(sub_seg)
                                cum_trimmed += micro_trim_us
                                current_sub_start = cp
                                patched_count += 1
                                
                    remaining_dur = v_end - current_sub_start
                    if remaining_dur > 0:
                        sub_seg = json.loads(json.dumps(seg))
                        sub_seg["target_timerange"] = {
                            "start": current_sub_start - cum_trimmed,
                            "duration": max(100_000, remaining_dur)
                        }
                        new_vsegs.append(sub_seg)
                        
                if new_vsegs:
                    vtrack["segments"] = new_vsegs
                    updated = True
                    
            # Giảm gối (Shift lùi) Timestamp cho phụ đề tương ứng với mốc bị xén
            for sub_info in sub_segments:
                sub_start = sub_info["start"]
                num_trims = sum(1 for cp in cut_points if cp <= sub_start)
                total_offset = num_trims * micro_trim_us
                
                sub_seg = sub_info["segment"]
                trange = sub_seg.setdefault("target_timerange", {})
                trange["start"] = max(0, sub_start - total_offset)
                updated = True
                
            if updated:
                with open(content_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Loi patch_smart_subtitle_gaps tai {content_path}: {e}")
            
    logger.info(f"Da hoan thanh Cat Thong Minh theo Phu De ({patched_count} vet cat thuc te).")
    return patched_count

def apply_full_anti_copyright_pipeline(draft_path: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Tự động thực thi toàn bộ quy trình Lách bản quyền ĐỘNG & Cắt Thông Minh."""
    if config is None:
        config = {}
        
    results = {
        "mirror": 0,
        "scale_crop": 0,
        "speed": 0,
        "color_adjust": 0,
        "smart_splits": 0
    }
    
    logger.info("=== BAT DAU THUC THI BO 5 THUAT TOAN LACH BAN QUYEN DONG (SMART DEFENSE) ===")
    
    # 1. Cắt thông minh theo khoảng nghỉ phụ đề trước (nếu bật)
    if config.get("auto_splits", True) or config.get("smart_splits", True):
        logger.info("[AntiCopyright 1/5] Tien hanh Cat Thong Minh theo Phu De (~30s intervals)...")
        results["smart_splits"] = patch_smart_subtitle_gaps(
            draft_path,
            target_interval_sec=float(config.get("max_segment_sec", 30.0)),
            micro_trim_ms=int(config.get("micro_trim_ms", 200))
        )
        
    # 2. Áp dụng các thuật toán ĐỘNG (Dynamic Matrix)
    if config.get("mirror_video", True):
        logger.info("[AntiCopyright 2/5] Tien hanh Lat Ngang Video Chinh (Horizontal Mirror)...")
        results["mirror"] = patch_video_mirror(draft_path, mirror_horizontal=True)
        
    if config.get("scale_crop", True):
        logger.info("[AntiCopyright 3/5] Tien hanh Zoom & Crop Dong 1.05x - 1.10x (Giu nguyen Logo/Sticker)...")
        ratio = float(config.get("scale_ratio", 1.07))
        results["scale_crop"] = patch_video_scale_crop_dynamic(draft_path, base_ratio=ratio, randomize=True)
        
    if config.get("speed_patch", True):
        logger.info("[AntiCopyright 4/5] Tien hanh Chinh Toc Do Dong ngau nhien (Speed Matrix)...")
        spd = float(config.get("video_speed", 1.05))
        results["speed"] = patch_video_speed_dynamic(draft_path, base_speed=spd, randomize=True)
        
    if config.get("color_adjust", True):
        logger.info("[AntiCopyright 5/5] Tien hanh Phu Bo Loc Mau Dong (Color Adjustments)...")
        results["color_adjust"] = patch_video_color_adjustments_dynamic(draft_path, randomize=True)
        
    logger.info(f"=== DA HOAN THANH QUY TRINH LACH BAN QUYEN DONG (SMART DEFENSE) ===")
    logger.info(f"Thong ke chi tiet: {results}")
    return results
