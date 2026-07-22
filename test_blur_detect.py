"""
Script test detect_hardsub_blur_config truc tiep tren video.
Chay: python test_blur_detect.py "path\to\video.mp4"
"""
import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r"c:\Users\nguye\Projects\CapCutAPI")

from capcut_gui_app import detect_hardsub_blur_config

if len(sys.argv) < 2:
    print("Usage: python test_blur_detect.py <video_path>")
    sys.exit(1)

video = sys.argv[1]
print(f"\n=== TEST DETECT BLUR ===")
print(f"Video: {video}")
print(f"Dang phan tich 20 frames x 3 lan thu...\n")

result = detect_hardsub_blur_config(video, sample_count=20, blur_radius=24)
print(f"\n=== KET QUA ===")
print(result)
