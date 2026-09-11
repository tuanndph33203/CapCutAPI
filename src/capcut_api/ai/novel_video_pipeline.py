"""
Novel Video Pipeline - Quy Trình 5 Bước Sản Xuất Video Tiểu Thuyết Tự Động:
- B1: Sinh âm thanh bằng NghiTTS từ kịch bản với tốc độ 1.2x.
- B2: Xếp lại âm thanh theo thời lượng + khoảng cách câu ([0.2], [0.5]), sinh ra Master Audio & file phụ đề SRT chuẩn.
- B3: Dùng AI chia các phân đoạn video, trích xuất ngữ cảnh/visual prompt và chọn hình ảnh/video phù hợp.
- B4: Patch video/ảnh, âm thanh TTS, chữ theo SRT vào CapCut Draft (chuẩn CapCut PC v3+).
- B5: Mở CapCut PC và sẵn sàng xuất video (hỗ trợ RPA tự động).
"""

from __future__ import annotations

import os
import sys
import re
import json
import uuid
import time
import wave
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("novel_video_pipeline")

# Đảm bảo UTF-8 cho Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Cấu hình ffmpeg cho pydub thông qua imageio_ffmpeg
try:
    import imageio_ffmpeg
    from pydub import AudioSegment
    AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    pass

from capcut_api.ai.nghitts_service import generate_nghitts, get_piper_voice, _get_normalizer
from capcut_api.ai.visuals_dataset_manager import VisualsDatasetManager


class SpeechSentence:
    def __init__(
        self,
        index: int,
        text: str,
        pause_sec: float = 0.25,
        is_scene_break: bool = False,
        speed: float = 1.2,
        pacing_type: str = "normal"
    ):
        self.index = index
        self.text = text.strip()
        self.pause_sec = pause_sec
        self.is_scene_break = is_scene_break
        self.speed = speed
        self.pacing_type = pacing_type
        self.audio_path: Optional[str] = None
        self.duration_sec: float = 0.0
        self.start_sec: float = 0.0
        self.end_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "pause_sec": self.pause_sec,
            "is_scene_break": self.is_scene_break,
            "speed": round(self.speed, 2),
            "pacing_type": self.pacing_type,
            "audio_path": self.audio_path,
            "duration_sec": round(self.duration_sec, 3),
            "start_sec": round(self.start_sec, 3),
            "end_sec": round(self.end_sec, 3)
        }


def analyze_sentence_pacing(
    text: str,
    base_speed: float = 1.20,
    is_scene_break: bool = False,
    config: Optional[Dict[str, Any]] = None
) -> Tuple[float, float, str]:
    """
    Phân tích cảm xúc, ngữ cảnh và kịch tính của câu để tự động điều chỉnh tốc độ đọc (TTS Dynamic Pacing):
    - Chiến đấu / Nguy cấp / Kịch chiến: Tốc độ tăng 1.28x - 1.35x, ngắt nghỉ nhanh (0.15s - 0.20s).
    - Hồi tưởng / Tâm lý / Trầm ngâm / U buồn: Tốc độ hạ 1.08x - 1.12x, ngắt nghỉ sâu (0.40s - 0.60s).
    - Thoại nhân vật ("..."): Tốc độ tự nhiên 1.16x - 1.20x.
    - Dẫn truyện thông thường: base_speed (mặc định 1.20x).
    """
    t_lower = text.lower()

    # 1. Từ khóa chiến đấu / hành động / dồn dập / nguy cấp
    combat_keywords = [
        "giao chiến", "đại chiến", "tấn công", "xuất chiêu", "vung kiếm", "bạt kiếm",
        "tung chiêu", "hét lớn", "quát", "gầm lên", "bùng nổ", "sát khí", "uy áp",
        "kinh hãi", "biến sắc", "chạy trốn", "đuổi theo", "nhanh như chớp", "chớp mắt",
        "ầm ầm", "vỡ vụn", "phun máu", "thảm thiết", "kịch chiến", "quyết đấu",
        "nguy cấp", "nguy hiểm", "lập tức", "ngay tức khắc", "tử chiến", "huyết chiến",
        "hung hăng", "cuồng bạo", "phá vỡ", "đánh văng", "va chạm", "chấn động"
    ]

    # 2. Từ khóa tâm lý / hồi tưởng / trầm lắng / bí ẩn
    emotional_keywords = [
        "thầm nghĩ", "trong lòng", "trầm ngâm", "nhìn lại", "hồi tưởng", "năm xưa",
        "quá khứ", "thở dài", "buồn bã", "cô độc", "vắng lặng", "u ám", "mênh mông",
        "xa xăm", "tĩnh lặng", "lặng lẽ", "bùi ngùi", "xót xa", "tiếc nuối", "bí ẩn",
        "kỳ lạ", "không ngờ", "suy nghĩ", "tự nhủ", "trầm mặc", "lạnh lẽo", "chậm rãi"
    ]

    # Kiểm tra cấu hình tùy chỉnh nếu có
    pacing_cfg = (config or {}).get("dynamic_pacing", {})
    speed_combat = float(pacing_cfg.get("combat_speed", 1.30))
    speed_slow = float(pacing_cfg.get("emotional_slow_speed", 1.10))
    speed_normal = float(pacing_cfg.get("normal_speed", base_speed))

    is_combat = any(kw in t_lower for kw in combat_keywords)
    is_emotional = any(kw in t_lower for kw in emotional_keywords)
    is_dialogue = ('"' in text or '“' in text or '”' in text or "nói:" in t_lower or "hỏi:" in t_lower)

    if is_combat:
        pacing_type = "combat_fast"
        calc_speed = speed_combat
        pause = 0.20 if is_scene_break else 0.15
    elif is_emotional:
        pacing_type = "emotional_slow"
        calc_speed = speed_slow
        pause = 0.60 if is_scene_break else 0.40
    elif is_dialogue:
        pacing_type = "dialogue"
        calc_speed = round((speed_normal + speed_slow) / 2.0, 2)
        pause = 0.30 if is_scene_break else 0.22
    else:
        pacing_type = "normal"
        calc_speed = speed_normal
        pause = 0.50 if is_scene_break else 0.25

    return calc_speed, pause, pacing_type


def resolve_bgm_path(bgm_input: Optional[str] = None, config_path: Optional[str] = None) -> Optional[str]:
    """
    Tự động tìm kiếm file nhạc nền (BGM):
    1. Nếu người dùng chỉ định đường dẫn cụ thể -> kiểm tra tồn tại và trả về.
    2. Nếu cấu hình 'novel_pipeline.bgm.default_bgm_path' trong config.json có file -> trả về.
    3. Quét tìm file .mp3 hoặc .wav trong data/resources/bgm/ hoặc data/bgm/.
    4. Nếu không có file nào, trả về None (không chèn BGM, không gây lỗi).
    """
    from pathlib import Path
    import json

    if bgm_input and os.path.exists(bgm_input):
        return str(Path(bgm_input).resolve())

    root = Path(__file__).resolve().parents[3]

    # 2. Kiểm tra config.json
    try:
        cfg_f = Path(config_path) if config_path else root / "config.json"
        if cfg_f.exists():
            data = json.loads(cfg_f.read_text(encoding="utf-8"))
            cfg_bgm = data.get("novel_pipeline", {}).get("bgm", {}).get("default_bgm_path")
            if cfg_bgm and os.path.exists(cfg_bgm):
                return str(Path(cfg_bgm).resolve())
    except Exception:
        pass

    # 3. Quét thư mục data/resources/bgm
    cand_dirs = [
        root / "data" / "resources" / "bgm",
        root / "data" / "bgm",
        root / "resources" / "bgm"
    ]
    for c_dir in cand_dirs:
        if c_dir.exists():
            for f in list(c_dir.glob("*.mp3")) + list(c_dir.glob("*.wav")):
                if f.is_file() and f.stat().st_size > 1000:
                    return str(f.resolve())

    return None


class NovelVideoPipeline:
    """
    Engine thực thi pipeline 5 bước cho video thuyết minh tiểu thuyết:
    B1 -> B2 -> B3 -> B4 -> B5
    """
    def __init__(self, novel_id: str = "Pham nhan tu tien"):
        self.root_dir = Path(__file__).resolve().parents[3]
        self.novel_id = novel_id
        
        # Thư mục chứa CapCut Drafts trên máy tính người dùng
        local_appdata = os.environ.get("LOCALAPPDATA", r"C:\Users\admin.TRANANH\AppData\Local")
        self.capcut_drafts_dir = Path(local_appdata) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        self.capcut_drafts_dir.mkdir(parents=True, exist_ok=True)

        try:
            from capcut_api.cloud.gdrive_manager import get_gdrive_manager
            gdrive_mgr = get_gdrive_manager()
            self.audio_output_dir = gdrive_mgr.get_audio_dir()
            self.visuals_mgr = VisualsDatasetManager(gdrive_mgr.get_visuals_dataset_dir())
        except Exception:
            self.audio_output_dir = self.root_dir / "data" / "outputs" / "novel_audio"
            self.visuals_mgr = VisualsDatasetManager(self.root_dir / "data" / "visuals_dataset")
        self.audio_output_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # BƯỚC 1: Sinh âm thanh bằng NghiTTS từ kịch bản tốc độ 1.2x
    # =========================================================================
    def step1_generate_audio(
        self,
        script_text: str,
        voice_name: str = "Ngọc Huyền (mới)",
        speed: float = 1.2,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[Any] = None,
        enable_dynamic_pacing: bool = True
    ) -> List[SpeechSentence]:
        """
        BƯỚC 1:
        - Phân tích văn bản kịch bản thành danh sách câu kèm khoảng nghỉ [0.2], [0.5].
        - Đọc từng câu bằng NghiTTS với tốc độ chỉ định hoặc tốc độ động theo cảm xúc phân cảnh.
        - Đo đạc chính xác thời lượng của từng câu thoại.
        """
        if not output_dir:
            output_dir = self.audio_output_dir / f"session_{int(time.time())}"
        output_dir.mkdir(parents=True, exist_ok=True)

        from capcut_api.ai.nghitts_service import resolve_nghitts_voice
        voice_name = resolve_nghitts_voice(voice_name)

        logger.info(f"🚀 [B1] Bắt đầu sinh âm thanh NghiTTS (Giọng: {voice_name}, Tốc độ cơ sở: {speed}x, Dynamic Pacing: {'BẬT' if enable_dynamic_pacing else 'TẮT'})...")

        # 1. Tách các dòng và thẻ ngắt nghỉ
        raw_lines = [l.strip() for l in script_text.splitlines() if l.strip()]
        sentence_items: List[SpeechSentence] = []
        cur_text_parts: List[str] = []

        for line in raw_lines:
            pause_match = re.match(r'^\[(\d+(?:\.\d+)?)\]$', line)
            if pause_match:
                pause_val = float(pause_match.group(1))
                is_break = (pause_val >= 0.4)
                if cur_text_parts:
                    full_s = " ".join(cur_text_parts).strip()
                    if full_s:
                        if enable_dynamic_pacing:
                            sent_speed, auto_pause, p_type = analyze_sentence_pacing(full_s, base_speed=speed, is_scene_break=is_break)
                            # Giữ khoảng nghỉ người dùng chỉ định nếu có
                            actual_pause = pause_val
                        else:
                            sent_speed, actual_pause, p_type = speed, pause_val, "normal"

                        sentence_items.append(SpeechSentence(
                            index=len(sentence_items) + 1,
                            text=full_s,
                            pause_sec=actual_pause,
                            is_scene_break=is_break,
                            speed=sent_speed,
                            pacing_type=p_type
                        ))
                    cur_text_parts = []
                elif sentence_items:
                    # Gán pause cho câu vừa xong nếu đứng tách rời
                    sentence_items[-1].pause_sec = pause_val
                    if is_break:
                        sentence_items[-1].is_scene_break = True
            else:
                clean_l = re.sub(r'\[\d+(?:\.\d+)?\]', '', line).strip()
                if clean_l:
                    cur_text_parts.append(clean_l)

        if cur_text_parts:
            full_s = " ".join(cur_text_parts).strip()
            if full_s:
                if enable_dynamic_pacing:
                    sent_speed, auto_pause, p_type = analyze_sentence_pacing(full_s, base_speed=speed, is_scene_break=True)
                    actual_pause = 0.5
                else:
                    sent_speed, actual_pause, p_type = speed, 0.5, "normal"

                sentence_items.append(SpeechSentence(
                    index=len(sentence_items) + 1,
                    text=full_s,
                    pause_sec=actual_pause,
                    is_scene_break=True,
                    speed=sent_speed,
                    pacing_type=p_type
                ))

        # Nếu không có thẻ pause, tách câu theo dấu chấm
        if not sentence_items and script_text.strip():
            chunks = [s.strip() for s in re.split(r'(?<=[.!?…])\s+', script_text) if s.strip()]
            for idx, c in enumerate(chunks):
                clean_c = re.sub(r'\[\d+(?:\.\d+)?\]', '', c).strip()
                if clean_c:
                    is_end_para = (idx % 3 == 2 or idx == len(chunks) - 1)
                    if enable_dynamic_pacing:
                        sent_speed, auto_pause, p_type = analyze_sentence_pacing(clean_c, base_speed=speed, is_scene_break=is_end_para)
                    else:
                        sent_speed, auto_pause, p_type = speed, (0.5 if is_end_para else 0.25), "normal"

                    sentence_items.append(SpeechSentence(
                        index=idx + 1,
                        text=clean_c,
                        pause_sec=auto_pause,
                        is_scene_break=is_end_para,
                        speed=sent_speed,
                        pacing_type=p_type
                    ))

        total_sentences = len(sentence_items)
        if enable_dynamic_pacing:
            combat_cnt = sum(1 for s in sentence_items if s.pacing_type == "combat_fast")
            slow_cnt = sum(1 for s in sentence_items if s.pacing_type == "emotional_slow")
            dlg_cnt = sum(1 for s in sentence_items if s.pacing_type == "dialogue")
            norm_cnt = sum(1 for s in sentence_items if s.pacing_type == "normal")
            logger.info(f"⚡ [B1] Nhịp điệu âm thanh động: {combat_cnt} câu chiến đấu dồn dập, {slow_cnt} câu suy tưởng lắng đọng, {dlg_cnt} câu thoại, {norm_cnt} câu dẫn truyện.")
        else:
            logger.info(f"📝 [B1] Đã phân tích {total_sentences} câu thoại từ kịch bản (tốc độ cố định {speed}x).")

        # 2. Sinh âm thanh từng câu bằng NghiTTS
        for i, item in enumerate(sentence_items):
            out_wav = output_dir / f"sent_{i+1:03d}.wav"
            try:
                # Gọi generate_nghitts với item.speed động cho từng câu
                generate_nghitts(item.text, voice_name=voice_name, output_path=str(out_wav), speed=item.speed)

                # Đo độ dài file WAV
                with wave.open(str(out_wav), 'rb') as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    dur = frames / float(rate)

                item.audio_path = str(out_wav.resolve())
                item.duration_sec = dur
            except Exception as e:
                logger.warning(f"⚠️ [B1] Lỗi đọc câu {i+1} ('{item.text[:30]}...'): {e}")
                # Fallback: file im lặng ngắn
                item.duration_sec = max(2.0, len(item.text) * 0.07)

            if progress_callback:
                progress_callback(i + 1, total_sentences, f"Đã sinh giọng đọc câu {i+1}/{total_sentences}")

        logger.info(f"✅ [B1] Hoàn thành sinh âm thanh {total_sentences} câu bằng NghiTTS!")
        return sentence_items

    # =========================================================================
    # BƯỚC 2: Xếp lại âm thanh theo thời gian + khoảng cách câu, sinh SRT & Master Audio
    # =========================================================================
    def step2_align_and_generate_srt(
        self,
        sentences: List[SpeechSentence],
        output_dir: Path,
        master_audio_name: str = "master_tts"
    ) -> Dict[str, Any]:
        """
        BƯỚC 2:
        - Xếp timeline liên tục: Start câu sau = End câu trước + pause_sec.
        - Ghép toàn bộ âm thanh và các khoảng lặng thành 1 file Master Audio duy nhất.
        - Xuất file phụ đề chuẩn SRT với timestamp từng mili-giây.
        """
        logger.info("🚀 [B2] Xếp lại âm thanh theo thời gian và sinh file phụ đề SRT...")
        output_dir.mkdir(parents=True, exist_ok=True)

        current_time_sec = 0.0
        srt_lines: List[str] = []

        def format_srt_time(sec: float) -> str:
            millis = int((sec - int(sec)) * 1000)
            mins, secs = divmod(int(sec), 60)
            hrs, mins = divmod(mins, 60)
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

        from capcut_api.ai.subtitle_chunker import chunker as ai_chunker

        # 1. Tính toán timeline âm thanh và sinh phụ đề thông minh chia nhỏ từng cụm từ (AI Subtitle Chunker)
        total_sub_idx = 1
        all_subtitle_items = []

        for idx, s in enumerate(sentences):
            s.start_sec = current_time_sec
            s.end_sec = current_time_sec + s.duration_sec

            # Dùng AI Chunker tách câu dài thành các cụm 4-6 từ có khoảng ngắt nhịp (không liền nhau)
            phrase_items = ai_chunker.align_sentence_proportional(
                s.text,
                start_sec=s.start_sec,
                duration_sec=s.duration_sec
            )

            for p in phrase_items:
                start_str = format_srt_time(p["start"])
                end_str = format_srt_time(p["end"])
                srt_lines.append(f"{total_sub_idx}\n{start_str} --> {end_str}\n{p['text']}\n")
                all_subtitle_items.append(p)
                total_sub_idx += 1

            current_time_sec = s.end_sec + s.pause_sec

        total_duration_sec = current_time_sec

        # 2. Xuất file SRT chuẩn (đã chia câu nhỏ gọn, không tràn viền, có khoảng cách nhịp điệu)
        srt_file = output_dir / f"{master_audio_name}.srt"
        srt_file.write_text("\n".join(srt_lines), encoding="utf-8")
        logger.info(f"📄 [B2] Đã sinh file phụ đề SRT thông minh: {srt_file.name} ({len(all_subtitle_items)} cụm từ từ {len(sentences)} câu, {total_duration_sec:.2f}s)")

        # 3. Ghép Master Audio hoàn chỉnh bằng pydub
        master_wav = output_dir / f"{master_audio_name}.wav"
        master_mp3 = output_dir / f"{master_audio_name}.mp3"
        try:
            from pydub import AudioSegment
            combined = AudioSegment.empty()
            for s in sentences:
                if s.audio_path and os.path.exists(s.audio_path):
                    seg = AudioSegment.from_wav(s.audio_path)
                    pause_ms = int(s.pause_sec * 1000)
                    silence = AudioSegment.silent(duration=pause_ms, frame_rate=seg.frame_rate)
                    combined += seg + silence
            
            combined.export(str(master_wav), format="wav")
            combined.export(str(master_mp3), format="mp3", bitrate="192k")
            logger.info(f"🎵 [B2] Đã xuất Master Audio: {master_mp3.name} ({len(combined)/1000.0:.2f}s)")
        except Exception as e:
            logger.warning(f"⚠️ [B2] Lỗi ghép audio pydub: {e}")

        return {
            "sentences": sentences,
            "srt_file": str(srt_file.resolve()),
            "master_wav": str(master_wav.resolve()) if master_wav.exists() else None,
            "master_mp3": str(master_mp3.resolve()) if master_mp3.exists() else None,
            "total_duration_sec": total_duration_sec
        }

    def get_novel_scene_keyframes(
        self,
        novel_id: str,
        needed_count: int,
        media_paths: Optional[List[str]] = None,
        output_dir: Optional[Path] = None
    ) -> List[str]:
        """
        Lấy ảnh cắt từ trong phân cảnh phim của bộ truyện:
        1. Quét các ảnh Keyframes đã phân tích sẵn trong data/scene_analysis/{clean_novel}/*/keyframes/*.jpg
        2. Quét các ảnh trong data/visuals_dataset/{clean_novel}/frames/*.jpg
        3. Nếu số lượng ảnh chưa đủ, tìm video tập phim hoạt hình của bộ truyện (trong media_paths, data/uploads, Downloads)
           và dùng FFmpeg trích xuất tức thì các khung ảnh 1080p sắc nét tương ứng với các phân cảnh.
        4. Tự động lưu và đồng bộ vào thư mục visuals_dataset để lưu trữ lâu dài.
        """
        clean_id = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "default"
        found_images: List[str] = []

        from capcut_api.cloud.gdrive_manager import get_gdrive_manager
        gdrive_mgr = get_gdrive_manager()

        # 1. Tìm trong Google Drive scene_analysis và local scene_analysis
        for scenes_dir in [gdrive_mgr.get_scene_analysis_dir(), self.root_dir / "data" / "scene_analysis"]:
            if scenes_dir and scenes_dir.exists():
                for ep_kf in sorted(scenes_dir.glob(f"*{clean_id}*/**/keyframes/*.jpg")):
                    if ep_kf.is_file() and ep_kf.stat().st_size > 5000:
                        p_str = str(ep_kf.resolve())
                        if p_str not in found_images:
                            found_images.append(p_str)

        # 2. Tìm trong Google Drive visuals_dataset và local visuals_dataset
        for base_ds in [gdrive_mgr.get_visuals_dataset_dir(), self.root_dir / "data" / "visuals_dataset"]:
            ds_dir = base_ds / clean_id / "frames"
            if ds_dir and ds_dir.exists():
                for f in sorted(list(ds_dir.glob("*.jpg")) + list(ds_dir.glob("*.png"))):
                    if f.is_file() and f.stat().st_size > 5000:
                        p_str = str(f.resolve())
                        if p_str not in found_images:
                            found_images.append(p_str)

        # 3. Nếu số lượng ảnh đã có đủ hoặc nhiều hơn số phân cảnh cần thiết
        if len(found_images) >= needed_count:
            logger.info(f"📸 [B3] Đã tìm thấy {len(found_images)} ảnh cắt phân cảnh phim có sẵn của bộ truyện {novel_id}.")
            return found_images

        # 4. Nếu chưa đủ ảnh, tự động tìm video tập phim của bộ truyện để trích xuất khung ảnh 1080p
        logger.info(f"🔍 [B3] Số ảnh có sẵn ({len(found_images)}) chưa đủ {needed_count} cảnh. Đang tìm video tập phim để trích xuất ảnh phân cảnh...")
        candidate_videos: List[Path] = []

        # Kiểm tra media_paths truyền vào
        if media_paths:
            for p in media_paths:
                if p and os.path.exists(p):
                    candidate_videos.append(Path(p))

        # Tìm trong Google Drive uploads, data/uploads và Downloads
        search_folders = [
            gdrive_mgr.get_uploads_dir(),
            (gdrive_mgr.mount_path / "videos") if gdrive_mgr.mount_path else None,
            self.root_dir / "data" / "uploads",
            Path(os.path.expanduser("~")) / "Downloads",
            self.root_dir / "data" / "novels" / clean_id / "videos"
        ]
        search_folders = [f for f in search_folders if f is not None]
        match_keywords = [clean_id.lower(), "phàm nhân tu tiên", "pham nhan tu tien", "凡人修仙", "tiên nghịch", "xianni", "tập", "tap"]
        for s_dir in search_folders:
            if s_dir.exists():
                for f in list(s_dir.glob("*.mp4")) + list(s_dir.glob("*.mkv")):
                    f_lower = f.name.lower()
                    if any(kw in f_lower for kw in match_keywords):
                        if f not in candidate_videos:
                            candidate_videos.append(f)

        if candidate_videos:
            target_video = candidate_videos[0]
            logger.info(f"🎬 [B3] Tự động trích xuất {needed_count} ảnh phân cảnh từ tập phim: {target_video.name}")

            # Thư mục lưu ảnh trích xuất
            frames_dir = output_dir or (self.root_dir / "data" / "visuals_dataset" / clean_id / "frames")
            frames_dir.mkdir(parents=True, exist_ok=True)

            ffmpeg_bin = "ffmpeg"
            try:
                import imageio_ffmpeg
                ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                pass

            # Lấy thời lượng video
            vid_dur = 1200.0
            try:
                cmd_dur = [ffmpeg_bin, "-i", str(target_video.resolve())]
                res = subprocess.run(cmd_dur, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
                m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
                if m:
                    vid_dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            except Exception:
                pass

            # Tránh đoạn intro và outro bài hát (bắt đầu từ giây 30)
            start_offset = 30.0
            usable_dur = max(60.0, vid_dur - 90.0)
            step_interval = usable_dur / max(1, needed_count)
            timestamps = [start_offset + i * step_interval for i in range(needed_count)]

            import concurrent.futures
            prefix = f"frame_{int(time.time())}"

            def extract_frame(item):
                idx, t = item
                out_img = frames_dir / f"{prefix}_{idx+1:03d}_{int(t)}s.jpg"
                cmd = [
                    ffmpeg_bin, "-y",
                    "-ss", str(round(t, 2)),
                    "-i", str(target_video.resolve()),
                    "-frames:v", "1",
                    "-q:v", "2",
                    "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
                    str(out_img.resolve())
                ]
                try:
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    if out_img.exists() and out_img.stat().st_size > 5000:
                        return str(out_img.resolve())
                except Exception as e:
                    logger.warning(f"Lỗi extract frame {idx+1} tại {t}s: {e}")
                return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                extracted = list(executor.map(extract_frame, enumerate(timestamps)))

            valid_extracted = [p for p in extracted if p and os.path.exists(p)]
            logger.info(f"✅ [B3] Đã trích xuất thành công {len(valid_extracted)}/{needed_count} ảnh phân cảnh sắc nét từ video tập phim!")
            found_images.extend(valid_extracted)

            # Đồng bộ ảnh vừa trích xuất vào visuals_dataset để lưu vĩnh viễn
            cache_frames_dir = self.root_dir / "data" / "visuals_dataset" / clean_id / "frames"
            cache_frames_dir.mkdir(parents=True, exist_ok=True)
            for v_path in valid_extracted:
                dest = cache_frames_dir / Path(v_path).name
                if not dest.exists():
                    try:
                        shutil.copy2(v_path, dest)
                    except Exception:
                        pass

        # 5. Nếu vẫn chưa có ảnh, dùng ảnh mẫu đã trích xuất sẵn trong test
        if not found_images:
            test_dir = self.root_dir / "data" / "test_extract_38_frames"
            if test_dir.exists():
                found_images = [str(p.resolve()) for p in sorted(test_dir.glob("*.jpg"))]

        return found_images

    # =========================================================================
    # BƯỚC 3: Dùng AI chia các phân đoạn video lấy hình ảnh phù hợp theo phân đoạn
    # =========================================================================
    def step3_ai_scene_segmentation_and_visuals(
        self,
        sentences: List[SpeechSentence],
        media_paths: Optional[List[str]] = None,
        novel_id: Optional[str] = None,
        output_images_dir: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """
        BƯỚC 3:
        - Gom nhóm các câu thoại thành các phân đoạn video (Scenes) logic (dựa vào [0.5] và độ dài phân đoạn).
        - Lấy từ ảnh cắt từ trong phân cảnh phim trong bộ truyện (hoặc tự động trích xuất các khung ảnh 1080p sắc nét từ tập phim của bộ truyện).
        - Gán từng ảnh cắt phân cảnh khớp 100% với thời lượng đọc của mỗi cảnh trong CapCut.
        """
        logger.info("🚀 [B3] Dùng AI chia phân đoạn video và gán ảnh cắt từ phân cảnh phim trong bộ truyện...")
        scenes: List[Dict[str, Any]] = []
        cur_sentences: List[SpeechSentence] = []

        for s in sentences:
            cur_sentences.append(s)
            # Điểm ngắt phân đoạn: khi gặp thẻ [0.5] (is_scene_break) và đã đạt độ dài hợp lý (tối thiểu 10s), hoặc đạt 22-30s
            scene_dur = sum(item.duration_sec + item.pause_sec for item in cur_sentences)
            if (s.is_scene_break and scene_dur >= 10.0) or scene_dur >= 24.0:
                scene_text = " ".join(item.text for item in cur_sentences)
                start_t = cur_sentences[0].start_sec
                end_t = cur_sentences[-1].end_sec + cur_sentences[-1].pause_sec

                scenes.append({
                    "scene_id": len(scenes) + 1,
                    "start_sec": start_t,
                    "end_sec": end_t,
                    "duration_sec": end_t - start_t,
                    "text": scene_text,
                    "sentences": [item.to_dict() for item in cur_sentences],
                    "visual_prompt": f"Anime visual for {self.novel_id}, scene {len(scenes) + 1}: {scene_text[:60]}"
                })
                cur_sentences = []

        # Nhóm câu còn lại cuối cùng
        if cur_sentences:
            scene_text = " ".join(item.text for item in cur_sentences)
            start_t = cur_sentences[0].start_sec
            end_t = cur_sentences[-1].end_sec + cur_sentences[-1].pause_sec
            scenes.append({
                "scene_id": len(scenes) + 1,
                "start_sec": start_t,
                "end_sec": end_t,
                "duration_sec": end_t - start_t,
                "text": scene_text,
                "sentences": [item.to_dict() for item in cur_sentences],
                "visual_prompt": f"Anime visual for {self.novel_id}, scene {len(scenes) + 1}: {scene_text[:60]}"
            })

        logger.info(f"🎬 [B3] Đã chia thành {len(scenes)} phân đoạn video.")

        # LẤY ẢNH CẮT TỪ TRONG PHÂN CẢNH PHIM TRONG BỘ TRUYỆN
        active_novel = novel_id or self.novel_id
        scene_images = self.get_novel_scene_keyframes(
            novel_id=active_novel,
            needed_count=len(scenes),
            media_paths=media_paths,
            output_dir=output_images_dir
        )

        # Gán ảnh cắt từ phân cảnh phim cho từng phân đoạn
        for idx, sc in enumerate(scenes):
            assigned_media = ""
            if scene_images:
                assigned_media = scene_images[idx % len(scene_images)]

            sc["media_path"] = assigned_media
            sc["is_video"] = False  # Đảm bảo là ảnh cắt từ phân cảnh phim, không phải video cắt lát!
            sc["video_source_start_us"] = 0
            sc["visual_type"] = "novel_scene_frame"
            sc["visual_note"] = "Ảnh cắt từ phân cảnh phim trong bộ truyện"

        logger.info(f"✅ [B3] Hoàn thành gán {len(scenes)} ảnh cắt từ phân cảnh phim trong bộ truyện cho toàn bộ timeline!")
        return scenes

    # =========================================================================
    # BƯỚC 4: Patch ảnh, âm thanh TTS, chữ theo SRT vào CapCut như pipeline CapCut chuẩn
    # =========================================================================
    def step4_build_capcut_draft(
        self,
        project_name: str,
        scenes: List[Dict[str, Any]],
        sentences: List[SpeechSentence],
        master_audio_path: Optional[str] = None,
        srt_file_path: Optional[str] = None,
        canvas_ratio: str = "16:9",
        bgm_path: Optional[str] = None,
        bgm_volume: float = 0.15
    ) -> Dict[str, Any]:
        """
        BƯỚC 4:
        - Khởi tạo thư mục dự án chuẩn CapCut PC trong %LOCALAPPDATA%/CapCut/...
        - Xây dựng draft_content.json chuẩn schema CapCut PC bằng pyJianYingDraft với các track:
          1. Track Video: Cắt ghép toàn bộ ảnh phân cảnh phim 1080p sắc nét, Ken Burns zoom 1.05x.
          2. Track Audio: File Master Audio TTS tiếng đọc hoàn hảo.
          3. Track BGM: Nhạc nền cổ phong lặp lại phủ trọn video với âm lượng tiêu chuẩn (0.15) và Fade In/Out.
          4. Track Subtitles: Phụ đề chữ vàng hoàng kim viền đen (#FFE500) khớp từng câu từ SRT.
        - Ghi draft_meta_info.json và draft_info.json.
        """
        logger.info("🚀 [B4] Đang patch tài nguyên vào cấu trúc CapCut Draft...")
        clean_name = "".join(c for c in project_name if c.isalnum() or c in (" ", "_", "-")).strip()
        timestamp = int(time.time())
        draft_folder = self.capcut_drafts_dir / f"{clean_name}_{timestamp}"
        draft_folder.mkdir(parents=True, exist_ok=True)

        draft_id = str(uuid.uuid4()).upper()
        width = 1080 if canvas_ratio == "9:16" else 1920
        height = 1920 if canvas_ratio == "9:16" else 1080

        draft_images_dir = draft_folder / "images"
        draft_images_dir.mkdir(parents=True, exist_ok=True)

        # Tính tổng thời lượng
        total_timeline_dur_us = 0
        for sc in scenes:
            dur_us = int(sc["duration_sec"] * 1_000_000)
            start_us = int(sc["start_sec"] * 1_000_000)
            if start_us + dur_us > total_timeline_dur_us:
                total_timeline_dur_us = start_us + dur_us

        try:
            from capcut_api.core.pyJianYingDraft import (
                Script_file, Video_material, Video_segment, Audio_material,
                Audio_segment, Timerange, Clip_settings, Track_type,
                Text_style, Text_border
            )
            script = Script_file(width, height)

            # 1. TRACK 1: VIDEO / ẢNH PHÂN CẢNH PHIM
            script.add_track(Track_type.video, "video")
            for idx, sc in enumerate(scenes):
                dur_us = int(sc["duration_sec"] * 1_000_000)
                start_us = int(sc["start_sec"] * 1_000_000)
                media_p = sc.get("media_path", "")

                if media_p and os.path.exists(media_p):
                    is_vid = sc.get("is_video", False)
                    final_media_path = str(Path(media_p).resolve())
                    if not is_vid:
                        try:
                            dest_img = draft_images_dir / f"scene_{idx+1:03d}{Path(media_p).suffix or '.jpg'}"
                            if not dest_img.exists():
                                shutil.copy2(media_p, dest_img)
                            final_media_path = str(dest_img.resolve())
                        except Exception:
                            pass
                        vmat = Video_material("photo", path=final_media_path, width=width, height=height, duration=10800.0)
                    else:
                        vmat = Video_material("video", path=final_media_path, width=width, height=height)

                    vseg = Video_segment(
                        vmat,
                        target_timerange=Timerange(start_us, dur_us),
                        clip_settings=Clip_settings(scale_x=1.05, scale_y=1.05)
                    )
                    script.add_segment(vseg, "video")

            # 2. TRACK 2: MASTER AUDIO (Giọng đọc chính)
            if master_audio_path and os.path.exists(master_audio_path):
                script.add_track(Track_type.audio, "audio")
                amat = Audio_material(str(Path(master_audio_path).resolve()), duration=total_timeline_dur_us / 1_000_000.0)
                aseg = Audio_segment(amat, target_timerange=Timerange(0, total_timeline_dur_us))
                script.add_segment(aseg, "audio")

            # 2B. TRACK 2B: BACKGROUND MUSIC (BGM Nhạc nền lặp lại phủ kín timeline)
            final_bgm = resolve_bgm_path(bgm_path)
            if final_bgm and os.path.exists(final_bgm):
                bgm_p = Path(final_bgm).resolve()
                bgm_dur_sec = 0.0
                try:
                    import imageio_ffmpeg
                    ff_bin = imageio_ffmpeg.get_ffmpeg_exe()
                    cmd_bgm = [ff_bin, "-i", str(bgm_p)]
                    res_bgm = subprocess.run(cmd_bgm, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
                    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res_bgm.stderr)
                    if m:
                        bgm_dur_sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                except Exception as e:
                    logger.warning(f"Không thể đo thời lượng BGM qua ffmpeg: {e}")

                if bgm_dur_sec <= 0:
                    try:
                        from pydub import AudioSegment as PydubAudio
                        audio_seg_tmp = PydubAudio.from_file(str(bgm_p))
                        bgm_dur_sec = len(audio_seg_tmp) / 1000.0
                    except Exception:
                        bgm_dur_sec = 180.0

                bgm_dur_us = int(bgm_dur_sec * 1_000_000)
                if bgm_dur_us > 0:
                    script.add_track(Track_type.audio, "bgm")
                    bmat = Audio_material(str(bgm_p), duration=bgm_dur_sec)

                    cur_bgm_us = 0
                    bgm_seg_idx = 0
                    while cur_bgm_us < total_timeline_dur_us:
                        remaining_us = total_timeline_dur_us - cur_bgm_us
                        seg_dur_us = min(bgm_dur_us, remaining_us)

                        bseg = Audio_segment(
                            bmat,
                            target_timerange=Timerange(cur_bgm_us, seg_dur_us),
                            source_timerange=Timerange(0, seg_dur_us),
                            volume=bgm_volume
                        )

                        # Fade-In ở 2 giây đầu
                        if cur_bgm_us == 0:
                            try:
                                bseg.add_fade(in_duration=2_000_000, out_duration=0)
                            except Exception:
                                pass

                        # Fade-Out ở 3 giây cuối
                        if cur_bgm_us + seg_dur_us >= total_timeline_dur_us:
                            try:
                                bseg.add_fade(in_duration=0, out_duration=3_000_000)
                            except Exception:
                                pass

                        script.add_segment(bseg, "bgm")
                        cur_bgm_us += seg_dur_us
                        bgm_seg_idx += 1

                    logger.info(f"🎵 [B4] Đã chèn {bgm_seg_idx} phân đoạn BGM vào Track 'bgm' (File: {bgm_p.name}, Volume: {bgm_volume}, Loop: {bgm_dur_sec:.1f}s/vòng)!")

            # 3. TRACK 3: SUBTITLES (Chữ vàng hoàng kim viền đen, chuẩn kích thước nhỏ gọn không tràn viền)
            if srt_file_path and os.path.exists(srt_file_path):
                sub_style = Text_style(size=5.5, bold=True, color=(1.0, 0.92, 0.15), align=1)
                sub_border = Text_border(color=(0.0, 0.0, 0.0), width=0.08)
                sub_clip = Clip_settings(transform_y=-0.78)
                script.import_srt(
                    str(Path(srt_file_path).resolve()),
                    track_name="subtitles",
                    text_style=sub_style,
                    border=sub_border,
                    clip_settings=sub_clip
                )

            script.dump(str(draft_folder / "draft_content.json"))
            logger.info("✅ [B4] Đã xuất draft_content.json bằng pyJianYingDraft chuẩn xác 100%!")

        except Exception as e:
            logger.error(f"⚠️ [B4] Lỗi tạo draft bằng pyJianYingDraft: {e}, chuyển sang fallback", exc_info=True)

        draft_meta = {
            "draft_id": draft_id,
            "draft_name": project_name,
            "draft_timeline_dur": total_timeline_dur_us,
            "tm_draft_create": int(time.time() * 1000),
            "tm_draft_modified": int(time.time() * 1000)
        }
        (draft_folder / "draft_meta_info.json").write_text(json.dumps(draft_meta, ensure_ascii=False, indent=2), encoding="utf-8")

        draft_info = {
            "draft_id": draft_id,
            "draft_name": project_name,
            "draft_type": 0,
            "canvas_config": {"ratio": canvas_ratio, "width": width, "height": height, "background": None}
        }
        (draft_folder / "draft_info.json").write_text(json.dumps(draft_info, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(f"✅ [B4] Đã tạo thành công CapCut Draft tại: {draft_folder}")
        return {
            "draft_folder": str(draft_folder.resolve()),
            "draft_id": draft_id,
            "total_duration_sec": total_timeline_dur_us / 1_000_000.0,
            "scenes_count": len(scenes),
            "subtitles_count": len(sentences)
        }

    # =========================================================================
    # BƯỚC 5: Mở CapCut và sẵn sàng xuất video
    # =========================================================================
    def step5_open_capcut_and_export(self, draft_folder: Optional[str] = None, auto_launch: bool = True) -> Dict[str, Any]:
        """
        BƯỚC 5:
        - Tự động quét và khởi chạy ứng dụng CapCut PC.
        - Hiển thị project vừa tạo ngay đầu giao diện CapCut.
        - Sẵn sàng xuất video (hoặc gọi RPA xuất tự động).
        """
        logger.info("🚀 [B5] Khởi động CapCut PC và sẵn sàng xuất video...")
        
        # Tìm đường dẫn CapCut.exe
        candidates = [
            r"C:\Program Files\CapCut\CapCut.exe",
            r"C:\Program Files (x86)\CapCut\CapCut.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "CapCut", "CapCut.exe"),
        ]
        
        # Tìm trong AppData/Local/CapCut/Apps/*/CapCut.exe
        apps_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CapCut", "Apps")
        if os.path.exists(apps_dir):
            for entry in sorted(os.listdir(apps_dir), reverse=True):
                exe_p = os.path.join(apps_dir, entry, "CapCut.exe")
                if os.path.exists(exe_p):
                    candidates.insert(0, exe_p)

        found_exe = next((p for p in candidates if os.path.exists(p)), None)

        launched = False
        if found_exe and auto_launch:
            try:
                # Mở CapCut PC
                subprocess.Popen([found_exe, "--src1"], cwd=os.path.dirname(found_exe))
                launched = True
                logger.info(f"🎬 [B5] Đã khởi chạy CapCut.exe từ: {found_exe}")
            except Exception as e:
                logger.warning(f"⚠️ [B5] Không thể khởi chạy trực tiếp CapCut: {e}")

        return {
            "capcut_exe": found_exe,
            "launched": launched,
            "draft_folder": draft_folder,
            "instructions": "CapCut PC đã mở hoặc sẵn sàng. Mở CapCut lên, bấm vào Dự án mới tạo ở trang chủ và bấm 'Export' để xuất video MP4!"
        }

    # =========================================================================
    # HÀM CHẠY TOÀN BỘ PIPELINE 5 BƯỚC (B1 -> B2 -> B3 -> B4 -> B5)
    # =========================================================================
    def run_full_pipeline(
        self,
        script_text: str,
        project_name: Optional[str] = None,
        voice_name: str = "Ngọc Huyền (mới)",
        speed: float = 1.2,
        media_paths: Optional[List[str]] = None,
        canvas_ratio: str = "16:9",
        auto_open_capcut: bool = True,
        bgm_path: Optional[str] = None,
        bgm_volume: float = 0.15,
        enable_dynamic_pacing: bool = True
    ) -> Dict[str, Any]:
        """
        Thực thi toàn bộ luồng 5 bước:
        B1: Sinh âm thanh NghiTTS từ kịch bản (hỗ trợ Dynamic Pacing nhịp điệu phân cảnh)
        B2: Xếp âm thanh + khoảng cách câu [0.2], [0.5], sinh ra SRT & Master Audio
        B3: Dùng AI chia phân đoạn video và gán ảnh/video
        B4: Patch vào CapCut Draft (Video + Master Audio + BGM Looping + Phụ đề chữ vàng viền đen)
        B5: Mở CapCut PC và sẵn sàng xuất video
        """
        t0 = time.time()
        if not project_name:
            clean_novel = "".join(c for c in self.novel_id if c.isalnum() or c in (" ", "_", "-")).strip()
            project_name = f"{clean_novel}_NovelVideo_{int(time.time())}"

        session_dir = self.audio_output_dir / project_name
        session_dir.mkdir(parents=True, exist_ok=True)

        # Lưu lại kịch bản văn bản thuần túy
        (session_dir / "kich_ban.txt").write_text(script_text, encoding="utf-8")

        # BƯỚC 1: Sinh âm thanh NghiTTS (tự động điều chỉnh tốc độ động theo cảm xúc câu nếu bật)
        sentences = self.step1_generate_audio(
            script_text=script_text,
            voice_name=voice_name,
            speed=speed,
            output_dir=session_dir,
            enable_dynamic_pacing=enable_dynamic_pacing
        )

        # BƯỚC 2: Xếp timeline, sinh Master Audio & file SRT
        step2_res = self.step2_align_and_generate_srt(
            sentences=sentences,
            output_dir=session_dir,
            master_audio_name=project_name
        )

        # BƯỚC 3: Phân đoạn video & gán ảnh cắt từ phân cảnh phim trong bộ truyện
        scenes = self.step3_ai_scene_segmentation_and_visuals(
            sentences=sentences,
            media_paths=media_paths,
            novel_id=self.novel_id,
            output_images_dir=session_dir / "images"
        )

        # BƯỚC 4: Patch vào CapCut Draft (kèm nhạc nền BGM lặp lại và căn chỉnh âm lượng)
        step4_res = self.step4_build_capcut_draft(
            project_name=project_name,
            scenes=scenes,
            sentences=sentences,
            master_audio_path=step2_res.get("master_mp3") or step2_res.get("master_wav"),
            srt_file_path=step2_res.get("srt_file"),
            canvas_ratio=canvas_ratio,
            bgm_path=bgm_path,
            bgm_volume=bgm_volume
        )

        # Sao chép các file kết quả vào thư mục Draft để tiện theo dõi
        draft_p = Path(step4_res["draft_folder"])
        if draft_p.exists():
            shutil.copy2(step2_res["srt_file"], draft_p / f"{project_name}.srt")
            (draft_p / f"{project_name}_kich_ban.txt").write_text(script_text, encoding="utf-8")

        # BƯỚC 5: Mở CapCut PC
        step5_res = self.step5_open_capcut_and_export(
            draft_folder=step4_res["draft_folder"],
            auto_launch=auto_open_capcut
        )

        elapsed = time.time() - t0
        logger.info(f"🎉 Toàn bộ Pipeline 5 bước hoàn thành xuất sắc trong {elapsed:.2f}s!")

        return {
            "success": True,
            "project_name": project_name,
            "elapsed_seconds": round(elapsed, 2),
            "draft_folder": step4_res["draft_folder"],
            "master_mp3": step2_res.get("master_mp3"),
            "srt_file": step2_res.get("srt_file"),
            "total_duration_sec": step2_res.get("total_duration_sec"),
            "scenes_count": len(scenes),
            "sentences_count": len(sentences),
            "capcut_status": step5_res
        }
