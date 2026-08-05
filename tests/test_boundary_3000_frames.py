# Test thuc te CHECK DAU CUOI 3000 FRAMES (500 cau x 6 frame/cau)
import time
import cv2
import av
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from local_whisper_captions import _prepend_nvidia_dll_dirs_to_path
_prepend_nvidia_dll_dirs_to_path()

import logging
logging.getLogger("ppocr").setLevel(logging.WARNING)
from paddleocr import PaddleOCR

# Tuyen duong file video cua nguoi dung
video_dir = r"C:\Users\nguye\Videos\Phim8"
target_file = None
for fname in os.listdir(video_dir):
    if "chinesedrama" in fname and fname.endswith(".mp4"):
        target_file = os.path.join(video_dir, fname)
        break

# Giai lap 500 cau thoai Whisper va 6 frame check dau/cuoi moi cau -> Tong 3,000 frames
whisper_sample_times = []
for i in range(500):
    st = i * 6.5
    for offset in [-0.3, 0.0, 0.3, 1.5, 1.8, 2.1]:
        whisper_sample_times.append(round(st + offset, 2))

print("=" * 70)
print("TEST THUC TE CHECK DAU CUOI 500 CAU (3,000 FRAMES) TREN VIDEO 57.5 PHUT")
print("=" * 70)

ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)

t0 = time.time()

container = av.open(target_file)
stream = container.streams.video[0]
stream.thread_type = "AUTO"
time_base = float(stream.time_base)
h = stream.height
crop_y_start = int(h * 0.70)

target_timestamps = sorted(whisper_sample_times)
target_idx = 0
found_subs = []
processed_count = 0

batch_images = []
batch_ts = []

def flush_ocr():
    if not batch_images:
        return
    for b_img, ts in zip(batch_images, batch_ts):
        res = ocr.ocr(b_img, cls=False)
        if res and res[0]:
            for line in res[0]:
                text = str(line[1][0]).strip()
                score = float(line[1][1])
                if score >= 0.5 and text:
                    found_subs.append((ts, text))
    batch_images.clear()
    batch_ts.clear()

for frame in container.decode(stream):
    if target_idx >= len(target_timestamps):
        break
    
    pts_sec = float(frame.pts * time_base) if frame.pts is not None else float(frame.time)
    target_ts = target_timestamps[target_idx]

    if pts_sec >= target_ts:
        img = frame.to_ndarray(format="bgr24")
        sub_crop = img[crop_y_start:, :]
        batch_images.append(sub_crop)
        batch_ts.append(target_ts)
        processed_count += 1
        target_idx += 1

        if len(batch_images) >= 16:
            flush_ocr()

flush_ocr()
container.close()

t1 = time.time()
elapsed = t1 - t0

print("=" * 70)
print("KET QUA QUET CHECK DAU CUOI 500 CAU THOAI:")
print(f"  * Tong thoi gian hoan tat: {elapsed:.2f} GIAY ({elapsed/60:.2f} phut)")
print(f"  * Tong so samples da check: {processed_count} frames")
print(f"  * Tong so phu de phat hien: {len(found_subs)} lines")
print(f"  * Toc do trung binh: {elapsed / max(1, processed_count) * 1000:.1f} ms / frame")
print("=" * 70)

print("\n--- 10 CAU PHU DE CHINESE CHECK DAU CUOI TIM THAY ---")
for ts, txt in found_subs[:10]:
    print(f"  [{ts:6.2f}s] {txt}")
print("=" * 70)
