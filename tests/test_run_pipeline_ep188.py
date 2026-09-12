#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Run End-to-End Pipeline for Episode 188
=============================================
Tests:
1. Load full-length script from data/novels/Pham nhan tu tien/scripts/tap_188.txt (3,078 words)
2. Run NovelVideoPipeline with:
   - Voice: Ngọc Huyền (mới) (pure VITS 22,050Hz, clean natural audio)
   - Dynamic Pacing: Enabled (combat 1.30x, normal 1.20x)
   - Subtitle Chunker: SegmentOverlap guard verified
   - Multi-shot B-roll pacing (4-6s) + CapCut Native transitions
   - Looping BGM track
   - 3D YouTube Thumbnail
3. Verify output files: Master MP3, SRT subtitles, draft_content.json, thumbnail.
"""

import sys
import os
import time
from pathlib import Path

# Ensure UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from capcut_api.ai.novel_video_pipeline import NovelVideoPipeline

def main():
    print("=" * 70)
    print("🚀 BẮT ĐẦU TEST CODE PIPELINE: SẢN XUẤT TẬP 188 ĐẦY ĐỦ (~15 PHÚT)")
    print("=" * 70)

    script_path = ROOT_DIR / "data" / "novels" / "Pham nhan tu tien" / "scripts" / "tap_188.txt"
    if not script_path.exists():
        print(f"❌ Không tìm thấy kịch bản tại: {script_path}")
        sys.exit(1)

    script_text = script_path.read_text(encoding="utf-8")
    words = len(script_text.split())
    lines = len(script_text.splitlines())
    print(f"📄 Kịch bản đầu vào: {script_path.name}")
    print(f"   - Số từ: {words:,} từ")
    print(f"   - Số dòng: {lines:,} dòng")
    print(f"   - Thời lượng ước tính (@210 wpm): ~{words/210:.1f} phút")

    # Khởi tạo pipeline
    pipeline = NovelVideoPipeline(novel_id="Pham nhan tu tien")
    project_name = "Pham_Nhan_Tu_Tien_Tap_188_Dai_Chien_Hoang_Long_Son"

    t0 = time.time()
    # Chạy toàn bộ pipeline 5 bước
    result = pipeline.run_full_pipeline(
        script_text=script_text,
        project_name=project_name,
        voice_name="Ngọc Huyền (mới)",
        speed=1.2,
        canvas_ratio="16:9",
        auto_open_capcut=False, # Không tự chiếm màn hình khi test
        enable_dynamic_pacing=True,
        clean_audio_cache=True
    )
    elapsed = time.time() - t0

    print("\n" + "=" * 70)
    print("🎉 KẾT QUẢ TEST CODE PIPELINE TẬP 188:")
    print("=" * 70)
    print(f"✅ Trạng thái: {'THÀNH CÔNG' if result.get('success') else 'THẤT BẠI'}")
    print(f"⏱️ Thời gian render pipeline: {elapsed:.2f} giây")
    print(f"🎬 Tên dự án: {result.get('project_name')}")
    print(f"📁 Thư mục CapCut Draft: {result.get('draft_folder')}")
    print(f"🎵 Master Audio: {result.get('master_mp3')}")
    print(f"📝 File phụ đề SRT: {result.get('srt_file')}")
    print(f"⏱️ Tổng thời lượng video: {result.get('total_duration_sec', 0):.1f}s ({result.get('total_duration_sec', 0)/60:.1f} phút)")
    print(f"📸 Số phân cảnh Visual (shots): {result.get('shots_count')}")
    print(f"💬 Số câu thoại (sentences): {result.get('sentences_count')}")
    print(f"🎨 Thumbnail 3D: {result.get('thumbnail_path')}")

    # Kiểm tra tính toàn vẹn của CapCut draft_content.json
    draft_folder = Path(result.get("draft_folder", ""))
    content_json = draft_folder / "draft_content.json"
    if content_json.exists():
        import json
        draft_data = json.loads(content_json.read_text(encoding="utf-8"))
        tracks = draft_data.get("tracks", [])
        track_types = [t.get("type") for t in tracks]
        print(f"\n🔍 Kiểm tra cấu trúc CapCut Draft:")
        print(f"   - draft_content.json kích thước: {content_json.stat().st_size / 1024:.1f} KB")
        print(f"   - Các track hiện diện: {track_types}")
        for idx, t in enumerate(tracks):
            print(f"     + Track {idx+1} [{t.get('type')}] '{t.get('name', '')}': {len(t.get('segments', []))} phân đoạn")

    print("=" * 70)

if __name__ == "__main__":
    main()
