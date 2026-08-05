"""
Script test extract_hardsub_from_video trực tiếp trên video.
Chạy: python test_ocr_detect.py "path\to\video.mp4"
"""
import os
# Tắt cơ chế spin-wait của ONNXRuntime trên CPU để tránh FULL CPU (100%) khi chờ GPU DirectML xử lý
os.environ["ONNXRUNTIME_CPU_THREAD_ALLOW_SPINNING"] = "0"

import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r"c:\Users\nguye\Projects\CapCutAPI")

# Ghi log ra file để dễ theo dõi real-time
log_file_path = r"c:\Users\nguye\Projects\CapCutAPI\scratch\ocr_test_output.txt"
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
log_file = open(log_file_path, "w", encoding="utf-8")

class Logger:
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

sys.stdout = Logger(sys.stdout, log_file)

# Nạp DLL trước khi import module OCR để tránh lỗi DLL 126
from local_whisper_captions import _prepend_nvidia_dll_dirs_to_path
_prepend_nvidia_dll_dirs_to_path()

from local_ocr_captions import extract_hardsub_from_video

if len(sys.argv) < 2:

    print("Usage: python test_ocr_detect.py <video_path>")
    sys.exit(1)

video = sys.argv[1]
print(f"\n=== TEST OCR HARD-SUB DETECT ===")
print(f"Video: {video}")
print(f"Đang phân tích OCR với tần suất quét 1.0s/lần...\n")

def on_progress(msg):
    print(f"  [Progress] {msg}", flush=True)

results = extract_hardsub_from_video(video, sample_rate_sec=1.0, progress_callback=on_progress)


print(f"\n=== KẾT QUẢ TÌM THẤY: {len(results)} dòng phụ đề ===")
for seg in results[:30]:
    # Ghi an toàn bằng cách dùng Logger đã config sẵn encoding utf-8
    sys.stdout.write(f"[{seg['start']:.2f}s -> {seg['end']:.2f}s]: {seg['text']}\n")

if len(results) > 30:
    sys.stdout.write(f"...và {len(results) - 30} dòng phụ đề khác.\n")

