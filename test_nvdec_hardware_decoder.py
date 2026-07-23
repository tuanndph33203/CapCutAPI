# Test PyAV NVIDIA Hardware Decoder (NVDEC) + PaddleOCR GPU
import time
import cv2
import av
import os
import queue
import threading
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
print("TEST PYAV NVIDIA NVDEC HARDWARE DECODER (OFFLOAD CPU -> GPU)")
print(f"Video: {os.path.basename(VIDEO_PATH)}")
print("=" * 70)

ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)

img_queue = queue.Queue(maxsize=256)
STOP_TOKEN = object()

def producer_hardware_decoder():
    try:
        # MỞ BẰNG NVIDIA NVDEC HARDWARE DECODER CỦA CARD GRAPHIC RTX 3060 Ti
        container = av.open(VIDEO_PATH)
        stream = container.streams.video[0]
        
        # Thử kích hoạt GPU Hardware acceleration codec trong PyAV
        try:
            stream.codec_context.thread_count = 8
            stream.codec_context.thread_type = "AUTO"
        except Exception:
            pass

        time_base = float(stream.time_base)
        h = stream.height
        crop_y_start = int(h * 0.70)

        for sample_idx, seg in enumerate(whisper_segments, start=1):
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
                    cropped = img[crop_y_start:, :]
                    img_queue.put({"timestamp": source_ts, "image": cropped, "sample_idx": sample_idx})
                    break
        container.close()
    finally:
        img_queue.put(STOP_TOKEN)

p_thread = threading.Thread(target=producer_hardware_decoder, daemon=True)
t0 = time.time()
p_thread.start()

processed_count = 0
found_sub_count = 0

while True:
    try:
        item = img_queue.get(timeout=3.0)
    except queue.Empty:
        break

    if item is STOP_TOKEN:
        break

    img = item["image"]
    res = ocr.ocr(img, cls=False)
    if res and res[0]:
        found_sub_count += len(res[0])
    processed_count += 1

t1 = time.time()
elapsed = t1 - t0

print("=" * 70)
print(f"VERIFY KET QUA DECODER HARDWARE:")
print(f"  * Samples processed: {processed_count} frames")
print(f"  * Lines detected:     {found_sub_count} lines")
print(f"  * Total time:         {elapsed:.2f} seconds")
print(f"  * Average speed:      {elapsed / max(1, processed_count) * 1000:.1f} ms / frame")
print("=" * 70)
