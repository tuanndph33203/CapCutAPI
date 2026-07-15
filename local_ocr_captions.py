import os
# Tắt cơ chế spin-wait của ONNXRuntime trên CPU để tránh FULL CPU (100%) khi chờ GPU DirectML xử lý
os.environ["ONNXRUNTIME_CPU_THREAD_ALLOW_SPINNING"] = "0"
# Hạn chế số luồng của FFMPEG giải mã trong OpenCV để tránh FULL CPU khi giải mã video
os.environ["OPENCV_FFMPEG_THREADS"] = "4"

import json
import time
import tempfile
import subprocess
import re
from pathlib import Path
from typing import Callable, Iterable
from difflib import SequenceMatcher

import cv2
import numpy as np
import pyJianYingDraft as draft

from local_whisper_captions import _import_srt_to_content, _find_primary_draft_json, _prepend_nvidia_dll_dirs_to_path


def _normalize_text(text: str) -> str:
    """Loại bỏ khoảng trắng và ký tự đặc biệt để so sánh chuỗi chính xác hơn."""
    return "".join(c for c in text if c.isalnum())

def _string_similarity(a: str, b: str) -> float:
    """Tính tỉ lệ tương đồng giữa hai chuỗi, hỗ trợ đảo thứ tự từ và chuỗi con."""
    norm_a = _normalize_text(a)
    norm_b = _normalize_text(b)
    if not norm_a or not norm_b:
        return 0.0
    
    # 1. SequenceMatcher ratio (tốt cho chuỗi đúng thứ tự)
    ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
    
    # 2. Character set overlap (Jaccard & containment - tốt cho đảo vị trí hoặc bị cắt/thiếu chữ)
    set_a = set(norm_a)
    set_b = set(norm_b)
    intersection = set_a.intersection(set_b)
    if not intersection:
        return ratio
        
    jaccard = len(intersection) / len(set_a.union(set_b))
    containment = len(intersection) / min(len(set_a), len(set_b))
    
    # Nếu một chuỗi ngắn (dưới 6 ký tự) và hầu như nằm trọn trong chuỗi dài
    if min(len(norm_a), len(norm_b)) <= 6 and containment >= 0.75:
        return max(ratio, containment)
        
    # Trả về giá trị lớn nhất trong các cách đo
    return max(ratio, jaccard, containment * 0.8)

def _config_get(config: dict | None, key: str, default):
    if not isinstance(config, dict):
        return default
    return config.get(key, default)

def _is_probable_ocr_noise(text: str, ocr_config: dict | None = None) -> bool:
    text = str(text or "").strip()
    if not text:
        return True
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return True
    if len(compact) <= 1:
        return True
    has_cjk = any("\u4e00" <= char <= "\u9fff" for char in compact)
    ascii_count = sum(1 for char in compact if char.isascii() and char.isalnum())
    digit_count = sum(1 for char in compact if char.isdigit())
    cjk_count = sum(1 for char in compact if "\u4e00" <= char <= "\u9fff")
    if not has_cjk and ascii_count >= max(2, len(compact) * 0.7):
        return True
    if digit_count >= max(2, len(compact) * 0.6):
        return True
    if cjk_count == 1 and len(compact) <= 3:
        allow_short = set(_config_get(ocr_config, "allow_short_cjk_texts", ["不", "是", "啊", "哦", "嗯", "对"]))
        if compact not in allow_short:
            return True
    blocklist = set(_config_get(ocr_config, "noise_text_blocklist", ["楚", "史", "中", "口", "吊"]))
    if compact in blocklist:
        return True
    return False

def _merge_speech_regions(regions: list[dict], max_gap_ms: int = 120) -> list[dict]:
    if not regions:
        return []
    max_gap = max_gap_ms / 1000.0
    merged = [dict(regions[0])]
    for region in regions[1:]:
        previous = merged[-1]
        if float(region["start"]) - float(previous["end"]) <= max_gap:
            previous["end"] = max(float(previous["end"]), float(region["end"]))
        else:
            merged.append(dict(region))
    return merged

def _pad_speech_regions(regions: list[dict], *, video_duration: float, before_ms: int = 250, after_ms: int = 350) -> list[dict]:
    padded = []
    before = before_ms / 1000.0
    after = after_ms / 1000.0
    for region in regions:
        start = max(0.0, float(region["start"]) - before)
        end = min(video_duration, float(region["end"]) + after)
        if end > start:
            padded.append({"start": start, "end": end})
    return padded

def detect_speech_regions_whisper(
    video_path: str | os.PathLike,
    *,
    video_duration: float,
    speech_config: dict | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> list[dict]:
    from local_whisper_captions import transcribe_video_to_segments

    vad_parameters = _config_get(speech_config, "vad_parameters", None)
    if not isinstance(vad_parameters, dict):
        vad_parameters = {
            "threshold": float(_config_get(speech_config, "threshold", 0.35)),
            "min_silence_duration_ms": int(_config_get(speech_config, "min_silence_duration_ms", 180)),
            "speech_pad_ms": int(_config_get(speech_config, "speech_pad_ms", 200)),
            "min_speech_duration_ms": int(_config_get(speech_config, "min_speech_duration_ms", 100)),
        }
    transcribe_options = {
        "language": _config_get(speech_config, "language", "zh"),
        "task": _config_get(speech_config, "task", "transcribe"),
        "beam_size": int(_config_get(speech_config, "beam_size", 1)),
        "best_of": int(_config_get(speech_config, "best_of", 1)),
        "temperature": float(_config_get(speech_config, "temperature", 0.0)),
        "word_timestamps": bool(_config_get(speech_config, "word_timestamps", True)),
        "condition_on_previous_text": bool(_config_get(speech_config, "condition_on_previous_text", False)),
        "vad_filter": bool(_config_get(speech_config, "vad_filter", True)),
        "vad_parameters": vad_parameters,
        "logprob_threshold": float(_config_get(speech_config, "logprob_threshold", -2.0)),
        "no_speech_threshold": float(_config_get(speech_config, "no_speech_threshold", 0.75)),
        "strict_filter": bool(_config_get(speech_config, "strict_filter", False)),
    }
    segments, _ = transcribe_video_to_segments(
        video_path,
        language=str(transcribe_options["language"] or "zh"),
        speed=float(_config_get(speech_config, "speed", 1.0) or 1.0),
        model_size=str(_config_get(speech_config, "model", os.environ.get("WHISPER_MODEL", "large-v3-turbo"))),
        device=str(_config_get(speech_config, "device", os.environ.get("WHISPER_DEVICE", "cuda"))),
        compute_type=_config_get(speech_config, "compute_type", os.environ.get("WHISPER_COMPUTE_TYPE")),
        transcribe_options=transcribe_options,
        progress_callback=progress_callback,
    )
    regions = [
        {"start": float(seg["start"]), "end": float(seg["end"])}
        for seg in segments
        if float(seg.get("end", 0) or 0) > float(seg.get("start", 0) or 0)
    ]
    merge_gap_ms = int(_config_get(speech_config, "merge_gap_ms", 0))
    if merge_gap_ms > 0:
        regions = _merge_speech_regions(regions, max_gap_ms=merge_gap_ms)
    return _pad_speech_regions(
        regions,
        video_duration=video_duration,
        before_ms=int(_config_get(speech_config, "ocr_padding_before_ms", 250)),
        after_ms=int(_config_get(speech_config, "ocr_padding_after_ms", 350)),
    )

def _build_ocr_sample_times(
    regions: list[dict] | None,
    *,
    duration: float,
    sample_rate_sec: float,
    ocr_config: dict | None = None,
) -> list[float]:
    def _add_dense_uncovered_samples(
        sample_times: set[float],
        *,
        scan_start: float,
        scan_end: float,
        step: float,
        covered_regions: list[dict],
    ) -> int:
        if scan_end <= scan_start or step <= 0:
            return 0
        added = 0
        current = scan_start
        epsilon = min(0.02, step / 4.0)
        while current < scan_end:
            covered = any(
                float(region.get("start", 0.0)) - epsilon <= current <= float(region.get("end", 0.0)) + epsilon
                for region in covered_regions
            )
            if not covered:
                before = len(sample_times)
                sample_times.add(round(current, 3))
                if len(sample_times) > before:
                    added += 1
            current += step
        return added

    if not regions:
        step = max(0.1, sample_rate_sec)
        sample_times = {round(float(t), 3) for t in np.arange(0.0, max(0.0, duration), step)}
        dense_start = _config_get(ocr_config, "dense_start_gap_scan", {})
        if isinstance(dense_start, dict) and bool(dense_start.get("enabled", True)):
            dense_end = min(duration, float(dense_start.get("duration_sec", 8.0) or 8.0))
            dense_step = max(0.05, int(dense_start.get("step_ms", 100) or 100) / 1000.0)
            _add_dense_uncovered_samples(
                sample_times,
                scan_start=0.0,
                scan_end=dense_end,
                step=dense_step,
                covered_regions=[],
            )
        return sorted(t for t in sample_times if 0.0 <= t < duration)

    fast_max = int(_config_get(ocr_config, "fast_pass_max_duration_ms", 1500)) / 1000.0
    coarse_step = int(_config_get(ocr_config, "coarse_step_ms", 1000)) / 1000.0
    long_step = int(_config_get(ocr_config, "long_region_step_ms", 1000)) / 1000.0
    fast_ratios = _config_get(ocr_config, "fast_sample_ratios", [0.2, 0.5, 0.8])
    sample_times = set()

    for region in regions:
        start = max(0.0, float(region["start"]))
        end = min(duration, float(region["end"]))
        if end <= start:
            continue
        region_duration = end - start
        if region_duration <= fast_max:
            for ratio in fast_ratios:
                sample_times.add(round(start + region_duration * float(ratio), 3))
        else:
            step = long_step if region_duration > 5.0 else coarse_step
            current = start
            while current <= end:
                sample_times.add(round(current, 3))
                current += step
            sample_times.add(round(end, 3))

    ocr_only = _config_get(ocr_config, "ocr_only_scan", {})
    if isinstance(ocr_only, dict) and bool(ocr_only.get("enabled", False)):
        step = max(0.25, int(ocr_only.get("step_ms", 1000)) / 1000.0)
        current = 0.0
        while current < duration:
            if not any(float(r["start"]) <= current <= float(r["end"]) for r in regions):
                sample_times.add(round(current, 3))
            current += step

    dense_start = _config_get(ocr_config, "dense_start_gap_scan", {})
    if isinstance(dense_start, dict) and bool(dense_start.get("enabled", True)):
        dense_end = min(duration, float(dense_start.get("duration_sec", 8.0) or 8.0))
        dense_step = max(0.05, int(dense_start.get("step_ms", 100) or 100) / 1000.0)
        added = _add_dense_uncovered_samples(
            sample_times,
            scan_start=0.0,
            scan_end=dense_end,
            step=dense_step,
            covered_regions=regions,
        )
        if added and bool(dense_start.get("include_boundaries", True)):
            sample_times.add(0.0)
            sample_times.add(round(max(0.0, dense_end - dense_step), 3))

    return sorted(t for t in sample_times if 0.0 <= t < duration)

def extract_hardsub_from_video(
    video_path: str | os.PathLike,
    sample_rate_sec: float = 1.0,
    min_score: float = 0.4,
    progress_callback: Callable[[str], None] | None = None,
    speech_config: dict | None = None,
    ocr_config: dict | None = None,
    timestamp_source: str = "whisper",
    speed: float = 1.0,
) -> list[dict]:
    """
    Quét video bằng OpenCV và RapidOCR để trích xuất phụ đề cứng (hardsub).
    Trả về danh sách: [{"start": float, "end": float, "text": str}]
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Không tìm thấy video: {video_path}")

    cap = cv2.VideoCapture(
        str(video_path), 
        cv2.CAP_FFMPEG, 
        [
            cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_ANY
        ]
    )
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    if fps <= 0 or total_frames <= 0:
        raise ValueError(f"Không thể đọc thông tin video: {video_path}")

    # Chỉ quét vùng bottom 25% của video (vùng chứa phụ đề) và 90% chiều rộng ở giữa (bỏ 5% biên trái và 5% biên phải)
    source_duration = total_frames / fps
    try:
        timeline_speed = float(speed or 1.0)
    except Exception:
        timeline_speed = 1.0
    if timeline_speed <= 0:
        timeline_speed = 1.0
    duration = source_duration / timeline_speed
    min_score = float(_config_get(ocr_config, "min_score", min_score))

    speech_regions = None
    normalized_timestamp_source = str(timestamp_source or "whisper").lower().replace("_", "-")
    if normalized_timestamp_source in {"whisper", "faster-whisper", "fasterwhisper"}:
        try:
            speech_regions = detect_speech_regions_whisper(
                video_path,
                video_duration=duration,
                speech_config=speech_config,
                progress_callback=progress_callback,
            )
            min_coverage = float(_config_get(speech_config, "speech_coverage_below_ratio", 0.05))
            coverage = sum(max(0.0, r["end"] - r["start"]) for r in speech_regions)
            if not speech_regions or (duration > 0 and coverage / duration < min_coverage):
                raise RuntimeError(f"Whisper coverage qua thap: {coverage:.1f}s/{duration:.1f}s")
            if progress_callback:
                progress_callback(f"Whisper timestamp: {len(speech_regions)} vung, coverage={coverage:.1f}s/{duration:.1f}s")
        except Exception as err:
            fallback_engine = str(_config_get(speech_config, "fallback_engine", "scan")).lower()
            if progress_callback:
                progress_callback(f"Whisper timestamp loi/khong du vung: {err}. Fallback={fallback_engine}")
            speech_regions = None
    sample_times = _build_ocr_sample_times(
        speech_regions,
        duration=duration,
        sample_rate_sec=sample_rate_sec,
        ocr_config=ocr_config,
    )

    crop_rect = _config_get(ocr_config, "crop_rect", None)
    if isinstance(crop_rect, dict) and all(key in crop_rect for key in ("x", "y", "w", "h")):
        pad_x = int(_config_get(ocr_config, "crop_pad_x", 8))
        pad_y = int(_config_get(ocr_config, "crop_pad_y", 8))
        crop_x_start = max(0, int(crop_rect.get("x", 0)) - pad_x)
        crop_y_start = max(0, int(crop_rect.get("y", 0)) - pad_y)
        crop_x_end = min(width, int(crop_rect.get("x", 0)) + int(crop_rect.get("w", width)) + pad_x)
        crop_y_end = min(height, int(crop_rect.get("y", 0)) + int(crop_rect.get("h", height)) + pad_y)
    else:
        crop_y_start = int(height * 0.75)
        crop_y_end = height
        crop_x_start = int(width * 0.05)
        crop_x_end = int(width * 0.95)
    if crop_x_end <= crop_x_start or crop_y_end <= crop_y_start:
        crop_y_start = int(height * 0.75)
        crop_y_end = height
        crop_x_start = int(width * 0.05)
        crop_x_end = int(width * 0.95)
    if progress_callback:
        progress_callback(
            f"OCR crop region: x={crop_x_start}, y={crop_y_start}, "
            f"w={crop_x_end - crop_x_start}, h={crop_y_end - crop_y_start}"
        )
    
    try:
        # Thêm đường dẫn DLL của CUDA và cuDNN vào PATH trước khi import PaddleOCR
        added_dirs = _prepend_nvidia_dll_dirs_to_path()
        if added_dirs and progress_callback:
            progress_callback(f"Đã thêm NVIDIA DLL dirs vào PATH cho CUDA OCR: {'; '.join(added_dirs)}")

        import logging
        # Tắt các log INFO thừa thãi từ module ppocr của PaddleOCR
        logging.getLogger("ppocr").setLevel(logging.WARNING)

        from paddleocr import PaddleOCR
        
        # Khởi động PaddleOCR chạy trên GPU bằng CUDA (sử dụng API phiên bản 2.8.x ổn định)
        ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)
        
        raw_detections = []
        ocr_cache = {}
        
        # Tính bước nhảy frame (step) dựa trên sample_rate_sec
        frame_step = max(1, int(fps * sample_rate_sec))
        
        if progress_callback:
            progress_callback(f"Bắt đầu PaddleOCR quét phụ đề cứng. FPS: {fps:.2f}, Step: {frame_step} frames ({sample_rate_sec}s/lần)")

        if progress_callback:
            progress_callback(f"OCR timestamp source={timestamp_source}, samples={len(sample_times)}")

        batch_images = []
        batch_metadata = []
        batch_size = 8  # Kích thước lô tối ưu cho VRAM GPU 3060 Ti

        def _parse_ocr_result(result):
            frame_text = ""
            if result and result[0]:
                valid_lines = []
                for item in result[0]:
                    box, (text, score) = item[0], item[1]
                    text = str(text).strip()
                    score = float(score)
                    if score >= min_score and text:
                        if bool(_config_get(ocr_config, "drop_noise_text", True)) and _is_probable_ocr_noise(text, ocr_config):
                            continue
                        ys = [point[1] for point in box]
                        xs = [point[0] for point in box]
                        mean_y = sum(ys) / len(ys)
                        mean_x = sum(xs) / len(xs)
                        valid_lines.append((mean_y, mean_x, text))
                # Sắp xếp theo dòng trước (làm tròn đến 20px để nhóm các chữ cùng hàng), sau đó theo cột từ trái sang phải
                valid_lines.sort(key=lambda x: (round(x[0] / 20) * 20, x[1]))
                if valid_lines:
                    frame_text = " ".join(line[2] for line in valid_lines)
            return frame_text

        def process_ocr_batch():
            if not batch_images:
                return
            for img, meta in zip(batch_images, batch_metadata):
                try:
                    result = ocr.ocr(img, cls=False)
                except Exception as ocr_err:
                    if progress_callback:
                        progress_callback(f"Lỗi OCR frame {meta['timestamp']:.1f}s: {ocr_err}")
                    continue

                frame_text = _parse_ocr_result(result)
                ocr_cache[round(float(meta["timestamp"]), 3)] = frame_text
                if frame_text:
                    raw_detections.append({
                        "timestamp": meta["timestamp"],
                        "text": frame_text
                    })
            batch_images.clear()
            batch_metadata.clear()

        def ocr_at(timestamp: float) -> str:
            timestamp = max(0.0, min(duration, float(timestamp)))
            source_timestamp = max(0.0, min(source_duration, timestamp * timeline_speed))
            cache_key = round(timestamp, 3)
            if cache_key in ocr_cache:
                return ocr_cache[cache_key]
            frame_idx = min(total_frames - 1, max(0, int(round(source_timestamp * fps))))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                ocr_cache[cache_key] = ""
                return ""
            cropped = frame[crop_y_start:crop_y_end, crop_x_start:crop_x_end]
            try:
                result = ocr.ocr(cropped, cls=False)
                frame_text = _parse_ocr_result(result)
            except Exception as ocr_err:
                if progress_callback:
                    progress_callback(f"Lỗi OCR refine frame {timestamp:.3f}s: {ocr_err}")
                frame_text = ""
            ocr_cache[cache_key] = frame_text
            return frame_text

        def refine_boundary(left_det: dict, right_det: dict) -> float:
            left_time = float(left_det["timestamp"])
            right_time = float(right_det["timestamp"])
            left_text = str(left_det["text"])
            right_text = str(right_det["text"])
            if right_time <= left_time:
                return right_time
            min_step = float(_config_get(ocr_config, "refine_min_step_ms", 125)) / 1000.0
            same_threshold = float(_config_get(ocr_config, "same_text_threshold", 0.65))
            iterations = 0
            while right_time - left_time > min_step and iterations < 8:
                mid = (left_time + right_time) / 2.0
                mid_text = ocr_at(mid)
                if not mid_text:
                    right_time = mid
                elif _string_similarity(left_text, mid_text) >= same_threshold:
                    left_time = mid
                elif _string_similarity(right_text, mid_text) >= same_threshold:
                    right_time = mid
                else:
                    right_time = mid
                iterations += 1
            return right_time

        last_report = 0
        for sample_index, timestamp in enumerate(sample_times, start=1):
            source_timestamp = max(0.0, min(source_duration, float(timestamp) * timeline_speed))
            frame_idx = min(total_frames - 1, max(0, int(round(source_timestamp * fps))))
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            cropped = frame[crop_y_start:crop_y_end, crop_x_start:crop_x_end]

            batch_images.append(cropped)
            batch_metadata.append({"timestamp": timestamp})

            if len(batch_images) >= batch_size:
                process_ocr_batch()

            if progress_callback and (sample_index - last_report >= 30 or sample_index >= len(sample_times)):
                last_report = sample_index
                percent = (sample_index / max(1, len(sample_times))) * 100
                progress_callback(
                    f"Dang phan tich video OCR... {percent:.1f}% "
                    f"(timeline={timestamp:.1f}s, frame={source_timestamp:.1f}s), "
                    f"tim thay={len(raw_detections)} frames co sub"
                )
        
        process_ocr_batch()
                
        # Xử lý lô ảnh còn dư cuối cùng
    finally:
        cap.release()

    # Nhóm các detections đơn lẻ thành các câu thoại hoàn chỉnh (segments)
    segments = []
    current_segment = None
    current_last_det = None
    max_same_text_gap = float(_config_get(ocr_config, "max_same_text_gap_ms", 1800)) / 1000.0
    max_segment_duration = float(_config_get(ocr_config, "max_segment_duration_ms", 6000)) / 1000.0
    min_segment_duration = float(_config_get(ocr_config, "min_segment_duration_ms", 180)) / 1000.0
    
    for det in raw_detections:
        t = det["timestamp"]
        txt = det["text"]
        if bool(_config_get(ocr_config, "drop_noise_text", True)) and _is_probable_ocr_noise(txt, ocr_config):
            continue
        
        if current_segment is None:
            # Khởi tạo segment mới
            current_segment = {
                "start": t,
                "end": t + sample_rate_sec,
                "text": txt
            }
            current_last_det = det
        else:
            # So sánh độ tương đồng với câu thoại hiện tại
            sim = _string_similarity(current_segment["text"], txt)
            last_t = float((current_last_det or {}).get("timestamp", current_segment["end"]))
            gap_from_last_detection = float(t) - last_t
            current_duration = float(t) - float(current_segment["start"])
            gap_too_large = gap_from_last_detection > max_same_text_gap
            segment_too_long = current_duration > max_segment_duration

            if gap_too_large or segment_too_long:
                current_segment["end"] = min(
                    current_segment["start"] + max_segment_duration,
                    max(current_segment["start"] + min_segment_duration, last_t + sample_rate_sec),
                )
                segments.append(current_segment)
                current_segment = {
                    "start": t,
                    "end": min(t + sample_rate_sec, t + max_segment_duration),
                    "text": txt
                }
                current_last_det = det
                continue

            # Nếu tương đồng cao (>70%) hoặc là một phần tiếp nối
            if sim >= 0.65:
                # Kéo dài thời gian kết thúc câu thoại
                current_segment["end"] = min(t + sample_rate_sec, current_segment["start"] + max_segment_duration)
                # Cập nhật text mới nhất (hoặc giữ text dài hơn/chính xác hơn)
                if len(txt) > len(current_segment["text"]):
                    current_segment["text"] = txt
                current_last_det = det
            else:
                boundary = refine_boundary(current_last_det or {"timestamp": current_segment["end"], "text": current_segment["text"]}, det)
                current_segment["end"] = max(current_segment["start"] + 0.12, boundary)
                # Lưu segment cũ và tạo cái mới
                segments.append(current_segment)
                current_segment = {
                    "start": max(boundary, current_segment["end"]),
                    "end": min(t + sample_rate_sec, t + max_segment_duration),
                    "text": txt
                }
                current_last_det = det
                
    if current_segment:
        current_segment["end"] = min(
            current_segment["end"],
            current_segment["start"] + max_segment_duration,
        )
        segments.append(current_segment)
        
    # Hậu xử lý các segments:
    # 1. Gộp các segment cực kỳ gần nhau (khoảng trống < 0.8s) nếu chữ giống nhau
    # 2. Đặt ID cho từng câu thoại
    final_segments = []
    for index, seg in enumerate(segments):
        if not final_segments:
            final_segments.append(seg)
        else:
            prev = final_segments[-1]
            gap = seg["start"] - prev["end"]
            sim = _string_similarity(prev["text"], seg["text"])
            
            if gap < 0.8 and sim >= 0.7:
                # Gộp làm một
                prev["end"] = seg["end"]
                if len(seg["text"]) > len(prev["text"]):
                    prev["text"] = seg["text"]
            else:
                final_segments.append(seg)
                
    for i, seg in enumerate(final_segments, start=1):
        seg["id"] = i
        
    if progress_callback:
        progress_callback(f"Hoàn thành trích xuất phụ đề cứng. Tìm thấy {len(final_segments)} câu thoại.")
        
    return final_segments

def segments_to_srt(segments: Iterable[dict]) -> str:
    """Chuyển đổi danh sách segment thành định dạng SRT."""
    from local_whisper_captions import _format_ts
    blocks = []
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = _format_ts(segment.get("start", 0))
        end = _format_ts(segment.get("end", segment.get("start", 0)))
        blocks.append(f"{index}\n{start} --> {end}\n{text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")

def sanitize_segments_for_srt(
    segments: Iterable[dict],
    *,
    min_duration: float = 0.12,
    min_gap: float = 0.02,
    max_duration: float | None = None,
    read_ms_per_char: int = 0,
) -> list[dict]:
    cleaned = []
    last_end = 0.0
    for index, segment in enumerate(
        sorted(segments, key=lambda item: (float(item.get("start", 0) or 0), float(item.get("end", 0) or 0))),
        start=1,
    ):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = max(0.0, float(segment.get("start", 0) or 0))
        end = max(start, float(segment.get("end", start) or start))
        dynamic_min_duration = float(min_duration)
        if read_ms_per_char > 0:
            compact_len = len(re.sub(r"\s+", "", text))
            dynamic_min_duration = max(dynamic_min_duration, compact_len * float(read_ms_per_char) / 1000.0)
        if end <= start + dynamic_min_duration:
            end = start + dynamic_min_duration
        if max_duration and end > start + max_duration:
            end = start + max_duration
        if start < last_end + min_gap:
            start = last_end + min_gap
        if end <= start + dynamic_min_duration:
            end = start + dynamic_min_duration
        if max_duration and end > start + max_duration:
            end = start + max_duration
        cleaned.append({
            **segment,
            "id": len(cleaned) + 1,
            "start": start,
            "end": end,
            "text": text,
        })
        last_end = end
    return cleaned

def patch_draft_with_local_ocr(
    *,
    draft_path: str | os.PathLike,
    draft_id: str,
    video_path: str | os.PathLike,
    repo_root: str | os.PathLike,
    language: str = "zh",
    speed: float = 1.0,
    font: str | None = None,
    font_size: float = 5.0,
    font_color: str = "#FFFFFF",
    width: int = 1920,
    height: int = 1080,
    subtitle_offset_ms: int = 0,
    progress_callback: Callable[[str], None] | None = None,
    translate_func: Callable[[list[str]], list[str]] | None = None,
    speech_config: dict | None = None,
    ocr_config: dict | None = None,
    timestamp_source: str = "whisper",
) -> dict:
    """
    Quet video bang OCR, dich tu dong qua translate_func va patch phu de tieng Viet vao nhap CapCut.
    """
    draft_path = Path(draft_path)
    repo_root = Path(repo_root)
    content_path = _find_primary_draft_json(draft_path)
    timestamp_source = str(timestamp_source or "whisper")

    # 1. OCR Trich xuat text tieng Trung tu video (luon quet o toc do goc 1.0)
    segments = extract_hardsub_from_video(
        video_path,
        sample_rate_sec=1.0,
        progress_callback=progress_callback,
        speech_config=speech_config,
        ocr_config=ocr_config,
        timestamp_source=timestamp_source,
        speed=speed,
    )
    min_segments = int(_config_get(ocr_config, "fallback_full_scan_below_segments", 8))
    if str(timestamp_source or "").lower().replace("_", "-") in {"whisper", "faster-whisper", "fasterwhisper"} and len(segments) < min_segments:
        if progress_callback:
            progress_callback(f"OCR Whisper timestamp chi ra {len(segments)} segments (<{min_segments}), quet lai toan video de tranh mat sub.")
        segments = extract_hardsub_from_video(
            video_path,
            sample_rate_sec=1.0,
            progress_callback=progress_callback,
            speech_config=speech_config,
            ocr_config=ocr_config,
            timestamp_source="scan",
            speed=speed,
        )
    
    if not segments:
        raise RuntimeError("Khong phat hien duoc bat ky phu de cung nao tren video.")

    # 2. Dich thuat tieng Trung -> tieng Viet bang API dich
    if translate_func:
        if progress_callback:
            progress_callback("Dang tien hanh dich AI phu de da quet sang tieng Viet...")
        zh_texts = [seg["text"] for seg in segments]
        try:
            vi_texts = translate_func(zh_texts)
            for seg, vi in zip(segments, vi_texts):
                seg["text_vi"] = vi
        except Exception as e:
            if progress_callback:
                progress_callback(f"Loi dich AI phu de quet OCR: {e}. Dung tieng Trung goc.")
            for seg in segments:
                seg["text_vi"] = seg["text"]
    else:
        for seg in segments:
            seg["text_vi"] = seg["text"]

    # 3. Tao file SRT theo timestamp goc. Video speed chi duoc patch o Step 7.
    ocr_segments = []
    for seg in segments:
        ocr_segments.append({
            "id": seg["id"],
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text_vi"],
        })
    max_srt_duration = float(_config_get(ocr_config, "max_segment_duration_ms", 6000)) / 1000.0
    min_display_duration = float(_config_get(ocr_config, "min_display_duration_ms", 850)) / 1000.0
    read_ms_per_char = int(_config_get(ocr_config, "read_ms_per_char", 55))
    ocr_segments = sanitize_segments_for_srt(
        ocr_segments,
        min_duration=min_display_duration,
        max_duration=max_srt_duration,
        read_ms_per_char=read_ms_per_char,
    )

    srt_text_merged = segments_to_srt(ocr_segments)
    srt_path = draft_path / "ocr_zh.srt"
    srt_path.write_text(srt_text_merged, encoding="utf-8")

    # 4. Import SRT truc tiep vao JSON cua CapCut Draft
    added = _import_srt_to_content(
        content_path,
        srt_text_merged,
        font=font,
        font_size=font_size,
        font_color=font_color,
        width=width,
        height=height,
        subtitle_offset_ms=subtitle_offset_ms,
    )

    # Sync kết quả sang thư mục repo nếu có
    repo_draft_path = repo_root / draft_id
    repo_content_path = repo_draft_path / content_path.name
    if repo_content_path.exists():
        repo_content_path.write_text(content_path.read_text(encoding="utf-8"), encoding="utf-8")
        (repo_draft_path / "ocr_zh.srt").write_text(srt_text_merged, encoding="utf-8")

    return {
        "segments": len(ocr_segments),
        "added_texts": added,
        "srt_path": str(srt_path),
        "content_path": str(content_path),
    }


