# Single Process Large GPU Batch (Best CUDA Throughput)
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
whisper_segments = []
for i in range(500):
    st = round(i * (320.0 / 500), 2)
    whisper_segments.append({"start": st, "end": round(st + 1.8, 2)})

print("=" * 70)
print("TEST OPTIMAL GPU TENSOR BATCH 32 (NO CONTEXT SWITCHING OVERHEAD)")
print(f"Video: {os.path.basename(VIDEO_PATH)}")
print("=" * 70)

ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)

container = av.open(VIDEO_PATH)
stream = container.streams.video[0]
stream.thread_type = "AUTO"
time_base = float(stream.time_base)
h = stream.height
crop_y_start = int(h * 0.70)

t0 = time.time()
found_sub_count = 0
processed_count = 0

batch_images = []

for seg in whisper_segments:
    source_ts = seg["start"]
    target_pts = int((source_ts - 0.5) / time_base) if time_base > 0 else 0
    try:
        container.seek(target_pts, stream=stream, backward=True)
    except Exception:
        pass

    for frame in container.decode(stream):
        pts_sec = float(frame.pts * time_base) if frame.pts is not None else float(frame.time)
        if pts_sec >= source_ts - 0.05:
            img = frame.to_ndarray(format="bgr24")
            sub_crop = img[crop_y_start:, :]
            batch_images.append(sub_crop)
            processed_count += 1
            break

    # ĐẨY BATCH 32 FRAME TRỰC TIẾP VÀO GPU 1 LƯỢT PADDLEOCR
    if len(batch_images) >= 32:
        for b_img in batch_images:
            res = ocr.ocr(b_img, cls=False)
            if res and res[0]:
                found_sub_count += len(res[0])
        batch_images.clear()

if batch_images:
    for b_img in batch_images:
        res = ocr.ocr(b_img, cls=False)
        if res and res[0]:
            found_sub_count += len(res[0])
    batch_images.clear()

container.close()
t1 = time.time()
elapsed = t1 - t0

print("=" * 70)
print(f"VERIFY KET QUA OPTIMAL SINGLE PROCESS BATCH:")
print(f"  * Samples processed: {processed_count} frames")
print(f"  * Lines detected:     {found_sub_count} lines")
print(f"  * Total time:         {elapsed:.2f} seconds")
print(f"  * Average speed:      {elapsed / max(1, processed_count) * 1000:.1f} ms / frame")
print("=" * 70)
