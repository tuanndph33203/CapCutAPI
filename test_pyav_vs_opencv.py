"""
Benchmark so sánh tốc độ & độ chính xác đọc Video: OpenCV vs PyAV (FFmpeg C-binding)
"""
import time
import cv2
import av
import os
import numpy as np

VIDEO_PATH = r"C:\Users\nguye\Projects\CapCutAPI\111111111111111111\assets\video\video_4e8fe43bafb2a271.mp4"
SAMPLE_RATE_SEC = 1.0

print(f"Video test: {os.path.basename(VIDEO_PATH)}")
print("=" * 60)

# ── 1. TEST OPENCV ────────────────────────────────────────────────────────
print("[1] Dang doc frames bang OPENCV...")
t0 = time.time()
cap = cv2.VideoCapture(VIDEO_PATH)
fps_cv = cap.get(cv2.CAP_PROP_FPS) or 30.0
total_frames_cv = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
frame_step_cv = max(1, int(fps_cv * SAMPLE_RATE_SEC))

cv_frames = []
for idx in range(0, total_frames_cv, frame_step_cv):
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ret, frame = cap.read()
    if ret:
        cv_frames.append(frame)
cap.release()
t1 = time.time()
cv_time = t1 - t0
print(f"-> OPENCV: Doc {len(cv_frames)} frames trong {cv_time:.3f}s ({cv_time/len(cv_frames)*1000:.2f} ms/frame)")

# ── 2. TEST PYAV (FFmpeg C-binding) ───────────────────────────────────────
print("\n[2] Dang doc frames bang PYAV (FFmpeg Direct)...")
t0 = time.time()
container = av.open(VIDEO_PATH)
stream = container.streams.video[0]
stream.thread_type = "AUTO" # Multi-thread decode

pyav_frames = []
last_pts = -1
target_interval_pts = int(float(stream.average_rate) * SAMPLE_RATE_SEC * stream.time_base.denominator / stream.time_base.numerator)

# Decode stream qua FFmpeg C Engine
for frame in container.decode(stream):
    if last_pts == -1 or (frame.pts - last_pts) >= target_interval_pts:
        # Convert frame sang BGR numpy array cho OCR
        img = frame.to_ndarray(format="bgr24")
        pyav_frames.append(img)
        last_pts = frame.pts

container.close()
t1 = time.time()
pyav_time = t1 - t0
print(f"-> PYAV: Doc {len(pyav_frames)} frames trong {pyav_time:.3f}s ({pyav_time/len(pyav_frames)*1000:.2f} ms/frame)")

# ── KẾT QUẢ SO SÁNH ───────────────────────────────────────────────────────
print("=" * 60)
print("KET QUA BENCHMARK DECODE VIDEO:")
print(f"  - OpenCV: {cv_time:.2f}s")
print(f"  - PyAV:   {pyav_time:.2f}s")
if pyav_time > 0:
    speedup = cv_time / pyav_time
    print(f"-> PyAV NHANH GAP {speedup:.2f} LAN SO VOI OPENCV!")
