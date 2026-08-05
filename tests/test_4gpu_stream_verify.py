# Test xác minh độc lập 4-GPU Workers Multi-Stream trên 500 frames
import time
import cv2
import av
import os
import queue
import threading
import concurrent.futures
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
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
print("TEST BENCHMARK DOC TOAN LUC: 4-GPU MULTI-STREAM WORKERS (500 FRAMES)")
print(f"Video: {os.path.basename(VIDEO_PATH)}")
print("=" * 70)

NUM_GPU_WORKERS = 4
ocr_workers = [PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False) for _ in range(NUM_GPU_WORKERS)]

img_queue = queue.Queue(maxsize=256)
STOP_TOKEN = object()

def producer_worker():
    container = av.open(VIDEO_PATH)
    stream = container.streams.video[0]
    stream.thread_type = "AUTO"
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
    img_queue.put(STOP_TOKEN)

p_thread = threading.Thread(target=producer_worker, daemon=True)
t0 = time.time()
p_thread.start()

def worker_task(worker_id, item):
    worker_ocr = ocr_workers[worker_id % NUM_GPU_WORKERS]
    img = item["image"]
    ts = item["timestamp"]
    res = worker_ocr.ocr(img, cls=False)
    lines_found = 0
    if res and res[0]:
        lines_found = len(res[0])
    return item["sample_idx"], lines_found

processed_count = 0
found_sub_count = 0

with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_GPU_WORKERS) as executor:
    futures = []
    item_idx = 0
    while True:
        try:
            item = img_queue.get(timeout=3.0)
        except queue.Empty:
            break

        if item is STOP_TOKEN:
            break

        w_id = item_idx % NUM_GPU_WORKERS
        fut = executor.submit(worker_task, w_id, item)
        futures.append(fut)
        item_idx += 1

    for fut in concurrent.futures.as_completed(futures):
        try:
            s_idx, lines = fut.result()
            processed_count += 1
            found_sub_count += lines
        except Exception:
            pass

t1 = time.time()
elapsed = t1 - t0

print("=" * 70)
print(f"VERIFY KET QUA 4-GPU WORKERS BENCHMARK:")
print(f"  * Total samples processed: {processed_count} frames")
print(f"  * Total subs detected:     {found_sub_count} lines")
print(f"  * Total execution time:    {elapsed:.2f} seconds")
print(f"  * Average speed:           {elapsed / max(1, processed_count) * 1000:.1f} ms / frame")
print("=" * 70)
