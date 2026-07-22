import os
import sys
import subprocess

# Ensure UTF-8 stdout encoding for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from vietnormalizer import VietnameseNormalizer

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "public", "tts-model", "vi", "Ngọc Huyền (mới).onnx")
    json_path = os.path.join(script_dir, "public", "tts-model", "vi", "Ngọc Huyền (mới).onnx.json")
    output_wav = os.path.join(script_dir, "output_ngoc_huyen.wav")

    print(f"📌 Model path: {model_path}")
    print(f"📌 JSON path: {json_path}")

    text = "Xin chào, đây là bài thử nghiệm giọng đọc Ngọc Huyền trực tiếp từ dòng lệnh."
    
    # 1. Normalization
    normalizer = VietnameseNormalizer()
    normalized_text = normalizer.normalize(text)
    print(f"📝 Original text: {text}")
    print(f"📝 Normalized text: {normalized_text}")

    # 2. Find piper executable
    venv_piper = os.path.join(sys.prefix, "Scripts", "piper.exe")
    piper_cmd = venv_piper if os.path.exists(venv_piper) else "piper"

    print(f"🚀 Running Piper CLI: {piper_cmd}")
    
    # Run Piper CLI
    cmd = [
        piper_cmd,
        "--model", model_path,
        "--output_file", output_wav
    ]

    process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    stdout, stderr = process.communicate(input=normalized_text)

    print(f"Return code: {process.returncode}")
    if stdout:
        print(f"Stdout: {stdout}")
    if stderr:
        print(f"Stderr: {stderr}")

    if os.path.exists(output_wav) and os.path.getsize(output_wav) > 0:
        print(f"✅ Success! Audio generated at: {output_wav} ({os.path.getsize(output_wav)} bytes)")
    else:
        print("❌ Failed to generate audio file.")

if __name__ == "__main__":
    main()
