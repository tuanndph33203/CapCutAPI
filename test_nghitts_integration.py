import os
import sys

# Ensure UTF-8 output encoding for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from nghitts_service import generate_nghitts

def test_integration():
    print("=" * 60)
    print("🧪 TESTING NGHI-TTS INTEGRATION IN CAPCUTAPI")
    print("=" * 60)

    test_cases = [
        ("Xin chào bạn! Đây là thử nghiệm tích hợp giọng đọc Ngọc Huyền vào CapCutAPI.", "Ngọc Huyền (mới)", "test_ngoc_huyen_service.wav"),
        ("Tự động chuẩn hóa số 123456 và ngày 22/07/2026 trong đoạn văn này.", "Ngọc Huyền (mới)", "test_normalization.wav"),
    ]

    for text, voice, out_filename in test_cases:
        print(f"\n🗣️ Testing Voice: '{voice}'")
        print(f"📝 Input Text : {text}")
        out_path = os.path.join(os.path.dirname(__file__), "output_audio", out_filename)
        
        generated_file = generate_nghitts(text, voice_name=voice, output_path=out_path)
        
        file_size = os.path.getsize(generated_file)
        print(f"✅ Success! Generated WAV file:")
        print(f"   Path : {generated_file}")
        print(f"   Size : {file_size:,} bytes")
        assert os.path.exists(generated_file)
        assert file_size > 0

    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_integration()
