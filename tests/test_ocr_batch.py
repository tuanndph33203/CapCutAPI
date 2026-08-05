"""
Test OCR batch GPU processing speed.
So sánh tốc độ trước (loop từng ảnh) và sau (batch cả list) khi fix.
"""
import time
import cv2
import sys
import os

VIDEO_PATH = r"C:\Users\nguye\Projects\CapCutAPI\111111111111111111\assets\video\video_4e8fe43bafb2a271.mp4"
SAMPLE_RATE_SEC = 1.0  # lấy mẫu mỗi 1 giây
BATCH_SIZE = 16

# ── Setup NVIDIA DLL path (dung ham chuan tu local_whisper_captions) ──────
from local_whisper_captions import _prepend_nvidia_dll_dirs_to_path
_prepend_nvidia_dll_dirs_to_path()

import logging
logging.getLogger("ppocr").setLevel(logging.WARNING)
from paddleocr import PaddleOCR

print("Khoi tao PaddleOCR GPU...")
ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)

# ── Load video & extract frames ────────────────────────────────────────────
cap = cv2.VideoCapture(VIDEO_PATH)
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
duration = total_frames / fps
print(f"Video: {os.path.basename(VIDEO_PATH)}, FPS={fps:.1f}, Duration={duration:.1f}s, Frames={total_frames}")

frame_step = max(1, int(fps * SAMPLE_RATE_SEC))
sample_indices = list(range(0, total_frames, frame_step))
print(f"Se lay {len(sample_indices)} frames (moi {SAMPLE_RATE_SEC}s)")

# Crop bottom 30% (vung phu de)
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
crop_y_start = int(h * 0.70)

frames_data = []
print("Dang doc frames tu video...")
for idx in sample_indices:
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ret, frame = cap.read()
    if ret:
        frames_data.append(frame[crop_y_start:, :])
cap.release()
print(f"Da doc {len(frames_data)} frames. Bat dau benchmark...\n")

# ── BENCHMARK 1: Tung anh mot (cach CU) ──────────────────────────────────
print("=" * 50)
print(f"[CU] Loop tung anh mot (sequential)...")
t0 = time.time()
results_old = []
for img in frames_data:
    r = ocr.ocr(img, cls=False)
    results_old.append(r)
t1 = time.time()
elapsed_old = t1 - t0
print(f"[CU] Xong {len(frames_data)} frames trong {elapsed_old:.2f}s  ({elapsed_old/len(frames_data)*1000:.1f}ms/frame)\n")

# ── BENCHMARK 2: Batch ca list (cach MOI) ────────────────────────────────
print("=" * 50)
print(f"[MOI] Batch {BATCH_SIZE} frames/lan (true GPU batch)...")
t0 = time.time()
results_new = []
for i in range(0, len(frames_data), BATCH_SIZE):
    batch = frames_data[i:i + BATCH_SIZE]
    r = ocr.ocr(batch, cls=False)
    results_new.extend(r if r else [None] * len(batch))
t1 = time.time()
elapsed_new = t1 - t0
print(f"[MOI] Xong {len(frames_data)} frames trong {elapsed_new:.2f}s  ({elapsed_new/len(frames_data)*1000:.1f}ms/frame)\n")

# ── Ket qua ───────────────────────────────────────────────────────────────
print("=" * 50)
speedup = elapsed_old / elapsed_new if elapsed_new > 0 else 0
print(f"Toc do tang: {speedup:.2f}x  ({elapsed_old:.1f}s -> {elapsed_new:.1f}s)")
print(f"Tiet kiem: {elapsed_old - elapsed_new:.1f}s tren {len(frames_data)} frames")

# Uoc tinh cho video 57 phut (3453s, ~1fps sample)
n_frames_57min = int(3453 / SAMPLE_RATE_SEC)
est_old = elapsed_old / len(frames_data) * n_frames_57min
est_new = elapsed_new / len(frames_data) * n_frames_57min
print(f"\nUoc tinh video 57.5 phut ({n_frames_57min} frames):")
print(f"  Cach CU: ~{est_old/60:.1f} phut")
print(f"  Cach MOI: ~{est_new/60:.1f} phut")
