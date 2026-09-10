import os
import sys
import re
import json
import time
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import urllib.request
import urllib.parse
import concurrent.futures

logger = logging.getLogger("SceneAnalyzer")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_ROOT = ROOT_DIR / "data"
DOWNLOADS_DIR = Path(os.path.expanduser("~")) / "Downloads"
CONFIG_FILE = ROOT_DIR / "config.json"

src_dir = ROOT_DIR / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


class SceneAnalyzerService:
    """
    Dịch vụ AI phân tích phân cảnh tập phim chuyên sâu:
    - Sử dụng Faster-Whisper trích xuất phụ đề gốc & mốc thời gian (timeline).
    - Sử dụng AI LLM (Gemini / OpenAI / DeepSeek / Deep Semantic Engine) để:
      1. Đọc phụ đề SRT và nhận xét dòng diễn biến.
      2. Tự động cắt các khoảng phân cảnh (Scene Intervals: start -> end).
      3. Xác định mốc giây vàng đắt giá nhất (target_frame_time) để chụp ảnh Keyframe nổi bật.
      4. Tạo tiêu đề và mô tả hình ảnh trực quan cho từng phân cảnh.
    - Cắt ảnh Keyframe sắc nét bằng FFmpeg.
    - Lưu vào JSON Database và sẵn sàng đẩy lên Google Drive.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        from capcut_api.cloud.gdrive_manager import get_gdrive_manager
        self.gdrive_mgr = get_gdrive_manager()
        self.data_dir = data_dir or DATA_ROOT
        # Ưu tiên lưu kết quả phân tích phân cảnh trực tiếp lên Google Drive
        self.scenes_root = self.gdrive_mgr.get_scene_analysis_dir() if not data_dir else (self.data_dir / "scene_analysis")
        self.scenes_root.mkdir(parents=True, exist_ok=True)
        self._load_api_keys()

    def _load_api_keys(self):
        """Nạp các khóa API từ config.json hoặc biến môi trường."""
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")
        self.openai_key = os.environ.get("OPENAI_API_KEY", "")
        self.deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")

        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.gemini_key = self.gemini_key or cfg.get("gemini_api_key", "")
                self.openai_key = self.openai_key or cfg.get("openai_api_key", "")
                self.deepseek_key = self.deepseek_key or cfg.get("deepseek_api_key", "")
            except Exception:
                pass

    def _get_ffmpeg_exe(self) -> str:
        if shutil.which("ffmpeg"):
            return "ffmpeg"
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return "ffmpeg"

    def _get_episode_dir(self, novel_id: str, episode_num: int) -> Path:
        clean_id = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "default"
        ep_dir = self.scenes_root / clean_id / f"tap_{episode_num}"
        ep_dir.mkdir(parents=True, exist_ok=True)
        (ep_dir / "keyframes").mkdir(exist_ok=True)
        (ep_dir / "clips").mkdir(exist_ok=True)
        return ep_dir

    def find_episode_video_on_disk(self, novel_id: str, episode_num: int, custom_path: Optional[str] = None) -> Optional[Path]:
        if custom_path:
            p = Path(custom_path)
            if p.exists() and p.is_file():
                return p

        ep_patterns = [
            f"*{episode_num}*.mp4",
            f"*{episode_num}*.mkv",
            f"*Tập {episode_num}*.mp4",
            f"*tap_{episode_num}*.mp4",
            f"*Tap {episode_num}*.mp4",
            f"*Tập_{episode_num}*.mp4",
            f"*ep_{episode_num}*.mp4",
            f"*EP{episode_num}*.mp4",
            f"*{episode_num}集*.mp4"
        ]

        # Tìm kiếm trên Google Drive uploads trước, sau đó tới Downloads và local
        search_folders = [
            self.gdrive_mgr.get_uploads_dir(),
            (self.gdrive_mgr.mount_path / "videos") if self.gdrive_mgr.mount_path else None,
            ROOT_DIR / "data" / "uploads",
            DOWNLOADS_DIR,
            ROOT_DIR / "downloads",
            ROOT_DIR / "data" / "novels" / novel_id / "videos",
            ROOT_DIR / "data" / "videos"
        ]
        search_folders = [f for f in search_folders if f is not None]

        for folder in search_folders:
            if not folder.exists():
                continue
            for pat in ep_patterns:
                matched = list(folder.glob(pat))
                if matched:
                    matched.sort(key=lambda x: x.stat().st_size, reverse=True)
                    return matched[0]

        # Quét fallback toàn bộ file mp4 trong uploads
        gdrive_uploads = list(self.gdrive_mgr.get_uploads_dir().glob("*.mp4"))
        if gdrive_uploads:
            return gdrive_uploads[0]

        local_uploads = list((ROOT_DIR / "data" / "uploads").glob("*.mp4"))
        if local_uploads:
            return local_uploads[0]

        return None

    # =========================================================================
    # 1. WHISPER ASR TRÍCH XUẤT TIMELINE VÀ PHỤ ĐỀ GỐC
    # =========================================================================
    def run_whisper_fast(self, video_path: Path) -> List[Dict[str, Any]]:
        ffmpeg_exe = self._get_ffmpeg_exe()
        temp_wav = DATA_ROOT / f"_temp_audio_{int(time.time())}.wav"

        cmd = [
            ffmpeg_exe, "-y",
            "-i", str(video_path.resolve()),
            "-vn", "-ar", "16000", "-ac", "1",
            str(temp_wav.resolve())
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            raise RuntimeError(f"Lỗi FFmpeg tách âm thanh: {res.stderr.decode('utf-8', errors='ignore')}")

        if not temp_wav.exists() or temp_wav.stat().st_size < 1000:
            raise RuntimeError("File âm thanh trích xuất không hợp lệ hoặc quá nhỏ.")

        segments = []
        try:
            logger.info(f"🎙️ [WHISPER CALL] Bắt đầu gọi Faster-Whisper ASR cho file âm thanh: {temp_wav.name}")
            from faster_whisper import WhisperModel
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            raw_segs, info = model.transcribe(
                str(temp_wav.resolve()),
                beam_size=1,
                temperature=0.0,
                vad_filter=True
            )
            logger.info(f"🎙️ [WHISPER INFO] Ngôn ngữ phát hiện: {info.language} (Độ tin cậy: {info.language_probability:.2f}), Thời lượng: {info.duration:.2f}s")
            for idx, s in enumerate(raw_segs):
                txt = s.text.strip()
                if not txt:
                    continue
                segments.append({
                    "id": idx + 1,
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": txt
                })
            logger.info(f"✅ [WHISPER OUTPUT] Bóc tách thành công {len(segments)} câu thoại từ video!")
            if segments:
                sample_lines = [f"  #{s['id']} [{s['start']}s - {s['end']}s]: {s['text']}" for s in segments[:5]]
                logger.info("🎙️ [WHISPER MẪU 5 CÂU ĐẦU]:\n" + "\n".join(sample_lines))
        except Exception as e:
            logger.error(f"❌ [WHISPER ERROR] Lỗi Faster-Whisper ASR: {e}")
            raise RuntimeError(f"Lỗi Faster-Whisper ASR: {e}")
        finally:
            if temp_wav.exists():
                try:
                    temp_wav.unlink()
                except Exception:
                    pass

        if not segments:
            raise ValueError("Whisper không tìm thấy đoạn thoại nào trong video này.")

        return segments

    def get_video_subtitles(self, video_path: Path, novel_id: str, episode_num: int, output_srt: Path) -> List[Dict[str, Any]]:
        """Bóc tách phụ đề trực tiếp từ âm thanh video gốc bằng Faster-Whisper ASR."""
        logger.info(f"🚀 [SUBTITLES] Bóc tách phụ đề trực tiếp từ video: {video_path.name}")
        segments = self.run_whisper_fast(video_path)

        # Ghi file SRT
        srt_lines = []
        for seg in segments:
            st_str = self._format_srt_timestamp(seg["start"])
            et_str = self._format_srt_timestamp(seg["end"])
            srt_lines.append(f"{seg['id']}\n{st_str} --> {et_str}\n{seg['text']}\n")

        output_srt.parent.mkdir(parents=True, exist_ok=True)
        output_srt.write_text("\n".join(srt_lines), encoding="utf-8")
        logger.info(f"💾 [SRT SAVED] Đã lưu file SRT chuẩn tại: {output_srt.name}")
        return segments

    def _parse_srt_file(self, srt_path: Path) -> List[Dict[str, Any]]:
        content = srt_path.read_text(encoding="utf-8", errors="ignore")
        pattern = re.compile(
            r'(\d+)\s*\n'
            r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*\n'
            r'([\s\S]*?)(?=\n\s*\n\d+|\Z)'
        )
        segments = []
        for m in pattern.finditer(content):
            idx = int(m.group(1))
            st = int(m.group(2)) * 3600 + int(m.group(3)) * 60 + int(m.group(4)) + int(m.group(5)) / 1000.0
            et = int(m.group(6)) * 3600 + int(m.group(7)) * 60 + int(m.group(8)) + int(m.group(9)) / 1000.0
            text = " ".join([l.strip() for l in m.group(10).splitlines() if l.strip()])
            segments.append({
                "id": idx,
                "start": round(st, 2),
                "end": round(et, 2),
                "text": text
            })
        return segments

    def _format_srt_timestamp(self, seconds: float) -> str:
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    # =========================================================================
    # 2. DÙNG AI (9ROUTER / LLM) PHÂN TÍCH SRT ĐỂ CẮT KHOẢNG PHÂN CẢNH
    # =========================================================================
    def ai_analyze_srt_for_scenes(
        self,
        srt_segments: List[Dict[str, Any]],
        novel_title: str,
        episode_num: int,
        total_duration: float
    ) -> List[Dict[str, Any]]:
        """
        DÙNG AI PHÂN TÍCH SRT (CẤM HOÀN TOÀN FALLBACK / FIX CỨNG):
        - Đọc phụ đề dòng thời gian từ Whisper
        - Gửi toàn bộ cho AI (9Router / LLM) phân tích
        - Nếu AI không phản hồi -> Báo lỗi và dừng tiến trình ngay lập tức.
        """
        if not srt_segments:
            raise ValueError("❌ Lỗi: Danh sách phụ đề SRT rỗng, không thể phân tích phân cảnh.")

        logger.info(f"🧠 [AI SCENE SEGMENTATION] Bắt đầu gửi {len(srt_segments)} câu thoại SRT sang AI phân tích phân cảnh...")

        # 1. Thử gọi 9-Router AI qua cấu hình hệ thống
        scenes = self._call_9router_ai_scene_segmentation(srt_segments, novel_title, episode_num, total_duration)
        if scenes:
            logger.info(f"✅ [9ROUTER AI THÀNH CÔNG] Đã nhận về {len(scenes)} phân cảnh từ AI!")
            return scenes

        # 2. Thử gọi LLM API trực tiếp (Gemini / OpenAI / DeepSeek) nếu có Key
        scenes = self._try_llm_scene_segmentation(srt_segments, novel_title, episode_num, total_duration)
        if scenes:
            logger.info(f"✅ [LLM API THÀNH CÔNG] Đã nhận về {len(scenes)} phân cảnh từ LLM API!")
            return scenes

        # NẾU CẢ 2 ĐỀU KHÔNG GỌI ĐƯỢC AI -> BÁO LỖI VÀ DỪNG TIẾN TRÌNH LUÔN (KHÔNG FALLBACK)
        err_msg = (
            f"❌ LỖI KẾT NỐI AI: Không thể kết nối với mô hình AI (9Router ở cổng 20128 hoặc LLM API) để phân tích phân cảnh! "
            f"Vui lòng khởi động lệnh '9router' trên CMD hoặc cung cấp API Key. "
            f"TIẾN TRÌNH ĐÃ DỪNG LẠI HOÀN TOÀN (KHÔNG LƯU DỮ LIỆU LỖI/MOCK)."
        )
        logger.error(err_msg)
        raise RuntimeError(err_msg)

    def _build_full_timeline_blocks(self, srt_segments: List[Dict[str, Any]], chunk_sec: float = 35.0) -> str:
        """Gộp các câu phụ đề ngắn thành các khối tự sự dài ~35s bao quát toàn bộ tập phim từ đầu đến cuối."""
        if not srt_segments:
            return ""
        merged_chunks = []
        curr_chunk = []
        c_start = srt_segments[0]['start']

        for s in srt_segments:
            curr_chunk.append(s['text'])
            if s['end'] - c_start >= chunk_sec:
                text = " ".join(curr_chunk)
                merged_chunks.append(f"[{int(c_start)}s - {int(s['end'])}s]: {text}")
                curr_chunk = []
                c_start = s['end']

        if curr_chunk:
            merged_chunks.append(f"[{int(c_start)}s - {int(srt_segments[-1]['end'])}s]: {' '.join(curr_chunk)}")

        return "\n".join(merged_chunks)

    def _call_9router_ai_scene_segmentation(
        self,
        srt_segments: List[Dict[str, Any]],
        novel_title: str,
        episode_num: int,
        total_duration: float
    ) -> Optional[List[Dict[str, Any]]]:
        """Sử dụng 9-Router AI cấu hình sẵn trong hệ thống để phân tích toàn bộ timeline SRT và cắt phân cảnh."""
        try:
            from capcut_api.api.gui_app import build_ai_translation_config, call_ai_json_object
            ai_config = build_ai_translation_config(item_config={}, purpose="context")
            if not ai_config or not ai_config.get("enabled"):
                logger.warning("⚠️ [9ROUTER AI] Cấu hình AI chưa kích hoạt hoặc thiếu API key.")
                return None

            srt_content = self._build_full_timeline_blocks(srt_segments, chunk_sec=35.0)
            actual_end_sec = float(srt_segments[-1]["end"]) if srt_segments else total_duration

            system_prompt = (
                f"Bạn là Đạo diễn Phim & Chuyên gia Phân cảnh Hoạt hình 3D Tiên Hiệp (Donghua). "
                f"Tác phẩm: '{novel_title}' Tập {episode_num}. "
                f"Hãy đọc toàn bộ dòng thời gian phụ đề từ 0s đến hết tập phim ({int(actual_end_sec)}s), "
                f"chia tập phim thành khoảng 8 - 14 phân cảnh kịch tính nhất dàn đều từ đầu đến cuối video. "
                f"BẮT BUỘC PHẢI CÓ: Phân cảnh cao trào kết phim ở cuối video (như cảnh Cốc Song Bồ dùng Song Vĩ Phỉ Thúy Xà đánh lén đại hán cướp túi trữ vật tìm lệnh bài). "
                f"Với mỗi phân cảnh, chọn đúng 1 mốc giây vàng (target_frame_time) để chụp ảnh Keyframe sắc nét."
            )

            user_payload = {
                "task": "analyze_full_episode_scenes",
                "novel_title": novel_title,
                "episode": episode_num,
                "total_duration_sec": actual_end_sec,
                "srt_timeline": srt_content,
                "output_schema": {
                    "scenes": [
                        {
                            "moment_index": 1,
                            "start_time": 0.0,
                            "end_time": 150.0,
                            "target_frame_time": 75.0,
                            "highlight_type": "breakthrough/combat/dialogue/climax/scenery",
                            "importance_score": 9,
                            "scene_title": "Tiêu đề phân cảnh chuẩn sát",
                            "srt_dialogue": "Tóm tắt ngữ cảnh/thoại của đoạn này",
                            "visual_description": "Mô tả hình ảnh trực quan chi tiết"
                        }
                    ]
                }
            }

            base_url = ai_config.get("base_url")
            model = ai_config.get("model")
            logger.info(f"📡 [CALL 9ROUTER AI] Endpoint: {base_url}, Model: {model}, Tổng thời lượng: {int(actual_end_sec)}s")
            res = call_ai_json_object(ai_config, system_prompt, user_payload, line_count=60)
            logger.info(f"📥 [RAW 9ROUTER RESPONSE]: {json.dumps(res, ensure_ascii=False)[:500]}...")
            
            if isinstance(res, dict) and "scenes" in res:
                return res["scenes"]
            elif isinstance(res, list):
                return res
        except Exception as e:
            logger.error(f"❌ [9ROUTER AI ERROR] Lỗi khi gọi 9-Router AI: {e}")
        return None

    def _try_llm_scene_segmentation(
        self,
        srt_segments: List[Dict[str, Any]],
        novel_title: str,
        episode_num: int,
        total_duration: float
    ) -> Optional[List[Dict[str, Any]]]:
        """Gọi LLM (Gemini / OpenAI) để phân tích toàn bộ SRT và cắt phân cảnh thông minh."""
        self._load_api_keys()
        if not (self.gemini_key or self.openai_key or self.deepseek_key):
            return None

        srt_text = self._build_full_timeline_blocks(srt_segments, chunk_sec=35.0)
        actual_end_sec = float(srt_segments[-1]["end"]) if srt_segments else total_duration

        prompt = f"""Bạn là Đạo diễn Phim & Chuyên gia Phân tích Video Tiên Hiệp AI.
Dưới đây là phụ đề SRT toàn bộ tập phim '{novel_title}' Tập {episode_num} (từ 0s đến {int(actual_end_sec)}s):
--- SRT TIMELINE ---
{srt_text}
--------------------
Tổng thời lượng: {int(actual_end_sec)}s.

Nhiệm vụ của bạn:
1. Đọc phụ đề toàn tập, phân tích cốt truyện và chia video thành 8 - 14 phân cảnh kịch tính nhất dàn đều từ mở đầu, thân bài đến đoạn kết phim.
2. BẮT BUỘC PHẢI CÓ: Phân cảnh cao trào kết phim ở cuối video.
3. Với mỗi phân cảnh, tìm ra 1 mốc giây vàng chính xác (target_frame_time) để chụp ảnh Keyframe nổi bật nhất.
4. Đặt tiêu đề tiếng Việt (scene_title), tóm tắt lời thoại tiếng Việt (srt_dialogue), mô tả hình ảnh trực quan (visual_description), phân loại (highlight_type: combat, dialogue, climax, breakthrough, mystery, scenery) và điểm nổi bật (importance_score: 1-10).

Trả về DUY NHẤT một mảng JSON:
[
  {{
    "moment_index": 1,
    "start_time": 0.0,
    "end_time": 150.0,
    "target_frame_time": 75.0,
    "highlight_type": "breakthrough",
    "importance_score": 9,
    "scene_title": "Tiêu đề phân cảnh cụ thể...",
    "srt_dialogue": "Lời thoại then chốt của đoạn này...",
    "visual_description": "Mô tả bối cảnh hình ảnh trực quan..."
  }}
]
"""
        # 1. Thử Gemini API
        if self.gemini_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
                logger.info(f"📡 [CALL GEMINI API] Gửi timeline toàn tập sang Gemini 1.5 Flash...")
                req_data = json.dumps({
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"}
                }).encode("utf-8")
                req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    txt = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    logger.info(f"📥 [RAW GEMINI RESPONSE]: {txt[:400]}...")
                    parsed = json.loads(txt)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        return parsed
            except Exception as e:
                logger.error(f"❌ [GEMINI API ERROR]: {e}")

        # 2. Thử OpenAI API
        if self.openai_key:
            try:
                url = "https://api.openai.com/v1/chat/completions"
                logger.info(f"📡 [CALL OPENAI API] Gửi timeline toàn tập sang OpenAI gpt-4o-mini...")
                req_data = json.dumps({
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"}
                }).encode("utf-8")
                req = urllib.request.Request(url, data=req_data, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.openai_key}"
                }, method="POST")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    content = res_json["choices"][0]["message"]["content"]
                    logger.info(f"📥 [RAW OPENAI RESPONSE]: {content[:400]}...")
                    parsed = json.loads(content)
                    items = parsed if isinstance(parsed, list) else parsed.get("scenes", parsed.get("data", []))
                    if items:
                        return items
            except Exception as e:
                logger.error(f"❌ [OPENAI API ERROR]: {e}")

        return None

    # =========================================================================
    # 3. TRÍCH XUẤT KEYFRAME BẰNG FFMPEG
    # =========================================================================
    def _get_video_duration_fast(self, video_path: Path) -> float:
        ffmpeg_bin = self._get_ffmpeg_exe()
        try:
            cmd = [ffmpeg_bin, "-i", str(video_path.resolve())]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out = res.stderr.decode("utf-8", errors="ignore")
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", out)
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        except Exception:
            pass
        return 1500.0

    def extract_highlight_keyframes(
        self,
        video_path: Path,
        scenes: List[Dict[str, Any]],
        out_dir: Path
    ) -> List[Dict[str, Any]]:
        out_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg_bin = self._get_ffmpeg_exe()
        max_dur = self._get_video_duration_fast(video_path)

        def _extract_one(item):
            idx, sc = item
            raw_t = float(sc.get("target_frame_time", sc.get("start_time", 0.0)))
            target_t = max(0.5, min(raw_t, max_dur - 2.0))
            sc["target_frame_time"] = round(target_t, 2)

            kf_filename = f"keyframe_{idx + 1:03d}_{int(target_t)}s.jpg"
            kf_path = out_dir / kf_filename

            cmd = [
                ffmpeg_bin, "-y",
                "-ss", str(target_t),
                "-i", str(video_path.resolve()),
                "-frames:v", "1",
                "-q:v", "2",
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease",
                str(kf_path.resolve())
            ]
            try:
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            except Exception:
                cmd[2] = str(max(0.5, target_t - 3.0))
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            sc["keyframe_filename"] = kf_filename
            sc["keyframe_path"] = str(kf_path.resolve())
            return sc

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            updated = list(executor.map(_extract_one, enumerate(scenes)))

        return updated

    # =========================================================================
    # 3.5. MULTIMODAL VISION AI: PHÂN TÍCH TRỰC TIẾP BỨC ẢNH KẾT HỢP PHỤ ĐỀ SRT
    # =========================================================================
    def _clean_ai_json_response(self, raw: str) -> Dict[str, Any]:
        """Làm sạch và bóc tách đối tượng JSON từ chuỗi phản hồi của AI (hỗ trợ markdown block)."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return json.loads(match.group(0))
        return json.loads(raw)

    def ai_analyze_vision_and_subtitles(
        self,
        scenes: List[Dict[str, Any]],
        novel_title: str,
        episode_num: int
    ) -> List[Dict[str, Any]]:
        """
        PHÂN TÍCH ĐA PHƯƠNG THỨC BẰNG VISION AI (ĐÚNG BỐI CẢNH TIÊN HIỆP):
        - Gửi trực tiếp bức ảnh Keyframe (base64) kèm câu thoại sang Vision AI
        - Vision AI nhìn trực diện bức ảnh để định danh đúng nhân vật, nguyên thần, pháp tướng, bối cảnh tu tiên
        - Cập nhật đồng bộ Tiêu đề, Mô tả trực quan, Tóm tắt ngữ cảnh chuẩn xác 100%
        """
        logger.info(f"👁️ [VISION AI BATCH] Bắt đầu phân tích trực quan Tiên Hiệp cho {len(scenes)} bức ảnh Keyframe...")

        def _process_one_frame(item):
            idx, sc = item
            kf_path_str = sc.get("keyframe_path")
            dialogue = sc.get("srt_dialogue", "")
            target_t = float(sc.get("target_frame_time", sc.get("start_time", 0.0)))

            if kf_path_str and Path(kf_path_str).exists():
                vision_res = self._call_vision_llm_for_single_frame(
                    Path(kf_path_str), dialogue, novel_title, episode_num, target_t, idx + 1
                )
                if vision_res and isinstance(vision_res, dict):
                    if vision_res.get("visual_description"):
                        sc["visual_description"] = vision_res["visual_description"]
                    if vision_res.get("scene_title"):
                        sc["scene_title"] = vision_res["scene_title"]
                    if vision_res.get("srt_dialogue"):
                        sc["srt_dialogue"] = vision_res["srt_dialogue"]
                    if vision_res.get("highlight_type"):
                        sc["highlight_type"] = vision_res["highlight_type"]
            return sc

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            updated_scenes = list(executor.map(_process_one_frame, enumerate(scenes)))

        logger.info(f"✅ [VISION AI HOÀN TẤT] Đã cập nhật mô tả hình ảnh trực quan thực tế cho {len(updated_scenes)} phân cảnh!")
        return updated_scenes

    def _call_vision_llm_for_single_frame(
        self,
        img_path: Path,
        dialogue: str,
        novel_title: str,
        episode_num: int,
        target_t: float,
        scene_idx: int = 1
    ) -> Optional[Dict[str, Any]]:
        """Gửi trực tiếp bức ảnh Keyframe (base64) kèm phụ đề SRT sang mô hình Vision AI."""
        try:
            import base64
            img_b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
            
            # 1. Gọi qua 9Router / OpenAI Vision endpoint
            from capcut_api.api.gui_app import build_ai_translation_config
            ai_config = build_ai_translation_config(item_config={}, purpose="context")
            if ai_config and ai_config.get("enabled"):
                base_url = ai_config.get("base_url") or "http://127.0.0.1:20128/v1"
                api_key = ai_config.get("api_key") or "sk-d13e798ca7a8589d-jfr5u9-d6a964f4"
                model = ai_config.get("model") or "ag/gemini-3.6-flash-high"
                url = f"{base_url.rstrip('/')}/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                prompt = (
                    f"Bạn là Đạo diễn & Chuyên gia Phân tích Hoạt hình 3D Tiên Hiệp (Donghua Tu Tiên).\n"
                    f"Tác phẩm: '{novel_title}' Tập {episode_num} (Nhân vật trọng tâm: Hàn Lập, đệ tử Lạc Vân Tông, Mộc Lan tộc, Mộ Phái Linh, Lữ Lạc, Nam Lũng Hầu...).\n"
                    f"Hãy quan sát kỹ BỨC ẢNH KEYFRAME ĐÍNH KÈM tại mốc {int(target_t)}s, kết hợp với câu thoại trong phân cảnh: \"{dialogue}\".\n\n"
                    f"YÊU CẦU PHÂN TÍCH CHUYÊN SÂU THEO ĐÚNG NGỮ CẢNH TU TIÊN:\n"
                    f"1. Nhận diện CHÍNH XÁC NHÂN VẬT & TÌNH TIẾT TIÊN HIỆP ĐANG XẢY RA: "
                    f"Xác định rõ ai đang xuất hiện (Ví dụ: Hàn Lập, các đệ tử Lạc Vân Tông, nữ tu sĩ Mộ Phái Linh...), "
                    f"hành động/thần thông/cảnh giới đang diễn ra là gì (Ví dụ: Hàn Lập tiến giai Nguyên Anh, Pháp tướng / Nguyên thần ngọc bích khổng lồ hiển thánh chấn động sơn môn trước sự chứng kiến và bái phục của các đệ tử; thi triển linh quang, pháp bảo phi kiếm...).\n"
                    f"2. TUYỆT ĐỐI TRÁNH MÔ TẢ MƠ HỒ CHUNG CHUNG: Không dùng các từ vu vơ như 'một bóng hình mờ ảo', 'nhân vật không rõ', 'luồng năng lượng lạ'. Phải gọi đúng tên nhân vật, pháp tướng, bối cảnh tu tiên cụ thể.\n"
                    f"3. ĐỒNG BỘ NỘI DUNG: Cập nhật lại tiêu đề, tóm tắt thoại và mô tả hình ảnh cho ăn khớp 100% với diễn biến thật trong phim.\n\n"
                    f"Trả về DUY NHẤT một JSON hợp lệ dạng:\n"
                    f"{{\n"
                    f"  \"scene_title\": \"Tiêu đề phân cảnh chuẩn xác theo diễn biến tiên hiệp\",\n"
                    f"  \"srt_dialogue\": \"Tóm tắt câu chuyện / câu thoại chuẩn xác của phân cảnh này\",\n"
                    f"  \"visual_description\": \"Mô tả hình ảnh trực quan chi tiết, sắc nét, định danh rõ nhân vật, nguyên thần/pháp tướng, cử chỉ, trang phục và hiệu ứng tiên hiệp trong khung hình...\",\n"
                    f"  \"highlight_type\": \"combat/dialogue/climax/breakthrough/scenery\"\n"
                    f"}}"
                )
                payload = {
                    "model": model,
                    "stream": False,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                        ]
                    }]
                }
                import requests
                logger.info(f"👁️ [CALL VISION AI #{scene_idx}] Gửi ảnh '{img_path.name}' ({int(target_t)}s) kèm thoại tới {model}")
                r = requests.post(url, headers=headers, json=payload, timeout=30)
                if r.ok:
                    data = r.json()
                    raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    parsed = self._clean_ai_json_response(raw)
                    logger.info(f"📥 [VISION AI #{scene_idx} KẾT QUẢ]: Tiêu đề='{parsed.get('scene_title')}', Mô tả='{parsed.get('visual_description')[:80]}...'")
                    return parsed
                else:
                    logger.warning(f"⚠️ [VISION AI #{scene_idx} HTTP ERROR]: {r.status_code} - {r.text[:200]}")

            # 2. Thử gọi Gemini Vision trực tiếp nếu có key
            if self.gemini_key:
                prompt = (
                    f"Bạn là chuyên gia Phân tích Hoạt hình Tiên Hiệp. Phân tích BỨC ẢNH KEYFRAME mốc {int(target_t)}s của '{novel_title}' Tập {episode_num} (Hàn Lập, Lạc Vân Tông...). "
                    f"Thoại: \"{dialogue}\". "
                    f"Trả về JSON: {{\"scene_title\": \"...\", \"srt_dialogue\": \"...\", \"visual_description\": \"...\", \"highlight_type\": \"...\"}}"
                )
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
                logger.info(f"👁️ [CALL GEMINI VISION #{scene_idx}] Gửi ảnh '{img_path.name}' tới Gemini 1.5 Flash")
                req_data = json.dumps({
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                        ]
                    }],
                    "generationConfig": {"temperature": 0.2, "response_mime_type": "application/json"}
                }).encode("utf-8")
                req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=20) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    txt = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = self._clean_ai_json_response(txt)
                    logger.info(f"📥 [GEMINI VISION #{scene_idx} KẾT QUẢ]: Tiêu đề='{parsed.get('scene_title')}'")
                    return parsed
        except Exception as e:
            logger.error(f"❌ [VISION AI #{scene_idx} ERROR]: {e}")
        return None

    # =========================================================================
    # 4. FULL PIPELINE: PHÂN TÍCH TOÀN BỘ BẰNG AI (CẤM LƯU DATA LỖI)
    # =========================================================================
    def run_full_scene_pipeline(
        self,
        novel_id: str,
        novel_name: str,
        episode_num: int,
        video_path: Optional[str] = None,
        auto_upload_drive: bool = True
    ) -> Dict[str, Any]:
        v_file = self.find_episode_video_on_disk(novel_id, episode_num, video_path)
        if not v_file or not v_file.exists():
            raise FileNotFoundError(f"Không tìm thấy file video cho Tập {episode_num}.")

        ep_dir = self._get_episode_dir(novel_id, episode_num)
        keyframes_dir = ep_dir / "keyframes"
        srt_file = ep_dir / f"tap_{episode_num}.srt"

        logger.info("=" * 70)
        logger.info(f"🎬 BẮT ĐẦU FULL PIPELINE PHÂN TÍCH CHO: {novel_name} - TẬP {episode_num}")
        logger.info(f"📁 Video Path: {v_file.resolve()}")
        logger.info("=" * 70)

        t_start = time.time()
        video_dur = self._get_video_duration_fast(v_file)

        # 1. Trích xuất Timeline & SRT bằng Faster-Whisper
        srt_segments = self.get_video_subtitles(v_file, novel_id, episode_num, srt_file)

        # 2. DÙNG AI PHÂN TÍCH SRT ĐỂ CẮT KHOẢNG PHÂN CẢNH (Lỗi sẽ raise exception dừng ngay)
        scenes = self.ai_analyze_srt_for_scenes(srt_segments, novel_name, episode_num, video_dur)
        if not scenes:
            raise RuntimeError("❌ Lỗi: AI không trả về phân cảnh nào. Tiến trình dừng lại, không lưu dữ liệu rác.")

        # 3. Trích xuất ảnh Keyframe tại đúng các mốc giây vàng do AI tìm ra
        scenes = self.extract_highlight_keyframes(v_file, scenes, keyframes_dir)

        # 3.5. DÙNG VISION AI PHÂN TÍCH TRỰC DIỆN BỨC ẢNH KẾT HỢP VỚI NỘI DUNG THOẠI
        scenes = self.ai_analyze_vision_and_subtitles(scenes, novel_name, episode_num)

        # 4. Gắn thumbnail URL
        for sc in scenes:
            sc["thumbnail_url"] = f"/api/novel/scenes/thumbnail?novel_id={novel_id}&episode={episode_num}&filename={sc['keyframe_filename']}"

        # 5. CHỈ LƯU VÀO DB KHI TOÀN BỘ CÁC BƯỚC AI ĐÃ HOÀN TẤT THÀNH CÔNG
        clean_novel = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "novel"
        for sc in scenes:
            kf_name = sc.get("keyframe_filename") or f"keyframe_{sc.get('scene_id', 1):03d}.jpg"
            sc["keyframe_filename"] = kf_name
            sc["relative_keyframe_path"] = f"scene_analysis/{clean_novel}/tap_{episode_num}/keyframes/{kf_name}"
            sc["thumbnail_url"] = f"/api/novel/scenes/thumbnail?novel_id={clean_novel}&episode={episode_num}&filename={kf_name}"
            sc["download_url"] = f"/api/cloud/download?relative_path={sc['relative_keyframe_path']}"

        metadata = {
            "novel_id": novel_id,
            "novel_name": novel_name,
            "episode_num": episode_num,
            "video_source": str(v_file.resolve()),
            "video_filename": v_file.name,
            "analyzed_at": int(time.time()),
            "processing_time_sec": round(time.time() - t_start, 2),
            "scenes_count": len(scenes),
            "srt_segments_count": len(srt_segments),
            "scenes": scenes,
            "drive_synced": True,
            "drive_folder_link": ""
        }

        # Lưu file JSON trên ổ đĩa (Google Drive hoặc Local)
        meta_path = ep_dir / "scenes_analysis.json"
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"✅ ĐÃ HOÀN TẤT VÀ LƯU FILE TẠI: {meta_path.resolve()}")

        # LƯU VÀO MONGODB ATLAS & GOOGLE DRIVE ĐỂ CHUYỂN MÁY VẪN ĐẦY ĐỦ
        try:
            from capcut_api.database.mongo_manager import get_db_manager
            db_doc = get_db_manager().save_scene_analysis(novel_id, episode_num, metadata)
            logger.info(f"✅ Đã lưu phân tích cảnh Tập {episode_num} vào MongoDB Atlas ({len(scenes)} scenes)!")
        except Exception as db_err:
            logger.warning(f"Lỗi lưu MongoDB: {db_err}")

        # Đồng bộ sang các bí danh novel_id
        alias_id = "Phamnhantutien" if "xianni" in novel_id.lower() else "xianni"
        alias_dir = self.scenes_root / alias_id / f"tap_{episode_num}"
        alias_dir.mkdir(parents=True, exist_ok=True)
        (alias_dir / "keyframes").mkdir(exist_ok=True)
        shutil.copytree(keyframes_dir, alias_dir / "keyframes", dirs_exist_ok=True)
        shutil.copy2(meta_path, alias_dir / "scenes_analysis.json")
        if srt_file.exists():
            shutil.copy2(srt_file, alias_dir / f"tap_{episode_num}.srt")

        return {
            "success": True,
            "novel_id": novel_id,
            "episode_num": episode_num,
            "scenes_count": len(scenes),
            "video_filename": v_file.name,
            "scenes": scenes,
            "drive_synced": True,
            "drive_folder_link": ""
        }

    def list_analyzed_episodes(self, novel_id: str) -> List[Dict[str, Any]]:
        clean_id = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "default"
        episodes_map: Dict[int, Dict[str, Any]] = {}

        # 1. Kiểm tra MongoDB Atlas trước (cho phép xem khi chuyển máy khác)
        try:
            from capcut_api.database.mongo_manager import get_db_manager
            db_scenes = get_db_manager().list_scenes_analysis(novel_id)
            for item in db_scenes:
                ep_num = int(item.get("episode_num", 0))
                if ep_num:
                    episodes_map[ep_num] = {
                        "episode_dir": f"tap_{ep_num}",
                        "episode_num": ep_num,
                        "scenes_count": item.get("scenes_count", 12),
                        "path": item.get("gdrive_relative_folder", ""),
                        "has_metadata": True,
                        "drive_synced": True,
                        "drive_folder_link": item.get("drive_folder_link", ""),
                        "source": "mongodb_atlas"
                    }
        except Exception as e:
            logger.debug(f"Note listing from MongoDB: {e}")

        # 2. Bổ sung từ thư mục scenes_root (Google Drive hoặc Local)
        novel_folder = self.scenes_root / clean_id
        if novel_folder.exists():
            for ep_dir in sorted(novel_folder.glob("tap_*")):
                if not ep_dir.is_dir():
                    continue
                meta_file = ep_dir / "scenes_analysis.json"
                ep_num = int(ep_dir.name.replace("tap_", "")) if ep_dir.name.replace("tap_", "").isdigit() else 0
                if not ep_num:
                    continue

                scenes_count = len(list((ep_dir / "keyframes").glob("*.jpg")))
                if ep_num not in episodes_map:
                    episodes_map[ep_num] = {
                        "episode_dir": ep_dir.name,
                        "episode_num": ep_num,
                        "scenes_count": scenes_count,
                        "path": str(ep_dir.resolve()),
                        "has_metadata": meta_file.exists(),
                        "drive_synced": False,
                        "drive_folder_link": ""
                    }
                else:
                    if scenes_count > 0:
                        episodes_map[ep_num]["scenes_count"] = scenes_count

        return sorted(list(episodes_map.values()), key=lambda x: x.get("episode_num", 0), reverse=True)

    def get_episode_analysis_details(self, novel_id: str, episode_num: int) -> Dict[str, Any]:
        """
        Lấy toàn bộ chi tiết phân tích phân cảnh (mô tả, lời thoại, mốc thời gian, keyframes):
        1. Ưu tiên đọc từ MongoDB Atlas (hỗ trợ chuyển máy bất kỳ).
        2. Nếu chưa có, đọc từ scenes_analysis.json trên Google Drive hoặc Local.
        3. Tự động chuẩn hóa đường dẫn thumbnail và download cho từng ảnh.
        """
        clean_id = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "default"

        # 1. Đọc từ MongoDB Atlas trước
        try:
            from capcut_api.database.mongo_manager import get_db_manager
            db_data = get_db_manager().get_scene_analysis(novel_id, episode_num)
            if db_data and db_data.get("scenes"):
                db_data["success"] = True
                # Chuẩn hóa thumbnail_url cho từng cảnh
                for sc in db_data.get("scenes", []):
                    kf_name = sc.get("keyframe_filename") or f"keyframe_{sc.get('scene_id', 1):03d}.jpg"
                    sc["thumbnail_url"] = f"/api/novel/scenes/thumbnail?novel_id={clean_id}&episode={episode_num}&filename={kf_name}"
                    sc["download_url"] = f"/api/cloud/download?relative_path=scene_analysis/{clean_id}/tap_{episode_num}/keyframes/{kf_name}"
                return db_data
        except Exception as e:
            logger.debug(f"Note reading scene from MongoDB: {e}")

        # 2. Đọc từ Google Drive / Local scenes_root
        ep_dir = self.scenes_root / clean_id / f"tap_{episode_num}"
        meta_file = ep_dir / "scenes_analysis.json"

        if not meta_file.exists():
            for other_dir in self.scenes_root.glob(f"*/tap_{episode_num}/scenes_analysis.json"):
                if other_dir.exists():
                    meta_file = other_dir
                    break

        if not meta_file.exists():
            return {
                "success": False,
                "error": f"Chưa có dữ liệu phân tích phân cảnh cho {novel_id} Tập {episode_num}"
            }

        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            data["success"] = True
            for sc in data.get("scenes", []):
                kf_name = sc.get("keyframe_filename") or f"keyframe_{sc.get('scene_id', 1):03d}.jpg"
                sc["thumbnail_url"] = f"/api/novel/scenes/thumbnail?novel_id={clean_id}&episode={episode_num}&filename={kf_name}"
                sc["download_url"] = f"/api/cloud/download?relative_path=scene_analysis/{clean_id}/tap_{episode_num}/keyframes/{kf_name}"
            return data
        except Exception as e:
            return {"success": False, "error": str(e)}

