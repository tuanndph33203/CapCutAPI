import os
import json
import logging
import random
import uuid
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
    if any(ext in tr_name for ext in [".gif", ".png", ".jpg", ".jpeg", ".webp", "sticker", "overlay", "logo"]):
        return False
    
    mat_map = {m.get("id"): str(m.get("path") or m.get("material_name") or "").lower() for m in materials.get("videos", []) if isinstance(m, dict)}
    has_valid_video = False
    for seg in track.get("segments", []):
        mat_id = seg.get("material_id")
        path = mat_map.get(mat_id, "").lower()
        if any(path.endswith(ext) or (ext in path) for ext in [".gif", ".png", ".jpg", ".jpeg", ".webp", ".bmp"]):
            return False
        if any(path.endswith(ext) or (ext in path) for ext in [".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".m4v", ".ts"]):
            has_valid_video = True
            
    return has_valid_video

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
            
            main_video_segments = []
            for track in data.get("tracks", []):
                if not _is_main_video_track(track, materials):
                    continue
                    
                current_time = 0
                for segment in track.get("segments", []):
                    if randomize:
                        spd = round(base_speed + random.uniform(-0.02, 0.02), 3)
                    else:
                        spd = float(base_speed)
                    
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
                main_video_segments = track.get("segments", [])

            # Đồng bộ 1-to-1 tốc độ và mốc thời gian của audio_filtered_vocal theo video chính
            if main_video_segments:
                for track in data.get("tracks", []):
                    if track.get("type") == "audio" and track.get("name") == "audio_filtered_vocal":
                        a_segs = track.get("segments", [])
                        for seg_idx, v_seg in enumerate(main_video_segments):
                            if seg_idx < len(a_segs):
                                a_seg = a_segs[seg_idx]
                                v_src = v_seg.get("source_timerange", {})
                                v_tgt = v_seg.get("target_timerange", {})
                                a_seg["source_timerange"] = {"start": v_src.get("start", 0), "duration": v_src.get("duration", 0)}
                                a_seg["target_timerange"] = {"start": v_tgt.get("start", 0), "duration": v_tgt.get("duration", 0)}
                                spd = v_seg.get("speed", base_speed)
                                a_seg["speed"] = spd
                                
                                speed_id = a_seg.get("speed_id")
                                if speed_id and speed_id in speed_map:
                                    speed_map[speed_id]["speed"] = spd
                                updated = True
                    
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
                
            # Lấy danh sách phụ đề có mốc thời gian nguồn (_ocr_source_start)
            sub_segments = []
            for tr in text_tracks:
                for seg in tr.get("segments", []):
                    trange = seg.get("target_timerange", {})
                    dur = trange.get("duration", 0)
                    if dur > 0:
                        if "_ocr_source_start" not in seg:
                            seg["_ocr_source_start"] = trange.get("start", 0)
                        src_start = seg["_ocr_source_start"]
                        sub_segments.append({
                            "segment": seg,
                            "start": src_start,
                            "end": src_start + dur,
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
            
            # Cắt các video segment theo cut_points chuẩn từ mốc 0 -> total_dur (không lặp gối)
            updated = False
            for vtrack in video_tracks:
                orig_segs = vtrack.get("segments", [])
                if not orig_segs:
                    continue

                total_src_dur = max(
                    s.get("source_timerange", {}).get("start", 0) + s.get("source_timerange", {}).get("duration", 0)
                    for s in orig_segs
                )
                if total_src_dur <= 0:
                    continue

                base_template = json.loads(json.dumps(orig_segs[0]))
                new_vsegs = []
                current_src_start = 0
                cum_trimmed = 0
                sorted_cut_points = sorted(list(set(cut_points)))

                for cp in sorted_cut_points:
                    if current_src_start < cp < total_src_dur:
                        seg_src_dur = cp - current_src_start
                        if seg_src_dur > 100_000:
                            sub_seg = json.loads(json.dumps(base_template))
                            sub_seg["id"] = str(uuid.uuid4()).upper()
                            trimmed_dur = seg_src_dur - micro_trim_us if seg_src_dur > micro_trim_us else seg_src_dur
                            
                            sub_seg["source_timerange"] = {
                                "start": current_src_start,
                                "duration": max(100_000, seg_src_dur)
                            }
                            sub_seg["target_timerange"] = {
                                "start": current_src_start - cum_trimmed,
                                "duration": max(100_000, trimmed_dur)
                            }
                            new_vsegs.append(sub_seg)
                            cum_trimmed += micro_trim_us
                            current_src_start = cp
                            patched_count += 1

                remaining_dur = total_src_dur - current_src_start
                if remaining_dur > 0:
                    sub_seg = json.loads(json.dumps(base_template))
                    sub_seg["id"] = str(uuid.uuid4()).upper()
                    sub_seg["source_timerange"] = {
                        "start": current_src_start,
                        "duration": max(100_000, remaining_dur)
                    }
                    sub_seg["target_timerange"] = {
                        "start": current_src_start - cum_trimmed,
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
        logger.info("[AntiCopyright 1/5] Tien hanh Cat Thong Minh theo Phu De (~15s intervals)...")
        results["smart_splits"] = patch_smart_subtitle_gaps(
            draft_path,
            target_interval_sec=float(config.get("max_segment_sec", 15.0)),
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
        spd = float(config.get("video_speed") or config.get("speed") or 1.05)
        results["speed"] = patch_video_speed_dynamic(draft_path, base_speed=spd, randomize=True)
        
    if config.get("color_adjust", True):
        logger.info("[AntiCopyright 5/5] Tien hanh Phu Bo Loc Mau Dong (Color Adjustments)...")
        results["color_adjust"] = patch_video_color_adjustments_dynamic(draft_path, randomize=True)
        
    # Tự động Resync mốc thời gian Phụ đề & TTS theo Video sau khi Cắt & Lách bản quyền
    results["resynced_subs"] = resync_subtitles_and_audio_to_video_timeline(draft_path)
        
    logger.info(f"=== DA HOAN THANH QUY TRINH LACH BAN QUYEN DONG (SMART DEFENSE) ===")
    logger.info(f"Thong ke chi tiet: {results}")
    return results

def map_source_to_target_timeline(t_src: int, video_segs: List[Dict[str, Any]]) -> tuple:
    """
    Chuyển đổi mốc thời gian t_src từ Video Gốc (Source Space) sang Timeline Video Mới (Target Space).
    Công thức đơn điệu (monotonic), không dồn ép, xử lý hoàn hảo khoảng hở (gaps) và phần vượt đuôi video.
    """
    if not video_segs:
        return max(0, t_src), 1.0

    # 1. Trước phân đoạn video đầu tiên
    v0 = video_segs[0]
    if t_src < v0["src_start"]:
        offset = t_src - v0["src_start"]
        t_tgt = v0["tgt_start"] + int(round(offset * v0["ratio"]))
        return max(0, t_tgt), v0["ratio"]

    # 2. Trong các phân đoạn video hoặc khoảng hở giữa các phân đoạn
    for i in range(len(video_segs)):
        vk = video_segs[i]
        if vk["src_start"] <= t_src < vk["src_end"]:
            # Rơi vào trong phân đoạn video vk
            offset = t_src - vk["src_start"]
            t_tgt = vk["tgt_start"] + int(round(offset * vk["ratio"]))
            return max(0, t_tgt), vk["ratio"]

        # Rơi vào khoảng hở giữa vk và vk+1 (khoảng bị cắt đi)
        if i + 1 < len(video_segs):
            v_next = video_segs[i + 1]
            if vk["src_end"] <= t_src < v_next["src_start"]:
                # Map mốc về đầu phân đoạn tiếp theo v_next
                return v_next["tgt_start"], vk["ratio"]

    # 3. Vượt qua đuôi phân đoạn video cuối cùng
    vn = video_segs[-1]
    offset = t_src - vn["src_end"]
    t_tgt = vn["tgt_end"] + int(round(offset * vn["ratio"]))
    return max(0, t_tgt), vn["ratio"]


def resync_only_subtitles_to_video_timeline(draft_path: str) -> int:
    """
    Chỉ đồng bộ mốc thời gian của Phụ Đề (track type="text") theo Timeline Video sau khi Cắt & Lách bản quyền.
    Tuyệt đối không can thiệp hay thay đổi audio, video hoặc logo sticker.
    """
    patched_count = 0
    for content_path in find_draft_content_paths(draft_path):
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            materials = data.get("materials", {})
            video_segs = []
            for tr in data.get("tracks", []):
                if _is_main_video_track(tr, materials):
                    for s in tr.get("segments", []):
                        s_src = s.get("source_timerange", {})
                        s_tgt = s.get("target_timerange", {})
                        src_start = s_src.get("start", 0)
                        src_dur = s_src.get("duration", 0)
                        tgt_start = s_tgt.get("start", 0)
                        tgt_dur = s_tgt.get("duration", 0)
                        if src_dur > 0 and tgt_dur > 0:
                            video_segs.append({
                                "src_start": src_start,
                                "src_end": src_start + src_dur,
                                "tgt_start": tgt_start,
                                "tgt_end": tgt_start + tgt_dur,
                                "ratio": tgt_dur / src_dur
                            })

            if not video_segs:
                continue

            video_segs.sort(key=lambda x: x["src_start"])
            updated = False

            for tr in data.get("tracks", []):
                if tr.get("type") == "text":
                    new_segs = []
                    for seg in tr.get("segments", []):
                        s_tgt = seg.setdefault("target_timerange", {})
                        cur_start = s_tgt.get("start", 0)
                        cur_dur = s_tgt.get("duration", 0)

                        if "_ocr_source_start" not in seg:
                            seg["_ocr_source_start"] = cur_start

                        src_time = seg["_ocr_source_start"]
                        new_start, ratio = map_source_to_target_timeline(src_time, video_segs)
                        new_dur = max(50_000, int(round(cur_dur * ratio)))

                        if s_tgt.get("start") != new_start or s_tgt.get("duration") != new_dur:
                            s_tgt["start"] = new_start
                            s_tgt["duration"] = new_dur
                            updated = True
                            patched_count += 1
                        new_segs.append(seg)
                    tr["segments"] = new_segs

            if updated:
                with open(content_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Loi resync_only_subtitles_to_video_timeline tai {content_path}: {e}")
    return patched_count


def resync_subtitles_and_audio_to_video_timeline(draft_path: str) -> int:
    """Tự động đồng bộ lại 100% mốc thời gian của Subtitle & Audio TTS theo Timeline Video sau khi Cắt & Lách bản quyền."""
    patched_count = 0
    for content_path in find_draft_content_paths(draft_path):
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            materials = data.get("materials", {})
            video_segs = []
            for tr in data.get("tracks", []):
                if _is_main_video_track(tr, materials):
                    for s in tr.get("segments", []):
                        s_src = s.get("source_timerange", {})
                        s_tgt = s.get("target_timerange", {})
                        src_start = s_src.get("start", 0)
                        src_dur = s_src.get("duration", 0)
                        tgt_start = s_tgt.get("start", 0)
                        tgt_dur = s_tgt.get("duration", 0)
                        if src_dur > 0 and tgt_dur > 0:
                            video_segs.append({
                                "src_start": src_start,
                                "src_end": src_start + src_dur,
                                "tgt_start": tgt_start,
                                "tgt_end": tgt_start + tgt_dur,
                                "ratio": tgt_dur / src_dur
                            })

            if not video_segs:
                continue

            video_segs.sort(key=lambda x: x["src_start"])
            updated = False

            main_video_target_dur = max(vs["tgt_end"] for vs in video_segs) if video_segs else 0

            for tr in data.get("tracks", []):
                if tr.get("type") in ("text", "audio"):
                    if tr.get("name") == "audio_filtered_vocal":
                        continue
                    new_segs = []
                    for seg in tr.get("segments", []):
                        s_tgt = seg.setdefault("target_timerange", {})
                        cur_start = s_tgt.get("start", 0)
                        cur_dur = s_tgt.get("duration", 0)

                        # Lưu giữ mốc thời gian OCR ban đầu để đảm bảo tính Idempotent (không bị trôi lặp)
                        if "_ocr_source_start" not in seg:
                            seg["_ocr_source_start"] = cur_start

                        src_time = seg["_ocr_source_start"]
                        new_start, ratio = map_source_to_target_timeline(src_time, video_segs)
                        new_dur = max(50_000, int(round(cur_dur * ratio)))

                        # Giới hạn new_start và duration nằm trong mốc video chính (đảm bảo giữ nguyên 100% số lượng phụ đề)
                        if main_video_target_dur > 0 and new_start >= main_video_target_dur:
                            new_start = max(0, main_video_target_dur - 100_000)

                        if main_video_target_dur > 0 and (new_start + new_dur) > main_video_target_dur:
                            new_dur = max(50_000, main_video_target_dur - new_start)

                        if s_tgt.get("start") != new_start or s_tgt.get("duration") != new_dur:
                            s_tgt["start"] = new_start
                            s_tgt["duration"] = new_dur
                            updated = True
                            patched_count += 1
                        new_segs.append(seg)
                    tr["segments"] = new_segs

            # 4. Đồng bộ lại thời lượng hiển thị cho các logo sticker (GIF/PNG) khớp 100% độ dài video chính mới
            main_video_target_dur = max(vs["tgt_end"] for vs in video_segs) if video_segs else 0
            if main_video_target_dur > 0:
                for tr in data.get("tracks", []):
                    if tr.get("type") == "video" and not _is_main_video_track(tr, materials):
                        for seg in tr.get("segments", []):
                            s_tgt = seg.setdefault("target_timerange", {})
                            s_tgt["start"] = 0
                            s_tgt["duration"] = main_video_target_dur
                            updated = True
                            patched_count += 1

            if updated:
                data["_resync_version"] = int(data.get("_resync_version", 0)) + 1
                with open(content_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Loi resync_subtitles_and_audio_to_video_timeline tai {content_path}: {e}")

    logger.info(f"Da dong bo lai Timeline Phu de & TTS cho {patched_count} phan doan theo Video moi.")
    return patched_count


