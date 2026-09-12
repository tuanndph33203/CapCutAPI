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

# Xác định thư mục lưu trữ model TTS tách biệt khỏi Git:
# 1. Biến môi trường CAPCUT_TTS_MODEL_DIR (nếu cấu hình)
# 2. Thư mục data/models/tts/ trong dự án (đã được .gitignore bảo vệ)
# 3. Thư mục user cache ~/.cache/capcut_api/models/tts/
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_PROJECT_DATA_MODEL_DIR = os.path.join(_REPO_ROOT, "data", "models", "tts")
_USER_CACHE_MODEL_DIR = os.path.join(os.path.expanduser("~"), ".cache", "capcut_api", "models", "tts")
_LEGACY_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nghitts", "public", "tts-model", "vi")

BASE_MODEL_DIR = os.environ.get("CAPCUT_TTS_MODEL_DIR", _PROJECT_DATA_MODEL_DIR)

def _get_gdrive_manager():
    try:
        from capcut_api.cloud.gdrive_manager import get_gdrive_manager
        return get_gdrive_manager()
    except Exception:
        return None

def _get_normalizer():
    global _NORMALIZER_INSTANCE
    if _NORMALIZER_INSTANCE is None:
        if VietnameseNormalizer is None:
            raise RuntimeError("vietnormalizer package is not installed.")
        _NORMALIZER_INSTANCE = VietnameseNormalizer()
    return _NORMALIZER_INSTANCE

VIETNAMESE_PRONUNCIATION_RULES = [
    (r'\bPK\b', 'Pê Ca'),
    (r'\bPvP\b', 'Pê Vê Pê'),
    (r'\bPvE\b', 'Pê Vê E'),
    (r'\bBoss\b', 'Bốt'),
    (r'\bboss\b', 'bốt'),
    (r'\bAdmin\b', 'Át min'),
    (r'\bReview\b', 'Ri viu'),
    (r'\breview\b', 'ri viu'),
    (r'\bGame\b', 'Gêm'),
    (r'\bgame\b', 'gêm'),
    (r'\bServer\b', 'Sơ vơ'),
    (r'\bserver\b', 'sơ vơ'),
    (r'\bSolo\b', 'Sô lô'),
    (r'\bsolo\b', 'sô lô'),
    (r'\bFarm\b', 'Fam'),
    (r'\bfarm\b', 'fam'),
    (r'\bItem\b', 'Ai tầm'),
    (r'\bitem\b', 'ai tầm'),
    (r'\bLevel\b', 'Lê vồ'),
    (r'\blevel\b', 'lê vồ'),
    (r'\bCombo\b', 'Com bô'),
    (r'\bcombo\b', 'com bô'),
    (r'\bTrailer\b', 'Tơ ray lơ'),
    (r'\btrailer\b', 'tơ ray lơ'),
    (r'\bCapCut\b', 'Cáp Cắt'),
    (r'\bcapcut\b', 'cáp cắt'),
    (r'\bTikTok\b', 'Tóp Tóp'),
    (r'\btiktok\b', 'tóp tóp'),
    (r'\bYouTube\b', 'Du Túp'),
    (r'\byoutube\b', 'du túp'),
    (r'\bVideo\b', 'Vi dé o'),
    (r'\bvideo\b', 'vi dé o'),
    (r'\bTop\b', 'Tốp'),
    (r'\btop\b', 'tốp'),
    (r'\bFan\b', 'Phen'),
    (r'\bfan\b', 'phen'),
]

def clean_vietnamese_pronunciation(text: str) -> str:
    """Chuẩn hóa các từ mượn, thuật ngữ gaming/review, từ viết tắt sang phiên âm tiếng Việt tự nhiên."""
    import re
    cleaned = text
    for pattern, repl in VIETNAMESE_PRONUNCIATION_RULES:
        cleaned = re.sub(pattern, repl, cleaned)
    return cleaned

def prepare_prosody_punctuation(text: str) -> str:
    """
    Chuẩn hóa khoảng trắng và dấu câu tự nhiên, loại bỏ các ký tự gây rè hoặc ngắt câu giật cục.
    """
    import re
    t = text
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def apply_studio_mastering(input_wav_path: str, output_wav_path: Optional[str] = None, gender: str = "male") -> str:
    """
    Bộ lọc âm thanh nhẹ nhàng (Transparent Mastering) qua FFmpeg:
    - High-pass Filter (60Hz): Khử ồn ù trầm hạ âm
    - Giữ nguyên tần số mẫu gốc (22,050 Hz), không nâng mẫu giả lập để tránh méo vỡ (aliasing)
    - Không boost treble hoặc nén dynamic compression để đảm bảo không bị rè tiếng
    """
    import subprocess
    import shutil

    if not os.path.exists(input_wav_path) or os.path.getsize(input_wav_path) == 0:
        return input_wav_path

    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg_exe = shutil.which("ffmpeg")

    if not ffmpeg_exe or not os.path.exists(ffmpeg_exe):
        return input_wav_path

    af = "highpass=f=60,loudnorm=I=-16:TP=-1.5:LRA=14"

    target_out = output_wav_path or input_wav_path
    temp_out = target_out + ".mastered.tmp.wav"

    cmd = [
        ffmpeg_exe, "-y",
        "-i", str(input_wav_path),
        "-af", af,
        str(temp_out)
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, timeout=30)
        if res.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
            if os.path.exists(target_out) and target_out != temp_out:
                try:
                    os.remove(target_out)
                except Exception:
                    pass
            os.replace(temp_out, target_out)
            return target_out
    except Exception as e:
        print(f"⚠️ Không thể chạy mastering FFmpeg: {e}")
        if os.path.exists(temp_out):
            try:
                os.remove(temp_out)
            except Exception:
                pass

    return input_wav_path

# Danh mục toàn bộ các giọng đọc chất lượng cao của NghiTTS kèm câu thoại mẫu đặc trưng
NGHITTS_VOICES: Dict[str, Dict[str, Any]] = {
    "Ngọc Huyền (mới)": {
        "slug": "ngoc_huyen_moi",
        "gender": "female",
        "region": "Bắc",
        "style": "Đọc truyện kiếm hiệp / tiên hiệp, truyền cảm, mượt mà",
        "sample_quote": "Chào bạn, ta là Ngọc Huyền. Hãy cùng ta bước vào thế giới tu tiên huyền huyễn đầy kịch tính nhé!",
        "is_default": True
    },
    "Duy Oryx": {
        "slug": "duy_oryx",
        "gender": "male",
        "region": "Bắc",
        "style": "Trầm ấm, đĩnh đạc, hiện đại, thuyết minh review",
        "sample_quote": "Xin chào các bạn, tôi là Duy Oryx. Chào mừng bạn đến với kênh tóm tắt phim và review tiểu thuyết."
    },
    "Mạnh Dũng": {
        "slug": "manh_dung",
        "gender": "male",
        "region": "Bắc",
        "style": "Hào hùng, khí thế, phóng sự, truyện hành động chiến đấu",
        "sample_quote": "Toàn quân nghe lệnh! Hãy sẵn sàng nghênh chiến bảo vệ môn phái đến giọt máu cuối cùng!"
    },
    "Ngọc Ngạn": {
        "slug": "ngoc_ngan",
        "gender": "male",
        "region": "Hải Ngoại",
        "style": "Kể chuyện đêm khuya, lôi cuốn, giọng điệu huyền bí đặc trưng",
        "sample_quote": "Đêm nay, xin mời quý vị cùng lắng nghe một câu chuyện kỳ bí chưa từng được hé lộ..."
    },
    "Trấn Thành": {
        "slug": "tran_thanh",
        "gender": "male",
        "region": "Nam",
        "style": "Hoạt ngôn, sinh động, biểu cảm phong phú",
        "sample_quote": "Trời ơi tin được không! Hôm nay tui sẽ kể cho các bạn nghe một câu chuyện cực kỳ ly kỳ và hấp dẫn nha!"
    },
    "Việt Thảo": {
        "slug": "viet_thao",
        "gender": "male",
        "region": "Hải Ngoại",
        "style": "Kể chuyện liêu trai, giật gân, bí ẩn, truyện kinh dị",
        "sample_quote": "Chào quý vị! Câu chuyện ngày hôm nay mang một màu sắc rất lạ lùng và rùng rợn..."
    },
    "Minh Quang": {
        "slug": "minh_quang",
        "gender": "male",
        "region": "Bắc",
        "style": "Rõ ràng, dứt khoát, tin tức, tài liệu",
        "sample_quote": "Bản tin hôm nay sẽ cập nhật những diễn biến chấn động nhất trên đại lục tu chân."
    },
    "Mai Phương": {
        "slug": "mai_phuong",
        "gender": "female",
        "region": "Bắc",
        "style": "Dịu dàng, nhẹ nhàng, sâu lắng",
        "sample_quote": "Chào bạn, chúc bạn một ngày mới thật bình yên và tràn ngập những điều tốt đẹp."
    },
    "Chiếu Thành": {
        "slug": "chieu_thanh",
        "gender": "male",
        "region": "Bắc",
        "style": "Cổ phong, tiên hiệp, kiếm hiệp kiếm khách",
        "sample_quote": "Kiếm xuất khỏi vỏ, định đoạt giang hồ, hôm nay quyết một trận sinh tử!"
    },
    "Lạc Phi": {
        "slug": "lac_phi",
        "gender": "female",
        "region": "Bắc",
        "style": "Trẻ trung, hiện đại, linh hoạt",
        "sample_quote": "Chào cả nhà, mình là Lạc Phi, cùng mình khám phá những bí mật trong tập phim mới nhất nhé!"
    },
    "Thanh Phương Viettel": {
        "slug": "thanh_phuong_viettel",
        "gender": "female",
        "region": "Bắc",
        "style": "Chuẩn mực phát thanh viên, giọng AI quốc dân",
        "sample_quote": "Kính chào quý khách. Trợ lý trí tuệ nhân tạo hân hạnh được đồng hành và hỗ trợ bạn."
    },
    "Phương Trang": {
        "slug": "phuong_trang",
        "gender": "female",
        "region": "Bắc",
        "style": "Truyền cảm, ấm áp, văn học tự sự",
        "sample_quote": "Từng trang sách mở ra mang theo những hoài niệm sâu lắng và cảm xúc khó phai."
    },
    "Thiện Tâm": {
        "slug": "thien_tam",
        "gender": "male",
        "region": "Bắc",
        "style": "Điềm đạm, triết lý, nhân văn, chiêm nghiệm",
        "sample_quote": "Vạn vật trong nhân gian đều có nhân duyên, tâm an thì cảnh giới tự khắc tỏ tường."
    },
    "Ban Mai": {
        "slug": "ban_mai",
        "gender": "female",
        "region": "Bắc",
        "style": "Tươi vui, rạng rỡ, năng động",
        "sample_quote": "Một ngày mới rạng rỡ lại bắt đầu, chúc bạn luôn tràn đầy năng lượng và niềm tin!"
    },
    "Tài An": {
        "slug": "tai_an",
        "gender": "male",
        "region": "Nam",
        "style": "Trầm ấm, chững chạc, tin cậy",
        "sample_quote": "Kính thưa quý vị khán giả, xin mời cùng chúng tôi theo dõi phóng sự đặc biệt kỳ này."
    },
    "Minh Khang": {
        "slug": "minh_khang",
        "gender": "male",
        "region": "Nam",
        "style": "Trẻ trung, tự nhiên, gần gũi",
        "sample_quote": "Chào anh em, hôm nay chúng ta cùng nhau xung trận trong tập tiếp theo nhé!"
    },
    "Mỹ Tâm": {
        "slug": "my_tam",
        "gender": "female",
        "region": "Trung",
        "style": "Đặc trưng giọng miền Trung, chân chất, cảm xúc",
        "sample_quote": "Chào mọi người nha, em rất vui khi được đọc truyện cho bà con cô bác nghe nè."
    },
    "Duy Onyx (mới)": {
        "slug": "duy_onyx_moi",
        "gender": "male",
        "region": "Bắc",
        "style": "Trầm ấm, chi tiết, bản nâng cấp mới",
        "sample_quote": "Xin chào các bạn, đây là bản nâng cấp giọng đọc mới nhất của Duy Onyx."
    },
    "Mỹ Tâm Real": {
        "slug": "my_tam_real",
        "gender": "female",
        "region": "Trung",
        "style": "Giọng miền Trung mộc mạc, tự nhiên nguyên bản",
        "sample_quote": "Chào cả nhà thương yêu, mình là Mỹ Tâm, rất vui được gặp lại mọi người!"
    },
}

def list_available_nghitts_voices() -> Dict[str, Dict[str, Any]]:
    """Trả về danh mục toàn bộ các giọng đọc NghiTTS kèm mô tả, câu thoại mẫu và trạng thái Local / Google Drive."""
    gdrive = _get_gdrive_manager()
    drive_models_dir = gdrive.get_tts_models_dir() if (gdrive and gdrive.mount_path and gdrive.mount_path.exists()) else None
    drive_samples_dir = gdrive.get_tts_samples_dir() if (gdrive and gdrive.mount_path and gdrive.mount_path.exists()) else None

    sample_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data", "tts_samples")

    result = {}
    for name, meta in NGHITTS_VOICES.items():
        slug = meta.get("slug") or _voice_to_ascii_filename(name)
        onnx_file = f"{slug}.onnx"
        local_exists = os.path.exists(os.path.join(BASE_MODEL_DIR, onnx_file))
        drive_exists = (drive_models_dir / onnx_file).exists() if drive_models_dir else False

        sample_file = f"sample_{slug}.wav"
        local_sample = os.path.exists(os.path.join(sample_dir, sample_file))
        drive_sample = (drive_samples_dir / sample_file).exists() if drive_samples_dir else False

        result[name] = {
            **meta,
            "is_local": local_exists,
            "is_in_drive": drive_exists,
            "is_sample_ready": local_sample or drive_sample
        }
    return result

def get_voice_sample_audio_path(voice_name: str, custom_text: Optional[str] = None, force_regenerate: bool = False) -> str:
    """Tạo hoặc lấy file audio mẫu (.wav) đã được cache cho giọng đọc chỉ định (hỗ trợ cả Local Cache & Google Drive)."""
    import shutil
    resolved_name = resolve_nghitts_voice(voice_name)
    slug = _voice_to_ascii_filename(resolved_name)
    sample_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data", "tts_samples")
    os.makedirs(sample_dir, exist_ok=True)
    
    cached_path = os.path.join(sample_dir, f"sample_{slug}.wav")

    gdrive = _get_gdrive_manager()
    drive_samples_dir = gdrive.get_tts_samples_dir() if (gdrive and gdrive.mount_path and gdrive.mount_path.exists()) else None
    
    # 1. Nếu đã có cache local và không yêu cầu custom_text / force_regenerate
    if os.path.exists(cached_path) and os.path.getsize(cached_path) > 0 and not custom_text and not force_regenerate:
        # Tự động sao lưu lên Google Drive nếu chưa có
        if drive_samples_dir:
            drive_sample = drive_samples_dir / f"sample_{slug}.wav"
            if not drive_sample.exists() or drive_sample.stat().st_size != os.path.getsize(cached_path):
                try:
                    shutil.copy2(cached_path, str(drive_sample))
                except Exception:
                    pass
        return cached_path

    # 2. Nếu thiếu file local nhưng đã có trên Google Drive -> phục hồi về local cache
    if not os.path.exists(cached_path) and drive_samples_dir and not custom_text and not force_regenerate:
        drive_sample = drive_samples_dir / f"sample_{slug}.wav"
        if drive_sample.exists() and drive_sample.stat().st_size > 0:
            try:
                shutil.copy2(str(drive_sample), cached_path)
                return cached_path
            except Exception:
                pass
        
    text_to_speak = custom_text or NGHITTS_VOICES.get(resolved_name, {}).get("sample_quote") or f"Xin chào, đây là giọng đọc thử nghiệm {resolved_name}."
    target_out = cached_path if not custom_text else None
    result_path = generate_nghitts(text_to_speak, voice_name=resolved_name, output_path=target_out, speed=1.0, enhance_audio=False)

    # 3. Sao lưu file âm thanh mẫu vừa tạo lên Google Drive
    if drive_samples_dir and not custom_text and os.path.exists(result_path):
        drive_sample = drive_samples_dir / f"sample_{slug}.wav"
        try:
            shutil.copy2(result_path, str(drive_sample))
        except Exception:
            pass

    return result_path

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
    Ensure that the .onnx and .onnx.json files for the requested voice exist.
    Priority order:
    1. Local repository model directory: BASE_MODEL_DIR
    2. Google Drive directory: G:\My Drive\CapCutRecapAI\tts_models\
       (restores to local BASE_MODEL_DIR for ultra-fast low-latency synthesis)
    3. Remote NGHI-TTS R2 storage endpoint (https://nghitts.app/api/model/...)
       and automatically backs up newly downloaded model to Google Drive.
    """
    import shutil
    os.makedirs(BASE_MODEL_DIR, exist_ok=True)

    ascii_name = _voice_to_ascii_filename(voice_name)
    onnx_file = f"{ascii_name}.onnx"
    json_file = f"{ascii_name}.onnx.json"

    onnx_path = os.path.join(BASE_MODEL_DIR, onnx_file)
    json_path = os.path.join(BASE_MODEL_DIR, json_file)

    # Step 0: Kiểm tra fallback từ user cache hoặc legacy directory nếu BASE_MODEL_DIR chưa có
    for c_dir in [_USER_CACHE_MODEL_DIR, _LEGACY_MODEL_DIR]:
        if not os.path.exists(onnx_path) and os.path.exists(os.path.join(c_dir, onnx_file)):
            shutil.copy2(os.path.join(c_dir, onnx_file), onnx_path)
        if not os.path.exists(json_path) and os.path.exists(os.path.join(c_dir, json_file)):
            shutil.copy2(os.path.join(c_dir, json_file), json_path)

    gdrive = _get_gdrive_manager()
    drive_models_dir = gdrive.get_tts_models_dir() if (gdrive and gdrive.mount_path and gdrive.mount_path.exists()) else None

    # Step 1: Kiểm tra xem có trên Google Drive không nếu local chưa có
    if drive_models_dir:
        drive_onnx = drive_models_dir / onnx_file
        drive_json = drive_models_dir / json_file

        if not os.path.exists(json_path) and drive_json.exists():
            print(f"☁️ Khôi phục config giọng '{voice_name}' từ Google Drive: {drive_json}...")
            shutil.copy2(str(drive_json), json_path)

        if not os.path.exists(onnx_path) and drive_onnx.exists():
            print(f"☁️ Khôi phục model ONNX giọng '{voice_name}' từ Google Drive: {drive_onnx}...")
            shutil.copy2(str(drive_onnx), onnx_path)

    # Step 2: Nếu cả local và Drive đều chưa có -> tải từ cloud endpoint
    encoded_name = urllib.parse.quote(voice_name)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    def _download_file(url, target_path):
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp, open(target_path, "wb") as out_f:
            out_f.write(resp.read())

    if not os.path.exists(json_path):
        json_url = f"https://nghitts.app/api/model/{encoded_name}.onnx.json"
        print(f"📥 Đang tải config cho giọng '{voice_name}' từ {json_url}...")
        try:
            _download_file(json_url, json_path)
        except Exception as e:
            template_json = os.path.join(BASE_MODEL_DIR, "duy_oryx.onnx.json")
            if not os.path.exists(template_json):
                template_json = os.path.join(BASE_MODEL_DIR, "ngoc_huyen_moi.onnx.json")
            if os.path.exists(template_json):
                print(f"ℹ️ Không tìm thấy config online cho '{voice_name}', dùng template chuẩn: {template_json}")
                shutil.copy2(template_json, json_path)
            else:
                raise e

    if not os.path.exists(onnx_path):
        onnx_url = f"https://nghitts.app/api/model/{encoded_name}.onnx"
        print(f"📥 Đang tải model ONNX cho giọng '{voice_name}' (khoảng ~60MB)...")
        _download_file(onnx_url, onnx_path)
        print(f"✅ Model '{voice_name}' đã tải về máy thành công!")

    # Step 3: Tự động sao lưu lên Google Drive nếu Drive chưa có file này
    if drive_models_dir and os.path.exists(onnx_path) and os.path.exists(json_path):
        drive_onnx = drive_models_dir / onnx_file
        drive_json = drive_models_dir / json_file
        try:
            if not drive_json.exists() or drive_json.stat().st_size != os.path.getsize(json_path):
                shutil.copy2(json_path, str(drive_json))
            if not drive_onnx.exists() or drive_onnx.stat().st_size != os.path.getsize(onnx_path):
                print(f"🚀 Tự động sao lưu model '{voice_name}' lên Google Drive: {drive_onnx}...")
                shutil.copy2(onnx_path, str(drive_onnx))
        except Exception as e:
            print(f"⚠️ Không thể tự động sao lưu model lên Drive: {e}")

    return onnx_path, json_path

def sync_voices_to_gdrive(voice_names: Optional[list] = None, download_missing: bool = False) -> Dict[str, Any]:
    """
    Đồng bộ model giọng đọc (.onnx, .json) và âm thanh mẫu (.wav) lên thư mục Google Drive (G:\\My Drive\\CapCutRecapAI\\tts_models).
    Tạo hoặc cập nhật voices_manifest.json quản lý tất cả các giọng đọc đã sao lưu.
    """
    import json
    import shutil
    from datetime import datetime

    gdrive = _get_gdrive_manager()
    if not gdrive:
        return {"success": False, "error": "Không thể kết nối GDriveManager"}

    drive_models_dir = gdrive.get_tts_models_dir()
    drive_samples_dir = gdrive.get_tts_samples_dir()

    target_voices = voice_names or list(NGHITTS_VOICES.keys())
    synced_models = []
    synced_samples = []
    skipped_models = []
    manifest_entries = {}

    for v_name in target_voices:
        resolved = resolve_nghitts_voice(v_name)
        meta = NGHITTS_VOICES.get(resolved, {})
        slug = meta.get("slug") or _voice_to_ascii_filename(resolved)
        onnx_file = f"{slug}.onnx"
        json_file = f"{slug}.onnx.json"
        sample_file = f"sample_{slug}.wav"

        local_onnx = os.path.join(BASE_MODEL_DIR, onnx_file)
        local_json = os.path.join(BASE_MODEL_DIR, json_file)
        drive_onnx = drive_models_dir / onnx_file
        drive_json = drive_models_dir / json_file
        drive_sample = drive_samples_dir / sample_file

        # Nếu người dùng yêu cầu download_missing và local chưa có -> tải về
        if download_missing and not os.path.exists(local_onnx):
            try:
                ensure_model_files(resolved)
            except Exception as e:
                print(f"⚠️ Lỗi tải model {resolved}: {e}")

        # Đồng bộ model ONNX & JSON config
        if os.path.exists(local_onnx) and os.path.exists(local_json):
            model_synced = False
            if not drive_onnx.exists() or drive_onnx.stat().st_size != os.path.getsize(local_onnx):
                shutil.copy2(local_onnx, str(drive_onnx))
                model_synced = True
            if not drive_json.exists() or drive_json.stat().st_size != os.path.getsize(local_json):
                shutil.copy2(local_json, str(drive_json))
                model_synced = True

            synced_models.append({
                "voice": resolved,
                "slug": slug,
                "file": onnx_file,
                "is_new": model_synced,
                "size_mb": round(os.path.getsize(local_onnx) / (1024 * 1024), 2)
            })
        elif drive_onnx.exists():
            synced_models.append({
                "voice": resolved,
                "slug": slug,
                "file": onnx_file,
                "is_new": False,
                "size_mb": round(drive_onnx.stat().st_size / (1024 * 1024), 2)
            })
        else:
            skipped_models.append(resolved)

        # Đồng bộ File âm thanh mẫu (.wav) - chỉ tạo nếu model có sẵn hoặc người dùng bật download_missing
        try:
            sample_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data", "tts_samples")
            local_sample_file = os.path.join(sample_dir, sample_file)
            if os.path.exists(local_sample_file) or drive_sample.exists() or os.path.exists(local_onnx) or drive_onnx.exists() or download_missing:
                sample_path = get_voice_sample_audio_path(resolved)
                if os.path.exists(sample_path):
                    if not drive_sample.exists() or drive_sample.stat().st_size != os.path.getsize(sample_path):
                        shutil.copy2(sample_path, str(drive_sample))
            if drive_sample.exists():
                synced_samples.append({
                    "voice": resolved,
                    "slug": slug,
                    "file": sample_file,
                    "size_kb": round(drive_sample.stat().st_size / 1024, 1)
                })
        except Exception as e:
            print(f"⚠️ Lỗi xử lý sample audio cho {resolved}: {e}")

        manifest_entries[resolved] = {
            **meta,
            "local_model_exists": os.path.exists(local_onnx),
            "drive_model_exists": drive_onnx.exists(),
            "drive_sample_exists": drive_sample.exists(),
            "onnx_filename": onnx_file,
            "sample_filename": sample_file,
            "last_synced": datetime.now().isoformat()
        }

    # Xuất file manifest quản lý model trên Drive
    manifest_path = drive_models_dir / "voices_manifest.json"
    manifest_data = {
        "updated_at": datetime.now().isoformat(),
        "storage_mode": gdrive.mode,
        "mount_path": str(gdrive.mount_path),
        "total_voices": len(manifest_entries),
        "synced_models_count": len([e for e in manifest_entries.values() if e["drive_model_exists"]]),
        "synced_samples_count": len([e for e in manifest_entries.values() if e["drive_sample_exists"]]),
        "voices": manifest_entries
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, ensure_ascii=False, indent=2)

    # Ghi thêm bản sao local
    try:
        with open(os.path.join(BASE_MODEL_DIR, "voices_manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return {
        "success": True,
        "mode": gdrive.mode,
        "drive_models_dir": str(drive_models_dir),
        "drive_samples_dir": str(drive_samples_dir),
        "manifest_path": str(manifest_path),
        "synced_models_count": len(synced_models),
        "synced_samples_count": len(synced_samples),
        "synced_models": synced_models,
        "synced_samples": synced_samples,
        "skipped_models": skipped_models
    }



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
    speed: float = 1.0,
    enhance_audio: bool = False,
    noise_scale: Optional[float] = None,
    noise_w: Optional[float] = None
) -> str:
    """
    Generate Vietnamese TTS audio using NGHI-TTS (Piper/VITS) model.
    Sử dụng tham số âm thanh gốc đã huấn luyện của model để đảm bảo giọng ấm, trong trẻo,
    tự nhiên và không bị rè hay vỡ tiếng kim loại.

    :param text: Raw text to convert to speech
    :param voice_name: Name of the voice model
    :param output_path: Destination WAV filepath
    :param speed: Speech speed multiplier
    :param enhance_audio: If True, applies transparent EBU R128 loudness normalization
    :param noise_scale: Optional override for phonetic noise (None uses model's trained prior 0.667)
    :param noise_w: Optional override for phoneme duration (None uses model's trained prior 0.8)
    :return: Absolute path to the generated .wav file
    """
    if not text or not text.strip():
        raise ValueError("Text input cannot be empty.")

    # 1. Clean loanwords, abbreviations & punctuation prosody
    clean_text = clean_vietnamese_pronunciation(text)
    prosody_text = prepare_prosody_punctuation(clean_text)

    # 2. Normalize text (Convert numbers, dates, abbreviations to full Vietnamese text)
    normalizer = _get_normalizer()
    normalized_text = normalizer.normalize(prosody_text)
    import re
    if not re.sub(r'[^\w\sàáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]', '', normalized_text).strip():
        raise ValueError(f"Text '{text}' contains no speakable words after normalization.")

    # 3. Get output filepath
    if not output_path:
        default_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data", "audio")
        os.makedirs(default_dir, exist_ok=True)
        filename = f"nghitts_{voice_name.replace(' ', '_')}_{hash(text) & 0xffffffff}.wav"
        output_path = os.path.join(default_dir, filename)

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 4. Load voice model (cached)
    voice = get_piper_voice(voice_name)

    # 5. Configure speed natively via Piper length_scale and trained noise params
    target_speed = max(0.2, min(5.0, float(speed or 1.0)))
    syn_config_kwargs: Dict[str, Any] = {
        "length_scale": float(1.0 / target_speed)
    }
    if noise_scale is not None:
        syn_config_kwargs["noise_scale"] = float(noise_scale)
    if noise_w is not None:
        syn_config_kwargs["noise_w_scale"] = float(noise_w)

    syn_config = SynthesisConfig(**syn_config_kwargs)

    # 6. Synthesize speech directly into WAV file at native sample rate (22,050 Hz)
    with wave.open(output_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(voice.config.sample_rate)

        for chunk in voice.synthesize(normalized_text, syn_config=syn_config):
            wav_file.writeframes(chunk.audio_int16_bytes)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"Failed to generate audio at {output_path}")

    # 7. Apply transparent mastering only if explicitly requested
    if enhance_audio:
        resolved_name = resolve_nghitts_voice(voice_name)
        gender = NGHITTS_VOICES.get(resolved_name, {}).get("gender", "male")
        output_path = apply_studio_mastering(output_path, gender=gender)

    return output_path

if __name__ == "__main__":
    # Simple CLI test run when executing script directly
    sample_text = "Xin chào, đây là bài thử nghiệm tích hợp NGHI-TTS trực tiếp vào CapCutAPI."
    print(f"Testing NGHI-TTS Service with text: '{sample_text}'")
    out_file = generate_nghitts(sample_text)
    print(f"✅ Generated WAV File: {out_file} ({os.path.getsize(out_file)} bytes)")
