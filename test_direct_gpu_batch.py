"""
Test direct TextDetector + TextRecognizer batch GPU processing.
Ép GPU chạy batch 16 frames cùng lúc bằng Paddle Inference Predictors.
"""
import time
import cv2
import os
import sys
import numpy as np

VIDEO_PATH = r"C:\Users\nguye\Projects\CapCutAPI\111111111111111111\assets\video\video_4e8fe43bafb2a271.mp4"
SAMPLE_RATE_SEC = 1.0
BATCH_SIZE = 16

# Setup NVIDIA DLL path
from local_whisper_captions import _prepend_nvidia_dll_dirs_to_path
_prepend_nvidia_dll_dirs_to_path()

import logging
logging.getLogger("ppocr").setLevel(logging.WARNING)

from paddleocr import PaddleOCR

print("Khoi tao PaddleOCR GPU voi det_limit_side_len=640...")
ocr_engine = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False, det_limit_side_len=640)

# Lay direct TextDetector va TextRecognizer predictor tu object PaddleOCR
text_detector = ocr_engine.text_detector
text_recognizer = ocr_engine.text_recognizer

# Read frames
cap = cv2.VideoCapture(VIDEO_PATH)
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
frame_step = max(1, int(fps * SAMPLE_RATE_SEC))
sample_indices = list(range(0, total_frames, frame_step))

h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
crop_y_start = int(h * 0.70)

print(f"Doc {len(sample_indices)} frames...")
frames_data = []
for idx in sample_indices:
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ret, frame = cap.read()
    if ret:
        frames_data.append(frame[crop_y_start:, :])
cap.release()

print(f"Da doc xong {len(frames_data)} frames.")
print("=" * 60)
print(f"BAT DAU TEST BATCH GPU (Batch size = {BATCH_SIZE})...")

t0 = time.time()
processed_count = 0

for i in range(0, len(frames_data), BATCH_SIZE):
    batch = frames_data[i:i + BATCH_SIZE]
    
    img_crop_list = []
    
    # 1. Detection per frame (nhẹ)
    for img in batch:
        dt_boxes, _ = text_detector(img)
        if dt_boxes is not None and len(dt_boxes) > 0:
            for box in dt_boxes:
                pts = np.array(box, dtype=np.int32)
                x_min, y_min = np.min(pts, axis=0)
                x_max, y_max = np.max(pts, axis=0)
                
                x_min, y_min = max(0, x_min), max(0, y_min)
                x_max, y_max = min(img.shape[1], x_max), min(img.shape[0], y_max)
                
                crop_img = img[y_min:y_max, x_min:x_max]
                if crop_img.shape[0] > 0 and crop_img.shape[1] > 0:
                    img_crop_list.append(crop_img)
                    
    # 2. Text Recognition BATCH TRÊN GPU (chiếm 80% thời gian OCR)
    if img_crop_list:
        rec_res, _ = text_recognizer(img_crop_list)
        
    processed_count += len(batch)
    print(f"-> Da xong batch {processed_count}/{len(frames_data)} frames (GPU vua doc batch {len(img_crop_list)} cum chu)")

t1 = time.time()
elapsed = t1 - t0
print("=" * 60)
print(f"HOAN THANH: {len(frames_data)} frames trong {elapsed:.2f} giay!")
print(f"Toc do trung binh: {elapsed / len(frames_data) * 1000:.1f} ms / frame")
