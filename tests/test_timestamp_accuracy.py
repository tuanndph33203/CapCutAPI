# Test kiểm tra độ chính xác Timestamp & Tốc độ giữa PyAV Single-Pass vs OpenCV CAP_PROP_POS_FRAMES
import time
import cv2
import av
import os
import numpy as np

VIDEO_PATH = r"C:\Users\nguye\Projects\CapCutAPI\111111111111111111\assets\video\video_4e8fe43bafb2a271.mp4"

# Tạo 10 mốc timestamp ngẫu nhiên giả lập từ Whisper (đơn vị: giây)
test_timestamps = [5.0, 12.5, 25.0, 48.2, 75.0, 110.0, 150.5, 200.0, 260.0, 310.0]

print("=" * 70)
print("TEST SO SÁNH ĐỘ CHÍNH XÁC TIMESTAMP VÀ HÌNH ẢNH: PYAV VS OPENCV")
print(f"Video: {os.path.basename(VIDEO_PATH)}")
print(f"Danh sách mốc thử nghiệm (Whisper audio segments): {test_timestamps}")
print("=" * 70)

# ── 1. LẤY FRAME THEO OPENCV (CAP_PROP_POS_FRAMES) ─────────────────────────
print("\n[1] Lay frame theo OpenCV (cach cap.set hien tai)...")
t0 = time.time()
cap = cv2.VideoCapture(VIDEO_PATH)
fps_cv = cap.get(cv2.CAP_PROP_FPS) or 30.0

cv_results = {}
for ts in test_timestamps:
    frame_idx = int(round(ts * fps_cv))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if ret:
        cv_results[ts] = (frame_idx, frame)
cap.release()
t1 = time.time()
time_cv = t1 - t0
print(f"-> OpenCV xong {len(cv_results)} mốc trong {time_cv:.3f} giây.")


# ── 2. LẤY FRAME THEO PYAV SINGLE-PASS (KHÔNG SEEK) ───────────────────────
print("\n[2] Lay frame theo PyAV Single-Pass (doc luon 1 luot theo PTS chuẩn)...")
t0 = time.time()
container = av.open(VIDEO_PATH)
stream = container.streams.video[0]
stream.thread_type = "AUTO"

time_base = float(stream.time_base)
pyav_results = {}
target_ts_set = sorted(test_timestamps)
current_target_idx = 0

for frame in container.decode(stream):
    if current_target_idx >= len(target_ts_set):
        break
    
    # Tính timestamp chính xác chuẩn xác từng microsecond từ PTS gốc của video
    pts_sec = float(frame.pts * time_base) if frame.pts is not None else float(frame.time)
    
    target_ts = target_ts_set[current_target_idx]
    if pts_sec >= target_ts:
        img = frame.to_ndarray(format="bgr24")
        pyav_results[target_ts] = (pts_sec, img)
        current_target_idx += 1

container.close()
t1 = time.time()
time_pyav = t1 - t0
print(f"-> PyAV xong {len(pyav_results)} mốc trong {time_pyav:.3f} giây.")


# ── 3. KIỂM TRA ĐỘ LỆCH TIMESTAMP & ĐỘ GIỐNG NHAU CỦA HÌNH ẢNH ─────────────
print("\n" + "=" * 70)
print("KẾT QUẢ KIỂM TRA ĐỘ CHÍNH XÁC HÌNH ẢNH THỰC TẾ:")
print("Timestamp (s) | Frame OpenCV | PTS PyAV (s) | Độ lệch (ms) | Ảnh khớp 100%?")
print("-" * 70)

for ts in test_timestamps:
    if ts in cv_results and ts in pyav_results:
        f_idx, img_cv = cv_results[ts]
        pts_sec, img_pyav = pyav_results[ts]
        
        diff_ms = abs(pts_sec - ts) * 1000.0
        
        # So sánh chênh lệch giữa 2 bức ảnh
        img_diff = np.mean(np.abs(img_cv.astype(float) - img_pyav.astype(float)))
        is_exact_match = "DUNG (Khop)" if img_diff < 5.0 else f"LECH ({img_diff:.1f})"
        
        print(f"{ts:13.1f} | Frame {f_idx:5d} | {pts_sec:10.3f}s | {diff_ms:10.1f}ms | {is_exact_match}")

print("=" * 70)
