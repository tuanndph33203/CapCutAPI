import os
# Tắt cơ chế spin-wait của ONNXRuntime trên CPU để tránh FULL CPU (100%) khi chờ GPU DirectML xử lý
os.environ["ONNXRUNTIME_CPU_THREAD_ALLOW_SPINNING"] = "0"
# Hạn chế số luồng của FFMPEG giải mã trong OpenCV để tránh FULL CPU khi giải mã video
os.environ["OPENCV_FFMPEG_THREADS"] = "4"

import json
import time
import tempfile
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
    """Tính tỉ lệ tương đồng giữa hai chuỗi."""
    return SequenceMatcher(None, _normalize_text(a), _normalize_text(b)).ratio()

def extract_hardsub_from_video(
    video_path: str | os.PathLike,
    sample_rate_sec: float = 1.0,
    min_score: float = 0.4,
    progress_callback: Callable[[str], None] | None = None,
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
    crop_y_start = int(height * 0.75)
    crop_x_start = int(width * 0.05)
    crop_x_end = int(width * 0.95)
    
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
        ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True)
        
        raw_detections = []
        
        # Tính bước nhảy frame (step) dựa trên sample_rate_sec
        frame_step = max(1, int(fps * sample_rate_sec))
        
        if progress_callback:
            progress_callback(f"Bắt đầu PaddleOCR quét phụ đề cứng. FPS: {fps:.2f}, Step: {frame_step} frames ({sample_rate_sec}s/lần)")

        batch_images = []
        batch_metadata = []
        batch_size = 8  # Kích thước lô tối ưu cho VRAM GPU 3060 Ti

        def process_ocr_batch():
            if not batch_images:
                return
            try:
                # ocr.ocr nhận danh sách ảnh và thực hiện batch inference trên GPU
                results = ocr.ocr(batch_images, cls=False)
            except Exception as ocr_err:
                if progress_callback:
                    progress_callback(f"Lỗi chạy Batch OCR: {ocr_err}")
                results = [None] * len(batch_images)

            for result, meta in zip(results, batch_metadata):
                frame_text = ""
                # Cấu trúc kết quả của batch: result tương ứng với 1 ảnh trong batch
                if result and result[0]:
                    valid_lines = []
                    for item in result[0]:
                        box, (text, score) = item[0], item[1]
                        text = str(text).strip()
                        score = float(score)
                        if score >= min_score and text:
                            ys = [point[1] for point in box]
                            mean_y = sum(ys) / len(ys)
                            valid_lines.append((mean_y, text))
                    valid_lines.sort(key=lambda x: x[0])
                    if valid_lines:
                        frame_text = " ".join(line[1] for line in valid_lines)
                if frame_text:
                    raw_detections.append({
                        "timestamp": meta["timestamp"],
                        "text": frame_text
                    })
            batch_images.clear()
            batch_metadata.clear()

        frame_idx = 0
        while frame_idx < total_frames:
            # Dùng cap.grab() để bỏ qua nhanh các frame trung gian mà không giải mã hình ảnh
            if frame_idx > 0:
                for _ in range(frame_step - 1):
                    if not cap.grab():
                        break
                    frame_idx += 1
                    
            ret, frame = cap.read()
            if not ret:
                break
                
            timestamp = frame_idx / fps
            frame_idx += 1
            
            # Cắt vùng đáy 25% chiều cao video, rộng 90% ở giữa
            cropped = frame[crop_y_start:height, crop_x_start:crop_x_end]
            
            batch_images.append(cropped)
            batch_metadata.append({"timestamp": timestamp})
            
            if len(batch_images) >= batch_size:
                process_ocr_batch()
                
            # Thỉnh thoảng thông báo tiến trình
            current_step_count = frame_idx // frame_step
            if progress_callback and (current_step_count % 30 == 0 or frame_idx >= total_frames - 1):
                percent = (frame_idx / total_frames) * 100
                progress_callback(f"Đang phân tích video OCR... {percent:.1f}% ({timestamp:.1f}s), tìm thấy={len(raw_detections)} frames có sub")
        
        # Xử lý lô ảnh còn dư cuối cùng
        process_ocr_batch()
    finally:
        cap.release()

    # Nhóm các detections đơn lẻ thành các câu thoại hoàn chỉnh (segments)
    segments = []
    current_segment = None
    
    for det in raw_detections:
        t = det["timestamp"]
        txt = det["text"]
        
        if current_segment is None:
            # Khởi tạo segment mới
            current_segment = {
                "start": t,
                "end": t + sample_rate_sec,
                "text": txt
            }
        else:
            # So sánh độ tương đồng với câu thoại hiện tại
            sim = _string_similarity(current_segment["text"], txt)
            # Nếu tương đồng cao (>70%) hoặc là một phần tiếp nối
            if sim >= 0.65:
                # Kéo dài thời gian kết thúc câu thoại
                current_segment["end"] = t + sample_rate_sec
                # Cập nhật text mới nhất (hoặc giữ text dài hơn/chính xác hơn)
                if len(txt) > len(current_segment["text"]):
                    current_segment["text"] = txt
            else:
                # Lưu segment cũ và tạo cái mới
                segments.append(current_segment)
                current_segment = {
                    "start": t,
                    "end": t + sample_rate_sec,
                    "text": txt
                }
                
    if current_segment:
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
) -> dict:
    """
    Quet video bang OCR, dich tu dong qua translate_func va patch phu de tieng Viet vao nhap CapCut.
    """
    draft_path = Path(draft_path)
    repo_root = Path(repo_root)
    content_path = _find_primary_draft_json(draft_path)

    # 1. OCR Trich xuat text tieng Trung tu video (luon quet o toc do goc 1.0)
    segments = extract_hardsub_from_video(
        video_path,
        sample_rate_sec=1.0,
        progress_callback=progress_callback
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

    # 3. Tao file SRT phu de Viet da dich (chia start/end cho speed de dan dong thoi gian theo CapCut)
    ocr_segments = []
    speed_factor = float(speed or 1.0)
    for seg in segments:
        ocr_segments.append({
            "id": seg["id"],
            "start": seg["start"] / speed_factor,
            "end": seg["end"] / speed_factor,
            "text": seg["text_vi"],
        })

    srt_text_merged = segments_to_srt(ocr_segments)
    srt_path = draft_path / "ocr_zh.srt"

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
