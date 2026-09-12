# -*- coding: utf-8 -*-
"""
AI-Powered Subtitle Chunker & Timeline Arranger for Video Recaps.
Designed to create rhythmically spoken, bite-sized, single-line subtitles
that sync with speech audio and avoid overflowing screen borders or appearing
as contiguous blocks on the timeline.
"""

import os
import re
import json
from typing import List, Dict, Any, Optional

class AISubtitleChunker:
    """
    Intelligent subtitle chunker and aligner.
    
    Rules:
    1. Maximum words per phrase: 4 to 6 words (hard cap 7).
    2. Maximum characters per phrase: 20 to 32 chars (hard cap 35) to fit 1 clean line in 16:9 1080p.
    3. Proper Entity Preservation: Never split inside Vietnamese capitalized names (e.g. Hàn Lập, Mộ Bái Linh).
    4. Conjunction Splitting: Prefers splitting before natural connectives (và, nhưng, rồi, mà, để, khi, etc.).
    5. Non-Contiguous Timeline: Enforces a clean 0.05s - 0.08s inter-phrase gap between subtitle blocks.
    6. Silence Truncation: Caps subtitle duration so it never lingers across speech pauses.
    """

    CONJUNCTIONS = {
        'và', 'nhưng', 'rồi', 'mà', 'hoặc', 'hay', 'để', 'khi', 'lúc', 'nếu', 'thì',
        'vì', 'do', 'bởi', 'tuy', 'rằng', 'là', 'như', 'với', 'cho', 'trong', 'tại',
        'sau', 'trước', 'ngay', 'khiến', 'giúp', 'chẳng', 'không', 'vừa', 'đã', 'liền'
    }

    COMPOUND_MARKERS = [
        'sau khi', 'trước khi', 'ngay khi', 'tuy nhiên', 'bởi vì', 'cho nên', 'thậm chí',
        'chẳng trách', 'không khỏi', 'đồng thời', 'mặc dù', 'khiến cho', 'đến mức', 'vô cùng'
    ]

    def __init__(
        self,
        max_words: int = 6,
        max_chars: int = 32,
        min_words: int = 3,
        inter_phrase_gap: float = 0.06
    ):
        self.max_words = max_words
        self.max_chars = max_chars
        self.min_words = min_words
        self.inter_phrase_gap = inter_phrase_gap

    def is_capitalized(self, word: str) -> bool:
        clean = re.sub(r'^[^\w]+|[^\w]+$', '', word)
        return bool(clean and clean[0].isupper())

    def split_clause_into_phrases(self, clause: str) -> List[str]:
        words = clause.strip().split()
        if not words:
            return []

        # If already fits comfortably within limits
        if len(words) <= self.max_words and len(clause.strip()) <= self.max_chars:
            return [clause.strip()]

        chunks = []
        i = 0
        n = len(words)

        while i < n:
            remaining = n - i
            if remaining <= self.max_words:
                sub_str = " ".join(words[i:n])
                if len(sub_str) <= self.max_chars or remaining <= 4:
                    chunks.append(sub_str)
                    break

            end = min(i + self.max_words, n)

            # Rule: Protect multi-word capitalized names/entities
            # If splitting inside capitalized consecutive words, adjust boundary
            if end < n and self.is_capitalized(words[end - 1]) and self.is_capitalized(words[end]):
                if end - i > self.min_words:
                    end -= 1
                elif end + 1 <= n and (end + 1 - i) <= self.max_words + 1:
                    end += 1

            # Rule: Prefer breaking before conjunctions/discourse markers
            best_split = None
            for j in range(end, max(i + self.min_words, end - 3), -1):
                if j < n:
                    two_w = f"{words[j-1].lower()} {words[j].lower()}" if j > i else ""
                    if any(two_w.endswith(m) for m in self.COMPOUND_MARKERS):
                        best_split = j - 1
                        break
                    if words[j].lower() in self.CONJUNCTIONS:
                        best_split = j
                        break

            if best_split and best_split > i + 1:
                end = best_split

            chunk_str = " ".join(words[i:end]).strip()
            if chunk_str:
                chunks.append(chunk_str)
            i = end

        return chunks

    def chunk_text(self, text: str) -> List[str]:
        """
        Split arbitrary paragraph/script text into bite-sized subtitle phrases.
        """
        clean_text = re.sub(r'\[\d+(?:\.\d+)?\]', '', text).strip()
        if not clean_text:
            return []

        # 1. Split on punctuation
        raw_clauses = re.split(r'(?<=[,;.!?…–—])\s+', clean_text)
        phrases = []
        for clause in raw_clauses:
            clause = clause.strip()
            if not clause:
                continue
            sub_phrases = self.split_clause_into_phrases(clause)
            phrases.extend(sub_phrases)

        return phrases

    def count_syllables(self, text: str) -> float:
        words = [w for w in text.split() if any(c.isalnum() for c in w)]
        punc_weight = (
            text.count(',') * 0.8 +
            text.count(';') * 1.0 +
            text.count('.') * 1.2 +
            text.count('!') * 1.2 +
            text.count('?') * 1.2
        )
        return max(1.0, len(words) + punc_weight)

    def align_sentence_proportional(
        self,
        sentence_text: str,
        start_sec: float,
        duration_sec: float
    ) -> List[Dict[str, Any]]:
        """
        Divide a sentence into short phrases and distribute duration
        proportionally according to syllable and pause weights,
        enforcing inter-phrase gaps.
        """
        phrases = self.chunk_text(sentence_text)
        if not phrases:
            return []

        if len(phrases) == 1:
            end_t = start_sec + duration_sec
            return [{
                "text": phrases[0],
                "start": round(start_sec, 3),
                "end": round(end_t, 3),
                "duration": round(duration_sec, 3),
                "words": len(phrases[0].split())
            }]

        weights = [self.count_syllables(p) for p in phrases]
        total_weight = sum(weights)

        res = []
        cur_t = start_sec
        gap = self.inter_phrase_gap

        for idx, (p, w) in enumerate(zip(phrases, weights)):
            p_dur = duration_sec * (w / total_weight)
            p_start = cur_t
            p_end = p_start + p_dur

            # Cut off end slightly for inter-phrase gap on timeline
            if idx < len(phrases) - 1:
                p_display_end = min(p_end - 0.01, max(p_start + 0.05, p_end - gap))
            else:
                p_display_end = p_end

            res.append({
                "text": p,
                "start": round(p_start, 3),
                "end": round(p_display_end, 3),
                "duration": round(p_display_end - p_start, 3),
                "words": len(p.split())
            })
            cur_t = p_end

        return res

    def align_script_with_whisper(
        self,
        script_text: str,
        whisper_words: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Align script phrases with Whisper word-level timestamps.
        Ensures high accuracy, avoids stretching across pauses,
        and enforces inter-phrase timeline separation.
        """
        lines = [
            l.strip() for l in script_text.splitlines()
            if l.strip() and not re.match(r'^\[\d+(?:\.\d+)?\]$', l.strip())
        ]

        all_phrases = []
        for line in lines:
            all_phrases.extend(self.chunk_text(line))

        phrase_items = []
        total_w = len(whisper_words)
        phrase_word_counts = [len(p.split()) for p in all_phrases]
        total_script_words = max(1, sum(phrase_word_counts))
        rho = total_w / total_script_words

        cum_w = 0
        for idx, (phrase, count) in enumerate(zip(all_phrases, phrase_word_counts)):
            s_idx = min(int(round(cum_w * rho)), total_w - 1)
            e_idx = min(max(s_idx + 1, int(round((cum_w + count) * rho))), total_w)

            p_start = whisper_words[s_idx]["start"]
            p_end = whisper_words[e_idx - 1]["end"]

            dur = max(0.25, p_end - p_start)
            phrase_items.append({
                "id": idx + 1,
                "text": phrase,
                "start": round(p_start, 3),
                "end": round(p_start + dur, 3),
                "duration": round(dur, 3),
                "words": count
            })
            cum_w += count

        # Enforce timeline gaps so blocks are visually separate and NEVER overlap
        MIN_GAP = self.inter_phrase_gap
        for i in range(len(phrase_items) - 1):
            c_start = phrase_items[i]["start"]
            n_start = phrase_items[i+1]["start"]
            if n_start < c_start + 0.25:
                phrase_items[i+1]["start"] = round(c_start + 0.25 + MIN_GAP, 3)
                n_start = phrase_items[i+1]["start"]
            max_allowed = max(0.15, n_start - MIN_GAP - c_start)
            phrase_items[i]["duration"] = round(min(phrase_items[i]["duration"], max_allowed), 3)
            phrase_items[i]["end"] = round(phrase_items[i]["start"] + phrase_items[i]["duration"], 3)

        return phrase_items

    @staticmethod
    def format_ts(sec: float) -> str:
        total_ms = max(0, round(float(sec) * 1000))
        h, rem = divmod(total_ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def write_srt(self, items: List[Dict[str, Any]], out_path: str) -> None:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            for idx, it in enumerate(items, start=1):
                f.write(f"{idx}\n")
                f.write(f"{self.format_ts(it['start'])} --> {self.format_ts(it['end'])}\n")
                f.write(f"{it['text']}\n\n")

# Global singleton instance
chunker = AISubtitleChunker()
