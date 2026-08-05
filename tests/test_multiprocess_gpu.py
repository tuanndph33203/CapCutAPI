# Benchmark Multiprocessing GPU Pipeline (Breaking Python GIL for True 4x GPU Acceleration)
import time
import cv2
import av
import os
import multiprocessing as mp
import numpy as np

VIDEO_PATH = r"C:\Users\nguye\Projects\CapCutAPI\111111111111111111\assets\video\video_4e8fe43bafb2a271.mp4"

def gpu_worker_process(worker_id, sample_sublist, return_dict):
    from local_whisper_captions import _prepend_nvidia_dll_dirs_to_path
    _prepend_nvidia_dll_dirs_to_path()
    import logging
    logging.getLogger("ppocr").setLevel(logging.WARNING)
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(use_angle_cls=False, lang="ch", use_gpu=True, show_log=False)

    container = av.open(VIDEO_PATH)
    stream = container.streams.video[0]
    stream.thread_type = "AUTO"
    time_base = float(stream.time_base)
    h = stream.height
    crop_y_start = int(h * 0.70)

    found_count = 0
    for seg in sample_sublist:
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
                res = ocr.ocr(cropped, cls=False)
                if res and res[0]:
                    found_count += len(res[0])
                break
    container.close()
    return_dict[worker_id] = found_count

if __name__ == "__main__":
    whisper_segments = []
    for i in range(500):
        st = round(i * (320.0 / 500), 2)
        whisper_segments.append({"start": st, "end": round(st + 1.8, 2)})

    print("=" * 70)
    print("TEST TRUE MULTIPROCESSING GPU PIPELINE (BREAKING GIL)")
    print(f"Video: {os.path.basename(VIDEO_PATH)}")
    print("=" * 70)

    NUM_PROCESSES = 4
    # Chia 500 frames thành 4 phần bằng nhau cho 4 Process độc lập
    chunks = np.array_split(whisper_segments, NUM_PROCESSES)

    manager = mp.Manager()
    return_dict = manager.dict()
    processes = []

    t0 = time.time()

    for i in range(NUM_PROCESSES):
        p = mp.Process(target=gpu_worker_process, args=(i, list(chunks[i]), return_dict))
        processes.append(p)
        p.start()

    for p in processes:
        p.join()

    t1 = time.time()
    elapsed = t1 - t0
    total_found = sum(return_dict.values())

    print("=" * 70)
    print("VERIFY MULTIPROCESSING GPU KET QUA:")
    print(f"  * Total samples processed: 500 frames across 4 processes")
    print(f"  * Total subs detected:     {total_found} lines")
    print(f"  * Total execution time:    {elapsed:.2f} seconds")
    print(f"  * Speedup Factor:          {51.35 / elapsed:.2f}x faster!")
    print(f"  * Real Effective Speed:    {elapsed / 500 * 1000:.1f} ms / frame 🚀")
    print("=" * 70)
