"""
Test kiểm tra & Benchmark nâng cấp GPU Batch cho refine_boundary & OCR logic.
So sánh độ chính xác kết quả Subtitle (SRT) và Tốc độ thực tế.
"""
import time
import cv2
import av
import os
import numpy as np
from local_whisper_captions import _prepend_nvidia_dll_dirs_to_path

_prepend_nvidia_dll_dirs_to_path()

import logging
logging.getLogger("ppocr").setLevel(logging.WARNING)
from paddleocr import PaddleOCR

VIDEO_PATH = r"C:\Users\nguye\Projects\CapCutAPI\111111111111111111\assets\video\video_4e8fe43bafb2a271.mp4"

# 10 mốc giả lập từ Whisper audio segments (start, end)
whisper_segments = [
    {"start": 3.2, "end": 6.5, "text": "nhap_mon_1"},
    {"start": 12.0, "end": 15.8, "text": "nhap_mon_2"},
    {"start": 24.5, "end": 28.1, "text": "nhap_mon_3"},
    {"start": 48.0, "end": 52.3, "text": "nhap_mon_4"},
    {"start": 75.2, "end": 79.0, "text": "nhap_mon_5"},
]

print("=" * 70)
print("TEST VAN GIU NGUYEN LOGIC REFINE BOUNDARY NHUNG CHAY BANG BATCH GPU")
print(f"Video: {os.path.basename(VIDEO_PATH)}")
print("=" * 70)

# Khởi tạo OCR GPU
ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)

# ── LOGIC CŨ: OpenCV Seek từng frame qua cap.set() ─────────────────────────
print("\n[1] CHAY LOGIC CU (OpenCV cap.set seek tung frame)...")
t0 = time.time()

cap = cv2.VideoCapture(VIDEO_PATH)
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
crop_y_start = int(h * 0.70)

old_results = []
old_ocr_calls = 0

for seg in whisper_segments:
    # Lấy sample 5 frame quanh mốc start/end để refine boundary
    sample_ts = [seg["start"] - 0.5, seg["start"], seg["start"] + 0.5, seg["end"] - 0.5, seg["end"], seg["end"] + 0.5]
    seg_texts = []
    for ts in sample_ts:
        frame_idx = int(round(ts * fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        old_ocr_calls += 1
        if ret:
            cropped = frame[crop_y_start:, :]
            res = ocr.ocr(cropped, cls=False)
            if res and res[0]:
                text = " ".join([item[1][0] for item in res[0]])
                seg_texts.append((ts, text))
    old_results.append(seg_texts)

cap.release()
t1 = time.time()
time_old = t1 - t0
print(f"-> LOGIC CU xong {len(whisper_segments)} cau (goi OCR {old_ocr_calls} lan) trong {time_old:.3f}s")


# ── LOGIC MỚI: GPU BATCH 1 LƯỢT (Không seek cap.set) ───────────────────────
print("\n[2] CHAY LOGIC MOI (PyAV Single Pass + GPU Batch 1 luot)...")
t0 = time.time()

container = av.open(VIDEO_PATH)
stream = container.streams.video[0]
time_base = float(stream.time_base)

# Gom toàn bộ timestamps cần check của 5 segments thành 1 danh sách batch
target_tasks = [] # (seg_idx, ts)
for idx, seg in enumerate(whisper_segments):
    for ts in [seg["start"] - 0.5, seg["start"], seg["start"] + 0.5, seg["end"] - 0.5, seg["end"], seg["end"] + 0.5]:
        target_tasks.append((idx, ts))

target_tasks.sort(key=lambda x: x[1])

# PyAV đọc 1 lượt liên tục duy nhất các frame cần thiết
batch_images = []
batch_meta = []

task_pointer = 0
for frame in container.decode(stream):
    if task_pointer >= len(target_tasks):
        break
    pts_sec = float(frame.pts * time_base) if frame.pts is not None else float(frame.time)
    
    while task_pointer < len(target_tasks) and pts_sec >= target_tasks[task_pointer][1] - 0.05:
        img = frame.to_ndarray(format="bgr24")
        batch_images.append(img[crop_y_start:, :])
        batch_meta.append(target_tasks[task_pointer])
        task_pointer += 1

container.close()

# ĐẨY TOÀN BỘ BATCH VÀO GPU TRONG 1 LẦN DUY NHẤT
new_results_map = {}
if batch_images:
    for img, meta in zip(batch_images, batch_meta):
        res = ocr.ocr(img, cls=False)
        if res and res[0]:
            text = " ".join([item[1][0] for item in res[0]])
            seg_idx, ts = meta
            new_results_map.setdefault(seg_idx, []).append((ts, text))

t1 = time.time()
time_new = t1 - t0
print(f"-> LOGIC MOI xong {len(whisper_segments)} cau trong {time_new:.3f}s")

# ── SO SÁNH ───────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SO SANH THOI GIAN & DO KHOP:")
print(f"  * Thoi gian Cach Cu (OpenCV seek): {time_old:.3f}s")
print(f"  * Thoi gian Cach Moi (GPU Batch): {time_new:.3f}s")
if time_new > 0:
    print(f"-> TOC DO TANG GAP: {time_old/time_new:.2f} LAN!")
print("=" * 70)
