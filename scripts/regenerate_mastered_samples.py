#!/usr/bin/env python3
"""
Tạo lại toàn bộ 19 file âm thanh mẫu (.wav) chuẩn gốc thuần khiết (Pure VITS 22,050 Hz)
- Loại bỏ hoàn toàn bộ lọc EQ/Treble và Compressor gây rè/vỡ tiếng
- Sử dụng đúng tham số prior gốc của model huấn luyện (noise_scale=0.667, noise_w=0.8)
- Ghi đè lên thư mục local (data/tts_samples/) và Google Drive (G:\My Drive\CapCutRecapAI\tts_samples).
"""
import sys
import os
import time
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from capcut_api.ai.nghitts_service import (
    NGHITTS_VOICES,
    get_voice_sample_audio_path,
    sync_voices_to_gdrive,
    _voice_to_ascii_filename
)
from capcut_api.cloud.gdrive_manager import get_gdrive_manager

def main():
    print("=" * 75)
    print("🚀 BẮT ĐẦU TẠO LẠI TOÀN BỘ 19 ÂM THANH MẪU (CHUẨN GỐC THUẦN KHIẾT - KHÔNG RÈ)")
    print("=" * 75)

    gdrive = get_gdrive_manager()
    drive_samples_dir = gdrive.get_tts_samples_dir()
    print(f"📁 Thư mục Google Drive Samples: {drive_samples_dir}")
    print("-" * 75)

    voices = list(NGHITTS_VOICES.keys())
    total = len(voices)

    for idx, v_name in enumerate(voices, 1):
        slug = _voice_to_ascii_filename(v_name)
        print(f"\n[{idx}/{total}] 🎙️ Đang tạo Sample chuẩn gốc: '{v_name}' ({slug})...")
        t0 = time.time()
        try:
            # force_regenerate=True sẽ chạy lại với cấu hình chuẩn gốc không qua EQ rè
            sample_path = get_voice_sample_audio_path(v_name, force_regenerate=True)
            elapsed = round(time.time() - t0, 2)
            sz_kb = round(os.path.getsize(sample_path) / 1024, 1)
            print(f"   ✅ Hoàn tất trong {elapsed}s | Kích thước: {sz_kb} KB (22.05kHz Pure VITS - Ấm, Tự Nhiên, Không Rè)")
        except Exception as e:
            print(f"   ❌ Lỗi khi tạo sample '{v_name}': {e}")

    # Cập nhật lại voices_manifest.json
    print("\n" + "=" * 75)
    print("📋 Đang cập nhật lại voices_manifest.json trên Google Drive...")
    res = sync_voices_to_gdrive()
    print("🎉 HOÀN TẤT ĐỒNG BỘ TOÀN BỘ GIỌNG ĐỌC CHUẨN GỐC LÊN GOOGLE DRIVE!")
    print(f"   • Tổng số Models trên Drive:  {res['synced_models_count']}/{total}")
    print(f"   • Tổng số Samples trên Drive: {res['synced_samples_count']}/{total}")
    print(f"   • File Manifest: {res['manifest_path']}")
    print("=" * 75)

if __name__ == "__main__":
    main()
