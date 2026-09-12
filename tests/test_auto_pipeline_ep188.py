#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Autonomous Pipeline Execution for Episode 188
===================================================
Chạy trực tiếp quy trình tự động của NovelVideoPipelineService:
1. Tự động đọc và trích xuất dải chương 729 -> 731 từ kho truyện.
2. Tự động sinh kịch bản review thuyết minh từ nội dung chương thô (không nhập tay).
3. Tự động chuyển giao kịch bản sang NovelVideoPipeline:
   - NghiTTS lồng tiếng tự nhiên (Dynamic Pacing 1.2x - 1.3x)
   - Ghép Master Audio MP3 + Phụ đề SRT (ngăn cách nhịp điệu)
   - Tự động chia multi-shot B-roll & hiệu ứng chuyển cảnh
   - Ghép nhạc nền BGM lặp lại & sinh Thumbnail 3D
   - Đăng ký vào root_meta_info.json để CapCut PC hiển thị ở trang chủ
"""

import sys
import time
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from capcut_api.ai.novel_recap_engine import NovelVideoPipelineService

def main():
    print("=" * 70)
    print("🤖 CHẠY TỰ ĐỘNG TOÀN BỘ PIPELINE TẬP 188 (KHÔNG VIẾT TAY KỊCH BẢN)")
    print("=" * 70)

    service = NovelVideoPipelineService(novel_id="Pham nhan tu tien")
    prompt = "Tập 188 từ chương 729 đến 731 Phàm Nhân Tu Tiên thời lượng 15 phút"

    t0 = time.time()
    result = service.run_full_novel_recap(
        current_episode_num=187,
        novel_id="Pham nhan tu tien",
        voice="Ngọc Huyền (mới)",
        tts_speed=1.2,
        canvas_ratio="16:9",
        prompt=prompt,
        auto_open_capcut=False
    )
    elapsed = time.time() - t0

    print("\n" + "=" * 70)
    print("🎉 KẾT QUẢ PIPELINE TỰ ĐỘNG CHẠY XONG:")
    print("=" * 70)
    print(f"✅ Trạng thái: {result.get('success')}")
    print(f"⏱️ Tổng thời gian chạy pipeline: {elapsed:.2f}s")
    print(f"🎬 Tên dự án: {result.get('project_name')}")
    print(f"📁 Thư mục CapCut Draft: {result.get('draft_folder')}")
    print(f"🎵 Master Audio: {result.get('master_mp3')}")
    print(f"📝 File phụ đề SRT: {result.get('srt_file')}")
    print(f"⏱️ Thời lượng video sinh ra: {result.get('total_duration_sec', 0):.1f}s ({result.get('total_duration_sec', 0)/60:.1f} phút)")
    print(f"💬 Số câu thoại (sentences): {result.get('sentences_count')}")
    print(f"📸 Số phân cảnh Visual (scenes): {result.get('scenes_count')}")
    print("=" * 70)

if __name__ == "__main__":
    main()
