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

# Danh mục toàn bộ các giọng đọc chất lượng cao của NghiTTS
NGHITTS_VOICES: Dict[str, Dict[str, Any]] = {
    "Ngọc Huyền (mới)": {
        "slug": "ngoc_huyen_moi",
        "gender": "female",
        "region": "Bắc",
        "style": "Đọc truyện kiếm hiệp / tiên hiệp, truyền cảm, mượt mà",
        "is_default": True
    },
    "Duy Oryx": {
        "slug": "duy_oryx",
        "gender": "male",
        "region": "Bắc",
        "style": "Trầm ấm, đĩnh đạc, hiện đại, thuyết minh review"
    },
    "Mạnh Dũng": {
        "slug": "manh_dung",
        "gender": "male",
        "region": "Bắc",
        "style": "Hào hùng, khí thế, phóng sự, truyện hành động chiến đấu"
    },
    "Ngọc Ngạn": {
        "slug": "ngoc_ngan",
        "gender": "male",
        "region": "Hải Ngoại",
        "style": "Kể chuyện đêm khuya, lôi cuốn, giọng điệu huyền bí đặc trưng"
    },
    "Trấn Thành": {
        "slug": "tran_thanh",
        "gender": "male",
        "region": "Nam",
        "style": "Hoạt ngôn, sinh động, biểu cảm phong phú"
    },
    "Việt Thảo": {
        "slug": "viet_thao",
        "gender": "male",
        "region": "Hải Ngoại",
        "style": "Kể chuyện liêu trai, giật gân, bí ẩn, truyện kinh dị"
    },
    "Minh Quang": {
        "slug": "minh_quang",
        "gender": "male",
        "region": "Bắc",
        "style": "Rõ ràng, dứt khoát, tin tức, tài liệu"
    },
    "Mai Phương": {
        "slug": "mai_phuong",
        "gender": "female",
        "region": "Bắc",
        "style": "Dịu dàng, nhẹ nhàng, sâu lắng"
    },
    "Chiêu Thành": {
        "slug": "chieu_thanh",
        "gender": "male",
        "region": "Bắc",
        "style": "Cổ phong, tiên hiệp, kiếm hiệp kiếm khách"
    },
    "Lạc Phi": {
        "slug": "lac_phi",
        "gender": "female",
        "region": "Bắc",
        "style": "Trẻ trung, hiện đại, linh hoạt"
    },
    "Thanh Phương Viettel": {
        "slug": "thanh_phuong_viettel",
        "gender": "female",
        "region": "Bắc",
        "style": "Chuẩn mực phát thanh viên, giọng AI quốc dân"
    },
    "Phương Trang": {
        "slug": "phuong_trang",
        "gender": "female",
        "region": "Bắc",
        "style": "Truyền cảm, ấm áp, văn học tự sự"
    },
    "Thiện Tâm": {
        "slug": "thien_tam",
        "gender": "male",
        "region": "Bắc",
        "style": "Điềm đạm, triết lý, nhân văn, chiêm nghiệm"
    },
    "Ban Mai": {
        "slug": "ban_mai",
        "gender": "female",
        "region": "Bắc",
        "style": "Tươi vui, rạng rỡ, năng động"
    },
    "Tài An": {
        "slug": "tai_an",
        "gender": "male",
        "region": "Nam",
        "style": "Trầm ấm, chững chạc, tin cậy"
    },
    "Minh Khang": {
        "slug": "minh_khang",
        "gender": "male",
        "region": "Nam",
        "style": "Trẻ trung, tự nhiên, gần gũi"
    },
    "Mỹ Tâm": {
        "slug": "my_tam",
        "gender": "female",
        "region": "Trung",
        "style": "Đặc trưng giọng miền Trung, chân chất, cảm xúc"
    },
}

def list_available_nghitts_voices() -> Dict[str, Dict[str, Any]]:
    """Trả về danh mục toàn bộ các giọng đọc NghiTTS kèm mô tả phong cách."""
    return NGHITTS_VOICES

def _voice_to_ascii_filename(voice_name: str) -> str:
    # 1. Tìm trực tiếp trong danh mục NghiTTS
    for v_name, meta in NGHITTS_VOICES.items():
        if v_name.lower() == voice_name.lower() or meta["slug"] == voice_name.lower():
            return meta["slug"]
    
    # 2. Fallback chuyển Unicode sang ASCII an toàn
    import unicodedata, re
    clean = unicodedata.normalize("NFKD", voice_name).encode("ASCII", "ignore").decode("ASCII")
    return re.sub(r"[^\w\-]", "_", clean).strip("_").lower() or "voice"

def resolve_nghitts_voice(voice_query: Optional[str] = None, config_path: Optional[str] = None) -> str:
    """
    Tự động phân giải giọng đọc động theo cấu hình dự án hoặc truy vấn của người dùng:
    1. Nếu voice_query khớp với tên hoặc slug của NghiTTS -> Trả về tên giọng chuẩn.
    2. Nếu voice_query là mặc định ('default', 'vi-VN-NamMinhNeural', '') -> Đọc cấu hình 'novel_pipeline.tts.voice' từ config.json.
    3. Fallback an toàn: 'Ngọc Huyền (mới)' (đã tích hợp offline trong repo).
    """
    import json
    from pathlib import Path

    # Đọc cấu hình dự án / toàn cục nếu có
    cfg_voice = None
    try:
        cfg_file = Path(config_path) if config_path else Path(__file__).resolve().parents[3] / "config.json"
        if cfg_file.exists():
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            cfg_voice = data.get("novel_pipeline", {}).get("tts", {}).get("voice") or data.get("tts_voice")
    except Exception:
        pass

    target = (voice_query or "").strip()
    
    # Nếu voice_query không có hoặc chỉ là generic edge-tts placeholder, ưu tiên dùng cấu hình dự án
    if not target or target.lower() in ("default", "vi-vn-namminhneural", "auto"):
        if cfg_voice and cfg_voice.strip():
            target = cfg_voice.strip()

    if not target or target.lower() in ("default", "vi-vn-namminhneural", "auto"):
        return "Ngọc Huyền (mới)"

    target_lower = target.lower()

    # 1. Khớp chính xác theo tên hiển thị
    for v_name in NGHITTS_VOICES:
        if v_name.lower() == target_lower:
            return v_name

    # 2. Khớp theo slug (ví dụ: ngoc_ngan, duy_oryx, manh_dung)
    for v_name, meta in NGHITTS_VOICES.items():
        if meta["slug"] == target_lower:
            return v_name

    # 3. Khớp từ khóa mờ không dấu (fuzzy matching)
    import unicodedata
    def strip_accents(s: str) -> str:
        return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()

    target_no_accent = strip_accents(target_lower)
    for v_name, meta in NGHITTS_VOICES.items():
        v_no_accent = strip_accents(v_name)
        if target_no_accent in v_no_accent or meta["slug"] in target_no_accent:
            return v_name
        # Thử từng từ khóa
        parts = [p for p in target_no_accent.split() if len(p) >= 3]
        if any(p in v_no_accent for p in parts):
            return v_name

    return "Ngọc Huyền (mới)"

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
