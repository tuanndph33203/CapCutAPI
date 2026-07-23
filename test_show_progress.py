# Test No-Seek OCR va Print% Tien do lien tuc va Print cau thoai
import time
import cv2
import av
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
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

# Test 300 moc sample
whisper_sample_times = [round(i * 1.5, 2) for i in range(300)]

print("=" * 70)
print("TEST SHOW REALTIME % PROGRESS & PRINT RESULTS")
print("=" * 70)

ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)

t0 = time.time()

container = av.open(target_file)
stream = container.streams.video[0]
stream.thread_type = "AUTO"
time_base = float(stream.time_base)
h = stream.height
crop_y_start = int(h * 0.55)
crop_y_end = int(h * 0.90)

target_timestamps = sorted(whisper_sample_times)
target_idx = 0
found_subs = []
processed_count = 0
total_targets = len(target_timestamps)

for frame in container.decode(stream):
    if target_idx >= total_targets:
        break
    
    pts_sec = float(frame.pts * time_base) if frame.pts is not None else float(frame.time)
    target_ts = target_timestamps[target_idx]

    if pts_sec >= target_ts:
        img = frame.to_ndarray(format="bgr24")
        sub_crop = img[crop_y_start:, :]
        
        # GPU OCR
        res = ocr.ocr(sub_crop, cls=False)
        if res and res[0]:
            for line in res[0]:
                text = str(line[1][0]).strip()
                score = float(line[1][1])
                if score >= 0.5 and text:
                    found_subs.append((target_ts, text))
                    print(f" -> [{target_ts:6.2f}s] Tim thay phu de: {text}")
        
        processed_count += 1
        target_idx += 1

        percent = (processed_count / total_targets) * 100.0
        print(f"[PROGRESS] Completed: {percent:.1f}% ({processed_count}/{total_targets} frames)...", flush=True)

container.close()
t1 = time.time()

print("=" * 70)
print(f"TONG KET: Quet xong {processed_count} frames trong {t1-t0:.2f}s ({len(found_subs)} cau phu de tim thay)")
print("=" * 70)
