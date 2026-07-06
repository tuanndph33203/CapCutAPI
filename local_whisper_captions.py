import json
import os
import subprocess
import tempfile
import site
import copy
from pathlib import Path
from typing import Callable, Iterable

import pyJianYingDraft as draft

_WHISPER_MODEL_CACHE = {}


def _format_ts(seconds: float) -> str:
    total_ms = max(0, round(float(seconds or 0.0) * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{millis:03d}"


def segments_to_srt(segments: Iterable[dict]) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = _format_ts(segment.get("start", 0))
        end = _format_ts(segment.get("end", segment.get("start", 0)))
        blocks.append(f"{len(blocks) + 1}\n{start} --> {end}\n{text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def segments_to_numbered_text(segments: Iterable[dict]) -> str:
    lines = []
    for segment in segments:
        segment_id = segment.get("id")
        start = float(segment.get("start", 0) or 0)
        end = float(segment.get("end", 0) or 0)
        text = str(segment.get("text") or "").strip()
        lines.append(f"{segment_id}. [{start:.2f}-{end:.2f}] {text}")
    return "\n".join(lines) + ("\n" if lines else "")


def _prepend_nvidia_dll_dirs_to_path() -> list[str]:
    added = []
    candidates = []
    for site_dir in site.getsitepackages():
        root = Path(site_dir)
        candidates.extend([
            root / "nvidia" / "cublas" / "bin",
            root / "nvidia" / "cudnn" / "bin",
            root / "nvidia" / "cuda_nvrtc" / "bin",
            root / "ctranslate2",
        ])

    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    existing_lower = {part.lower() for part in path_parts if part}
    for candidate in candidates:
        if not candidate.exists():
            continue
        candidate_str = str(candidate)
        if candidate_str.lower() in existing_lower:
            continue
        os.environ["PATH"] = candidate_str + os.pathsep + os.environ.get("PATH", "")
        added.append(candidate_str)
    return added


def _path_has_cuda_runtime() -> bool:
    _prepend_nvidia_dll_dirs_to_path()
    found = set()
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if not folder:
            continue
        try:
            existing = {path.name.lower() for path in Path(folder).glob("*.dll")}
        except Exception:
            continue
        if "cublas64_12.dll" in existing:
            found.add("cublas")
        if any(name in existing for name in ("cudnn64_9.dll", "cudnn_ops64_9.dll")):
            found.add("cudnn")
    return {"cublas", "cudnn"}.issubset(found)


def _build_atempo_filter(speed: float) -> str:
    filters = []
    tempo = float(speed or 1.0)
    while tempo > 2.0:
        filters.append("atempo=2.0")
        tempo /= 2.0
    while tempo < 0.5:
        filters.append("atempo=0.5")
        tempo /= 0.5
    if abs(tempo - 1.0) > 0.001:
        filters.append(f"atempo={tempo}")
    return ",".join(filters)


def transcribe_video_to_segments(
    video_path: str | os.PathLike,
    *,
    language: str = "zh",
    speed: float = 1.0,
    model_size: str | None = None,
    device: str | None = None,
    compute_type: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[list[dict], dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Chưa cài faster-whisper. Chạy: python -m pip install faster-whisper==1.1.0"
        ) from exc

    model_size = model_size or os.environ.get("WHISPER_MODEL", "large-v3-turbo")
    device = device or os.environ.get("WHISPER_DEVICE", "cuda")
    added_dll_dirs = _prepend_nvidia_dll_dirs_to_path()
    if added_dll_dirs and progress_callback:
        progress_callback(f"Đã thêm NVIDIA DLL dirs vào PATH: {'; '.join(added_dll_dirs)}")

    if device == "cuda" and not _path_has_cuda_runtime():
        if progress_callback:
            progress_callback("Không thấy CUDA/cuBLAS runtime trong PATH, dùng CPU int8 cho Whisper.")
        device = "cpu"
    compute_type = compute_type or os.environ.get(
        "WHISPER_COMPUTE_TYPE",
        "float16" if device == "cuda" else "int8",
    )
    if device == "cpu" and compute_type in {"float16", "float32"}:
        compute_type = "int8"

    def load_model(model_device: str, model_compute_type: str):
        cache_key = (model_size, model_device, model_compute_type)
        if cache_key in _WHISPER_MODEL_CACHE:
            return _WHISPER_MODEL_CACHE[cache_key]
        if progress_callback:
            progress_callback(
                f"Đang load faster-whisper model={model_size}, "
                f"device={model_device}, compute={model_compute_type}..."
            )
        loaded_model = WhisperModel(model_size, device=model_device, compute_type=model_compute_type)
        _WHISPER_MODEL_CACHE[cache_key] = loaded_model
        return loaded_model

    model = load_model(device, compute_type)
    kwargs = {
        "language": language or "zh",
        "vad_filter": True,
        "word_timestamps": True,
        "beam_size": 5,
        "condition_on_previous_text": True,
        "temperature": [0.0, 0.2, 0.4],
        "hallucination_silence_threshold": 1.0,
        "vad_parameters": {
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 200,
        },
    }

    transcribe_path = str(video_path)
    temp_audio_path = None
    try:
        speed = float(speed or 1.0)
    except Exception:
        speed = 1.0
    if abs(speed - 1.0) > 0.001:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_audio_path = temp_file.name
        temp_file.close()
        if progress_callback:
            progress_callback(f"Đang trích audio đã làm chậm speed={speed} trước khi Whisper...")
        atempo_filter = _build_atempo_filter(speed)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-filter:a",
                atempo_filter,
                "-ac",
                "1",
                "-ar",
                "16000",
                temp_audio_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        transcribe_path = temp_audio_path

    if progress_callback:
        progress_callback(f"Đang chạy Whisper local cho audio/video: {transcribe_path}")

    def execute_transcribe(active_model):
        generated_segments, generated_info = active_model.transcribe(transcribe_path, **kwargs)
        return list(generated_segments), generated_info

    raw_segment_objects = []
    info = None
    filtered_counts = {}
    try:
        try:
            raw_segment_objects, info = execute_transcribe(model)
        except Exception as exc:
            message = str(exc)
            cuda_missing = (
                device == "cuda"
                and (
                    "cublas64" in message.lower()
                    or "cudnn" in message.lower()
                    or "cuda" in message.lower()
                    or "could not load library" in message.lower()
                )
            )
            if not cuda_missing:
                raise
            if progress_callback:
                progress_callback(
                    f"GPU Whisper lỗi CUDA ({message}). Fallback sang CPU int8 để không chết pipeline..."
                )
            device = "cpu"
            compute_type = "int8"
            model = load_model(device, compute_type)
            raw_segment_objects, info = execute_transcribe(model)
        info_duration = float(getattr(info, "duration", 0.0) or 0.0)
        max_allowed_end = info_duration + 1.0 if info_duration > 0 else None
        segments = []
        all_raw_segments = []
        filtered_counts = {
            "empty": 0,
            "beyond_duration": 0,
            "low_logprob": 0,
            "high_temperature": 0,
            "high_no_speech": 0,
            "high_compression": 0,
            "repeat_tail": 0,
        }
        recent_texts = []
        strict_filter = os.environ.get("CAPCUT_WHISPER_STRICT_FILTER", "true").strip().lower() in {
            "1", "true", "yes", "on"
        }
        for segment in raw_segment_objects:
            text = (segment.text or "").strip()
            start = float(segment.start or 0.0)
            end = float(segment.end or segment.start or 0.0)
            avg_logprob = getattr(segment, "avg_logprob", None)
            temperature = float(getattr(segment, "temperature", 0.0) or 0.0)
            no_speech_prob = getattr(segment, "no_speech_prob", None)
            compression_ratio = getattr(segment, "compression_ratio", None)

            words = []
            for word in getattr(segment, "words", None) or []:
                word_text = str(getattr(word, "word", "") or "").strip()
                if not word_text:
                    continue
                words.append({
                    "start": float(getattr(word, "start", 0.0) or 0.0),
                    "end": float(getattr(word, "end", 0.0) or 0.0),
                    "word": word_text,
                    "probability": float(getattr(word, "probability", 0.0) or 0.0),
                })

            raw_seg_dict = {
                "id": len(all_raw_segments) + 1,
                "raw_id": int(getattr(segment, "id", len(all_raw_segments) + 1)),
                "start": start,
                "end": end,
                "text": text,
                "avg_logprob": float(avg_logprob) if avg_logprob is not None else None,
                "temperature": temperature,
                "no_speech_prob": float(no_speech_prob) if no_speech_prob is not None else None,
                "compression_ratio": float(compression_ratio) if compression_ratio is not None else None,
                "words": words,
            }
            all_raw_segments.append(raw_seg_dict)

            # Apply filters
            if not text:
                filtered_counts["empty"] += 1
                continue

            if max_allowed_end is not None and (start > max_allowed_end or end > max_allowed_end):
                filtered_counts["beyond_duration"] += 1
                continue

            suspicious_reasons = []
            if avg_logprob is not None and float(avg_logprob) < -1.25:
                suspicious_reasons.append("low_logprob")
            if temperature >= 0.8:
                suspicious_reasons.append("high_temperature")
            if no_speech_prob is not None and float(no_speech_prob) > 0.75:
                suspicious_reasons.append("high_no_speech")
            if compression_ratio is not None and float(compression_ratio) > 2.8:
                suspicious_reasons.append("high_compression")
            if text in recent_texts[-3:]:
                suspicious_reasons.append("repeat_tail")

            if strict_filter and len(suspicious_reasons) >= 2:
                for reason in suspicious_reasons:
                    filtered_counts[reason] = filtered_counts.get(reason, 0) + 1
                continue

            recent_texts.append(text)
            if len(recent_texts) > 6:
                recent_texts = recent_texts[-6:]

            filtered_seg = copy.deepcopy(raw_seg_dict)
            filtered_seg["id"] = len(segments) + 1
            segments.append(filtered_seg)
    finally:
        if temp_audio_path:
            try:
                os.unlink(temp_audio_path)
            except OSError:
                pass

    if abs(speed - 1.0) > 0.001:
        for seg in segments:
            seg["start"] *= speed
            seg["end"] *= speed
            for word in seg.get("words") or []:
                word["start"] *= speed
                word["end"] *= speed
        for seg in all_raw_segments:
            seg["start"] *= speed
            seg["end"] *= speed
            for word in seg.get("words") or []:
                word["start"] *= speed
                word["end"] *= speed

    if progress_callback:
        progress_callback(
            f"Whisper hoàn thành: {len(segments)} dòng, language={getattr(info, 'language', '')}, "
            f"duration={round(float(getattr(info, 'duration', 0.0) or 0.0), 2)}s."
        )
    if progress_callback:
        removed = {key: value for key, value in filtered_counts.items() if value}
        if removed:
            progress_callback(
                f"Whisper filter: kept={len(segments)}/{len(raw_segment_objects)}, removed={removed}"
            )

    raw_output = {
        "info_repr": repr(info),
        "segments_repr": [repr(segment) for segment in raw_segment_objects],
        "filtered_counts": filtered_counts,
        "all_raw_segments": all_raw_segments,
    }
    return segments, raw_output


def _import_srt_to_content(
    content_path: Path,
    srt_text: str,
    *,
    font: str | None,
    font_size: float,
    font_color: str,
    width: int,
    height: int,
    track_name: str = "subtitle",
) -> int:
    script = draft.Script_file.load_template(str(content_path))
    before = len((script.content.get("materials") or {}).get("texts") or [])
    font = _normalize_font_name(font)
    script.import_srt(
        srt_text,
        track_name=track_name,
        time_offset=0,
        text_style=draft.Text_style(
            size=font_size,
            color=_hex_to_rgb(font_color),
            align=1,
            vertical=False,
            alpha=1.0,
        ),
        font=font,
        clip_settings=draft.Clip_settings(transform_x=0.0, transform_y=-0.8),
        border=draft.Text_border(alpha=1.0, color=(0.0, 0.0, 0.0), width=0.08),
    )
    script.width = width
    script.height = height
    script.dump(str(content_path))
    after_data = json.loads(content_path.read_text(encoding="utf-8"))
    after = len((after_data.get("materials") or {}).get("texts") or [])
    return max(0, after - before)


def _find_primary_draft_json(draft_path: Path) -> Path:
    for name in ("draft_content.json", "draft_info.json"):
        candidate = draft_path / name
        if candidate.exists() and candidate.is_file():
            return candidate
    for candidate in sorted(draft_path.glob("template-*.tmp")):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"Không tìm thấy draft_content.json/draft_info.json/template-*.tmp trong {draft_path}"
    )


def _normalize_font_name(font: str | None) -> str:
    if not font:
        return "HarmonyOS_Sans_SC_Regular"
    font_value = str(font).strip()
    if not font_value:
        return "HarmonyOS_Sans_SC_Regular"
    if "/" in font_value or "\\" in font_value or font_value.lower().endswith((".ttf", ".otf")):
        return "HarmonyOS_Sans_SC_Regular"
    return font_value


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = str(value or "#FFFFFF").strip().lstrip("#")
    if len(value) != 6:
        value = "FFFFFF"
    return (
        int(value[0:2], 16) / 255.0,
        int(value[2:4], 16) / 255.0,
        int(value[4:6], 16) / 255.0,
    )


def calculate_pause(
    current_segment: dict,
    next_segment: dict,
) -> float:
    current_words = current_segment.get("words") or []
    next_words = next_segment.get("words") or []

    current_end = (
        current_words[-1]["end"]
        if current_words
        else current_segment["end"]
    )

    next_start = (
        next_words[0]["start"]
        if next_words
        else next_segment["start"]
    )

    return max(0.0, float(next_start) - float(current_end))


def _do_merge(s1: dict, s2: dict) -> dict:
    text1 = s1.get("text", "").strip()
    text2 = s2.get("text", "").strip()
    
    import re
    if re.search(r'[a-zA-Z0-9]$', text1) and re.match(r'^[a-zA-Z0-9]', text2):
        combined_text = f"{text1} {text2}"
    else:
        combined_text = f"{text1}{text2}"
        
    words1 = s1.get("words") or []
    words2 = s2.get("words") or []
    combined_words = words1 + words2
    
    return {
        "id": s1.get("id"),
        "raw_id": s1.get("raw_id"),
        "start": s1["start"],
        "end": s2["end"],
        "text": combined_text,
        "avg_logprob": s1.get("avg_logprob"),
        "temperature": s1.get("temperature"),
        "no_speech_prob": s1.get("no_speech_prob"),
        "compression_ratio": s1.get("compression_ratio"),
        "words": combined_words,
    }


def ask_ai_to_split(s1: dict, s2: dict) -> bool:
    import urllib.request
    
    # Fallback to local heuristic if no API key is present
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        text1 = s1.get("text", "").strip()
        if text1 and text1[-1] in {".", "?", "!", "。", "？", "！"}:
            return True
        if len(text1) > 20:
            return True
        return False
        
    text1 = s1.get("text", "").strip()
    text2 = s2.get("text", "").strip()
    
    prompt = (
        "Decide whether to merge these two consecutive speech transcription segments into one sentence, "
        "or split them (meaning they are separate sentences or have a clear boundary).\n"
        f"Segment 1: \"{text1}\"\n"
        f"Segment 2: \"{text2}\"\n\n"
        "Reply with exactly one word: 'SPLIT' or 'MERGE' (do not include any other text or punctuation)."
    )
    
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 5
                }
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                text_response = res_data["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
                if "SPLIT" in text_response:
                    return True
                if "MERGE" in text_response:
                    return False
        except Exception:
            pass
            
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_key}"
            }
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.0,
                "max_tokens": 5
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                text_response = res_data["choices"][0]["message"]["content"].strip().upper()
                if "SPLIT" in text_response:
                    return True
                if "MERGE" in text_response:
                    return False
        except Exception:
            pass
            
    # Default fallback
    if text1 and text1[-1] in {".", "?", "!", "。", "？", "！"}:
        return True
    if len(text1) > 20:
        return True
    return False


def merge_segments_with_ai(
    raw_segments: list[dict],
    progress_callback: Callable[[str], None] | None = None
) -> list[dict]:
    if not raw_segments:
        return []

    if progress_callback:
        progress_callback("Đang tiến hành ghép các segment thô thành câu hoàn chỉnh...")

    merged = []
    current = copy.deepcopy(raw_segments[0])
    
    for next_seg in raw_segments[1:]:
        pause = calculate_pause(current, next_seg)
        if pause >= 0.75:
            # Clear split
            merged.append(current)
            current = copy.deepcopy(next_seg)
        elif pause <= 0.12:
            # Clear merge
            current = _do_merge(current, next_seg)
        else:
            # Ambiguous: ask AI or use fallback
            should_split = ask_ai_to_split(current, next_seg)
            if should_split:
                merged.append(current)
                current = copy.deepcopy(next_seg)
            else:
                current = _do_merge(current, next_seg)
                
    merged.append(current)
    
    # Re-index the merged segments
    for idx, seg in enumerate(merged, start=1):
        seg["id"] = idx
        
    if progress_callback:
        progress_callback(f"Ghép câu thành công: từ {len(raw_segments)} segments thô còn {len(merged)} câu.")
        
    return merged


def patch_draft_with_local_whisper(
    *,
    draft_path: str | os.PathLike,
    draft_id: str,
    video_path: str | os.PathLike,
    repo_root: str | os.PathLike,
    language: str = "zh",
    speed: float = 1.0,
    font: str | None = None,
    font_size: float = 5.0,
    font_color: str = "#FFFFFF",
    width: int = 1920,
    height: int = 1080,
    progress_callback: Callable[[str], None] | None = None,
) -> dict:
    draft_path = Path(draft_path)
    repo_root = Path(repo_root)
    content_path = _find_primary_draft_json(draft_path)

    segments, raw_whisper_output = transcribe_video_to_segments(
        video_path,
        language=language,
        speed=speed,
        progress_callback=progress_callback,
    )
    if not segments:
        raise RuntimeError("Whisper không tạo ra dòng phụ đề nào.")

    raw_segments = segments
    merged_segments = merge_segments_with_ai(
        raw_segments,
        progress_callback=progress_callback,
    )

    duration = max((float(segment.get("end", 0) or 0) for segment in raw_segments), default=0.0)
    all_raw_segments = raw_whisper_output.get("all_raw_segments") or []

    unfiltered_whisper_dump = {
        "draft_id": draft_id,
        "video_path": str(video_path),
        "language": language,
        "speed": speed,
        "duration": duration,
        "segment_count": len(all_raw_segments),
        "raw_segment_count": len(raw_whisper_output.get("segments_repr") or []),
        "filtered_counts": raw_whisper_output.get("filtered_counts") or {},
        "segments": all_raw_segments,
    }

    raw_whisper_dump = {
        "draft_id": draft_id,
        "video_path": str(video_path),
        "language": language,
        "speed": speed,
        "duration": duration,
        "segment_count": len(raw_segments),
        "raw_segment_count": len(raw_whisper_output.get("segments_repr") or []),
        "filtered_counts": raw_whisper_output.get("filtered_counts") or {},
        "segments": raw_segments,
    }

    merged_whisper_dump = {
        "draft_id": draft_id,
        "video_path": str(video_path),
        "language": language,
        "speed": speed,
        "duration": duration,
        "segment_count": len(merged_segments),
        "raw_segment_count": len(raw_whisper_output.get("segments_repr") or []),
        "filtered_counts": raw_whisper_output.get("filtered_counts") or {},
        "segments": merged_segments,
    }

    dump_unfiltered_json = draft_path / "whisper_unfiltered_segments.json"
    dump_raw_json = draft_path / "whisper_raw_segments.json"
    dump_merged_json = draft_path / "whisper_merged_segments.json"
    dump_txt = draft_path / "whisper_segments_for_ai.txt"
    dump_raw_txt = draft_path / "whisper_raw_segments_numbered.txt"
    dump_raw = draft_path / "whisper_raw_object_repr.txt"
    
    dump_unfiltered_json.write_text(json.dumps(unfiltered_whisper_dump, ensure_ascii=False, indent=2), encoding="utf-8")
    dump_raw_json.write_text(json.dumps(raw_whisper_dump, ensure_ascii=False, indent=2), encoding="utf-8")
    dump_merged_json.write_text(json.dumps(merged_whisper_dump, ensure_ascii=False, indent=2), encoding="utf-8")
    dump_txt.write_text(segments_to_numbered_text(merged_segments), encoding="utf-8")
    dump_raw_txt.write_text(segments_to_numbered_text(raw_segments), encoding="utf-8")
    dump_raw.write_text(
        "INFO\n"
        f"{raw_whisper_output.get('info_repr', '')}\n\n"
        "SEGMENTS\n"
        + "\n".join(raw_whisper_output.get("segments_repr") or [])
        + "\n",
        encoding="utf-8",
    )

    logs_dir = repo_root / "logs" / "whisper"
    logs_dir.mkdir(parents=True, exist_ok=True)
    safe_video_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in Path(video_path).stem)[:80]
    log_base = logs_dir / f"{draft_id}_{safe_video_name}"
    
    log_base.with_suffix(".unfiltered.json").write_text(
        json.dumps(unfiltered_whisper_dump, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log_base.with_suffix(".raw.json").write_text(
        json.dumps(raw_whisper_dump, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log_base.with_suffix(".merged.json").write_text(
        json.dumps(merged_whisper_dump, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log_base.with_suffix(".segments.txt").write_text(segments_to_numbered_text(merged_segments), encoding="utf-8")
    log_base.with_suffix(".raw_object.txt").write_text(
        "INFO\n"
        f"{raw_whisper_output.get('info_repr', '')}\n\n"
        "SEGMENTS\n"
        + "\n".join(raw_whisper_output.get("segments_repr") or [])
        + "\n",
        encoding="utf-8",
    )
    if progress_callback:
        progress_callback(f"Đã lưu output Whisper để test ghép câu: {log_base.with_suffix('.unfiltered.json')}")

    srt_text_raw = segments_to_srt(raw_segments)
    srt_text_merged = segments_to_srt(merged_segments)
    
    srt_path_raw = draft_path / "whisper_zh_raw.srt"
    srt_path_merged = draft_path / "whisper_zh_merged.srt"
    srt_path = draft_path / "whisper_zh.srt"

    srt_path_raw.write_text(srt_text_raw, encoding="utf-8")
    srt_path_merged.write_text(srt_text_merged, encoding="utf-8")
    srt_path.write_text(srt_text_merged, encoding="utf-8")

    added = _import_srt_to_content(
        content_path,
        srt_text_merged,
        font=font,
        font_size=font_size,
        font_color=font_color,
        width=width,
        height=height,
    )

    repo_draft_path = repo_root / draft_id
    repo_content_path = repo_draft_path / content_path.name
    if repo_content_path.exists():
        repo_content_path.write_text(content_path.read_text(encoding="utf-8"), encoding="utf-8")
        (repo_draft_path / "whisper_zh_raw.srt").write_text(srt_text_raw, encoding="utf-8")
        (repo_draft_path / "whisper_zh_merged.srt").write_text(srt_text_merged, encoding="utf-8")
        (repo_draft_path / "whisper_zh.srt").write_text(srt_text_merged, encoding="utf-8")

    return {
        "segments": len(merged_segments),
        "added_texts": added,
        "srt_path": str(srt_path),
        "content_path": str(content_path),
    }
