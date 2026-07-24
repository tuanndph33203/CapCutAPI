import os
import json
import logging
import random
import uuid
from typing import Dict, List, Any, Optional

from timeline.models import VideoSegment, SubtitleSegment, AudioSegment
from timeline.parser import parse_draft, _is_main_video_track
from timeline.compiler import compile_timeline, compile_associated_segments
from timeline.mapper import map_source_to_target, map_target_to_source
from timeline.exporter import export_draft
from timeline.validator import validate_timeline
from timeline.logger import TimelineLogger

from operations.split import split_video_segments
from operations.speed import apply_speed_dynamic
from operations.mirror import apply_mirror
from operations.crop import apply_scale_crop_dynamic
from operations.color import apply_color_adjustments_dynamic

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

def patch_video_mirror(draft_path: str, mirror_horizontal: bool = True) -> int:
    """1. Lật ngang toàn bộ video chính (Horizontal Flip / Mirror) sử dụng Timeline Engine."""
    patched_count = 0
    for content_path in find_draft_content_paths(draft_path):
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            video_segs, subtitle_segs, audio_segs = parse_draft(data)
            if not video_segs:
                continue
                
            apply_mirror(video_segs, mirror_horizontal)
            compile_timeline(video_segs)
            export_draft(data, video_segs, subtitle_segs, audio_segs)
            
            with open(content_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            patched_count += len(video_segs)
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
                
            video_segs, subtitle_segs, audio_segs = parse_draft(data)
            if not video_segs:
                continue
                
            apply_scale_crop_dynamic(video_segs, base_ratio, randomize)
            compile_timeline(video_segs)
            export_draft(data, video_segs, subtitle_segs, audio_segs)
            
            with open(content_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            patched_count += len(video_segs)
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
                
            video_segs, subtitle_segs, audio_segs = parse_draft(data)
            if not video_segs:
                continue
                
            apply_speed_dynamic(video_segs, base_speed, randomize)
            compile_timeline(video_segs)
            
            # Compile associated subtitles and audio segments
            from subtitle.compiler import compile_subtitles
            from audio.compiler import compile_audio
            compile_subtitles(subtitle_segs, video_segs)
            compile_audio(audio_segs, video_segs)
            
            validate_timeline(video_segs, subtitle_segs, audio_segs)
            export_draft(data, video_segs, subtitle_segs, audio_segs)
            
            with open(content_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            patched_count += len(video_segs)
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
                
            video_segs, subtitle_segs, audio_segs = parse_draft(data)
            if not video_segs:
                continue
                
            apply_color_adjustments_dynamic(video_segs, randomize)
            compile_timeline(video_segs)
            export_draft(data, video_segs, subtitle_segs, audio_segs)
            
            with open(content_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            patched_count += len(video_segs)
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
                
            video_segs, subtitle_segs, audio_segs = parse_draft(data)
            if not subtitle_segs or not video_segs:
                continue
                
            # Find cut points (silences) from subtitles
            sub_segments = []
            for sub in subtitle_segs:
                sub_segments.append({
                    "start": sub.ocr_source_start,
                    "end": sub.ocr_source_start + sub.ocr_source_duration
                })
            sub_segments.sort(key=lambda x: x["start"])
            
            cut_points = []
            last_cut_time = 0
            
            for i in range(len(sub_segments) - 1):
                cur_end = sub_segments[i]["end"]
                next_start = sub_segments[i+1]["start"]
                gap = next_start - cur_end
                
                if gap >= 150_000:
                    current_duration = next_start - last_cut_time
                    if current_duration >= target_interval_us:
                        cut_point = cur_end + (gap // 2)
                        cut_points.append(cut_point)
                        last_cut_time = cut_point
                        
            # Fallback
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
                continue
                
            # Split video segments using split operations
            split_segs = split_video_segments(video_segs, cut_points, micro_trim_us)
            
            # Compile
            compile_timeline(split_segs)
            
            # Compile subtitles and audio segments
            from subtitle.compiler import compile_subtitles
            from audio.compiler import compile_audio
            compile_subtitles(subtitle_segs, split_segs)
            compile_audio(audio_segs, split_segs)
            
            validate_timeline(split_segs, subtitle_segs, audio_segs)
            export_draft(data, split_segs, subtitle_segs, audio_segs)
            
            with open(content_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
            patched_count += len(cut_points)
            
            # Log video segments state
            TimelineLogger.log_video_segments(split_segs)
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
    logger.info(f"Thong ke chi tiết: {results}")
    return results

def map_source_to_target_timeline(t_src: int, video_segs: List[Dict[str, Any]]) -> tuple:
    """
    Chuyển đổi mốc thời gian t_src từ Video Gốc (Source Space) sang Timeline Video Mới (Target Space).
    Backward-compatible wrapper converting list of dicts to VideoSegment models.
    """
    models = []
    for vk in video_segs:
        models.append(VideoSegment(
            id=vk.get("id", ""),
            material_id=vk.get("material_id", ""),
            src_start=vk["src_start"],
            src_duration=vk["src_end"] - vk["src_start"],
            trim_left=0,
            trim_right=0,
            speed=vk.get("speed", 1.0),
            target_start=vk["tgt_start"],
            target_duration=vk["tgt_end"] - vk["tgt_start"]
        ))
    return map_source_to_target(t_src, models)

def _resync_timeline_new(draft_path: str, sync_audio: bool) -> int:
    patched_count = 0
    for content_path in find_draft_content_paths(draft_path):
        try:
            with open(content_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            video_segs, subtitle_segs, audio_segs = parse_draft(data)
            if not video_segs:
                continue
                
            compile_timeline(video_segs)
            
            from subtitle.compiler import compile_subtitles
            compile_subtitles(subtitle_segs, video_segs)
            
            if sync_audio:
                from audio.compiler import compile_audio
                compile_audio(audio_segs, video_segs)
                
            validate_timeline(video_segs, subtitle_segs, audio_segs)
            export_draft(data, video_segs, subtitle_segs, audio_segs, sync_video=False, sync_audio=sync_audio, sync_subtitles=True)
            
            with open(content_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
            patched_count += len(subtitle_segs) + (len(audio_segs) if sync_audio else 0)
        except Exception as e:
            logger.error(f"Loi _resync_timeline_new: {e}")
    return patched_count

def resync_only_subtitles_to_video_timeline(draft_path: str) -> int:
    """
    Chỉ đồng bộ mốc thời gian của Phụ Đề (track type="text") theo Timeline Video sau khi Cắt & Lách bản quyền.
    Tuyệt đối không can thiệp hay thay đổi audio, video hoặc logo sticker.
    """
    return _resync_timeline_new(draft_path, sync_audio=False)

def resync_subtitles_and_audio_to_video_timeline(draft_path: str) -> int:
    """Tự động đồng bộ lại 100% mốc thời gian của Subtitle & Audio TTS theo Timeline Video sau khi Cắt & Lách bản quyền."""
    return _resync_timeline_new(draft_path, sync_audio=True)
