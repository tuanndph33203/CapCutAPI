# Benchmark PyAV Keyframe Seek + GPU Batch Recognition
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

# Giả lập 500 mốc thoại rải đều trên video 328 giây
whisper_segments = []
for i in range(500):
    st = round(i * (320.0 / 500), 2)
    whisper_segments.append({"start": st, "end": round(st + 1.8, 2)})

print("=" * 70)
print(f"TEST LARGE-SCALE: PYAV KEYFRAME SEEK + GPU BATCH (500 segments = 3,000 frames)")
print(f"Video: {os.path.basename(VIDEO_PATH)}")
print("=" * 70)

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

# 500 mốc thoại từ Whisper
whisper_segments = []
for i in range(500):
    st = round(i * (320.0 / 500), 2)
    whisper_segments.append({"start": st, "end": round(st + 1.8, 2)})

print("=" * 70)
print(f"TEST PRODUCER-CONSUMER PIPELINE: EP GPU CHAY LIEN TUC 80-90%")
print(f"Video: {os.path.basename(VIDEO_PATH)}")
print("=" * 70)

ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)
text_detector = ocr.text_detector
text_recognizer = ocr.text_recognizer

img_queue = queue.Queue(maxsize=128)
STOP_TOKEN = None

# ── PRODUCER THỜT CPU: ĐỌC VÀ CẮT ẢNH LIÊN TỤC ─────────────────────────────
def producer_thread():
    container = av.open(VIDEO_PATH)
    stream = container.streams.video[0]
    stream.thread_type = "AUTO"
    time_base = float(stream.time_base)
    h = stream.height
    crop_y_start = int(h * 0.70)
    
    for seg_idx, seg in enumerate(whisper_segments):
        start_ts = seg["start"]
        end_ts = seg["end"]
        sample_timestamps = [start_ts - 0.3, start_ts, start_ts + 0.3, end_ts - 0.3, end_ts, end_ts + 0.3]
        
        target_pts = int((start_ts - 1.0) / time_base)
        container.seek(target_pts, stream=stream, backward=True)
        
        ts_idx = 0
        for frame in container.decode(stream):
            if ts_idx >= len(sample_timestamps):
                break
            pts_sec = float(frame.pts * time_base) if frame.pts is not None else float(frame.time)
            target_ts = sample_timestamps[ts_idx]
            
            if pts_sec >= target_ts - 0.05:
                img = frame.to_ndarray(format="bgr24")
                cropped = img[crop_y_start:, :]
                img_queue.put(cropped)
                ts_idx += 1
                
    container.close()
    img_queue.put(STOP_TOKEN)

# ── CONSUMER THỜT GPU: ÉP BẮT GPU OCR KHÔNG NGỪNG NGHỈ ───────────────────
def consumer_thread():
    total_processed = 0
    t0 = time.time()
    
    batch = []
    while True:
        try:
            item = img_queue.get(timeout=2.0)
        except queue.Empty:
            break
            
        if item is STOP_TOKEN:
            if batch:
                # Process remaining
                text_detector(batch[0])
                batch_crops = []
                for b_img in batch:
                    dt_boxes, _ = text_detector(b_img)
                    if dt_boxes is not None and len(dt_boxes) > 0:
                        for box in dt_boxes:
                            pts = np.array(box, dtype=np.int32)
                            x_min, y_min = max(0, np.min(pts[:, 0])), max(0, np.min(pts[:, 1]))
                            x_max, y_max = min(b_img.shape[1], np.max(pts[:, 0])), min(b_img.shape[0], np.max(pts[:, 1]))
                            box_img = b_img[y_min:y_max, x_min:x_max]
                            if box_img.shape[0] > 0 and box_img.shape[1] > 0:
                                batch_crops.append(box_img)
                if batch_crops:
                    text_recognizer(batch_crops)
            break
            
        batch.append(item)
        if len(batch) >= 16:
            batch_crops = []
            for b_img in batch:
                dt_boxes, _ = text_detector(b_img)
                if dt_boxes is not None and len(dt_boxes) > 0:
                    for box in dt_boxes:
                        pts = np.array(box, dtype=np.int32)
                        x_min, y_min = max(0, np.min(pts[:, 0])), max(0, np.min(pts[:, 1]))
                        x_max, y_max = min(b_img.shape[1], np.max(pts[:, 0])), min(b_img.shape[0], np.max(pts[:, 1]))
                        box_img = b_img[y_min:y_max, x_min:x_max]
                        if box_img.shape[0] > 0 and box_img.shape[1] > 0:
                            batch_crops.append(box_img)
            if batch_crops:
                text_recognizer(batch_crops)
            total_processed += len(batch)
            batch.clear()
            
    t1 = time.time()
    print("=" * 70)
    print(f"CONSUMER GPU HOAN THANH: {total_processed} frames trong {t1 - t0:.2f} giay!")

p_thread = threading.Thread(target=producer_thread)
c_thread = threading.Thread(target=consumer_thread)

p_thread.start()
c_thread.start()

p_thread.join()
c_thread.join()
