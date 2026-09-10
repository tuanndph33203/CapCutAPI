# -*- coding: utf-8 -*-
"""
NovelScriptGenerator — Tự động đọc chương truyện thô → tóm tắt thành kịch bản thuyết minh YouTube
Hỗ trợ nhiều LLM backend: OpenAI / Gemini / Groq / DeepSeek / Ollama (local) / Fallback template
"""

import os
import sys
import re
import json
import time
import asyncio
import edge_tts
from pathlib import Path
from typing import Optional, List, Dict, Any

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ─────────────────────────────────────────────────────────
# SECTION 1: LLM BACKEND ABSTRACTION
# ─────────────────────────────────────────────────────────

class LLMBackend:
    """Lớp trừu tượng cho các LLM backend khác nhau."""
    name = "base"

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        raise NotImplementedError


class OpenAIBackend(LLMBackend):
    name = "openai"
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        return resp.choices[0].message.content.strip()


class DeepSeekBackend(LLMBackend):
    """DeepSeek API — tương thích OpenAI SDK, giá rẻ, tiếng Việt tốt."""
    name = "deepseek"
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        return resp.choices[0].message.content.strip()


class GeminiBackend(LLMBackend):
    """Google Gemini API — miễn phí quota khá lớn."""
    name = "gemini"
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.model_obj = genai.GenerativeModel(model)

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        combined = f"{system_prompt}\n\n{user_prompt}"
        resp = self.model_obj.generate_content(
            combined,
            generation_config={"max_output_tokens": max_tokens, "temperature": 0.7}
        )
        return resp.text.strip()


class GroqBackend(LLMBackend):
    """Groq — siêu nhanh, miễn phí tier khá rộng."""
    name = "groq"
    def __init__(self, api_key: str, model: str = "llama3-8b-8192"):
        from groq import Groq
        self.client = Groq(api_key=api_key)
        self.model = model

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        return resp.choices[0].message.content.strip()


class OllamaBackend(LLMBackend):
    """Ollama local — hoàn toàn offline, cần cài sẵn model."""
    name = "ollama"
    def __init__(self, model: str = "gemma3:4b", host: str = "http://localhost:11434"):
        import requests
        self.model = model
        self.host = host
        self.requests = requests

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.7}
        }
        resp = self.requests.post(f"{self.host}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()


class FallbackTemplateBackend(LLMBackend):
    """
    Không cần API — tự xây dựng kịch bản theo template có cấu trúc
    từ nội dung chương thô đã được làm sạch.
    Phù hợp khi không có API key nào.
    """
    name = "template"

    # Các cụm từ chuyển tiếp để tạo sự tự nhiên
    TRANSITIONS = [
        "[0.2] Tiếp đó,", "[0.2] Không lâu sau,", "[0.2] Lúc này,",
        "[0.2] Đồng thời,", "[0.2] Trong khi đó,", "[0.2] Bất ngờ thay,",
        "[0.2] Nhưng rồi,", "[0.2] Chính lúc đó,", "[0.2] Ngay sau đó,"
    ]

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
        # Trích xuất nội dung chương từ user_prompt
        m = re.search(r'NỘI DUNG CHƯƠNG:\n(.*?)(?:\n\nYÊU CẦU:|$)', user_prompt, re.DOTALL)
        chapter_text = m.group(1).strip() if m else user_prompt

        # Trích xuất target_words từ prompt
        m_tw = re.search(r'Độ dài mục tiêu:\s*(\d+)\s*từ', user_prompt)
        target_words = int(m_tw.group(1)) if m_tw else 2500

        # Tách các đoạn văn, loại bỏ đoạn rỗng và quá ngắn
        paragraphs = [p.strip() for p in chapter_text.split('\n') if len(p.strip()) > 30]
        if not paragraphs:
            return chapter_text[:max_tokens]

        # Ước tính số đoạn văn cần lấy (trung bình ~30 từ/đoạn)
        avg_w = max(15, sum(len(p.split()) for p in paragraphs[:20]) // max(1, min(len(paragraphs), 20)))
        needed_paras = max(2, int(target_words / avg_w))
        target_paragraphs = min(len(paragraphs), needed_paras)
        step = max(1, len(paragraphs) // max(1, target_paragraphs))
        selected = paragraphs[::step][:target_paragraphs]

        # Ghép lại thành văn bản thuyết minh theo đúng target_words
        parts = []
        cur_w = 0
        for i, para in enumerate(selected):
            words = para.split()
            if len(words) > 160:
                para = ' '.join(words[:160]) + '...'
                words = para.split()

            if i > 0 and i % 3 == 0:
                trans = self.TRANSITIONS[i % len(self.TRANSITIONS)]
                para = trans + ' ' + para
                words = para.split()

            parts.append(para)
            cur_w += len(words)
            if cur_w >= target_words:
                break

        return ' [0.2] '.join(parts)


# ─────────────────────────────────────────────────────────
# SECTION 2: NOVEL CHAPTER READER
# ─────────────────────────────────────────────────────────

class NovelChapterReader:
    """Đọc và làm sạch nội dung chương từ nhiều nguồn khác nhau."""

    @staticmethod
    def read_from_file(file_path: str) -> str:
        """Đọc file .md hoặc .txt."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {file_path}")
        text = p.read_text(encoding='utf-8', errors='ignore')
        return NovelChapterReader.clean(text)

    @staticmethod
    def read_chapters_range(chapters_dir: str, ch_start: int, ch_end: int) -> str:
        """Đọc nhiều chương liên tiếp từ thư mục chapters/."""
        chapters_path = Path(chapters_dir)
        all_files = sorted(chapters_path.glob("ch_*.md"))
        selected = []
        for f in all_files:
            # Trích số chương từ tên file: ch_00736_...
            m = re.match(r'ch_0*(\d+)', f.name)
            if m:
                ch_num = int(m.group(1))
                if ch_start <= ch_num <= ch_end:
                    selected.append((ch_num, f))
        selected.sort(key=lambda x: x[0])
        if not selected:
            raise ValueError(f"Không tìm thấy chương {ch_start}-{ch_end} trong {chapters_dir}")

        combined = []
        for ch_num, fpath in selected:
            text = fpath.read_text(encoding='utf-8', errors='ignore')
            combined.append(f"=== CHƯƠNG {ch_num} ===\n{NovelChapterReader.clean(text)}")
            print(f"  Đọc chương {ch_num} ({len(text):,} bytes): {fpath.name}")

        return "\n\n".join(combined)

    @staticmethod
    def count_content_words(text: str) -> int:
        words = text.split()
        if len(words) < max(1, len(text) / 10):
            cjk = re.findall(r'[\u4e00-\u9fff]', text)
            return len(cjk) if cjk else len(words)
        return len(words)

    @staticmethod
    def auto_span_chapters(chapters_dir: str, ch_start: int, target_words: int, max_chapters: int = 10) -> tuple:
        """
        Tự động quét từ ch_start trở đi cho đến khi gom đủ số từ target_words.
        Hỗ trợ cả text tiếng Việt và raw CJK.
        Trả về: (ch_end, combined_text)
        """
        chapters_path = Path(chapters_dir)
        all_files = sorted(chapters_path.glob("ch_*.md"))
        file_map = {}
        for f in all_files:
            m = re.match(r'ch_0*(\d+)', f.name)
            if m:
                file_map[int(m.group(1))] = f

        combined = []
        cur_ch = ch_start
        total_w = 0
        while cur_ch in file_map and len(combined) < max_chapters:
            fpath = file_map[cur_ch]
            text = NovelChapterReader.clean(fpath.read_text(encoding='utf-8', errors='ignore'))
            w_count = NovelChapterReader.count_content_words(text)
            combined.append(f"=== CHƯƠNG {cur_ch} ===\n{text}")
            total_w += w_count
            print(f"  [auto_span] Gom chương {cur_ch}: +{w_count} từ/ký tự (tổng {total_w}/{target_words})")
            if total_w >= target_words:
                break
            cur_ch += 1

        return cur_ch, "\n\n".join(combined)

    @staticmethod
    def read_from_txt(script_txt_path: str) -> str:
        """Đọc từ file kịch bản thô .txt đã có."""
        p = Path(script_txt_path)
        text = p.read_text(encoding='utf-8', errors='ignore')
        return NovelChapterReader.clean(text)

    @staticmethod
    def clean(text: str) -> str:
        """Làm sạch text: bỏ markdown headers, tags HTML, ký tự đặc biệt thừa."""
        text = re.sub(r'<[^>]+>', ' ', text)          # HTML tags
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text) # Bold markdown
        text = re.sub(r'#{1,6}\s+', '', text)           # Markdown headers
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Markdown links
        text = re.sub(r'={3,}', '', text)               # Separators
        text = re.sub(r'\n{3,}', '\n\n', text)          # Multiple newlines
        text = re.sub(r'[ \t]+', ' ', text)             # Multiple spaces
        return text.strip()


# ─────────────────────────────────────────────────────────
# SECTION 3: SCRIPT GENERATOR CORE
# ─────────────────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "detailed": """Bạn là biên kịch chuyên nghiệp cho kênh YouTube recap truyện tiên hiệp tiếng Việt.
Nhiệm vụ: Chuyển đổi nội dung chương truyện thành kịch bản kể chuyện chi tiết, chuyên sâu (Storytelling 15-30 phút).
YÊU CẦU KỸ THUẬT:
- Giữ lại 75-85% chi tiết: giữ các lời thoại đắt giá của nhân vật, diễn biến giao chiến chi tiết, miêu tả chiêu thức, pháp bảo, tâm lý nhân vật
- Viết theo phong cách thuyết minh YouTube: cuốn hút, có cảm xúc, chuyển từ văn viết sang văn nói tự nhiên
- Mỗi phân đoạn cách nhau bằng [0.2] hoặc [0.3] để ngắt nhịp thở tự nhiên
- KHÔNG dùng bullet points, KHÔNG dùng headers, chỉ viết văn xuôi liên tục
- Giữ nguyên tên nhân vật, địa điểm, kỹ năng (Hàn Lập, Mộ Lan, Càn Lam Băng Diễm...)
- Viết đủ dài: khoảng {target_words} từ cho nội dung chính
- KHÔNG thêm hook mở đầu hay outro kết thúc — chỉ viết nội dung chính""",

    "standard": """Bạn là biên kịch chuyên nghiệp cho kênh YouTube recap truyện tiên hiệp tiếng Việt.
Nhiệm vụ: Tóm tắt mạch truyện chính thành kịch bản recap dồn dập, lôi cuốn (8-12 phút).
YÊU CẦU KỸ THUẬT:
- Tập trung vào các sự kiện cốt lõi, đột phá cảnh giới, mưu lược, các pha combat cao trào
- Lược bỏ các đoạn miêu tả phong cảnh và giải thích rườm rà
- Mỗi phân đoạn cách nhau bằng [0.3]
- Viết đủ dài: khoảng {target_words} từ cho nội dung chính
- KHÔNG thêm hook mở đầu hay outro kết thúc""",

    "short": """Bạn là biên kịch chuyên nghiệp cho kênh YouTube recap truyện tiên hiệp tiếng Việt.
Nhiệm vụ: Viết tóm tắt nhanh siêu ngắn / Highlight (3-5 phút).
YÊU CẦU KỸ THUẬT:
- Cực kỳ cô đọng, dồn dập, chỉ tập trung vào cao trào và nút thắt bất ngờ nhất
- Mỗi phân đoạn cách nhau bằng [0.3]
- Viết đủ dài: khoảng {target_words} từ
- KHÔNG thêm hook mở đầu hay outro kết thúc"""
}

USER_PROMPT_TEMPLATE = """NỘI DUNG CHƯƠNG:
{chapter_text}

YÊU CẦU:
Viết kịch bản thuyết minh YouTube tiếng Việt từ nội dung trên.
Độ dài mục tiêu: {target_words} từ.
Chia thành {num_scenes} phân đoạn rõ ràng, mỗi phân đoạn ngăn cách bằng [0.5].
Mỗi phân đoạn khoảng {words_per_scene} từ, có [0.2] ở giữa các câu để tạo nhịp thở tự nhiên."""


class NovelScriptGenerator:
    """
    Pipeline kịch bản truyện tiên hiệp đa chế độ:
    - 'raw': Đọc nguyên tác 100% (Audiobook, 0đ LLM, tốc độ tức thì)
    - 'detailed': Kể chuyện chi tiết sâu 75-85% chi tiết (Recap 15-30 phút)
    - 'standard': Recap tiêu chuẩn 40-50% (8-12 phút)
    - 'short': Tóm tắt ngắn/Highlight 15-25% (3-5 phút)
    """

    HOOK_TEMPLATE = "Tập {ep} — {title}!"
    OUTRO_TEMPLATE = "Bấm Like, Đăng ký và Bật chuông xem tiếp Tập {next_ep} nhé! Hẹn gặp lại!"

    def __init__(
        self,
        backend: Optional[LLMBackend] = None,
        mode: str = "detailed",
        target_duration_min: float = 15.0,
        tts_voice: str = "vi-VN-NamMinhNeural",
        tts_rate: str = "+5%",
        output_dir: str = "data/outputs/novel_audio/Auto_Pipeline",
        hook_template: Optional[str] = None,
        outro_template: Optional[str] = None
    ):
        self.backend = backend or FallbackTemplateBackend()
        self.mode = mode.lower()
        self.target_duration_min = target_duration_min
        self.tts_voice = tts_voice
        self.tts_rate = tts_rate
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.hook_template = hook_template or self.HOOK_TEMPLATE
        self.outro_template = outro_template or self.OUTRO_TEMPLATE

        # Ước tính tốc độ đọc TTS tiếng Việt: ~200-220 từ/phút
        self.words_per_min = 210.0
        self.target_words = int(target_duration_min * self.words_per_min)
        print(f"[NovelScriptGenerator] Chế độ: {self.mode.upper()}")
        print(f"[NovelScriptGenerator] Backend: {self.backend.name}")
        print(f"[NovelScriptGenerator] Mục tiêu: {target_duration_min:.1f} phút ≈ {self.target_words} từ")

    @classmethod
    def from_config(cls, config_path: str = "config.json", backend: Optional[LLMBackend] = None, **overrides) -> "NovelScriptGenerator":
        cfg = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    full_cfg = json.load(f)
                    cfg = full_cfg.get("novel_pipeline", {})
            except Exception:
                pass

        mode = overrides.get("mode") or cfg.get("mode", "detailed")
        duration = overrides.get("duration") or cfg.get("target_duration_min", 15.0)
        voice = overrides.get("tts_voice") or cfg.get("tts", {}).get("voice", "vi-VN-NamMinhNeural")
        rate = overrides.get("tts_rate") or cfg.get("tts", {}).get("rate", "+5%")
        out_dir = overrides.get("output_dir") or "data/outputs/novel_audio/Auto_Pipeline"

        hook_t = cfg.get("hook_outro", {}).get("hook_template")
        outro_t = cfg.get("hook_outro", {}).get("outro_template")

        if not backend:
            backend = auto_detect_backend(config_path)

        return cls(
            backend=backend,
            mode=mode,
            target_duration_min=duration,
            tts_voice=voice,
            tts_rate=rate,
            output_dir=out_dir,
            hook_template=hook_t,
            outro_template=outro_t
        )

    # ── Bước 1: Đọc chương ──────────────────────────────
    def load_chapters(
        self,
        chapters_dir: Optional[str] = None,
        ch_start: Optional[int] = None,
        ch_end: Optional[int] = None,
        direct_file: Optional[str] = None,
        direct_text: Optional[str] = None,
        auto_span: bool = False
    ) -> str:
        """Load nội dung chương từ nhiều nguồn."""
        if direct_text:
            print(f"[load] Dùng text trực tiếp ({len(direct_text.split())} từ)")
            return NovelChapterReader.clean(direct_text)
        elif direct_file:
            print(f"[load] Đọc file: {direct_file}")
            return NovelChapterReader.read_from_file(direct_file)
        elif chapters_dir and ch_start:
            if auto_span or not ch_end:
                needed_raw = self.target_words if self.mode == "raw" else int(self.target_words * 1.35)
                print(f"[load] Auto-span: Gom chương từ {ch_start} đến khi đủ ~{needed_raw} từ...")
                actual_end, text = NovelChapterReader.auto_span_chapters(chapters_dir, ch_start, needed_raw)
                print(f"[load] Đã tự động gom chương {ch_start} đến {actual_end} ({len(text.split())} từ raw)")
                return text
            else:
                print(f"[load] Đọc chương {ch_start}-{ch_end} từ {chapters_dir}")
                return NovelChapterReader.read_chapters_range(chapters_dir, ch_start, ch_end)
        else:
            raise ValueError("Phải cung cấp ít nhất một trong: direct_text, direct_file, chapters_dir+ch_start")

    def format_raw_novel_script(self, chapter_text: str, num_scenes: int = 25) -> str:
        """
        Chế độ RAW (Audiobook): Giữ 100% câu chữ nguyên tác, không tóm tắt, không gọi LLM.
        Làm sạch tiêu đề, thêm ngắt câu nhịp thở tự nhiên cho TTS và chia đều các scenes.
        """
        paras = [p.strip() for p in chapter_text.splitlines() if p.strip()]
        clean_paras = [p for p in paras if not re.match(r'^===.*===$', p)]
        total_p = len(clean_paras)
        chunk_size = max(1, total_p // max(1, num_scenes))
        scenes = []
        for i in range(0, total_p, chunk_size):
            group = clean_paras[i:i+chunk_size]
            scene_text = " [0.2] ".join(group)
            scenes.append(scene_text)
        total_words = sum(len(p.split()) for p in clean_paras)
        print(f"[raw_mode] Giữ trọn 100% nguyên tác: {total_words} từ chia {len(scenes)} phân cảnh.")
        return " [0.5] \n\n".join(scenes)

    # ── Bước 2: Chia thành từng batch và gọi LLM ────────
    def generate_script_content(self, chapter_text: str, num_scenes: int = 10) -> str:
        """
        Tạo kịch bản nội dung theo chế độ đã cấu hình:
        - Nếu 'raw': Format trực tiếp nguyên tác 100% không gọi LLM
        - Nếu 'detailed' / 'standard' / 'short': Dùng prompt chuyên biệt tương ứng
        """
        if self.mode == "raw":
            return self.format_raw_novel_script(chapter_text, num_scenes=num_scenes)

        MAX_CHARS_PER_CALL = 8000  # Giới hạn an toàn cho hầu hết LLM
        words_per_scene = max(80, self.target_words // max(1, num_scenes))
        prompt_tmpl = SYSTEM_PROMPTS.get(self.mode, SYSTEM_PROMPTS["detailed"])
        system_p = prompt_tmpl.format(target_words=self.target_words)

        # Nếu ngắn đủ — gọi 1 lần
        if len(chapter_text) <= MAX_CHARS_PER_CALL:
            print(f"[generate] 1 lần gọi LLM ({len(chapter_text)} ký tự, mode={self.mode}) → mục tiêu {self.target_words} từ")
            user_p = USER_PROMPT_TEMPLATE.format(
                chapter_text=chapter_text,
                target_words=self.target_words,
                num_scenes=num_scenes,
                words_per_scene=words_per_scene
            )
            result = self.backend.generate(system_p, user_p, max_tokens=6000)
            return result

        # Chia batch nếu nội dung dài
        print(f"[generate] Nội dung dài ({len(chapter_text)} ký tự, mode={self.mode}) — chia {num_scenes} batch")
        chunk_size = MAX_CHARS_PER_CALL
        chunks = []
        for i in range(0, len(chapter_text), chunk_size):
            chunks.append(chapter_text[i:i+chunk_size])

        # Phân phối số scenes đều cho từng chunk
        scenes_per_chunk = max(1, num_scenes // len(chunks))
        target_words_per_chunk = self.target_words // len(chunks)

        all_parts = []
        for idx, chunk in enumerate(chunks):
            prompt_tmpl = SYSTEM_PROMPTS.get(self.mode, SYSTEM_PROMPTS["detailed"])
            sys_p_chunk = prompt_tmpl.format(target_words=target_words_per_chunk)
            user_p_chunk = USER_PROMPT_TEMPLATE.format(
                chapter_text=chunk,
                target_words=target_words_per_chunk,
                num_scenes=scenes_per_chunk,
                words_per_scene=target_words_per_chunk // max(1, scenes_per_chunk)
            )
            try:
                part = self.backend.generate(sys_p_chunk, user_p_chunk, max_tokens=4000)
                all_parts.append(part)
                time.sleep(0.5)  # Tránh rate limit
            except Exception as e:
                print(f"  [WARN] Batch {idx+1} lỗi: {e} — dùng fallback")
                fallback = FallbackTemplateBackend()
                part = fallback.generate(sys_p_chunk, user_p_chunk)
                all_parts.append(part)

        return "\n[0.5]\n".join(all_parts)

    # ── Bước 3: Lắp Hook + Outro ────────────────────────
    def assemble_full_script(
        self,
        content: str,
        episode: int,
        title: str,
        next_ep: Optional[int] = None
    ) -> str:
        """Lắp hook ngắn + nội dung + outro ngắn."""
        hook = self.HOOK_TEMPLATE.format(ep=episode, title=title)
        outro = self.OUTRO_TEMPLATE.format(next_ep=next_ep or episode + 1)
        return f"{hook}\n[0.5]\n{content}\n[0.5]\n{outro}"

    # ── Bước 4: Đếm từ và đánh giá ─────────────────────
    def analyze_script(self, full_script: str) -> Dict[str, Any]:
        clean = re.sub(r'\[\s*\d+(?:\.\d+)?\s*\]', ' ', full_script)
        clean = re.sub(r'\s+', ' ', clean).strip()
        words = clean.split()
        est_min = len(words) / self.words_per_min
        return {
            "total_words": len(words),
            "total_chars": len(clean),
            "estimated_minutes": round(est_min, 2),
            "target_minutes": self.target_duration_min,
            "ratio_ok": est_min >= self.target_duration_min * 0.85
        }

    # ── Bước 5: Sinh audio Edge-TTS ─────────────────────
    async def synthesize_audio(self, script_text: str, filename: str) -> Path:
        tts_text = re.sub(r'\[\s*\d+(?:\.\d+)?\s*\]', ' ', script_text)
        tts_text = re.sub(r'\s+', ' ', tts_text).strip()
        out_path = self.output_dir / filename
        print(f"[tts] Sinh audio {len(tts_text.split())} từ → {out_path}")
        t0 = time.time()
        comm = edge_tts.Communicate(tts_text, self.tts_voice, rate=self.tts_rate)
        await comm.save(str(out_path))
        print(f"[tts] Hoàn tất trong {time.time()-t0:.1f}s, {out_path.stat().st_size/(1024*1024):.2f} MB")
        return out_path

    # ── Bước 6: Pipeline tổng hợp ────────────────────────────────
    async def run(
        self,
        episode: int,
        title: str,
        chapters_dir: Optional[str] = None,
        ch_start: Optional[int] = None,
        ch_end: Optional[int] = None,
        direct_file: Optional[str] = None,
        direct_text: Optional[str] = None,
        num_scenes: int = 20,
        next_ep: Optional[int] = None,
        auto_span: bool = False
    ) -> Dict[str, Any]:
        print(f"\n{'='*60}")
        print(f"=== NOVEL SCRIPT GENERATOR: TẬP {episode} — {title} (MODE: {self.mode.upper()}) ===")
        print(f"{'='*60}")

        # 1. Đọc chương
        chapter_text = self.load_chapters(
            chapters_dir=chapters_dir, ch_start=ch_start, ch_end=ch_end,
            direct_file=direct_file, direct_text=direct_text,
            auto_span=auto_span
        )
        print(f"[1/5] Đọc xong: {len(chapter_text.split())} từ, {len(chapter_text)} ký tự")

        # 2. Sinh kịch bản
        print(f"[2/5] Tạo kịch bản (mode={self.mode}, backend={self.backend.name})...")
        content = self.generate_script_content(chapter_text, num_scenes=num_scenes)
        print(f"  → Kịch bản nội dung: {len(content.split())} từ")

        # 3. Lắp Hook + Outro
        full_script = self.assemble_full_script(content, episode, title, next_ep)

        # 4. Đánh giá
        stats = self.analyze_script(full_script)
        print(f"[3/5] Phân tích:")
        print(f"  → Tổng từ: {stats['total_words']} từ")
        print(f"  → Thời lượng ước tính: {stats['estimated_minutes']:.1f} phút (mục tiêu: {stats['target_minutes']:.1f} phút)")
        print(f"  → Đạt yêu cầu: {'✅ CÓ' if stats['ratio_ok'] else '❌ CHƯA ĐỦ — cần bổ sung'}")

        # 5. Lưu kịch bản
        ep_str = f"Tap_{episode:03d}"
        script_path = self.output_dir / f"{ep_str}_kich_ban.txt"
        script_path.write_text(full_script, encoding='utf-8')
        print(f"[4/5] Đã lưu kịch bản: {script_path}")

        # 6. Sinh audio
        audio_filename = f"Pham_Nhan_Tu_Tien_Tap_{episode:03d}.mp3"
        audio_path = await self.synthesize_audio(full_script, audio_filename)

        # 7. Đo thời lượng thực tế
        import subprocess
        cmd = [r'C:\Users\admin.TRANANH\AppData\Local\Programs\Python\Python311\Scripts\ffmpeg.EXE',
               '-i', str(audio_path)]
        res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        m = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', res.stderr)
        real_dur = m.group(0) if m else "N/A"
        print(f"[5/5] Thời lượng audio thực tế: {real_dur}")

        return {
            "episode": episode,
            "title": title,
            "mode": self.mode,
            "backend": self.backend.name,
            "script_path": str(script_path),
            "audio_path": str(audio_path),
            "real_duration": real_dur,
            "stats": stats
        }


# ─────────────────────────────────────────────────────────
# SECTION 4: BACKEND AUTO-DETECTOR
# ─────────────────────────────────────────────────────────

def auto_detect_backend(config_path: str = "config.json") -> LLMBackend:
    """
    Tự động phát hiện LLM backend khả dụng theo thứ tự ưu tiên:
    1. DeepSeek (rẻ nhất, tiếng Việt tốt)
    2. Gemini (miễn phí quota)
    3. Groq (siêu nhanh, miễn phí)
    4. OpenAI
    5. Ollama (local)
    6. FallbackTemplate (không cần API)
    """
    config = {}
    if os.path.exists(config_path):
        try:
            config = json.load(open(config_path, encoding='utf-8'))
        except Exception:
            pass

    # Ưu tiên 1: DeepSeek
    key = config.get("deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        print(f"[auto_detect] Dùng DeepSeek backend")
        return DeepSeekBackend(api_key=key)

    # Ưu tiên 2: Gemini
    key = config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if key:
        try:
            import google.generativeai
            print(f"[auto_detect] Dùng Gemini backend")
            return GeminiBackend(api_key=key)
        except ImportError:
            print("[auto_detect] google-generativeai chưa cài: pip install google-generativeai")

    # Ưu tiên 3: Groq
    key = config.get("groq_api_key") or os.environ.get("GROQ_API_KEY", "")
    if key:
        try:
            import groq
            print(f"[auto_detect] Dùng Groq backend")
            return GroqBackend(api_key=key)
        except ImportError:
            print("[auto_detect] groq chưa cài: pip install groq")

    # Ưu tiên 4: OpenAI
    key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
    if key:
        print(f"[auto_detect] Dùng OpenAI backend")
        return OpenAIBackend(api_key=key)

    # Ưu tiên 5: Ollama local
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        models = [m['name'] for m in r.json().get('models', [])]
        if models:
            chosen = models[0]
            print(f"[auto_detect] Dùng Ollama local, model: {chosen}")
            return OllamaBackend(model=chosen)
    except Exception:
        pass

    # Fallback cuối cùng
    print("[auto_detect] Không tìm thấy LLM API — dùng FallbackTemplate (không cần API)")
    return FallbackTemplateBackend()


# ─────────────────────────────────────────────────────────
# SECTION 5: ENTRY POINT
# ─────────────────────────────────────────────────────────

async def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="NovelScriptGenerator — Đọc chương → Kịch bản thuyết minh → Audio"
    )
    # Chế độ nội dung
    parser.add_argument("--mode", choices=["raw", "detailed", "standard", "short"],
                        default=None, help="Chế độ: raw (nguyên tác), detailed (15-30p), standard (8-12p), short (3-5p)")
    parser.add_argument("--auto-span", action="store_true",
                        help="Tự động gom chương từ ch-start đến khi đủ thời lượng mong muốn")

    # Nguồn dữ liệu
    parser.add_argument("--chapters-dir", default=r"data/novels/Pham nhan tu tien/chapters",
                        help="Thư mục chứa file chương .md")
    parser.add_argument("--ch-start", type=int, help="Số chương bắt đầu (vd: 736)")
    parser.add_argument("--ch-end", type=int, help="Số chương kết thúc (vd: 740)")
    parser.add_argument("--direct-file", help="Đọc trực tiếp từ 1 file .md/.txt")

    # Thông tin tập
    parser.add_argument("--episode", type=int, default=191, help="Số tập (vd: 191)")
    parser.add_argument("--title", default="Đại Chiến Hoàng Long Sơn", help="Tên tập")
    parser.add_argument("--next-ep", type=int, help="Số tập tiếp theo cho outro")

    # Cài đặt chất lượng
    parser.add_argument("--duration", type=float, default=None,
                        help="Thời lượng mục tiêu (phút, mặc định theo config hoặc 15)")
    parser.add_argument("--scenes", type=int, default=25,
                        help="Số phân đoạn kịch bản (mặc định 25)")

    # LLM backend
    parser.add_argument("--backend", choices=["auto", "deepseek", "gemini", "groq", "openai", "ollama", "template"],
                        default="auto", help="LLM backend (mặc định: auto-detect)")
    parser.add_argument("--api-key", help="API key (nếu không set trong config.json hay env)")
    parser.add_argument("--ollama-model", default="gemma3:4b", help="Model Ollama")

    # Output
    parser.add_argument("--output-dir", default="data/outputs/novel_audio/Auto_Pipeline",
                        help="Thư mục lưu output")
    parser.add_argument("--tts-voice", default="vi-VN-NamMinhNeural", help="Giọng TTS")
    parser.add_argument("--tts-rate", default="+5%", help="Tốc độ TTS")
    parser.add_argument("--config", default="config.json", help="File config")

    args = parser.parse_args()

    # Khởi tạo backend (nếu mode là raw thì không cần LLM)
    if args.mode == "raw":
        backend = FallbackTemplateBackend()
    elif args.backend == "auto":
        backend = auto_detect_backend(args.config)
    elif args.backend == "deepseek":
        key = args.api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        backend = DeepSeekBackend(api_key=key)
    elif args.backend == "gemini":
        key = args.api_key or os.environ.get("GEMINI_API_KEY", "")
        backend = GeminiBackend(api_key=key)
    elif args.backend == "groq":
        key = args.api_key or os.environ.get("GROQ_API_KEY", "")
        backend = GroqBackend(api_key=key)
    elif args.backend == "openai":
        key = args.api_key or os.environ.get("OPENAI_API_KEY", "")
        backend = OpenAIBackend(api_key=key)
    elif args.backend == "ollama":
        backend = OllamaBackend(model=args.ollama_model)
    else:
        backend = FallbackTemplateBackend()

    # Khởi tạo generator từ config với các overrides
    overrides = {}
    if args.mode:
        overrides["mode"] = args.mode
    if args.duration is not None:
        overrides["duration"] = args.duration
    if args.tts_voice:
        overrides["tts_voice"] = args.tts_voice
    if args.tts_rate:
        overrides["tts_rate"] = args.tts_rate
    if args.output_dir:
        overrides["output_dir"] = args.output_dir

    generator = NovelScriptGenerator.from_config(
        config_path=args.config,
        backend=backend,
        **overrides
    )

    # Chạy pipeline
    result = await generator.run(
        episode=args.episode,
        title=args.title,
        chapters_dir=args.chapters_dir if args.ch_start else None,
        ch_start=args.ch_start,
        ch_end=args.ch_end,
        direct_file=args.direct_file,
        num_scenes=args.scenes,
        next_ep=args.next_ep,
        auto_span=args.auto_span
    )

    print(f"\n{'='*60}")
    print("=== KẾT QUẢ PIPELINE ===")
    print(f"  Chế độ         : {result['mode'].upper()}")
    print(f"  Backend LLM    : {result['backend']}")
    print(f"  Từ kịch bản    : {result['stats']['total_words']} từ")
    print(f"  Thời lượng ước : {result['stats']['estimated_minutes']:.1f} phút")
    print(f"  Thời lượng thật: {result['real_duration']}")
    print(f"  Kịch bản       : {result['script_path']}")
    print(f"  Audio          : {result['audio_path']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
