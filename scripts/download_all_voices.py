#!/usr/bin/env python3
"""
Script tải và đồng bộ toàn bộ 17 giọng đọc NghiTTS (.onnx, config) và âm thanh mẫu (.wav) lên Google Drive.
"""
import sys
import os
import time
from pathlib import Path

# Add src to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from capcut_api.ai.nghitts_service import (
    NGHITTS_VOICES,
    ensure_model_files,
    get_voice_sample_audio_path,
    sync_voices_to_gdrive,
    resolve_nghitts_voice
)
from capcut_api.cloud.gdrive_manager import get_gdrive_manager

def main():
    print("=" * 70)
    print("🚀 BẮT ĐẦU TẢI VÀ ĐỒNG BỘ FULL TOÀN BỘ 17 GIỌNG ĐỌC LÊN GOOGLE DRIVE")
    print("=" * 70)

    gdrive = get_gdrive_manager()
    print(f"📁 Chế độ Google Drive: {gdrive.mode}")
    print(f"📁 Thư mục đích Models: {gdrive.get_tts_models_dir()}")
    print(f"📁 Thư mục đích Samples: {gdrive.get_tts_samples_dir()}")
    print("-" * 70)

    all_voices = list(NGHITTS_VOICES.keys())
    total = len(all_voices)

    for idx, v_name in enumerate(all_voices, 1):
        print(f"\n[{idx}/{total}] 🎙️ Đang xử lý giọng đọc: '{v_name}'...")
        t0 = time.time()
        try:
            # 1. Đảm bảo model file (.onnx, .json) có sẵn và sao lưu lên Drive
            onnx_path, json_path = ensure_model_files(v_name)
            onnx_mb = round(os.path.getsize(onnx_path) / (1024 * 1024), 1)
            print(f"   ✓ Model ONNX sẵn sàng: {onnx_mb} MB")

            # 2. Tạo hoặc khôi phục file âm thanh mẫu và đồng bộ lên Drive
            sample_path = get_voice_sample_audio_path(v_name)
            sample_kb = round(os.path.getsize(sample_path) / 1024, 1)
            print(f"   ✓ Âm thanh mẫu sẵn sàng: {sample_kb} KB ({sample_path})")

            elapsed = round(time.time() - t0, 1)
            print(f"   ✅ Hoàn tất '{v_name}' trong {elapsed}s")
        except Exception as e:
            print(f"   ❌ Lỗi khi xử lý giọng '{v_name}': {e}")

    # 3. Đồng bộ toàn bộ và cập nhật voices_manifest.json
    print("\n" + "=" * 70)
    print("📋 Đang cập nhật lại file quản lý voices_manifest.json...")
    res = sync_voices_to_gdrive()
    print(f"🎉 HOÀN THÀNH ĐỒNG BỘ FULL TOÀN BỘ GIỌNG ĐỌC!")
    print(f"   • Tổng số models trên Drive:  {res['synced_models_count']}/{total}")
    print(f"   • Tổng số samples trên Drive: {res['synced_samples_count']}/{total}")
    print(f"   • File manifest: {res['manifest_path']}")
    print("=" * 70)

if __name__ == "__main__":
    main()
