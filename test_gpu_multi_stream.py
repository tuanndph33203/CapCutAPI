"""
Test CUDA Multi-Stream / Multi-Instance GPU OCR để vắt 70-90% công suất GPU RTX 3060 Ti
"""
import time
import cv2
import av
import os
import concurrent.futures
from local_whisper_captions import _prepend_nvidia_dll_dirs_to_path

_prepend_nvidia_dll_dirs_to_path()

import logging
logging.getLogger("ppocr").setLevel(logging.WARNING)
from paddleocr import PaddleOCR

VIDEO_PATH = r"C:\Users\nguye\Projects\CapCutAPI\111111111111111111\assets\video\video_4e8fe43bafb2a271.mp4"
NUM_GPU_WORKERS = 16  # 16 thớt GPU song song để ép GPU 0 chạy 80-90%

print(f"Khoi tao {NUM_GPU_WORKERS} GPU OCR Workers tren GPU 0...")
ocr_workers = [PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False) for _ in range(NUM_GPU_WORKERS)]

print("Dang doc 300 frames tu video...")
container = av.open(VIDEO_PATH)
stream = container.streams.video[0]
stream.thread_type = "AUTO"

frames_data = []
for i, frame in enumerate(container.decode(stream)):
    if i >= 1000:
        break
    img = frame.to_ndarray(format="bgr24")
    h = img.shape[0]
    frames_data.append(img[int(h*0.7):, :])
container.close()

print(f"Da doc {len(frames_data)} frames. BAT DAU VAT CONG SUAT GPU 0 (4-Stream Parallel)...")

def worker_task(worker_id, img):
    worker = ocr_workers[worker_id % NUM_GPU_WORKERS]
    return worker.ocr(img, cls=False)

t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_GPU_WORKERS) as executor:
    futures = [executor.submit(worker_task, i, img) for i, img in enumerate(frames_data)]
    results = [f.result() for f in futures]
t1 = time.time()

elapsed = t1 - t0
print("=" * 60)
print(f"HOAN THANH {len(frames_data)} frames trong {elapsed:.2f} giay!")
print(f"Toc do trung binh: {elapsed / len(frames_data) * 1000:.1f} ms / frame")
