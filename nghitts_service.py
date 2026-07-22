import os
import sys
import wave
import urllib.request
import urllib.parse
from typing import Dict, Optional

# Ensure UTF-8 stdout encoding for Windows console environments
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from piper.voice import PiperVoice
from vietnormalizer import VietnameseNormalizer

# Global model cache to prevent reloading ONNX models into memory on every function call
_VOICE_CACHE: Dict[str, PiperVoice] = {}
_NORMALIZER_INSTANCE: Optional[VietnameseNormalizer] = None

BASE_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nghitts", "public", "tts-model", "vi")

def _get_normalizer() -> VietnameseNormalizer:
    global _NORMALIZER_INSTANCE
    if _NORMALIZER_INSTANCE is None:
        _NORMALIZER_INSTANCE = VietnameseNormalizer()
    return _NORMALIZER_INSTANCE

def ensure_model_files(voice_name: str) -> tuple[str, str]:
    """
    Ensure that the .onnx and .onnx.json files for the requested voice exist locally.
    If missing, automatically download them from the NGHI-TTS R2 storage endpoint.
    """
    os.makedirs(BASE_MODEL_DIR, exist_ok=True)

    onnx_file = f"{voice_name}.onnx"
    json_file = f"{voice_name}.onnx.json"

    onnx_path = os.path.join(BASE_MODEL_DIR, onnx_file)
    json_path = os.path.join(BASE_MODEL_DIR, json_file)

    encoded_name = urllib.parse.quote(voice_name)

    if not os.path.exists(json_path):
        json_url = f"https://nghitts.app/api/model/{encoded_name}.onnx.json"
        print(f"📥 Downloading config for voice '{voice_name}' from {json_url}...")
        urllib.request.urlretrieve(json_url, json_path)

    if not os.path.exists(onnx_path):
        onnx_url = f"https://nghitts.app/api/model/{encoded_name}.onnx"
        print(f"📥 Downloading ONNX model for voice '{voice_name}' (this may take a moment)...")
        urllib.request.urlretrieve(onnx_url, onnx_path)
        print(f"✅ Model '{voice_name}' downloaded successfully!")

    return onnx_path, json_path

def get_piper_voice(voice_name: str = "Ngọc Huyền (mới)") -> PiperVoice:
    """
    Load or retrieve a cached PiperVoice model instance.
    """
    global _VOICE_CACHE
    if voice_name in _VOICE_CACHE:
        return _VOICE_CACHE[voice_name]

    onnx_path, json_path = ensure_model_files(voice_name)
    voice = PiperVoice.load(onnx_path, config_path=json_path)
    _VOICE_CACHE[voice_name] = voice
    return voice

from piper.config import SynthesisConfig

def generate_nghitts(
    text: str,
    voice_name: str = "Ngọc Huyền (mới)",
    output_path: Optional[str] = None,
    speed: float = 1.0
) -> str:
    """
    Generate Vietnamese TTS audio using NGHI-TTS model.

    :param text: Raw text to convert to speech (e.g. "Xin chào bạn, hôm nay là ngày 22/07/2026.")
    :param voice_name: Name of the voice model (e.g. "Ngọc Huyền (mới)", "Ban Mai", "Trấn Thành", "Ngọc Ngạn")
    :param output_path: Destination WAV filepath (optional, defaults to generated file in current dir)
    :param speed: Speech speed multiplier (1.0 = normal, 1.2 = 20% faster, 0.8 = 20% slower)
    :return: Absolute path to the generated .wav file
    """
    if not text or not text.strip():
        raise ValueError("Text input cannot be empty.")

    # 1. Normalize text (Convert numbers, dates, abbreviations to full Vietnamese text)
    normalizer = _get_normalizer()
    normalized_text = normalizer.normalize(text)

    # 2. Get output filepath
    if not output_path:
        os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_audio"), exist_ok=True)
        filename = f"nghitts_{voice_name.replace(' ', '_')}_{hash(text) & 0xffffffff}.wav"
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_audio", filename)

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 3. Load voice model (cached)
    voice = get_piper_voice(voice_name)

    # 4. Configure speed via length_scale (inverse relationship)
    target_speed = max(0.2, min(5.0, float(speed or 1.0)))
    syn_config = SynthesisConfig(length_scale=1.0 / target_speed)

    # 5. Synthesize speech directly into WAV file
    with wave.open(output_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(voice.config.sample_rate)

        for chunk in voice.synthesize(normalized_text, syn_config=syn_config):
            wav_file.writeframes(chunk.audio_int16_bytes)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"Failed to generate audio at {output_path}")

    return output_path

if __name__ == "__main__":
    # Simple CLI test run when executing script directly
    sample_text = "Xin chào, đây là bài thử nghiệm tích hợp NGHI-TTS trực tiếp vào CapCutAPI."
    print(f"Testing NGHI-TTS Service with text: '{sample_text}'")
    out_file = generate_nghitts(sample_text)
    print(f"✅ Generated WAV File: {out_file} ({os.path.getsize(out_file)} bytes)")
