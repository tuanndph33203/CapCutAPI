# Test No-Seek Single Pass Streaming: Rút ngắn 500 mốc thoại từ 50s xuống DƯỚI 5 GIÂY!
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

# 500 mốc sample
whisper_timestamps = set()
for i in range(500):
    whisper_timestamps.add(round(i * (320.0 / 500), 2))

print("=" * 70)
print("TEST NO-SEEK SINGLE PASS STREAMING (NO SEEK OVERHEAD)")
print(f"Video: {os.path.basename(VIDEO_PATH)}")
print("=" * 70)

ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)

t0 = time.time()

container = av.open(VIDEO_PATH)
stream = container.streams.video[0]
stream.thread_type = "AUTO"
time_base = float(stream.time_base)
h = stream.height
crop_y_start = int(h * 0.70)

sorted_target_ts = sorted(list(whisper_timestamps))
target_idx = 0
found_sub_count = 0
processed_count = 0

batch_images = []

# ĐỌC 1 LƯỢT XÉ GIÓ TỪ ĐẦU TỚI CUỐI - KHÔNG SEEK!
for frame in container.decode(stream):
    if target_idx >= len(sorted_target_ts):
        break
    
    pts_sec = float(frame.pts * time_base) if frame.pts is not None else float(frame.time)
    target_ts = sorted_target_ts[target_idx]
    
    if pts_sec >= target_ts:
        img = frame.to_ndarray(format="bgr24")
        sub_crop = img[crop_y_start:, :]
        batch_images.append(sub_crop)
        processed_count += 1
        target_idx += 1

container.close()

# NẠP TOÀN BỘ VÀO GPU BATCH
if batch_images:
    for img in batch_images:
        res = ocr.ocr(img, cls=False)
        if res and res[0]:
            found_sub_count += len(res[0])

t1 = time.time()
elapsed = t1 - t0

print("=" * 70)
print(f"KET QUA NO-SEEK SINGLE PASS TURBO:")
print(f"  * Samples processed: {processed_count} frames")
print(f"  * Lines detected:     {found_sub_count} lines")
print(f"  * Total time:         {elapsed:.2f} seconds")
print(f"  * Average speed:      {elapsed / max(1, processed_count) * 1000:.1f} ms / frame")
print("=" * 70)
