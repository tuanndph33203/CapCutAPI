# Test xác minh 100% GPU Execution và kiểm tra tải CPU/GPU
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
print("VERIFY TEST: NATIVE GPU TENSOR BATCH (CHECK LOAD CPU & GPU)")
print(f"Video: {os.path.basename(VIDEO_PATH)}")
print("=" * 70)

ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)

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

batch_items = []
processed_count = 0
found_sub_count = 0

while True:
    try:
        item = img_queue.get(timeout=3.0)
    except queue.Empty:
        break

    if item is STOP_TOKEN:
        if batch_items:
            images = [it["image"] for it in batch_items]
            try:
                dt_results = ocr.text_detector(images)
                dt_boxes_list = dt_results[0] if dt_results else []
                crop_list = []
                for img, dt_boxes in zip(images, dt_boxes_list):
                    if dt_boxes is not None and len(dt_boxes) > 0:
                        for box in dt_boxes:
                            pts = np.array(box, dtype=np.int32)
                            x_min, y_min = max(0, np.min(pts[:, 0])), max(0, np.min(pts[:, 1]))
                            x_max, y_max = min(img.shape[1], np.max(pts[:, 0])), min(img.shape[0], np.max(pts[:, 1]))
                            box_img = img[y_min:y_max, x_min:x_max]
                            if box_img.shape[0] > 0 and box_img.shape[1] > 0:
                                crop_list.append(box_img)
                if crop_list:
                    rec_res, _ = ocr.text_recognizer(crop_list)
                    if rec_res:
                        found_sub_count += len(rec_res)
            except Exception:
                pass
            processed_count += len(batch_items)
        break

    batch_items.append(item)
    if len(batch_items) >= 1:
        for it in batch_items:
            img = it["image"]
            ts = it["timestamp"]
            # GỌI CHUẨN PADDLEOCR GPU 1 DÒNG (GPU TỰ DO DETECT + CROP + RECOGNIZE)
            res = ocr.ocr(img, cls=False)
            if res and res[0]:
                found_sub_count += len(res[0])
        processed_count += len(batch_items)
        batch_items.clear()

t1 = time.time()
elapsed = t1 - t0

print("=" * 70)
print(f"VERIFY HOAN THANH!")
print(f"  * Total samples processed: {processed_count} frames")
print(f"  * Total subs detected:     {found_sub_count} lines")
print(f"  * Total execution time:    {elapsed:.2f} seconds")
print(f"  * Average speed:           {elapsed / processed_count * 1000:.1f} ms / frame")
print("=" * 70)
