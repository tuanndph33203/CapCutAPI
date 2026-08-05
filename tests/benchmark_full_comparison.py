"""
Benchmark So Sánh Trực Tiếp 2 Phương Pháp OCR Video:
- Cách 1 (Cũ): OpenCV + Single Worker Sequential
- Cách 2 (Mới): PyAV + 4 Multi-Stream GPU Workers
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
TEST_FRAMES = 500

print("=" * 60)
print(f"BAT DAU BENCHMARK SO SANH TRUC TIEP ({TEST_FRAMES} frames)")
print(f"Video: {os.path.basename(VIDEO_PATH)}")
print("=" * 60)

# ── CACH 1: OPENCV + SINGLE WORKER ───────────────────────────────────────
print("\n[CACH 1 - CU] OpenCV + Single GPU Worker Sequential...")
t0 = time.time()
ocr_single = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)

cap = cv2.VideoCapture(VIDEO_PATH)
h_cv = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
crop_y_cv = int(h_cv * 0.7)

results_1 = []
for i in range(TEST_FRAMES):
    ret, frame = cap.read()
    if not ret:
        break
    cropped = frame[crop_y_cv:, :]
    r = ocr_single.ocr(cropped, cls=False)
    results_1.append(r)
cap.release()
t1 = time.time()
time_1 = t1 - t0
print(f"-> [CACH 1] Xong {len(results_1)} frames trong {time_1:.2f}s ({time_1/len(results_1)*1000:.1f} ms/frame)")


# ── CACH 2: PYAV + 4 GPU WORKERS PARALLEL ─────────────────────────────────
print("\n[CACH 2 - MOI] PyAV + 4 Multi-Stream GPU Workers...")
t0 = time.time()
NUM_WORKERS = 4
ocr_workers = [PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False) for _ in range(NUM_WORKERS)]

container = av.open(VIDEO_PATH)
stream = container.streams.video[0]
stream.thread_type = "AUTO"

frames_2 = []
for i, frame in enumerate(container.decode(stream)):
    if i >= TEST_FRAMES:
        break
    img = frame.to_ndarray(format="bgr24")
    h = img.shape[0]
    frames_2.append(img[int(h*0.7):, :])
container.close()

def worker_task(worker_id, img):
    w = ocr_workers[worker_id % NUM_WORKERS]
    return w.ocr(img, cls=False)

with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
    futures = [executor.submit(worker_task, i, img) for i, img in enumerate(frames_2)]
    results_2 = [f.result() for f in futures]

t1 = time.time()
time_2 = t1 - t0
print(f"-> [CACH 2] Xong {len(results_2)} frames trong {time_2:.2f}s ({time_2/len(results_2)*1000:.1f} ms/frame)")


# ── SO SANH KET QUA ───────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("BANG BAO CAO KET QUA SO SANH TRUC TIEP:")
print(f"  * Cach 1 (OpenCV + Single Worker):  {time_1:.2f} giay ({time_1/TEST_FRAMES*1000:.1f} ms/frame)")
print(f"  * Cach 2 (PyAV + 4 GPU Workers):    {time_2:.2f} giay ({time_2/TEST_FRAMES*1000:.1f} ms/frame)")
speedup = time_1 / time_2 if time_2 > 0 else 0
print(f"-> CACH 2 NHANH GAP: {speedup:.2f} LAN!")
print(f"-> Uoc tinh video 57.5 phut (3453s):")
print(f"    - Cach 1: ~{(time_1/TEST_FRAMES * 3453)/60:.1f} phut")
print(f"    - Cach 2: ~{(time_2/TEST_FRAMES * 3453)/60:.1f} phut")
print("=" * 60)
