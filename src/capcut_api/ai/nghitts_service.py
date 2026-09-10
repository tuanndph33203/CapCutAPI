import os
import sys
import wave
import urllib.request
import urllib.parse
from typing import Dict, Optional, Any

# Ensure UTF-8 stdout encoding for Windows console environments
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

try:
    from piper.voice import PiperVoice
    from piper.config import SynthesisConfig
except ImportError:
    PiperVoice = None
    SynthesisConfig = None

try:
    from vietnormalizer import VietnameseNormalizer
except ImportError:
    VietnameseNormalizer = None

try:
    import imageio_ffmpeg
    from pydub import AudioSegment
    AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    pass

# Global model cache to prevent reloading ONNX models into memory on every function call
_VOICE_CACHE: Dict[str, Any] = {}
_NORMALIZER_INSTANCE: Optional[Any] = None

BASE_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nghitts", "public", "tts-model", "vi")

def _get_normalizer():
    global _NORMALIZER_INSTANCE
    if _NORMALIZER_INSTANCE is None:
        if VietnameseNormalizer is None:
            raise RuntimeError("vietnormalizer package is not installed.")
        _NORMALIZER_INSTANCE = VietnameseNormalizer()
    return _NORMALIZER_INSTANCE

def _voice_to_ascii_filename(voice_name: str) -> str:
    mapping = {
        "Ngọc Huyền (mới)": "ngoc_huyen_moi",
        "Nam Miền Nam": "nam_mien_nam",
        "Nữ Miền Nam": "nu_mien_nam",
    }
    if voice_name in mapping:
        return mapping[voice_name]
    import unicodedata, re
    clean = unicodedata.normalize("NFKD", voice_name).encode("ASCII", "ignore").decode("ASCII")
    return re.sub(r"[^\w\-]", "_", clean).strip("_").lower() or "voice"

def ensure_model_files(voice_name: str) -> tuple[str, str]:
    """
    Ensure that the .onnx and .onnx.json files for the requested voice exist locally.
    If missing, automatically download them from the NGHI-TTS R2 storage endpoint.
    """
    os.makedirs(BASE_MODEL_DIR, exist_ok=True)

    ascii_name = _voice_to_ascii_filename(voice_name)
    onnx_file = f"{ascii_name}.onnx"
    json_file = f"{ascii_name}.onnx.json"

    onnx_path = os.path.join(BASE_MODEL_DIR, onnx_file)
    json_path = os.path.join(BASE_MODEL_DIR, json_file)

    encoded_name = urllib.parse.quote(voice_name)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    def _download_file(url, target_path):
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp, open(target_path, "wb") as out_f:
            out_f.write(resp.read())

    if not os.path.exists(json_path):
        json_url = f"https://nghitts.app/api/model/{encoded_name}.onnx.json"
        print(f"📥 Downloading config for voice '{voice_name}' from {json_url}...")
        _download_file(json_url, json_path)

    if not os.path.exists(onnx_path):
        onnx_url = f"https://nghitts.app/api/model/{encoded_name}.onnx"
        print(f"📥 Downloading ONNX model for voice '{voice_name}' (this may take a moment)...")
        _download_file(onnx_url, onnx_path)
        print(f"✅ Model '{voice_name}' downloaded successfully!")

    return onnx_path, json_path



def get_piper_voice(voice_name: str = "Ngọc Huyền (mới)"):
    """
    Load or retrieve a cached PiperVoice model instance.
    """
    if PiperVoice is None:
        raise RuntimeError("piper-tts package is not installed.")
    global _VOICE_CACHE
    if voice_name in _VOICE_CACHE:
        return _VOICE_CACHE[voice_name]

    onnx_path, json_path = ensure_model_files(voice_name)
    voice = PiperVoice.load(onnx_path, config_path=json_path)
    _VOICE_CACHE[voice_name] = voice
    return voice

def unload_voice_cache() -> None:
    """
    Clear cached Piper ONNX models from RAM and trigger Python garbage collection.
    """
    global _VOICE_CACHE
    import gc
    _VOICE_CACHE.clear()
    gc.collect()
    print("[NghiTTS] Voice cache unloaded from RAM.")


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
    import re
    if not re.sub(r'[^\w\sàáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]', '', normalized_text).strip():
        raise ValueError(f"Text '{text}' contains no speakable words after normalization.")

    # 2. Get output filepath
    if not output_path:
        default_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data", "audio")
        os.makedirs(default_dir, exist_ok=True)
        filename = f"nghitts_{voice_name.replace(' ', '_')}_{hash(text) & 0xffffffff}.wav"
        output_path = os.path.join(default_dir, filename)

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 3. Load voice model (cached)
    voice = get_piper_voice(voice_name)

    # 4. Configure speed natively via Piper length_scale (1.0 / target_speed)
    target_speed = max(0.2, min(5.0, float(speed or 1.0)))
    syn_config = SynthesisConfig(length_scale=float(1.0 / target_speed))

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
