# Test thuc te thuat toan No-Seek GPU Engine tren video cua User
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

if not target_file:
    print("Khong tim thay file video chinesedrama!")
    sys.exit(1)

print("=" * 70)
print("TEST NO-SEEK GPU OCR TREN VIDEO THUC TE CUA USER")
print("Video Path: [Target Video Chinesedrama MP4]")
print("=" * 70)

# Kiem tra tong thoi gian & FPS video
cap = cv2.VideoCapture(target_file)
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
duration_sec = total_frames / fps
cap.release()

print(f"Thong so video: {duration_sec:.1f} giay ({duration_sec/60:.1f} phut), Total frames: {total_frames}, FPS: {fps:.2f}")

# Lay sample 0.2s/lan (5 samples/giay)
sample_times = [round(i * 0.2, 2) for i in range(int(duration_sec / 0.2))]
print(f"Tong so sample moc thoi gian can quet: {len(sample_times)} mocs")

ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)

t0 = time.time()

container = av.open(target_file)
stream = container.streams.video[0]
stream.thread_type = "AUTO"
time_base = float(stream.time_base)
h = stream.height
crop_y_start = int(h * 0.70)

target_timestamps = sorted(sample_times)
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
print("KET QUA QUET DONG PHU DE THUAN THUC TIEP:")
print(f"  * Tong thoi gian quet: {elapsed:.2f} GIAY ({elapsed/60:.2f} phut)")
print(f"  * Tong so samples quet: {processed_count} mocs")
print(f"  * Tong so cau phu de tim thay: {len(found_subs)} lines")
print(f"  * Toc do trung binh: {elapsed / max(1, processed_count) * 1000:.1f} ms / frame")
print("=" * 70)

print("\n--- IN THU 10 CAU PHU DE CHINESE TIM THAY DAU TIEN ---")
for ts, txt in found_subs[:10]:
    print(f"  [{ts:6.2f}s] {txt}")
print("=" * 70)
