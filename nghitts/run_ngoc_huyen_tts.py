import os
import sys
import wave
import argparse

# Configure UTF-8 stdout for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from piper.voice import PiperVoice
from vietnormalizer import VietnameseNormalizer

def generate_tts(text_input, output_wav="ngoc_huyen_audio.wav"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "public", "tts-model", "vi", "Ngọc Huyền (mới).onnx")
    json_path = os.path.join(script_dir, "public", "tts-model", "vi", "Ngọc Huyền (mới).onnx.json")
    output_path = os.path.join(script_dir, output_wav)

    if not os.path.exists(model_path):
        print(f"❌ Error: Model ONNX file not found at: {model_path}")
        return False

    # 1. Normalization (Numbers, dates, currencies, abbreviations to full Vietnamese text)
    normalizer = VietnameseNormalizer()
    normalized_text = normalizer.normalize(text_input)

    print("--------------------------------------------------")
    print(f"📥 Input Text      : {text_input}")
    print(f"📝 Normalized Text : {normalized_text}")
    print(f"🗣️  Voice Model     : Ngọc Huyền (mới) [Vietnamese Accent]")
    print(f"🔊 Output Wav File : {output_path}")
    print("--------------------------------------------------")

    # 2. Load Piper Model with Vietnamese espeak configuration
    voice = PiperVoice.load(model_path, config_path=json_path)

    # 3. Synthesize speech directly into WAV file with 16-bit PCM mono audio
    with wave.open(output_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(voice.config.sample_rate)
        
        for chunk in voice.synthesize(normalized_text):
            wav_file.writeframes(chunk.audio_int16_bytes)

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        file_size = os.path.getsize(output_path)
        print(f"✅ SUCCESS! Generated Vietnamese audio: {output_path} ({file_size} bytes)")
        return True
    else:
        print("❌ FAILED to generate audio file.")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NGHI-TTS Ngọc Huyền Voice CLI Generator (Pure Vietnamese)")
    parser.add_argument("--text", type=str, default="Xin chào, đây là bài thử nghiệm đọc tiếng Việt từ dòng lệnh với giọng Ngọc Huyền chuẩn tiếng Việt.", help="Text to convert to speech")
    parser.add_argument("--output", type=str, default="ngoc_huyen_audio.wav", help="Output WAV filename")
    args = parser.parse_args()

    generate_tts(args.text, args.output)
