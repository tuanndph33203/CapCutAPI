import os
import sys
import json
import uuid
import wave
import shutil
import logging
from typing import Dict, List, Any, Optional

# Ensure UTF-8 output encoding for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from nghitts_service import generate_nghitts

logger = logging.getLogger("OfflineTTSPatcher")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s][%(levelname)s][OfflineTTS] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

def get_draft_json_paths(draft_path: str) -> List[str]:
    """Find all draft_content.json, draft_info.json, and .tmp timeline files in a draft directory."""
    paths = []
    for root, _, files in os.walk(draft_path):
        for file in files:
            if file in ("draft_content.json", "draft_info.json") or file.endswith(".tmp"):
                file_path = os.path.join(root, file)
                if file_path not in paths:
                    paths.append(file_path)

    # Sort paths so draft_content.json and .tmp files are always processed FIRST before draft_info.json
    paths.sort(key=lambda p: (0 if ("draft_content.json" in p or p.endswith(".tmp")) else 1, p))
    return paths

def get_wav_duration_us(wav_path: str) -> int:
    """Get WAV audio duration in microseconds."""
    with wave.open(wav_path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return int((frames / float(rate)) * 1_000_000)

def is_vietnamese_text(text: str) -> bool:
    """Check if string contains Vietnamese diacritics."""
    vietnamese_chars = set("àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ")
    return any(c in vietnamese_chars for c in text)

def extract_text_segments_from_draft(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract text materials and their segment timing from the main translated subtitle track.
    """
    materials = data.get("materials", {})
    texts_list = materials.get("texts", [])
    text_map = {}

    for t in texts_list:
        mat_id = t.get("id")
        text_content = ""
        content_str = t.get("content", "")
        if isinstance(content_str, str) and content_str.startswith("{"):
            try:
                parsed = json.loads(content_str)
                text_content = parsed.get("text", "")
            except Exception:
                text_content = t.get("recognize_text") or t.get("text") or ""
        else:
            text_content = t.get("recognize_text") or t.get("text") or ""

        if mat_id and text_content:
            text_map[mat_id] = text_content

    # Find the best target text track (prefer track named 'subtitle' or track containing Vietnamese text)
    text_tracks = [tr for tr in data.get("tracks", []) if tr.get("type") == "text"]
    if not text_tracks:
        return []

    target_track = None
    best_vi_count = -1

    for tr in text_tracks:
        tr_name = str(tr.get("name") or "").lower()
        segs = tr.get("segments", [])
        vi_count = sum(1 for s in segs if is_vietnamese_text(text_map.get(s.get("material_id"), "")))
        
        # Priority: named 'subtitle' or track with highest Vietnamese segment count
        if tr_name in ("subtitle", "subtitles", "phụ đề"):
            target_track = tr
            break
        elif vi_count > best_vi_count:
            best_vi_count = vi_count
            target_track = tr

    if not target_track:
        target_track = text_tracks[0]

    segments_info = []
    for seg in target_track.get("segments", []):
        mat_id = seg.get("material_id")
        text = text_map.get(mat_id)
        target_range = seg.get("target_timerange", {})
        start_us = target_range.get("start", 0)
        dur_us = target_range.get("duration", 0)

        if text and text.strip():
            segments_info.append({
                "text_material_id": mat_id,
                "text": text.strip(),
                "start_us": start_us,
                "duration_us": dur_us,
                "segment_id": seg.get("id")
            })

    # Sort segments strictly by start time
    segments_info.sort(key=lambda x: x["start_us"])
    return segments_info

def get_draft_id_from_meta(draft_path: str) -> str:
    """Read draft_id from draft_meta_info.json."""
    meta_path = os.path.join(draft_path, "draft_meta_info.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            return meta.get("draft_id", "")
        except Exception:
            pass
    return ""


import subprocess

def apply_deepfilternet3_ultra_clean(input_wav: str, output_wav: str, chunk_sec: int = 60) -> bool:
    """Run DeepFilterNet3 CUDA GPU Speech Denoising in memory-efficient chunks to destroy 100% background sounds."""
    try:
        import torch
        import numpy as np
        import soundfile as sf
        from df.enhance import init_df, enhance

        df_model, df_state, _ = init_df()
        sr = df_state.sr()
        info = sf.info(input_wav)
        chunk_samples = int(chunk_sec * info.samplerate)
        total_samples = info.frames

        enhanced_chunks = []
        with sf.SoundFile(input_wav) as f:
            while f.tell() < total_samples:
                block = f.read(chunk_samples, dtype='float32')
                if block.ndim == 2:
                    block = block.mean(axis=1)
                tensor = torch.from_numpy(block).unsqueeze(0)
                with torch.no_grad():
                    enhanced = enhance(df_model, df_state, tensor)
                enhanced_np = enhanced.squeeze(0).cpu().numpy()
                enhanced_chunks.append(enhanced_np)

        full_enhanced = np.concatenate(enhanced_chunks)
        sf.write(output_wav, full_enhanced, sr)
        return os.path.isfile(output_wav) and os.path.getsize(output_wav) > 0
    except Exception as e:
        logger.warning(f"[AudioFilter] DeepFilterNet3 chunked enhancement error: {e}")
        return False


def apply_copyright_safe_pitch_shift(input_wav: str, output_wav: str, pitch_factor: float = 1.05) -> str:
    """Biến dạng nhẹ tông giọng (Pitch Shift + Formant Equalizer) để lách bản quyền Content ID nhưng vẫn giữ nguyên 100% thời lượng."""
    try:
        cmd = [
            "ffmpeg", "-y", "-i", input_wav,
            "-af", f"asetrate=44100*{pitch_factor},atempo=1/{pitch_factor},aresample=44100,equalizer=f=1500:t=q:w=1:g=2.5",
            "-ar", "44100", "-ac", "2",
            output_wav
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        if os.path.isfile(output_wav) and os.path.getsize(output_wav) > 0:
            logger.info(f"[AudioFilter] Đã áp dụng lách bản quyền vân giọng (Pitch {pitch_factor}x + Formant Shift): {output_wav}")
            return output_wav
    except Exception as e:
        logger.warning(f"[AudioFilter] Lỗi khi biến dạng giọng lách bản quyền: {e}")
    return input_wav


def extract_filtered_vocal_audio(video_path: str, output_audio_dir: str = "output_audio") -> Optional[str]:
    """
    Trích xuất âm thanh từ video và lọc lấy duy nhất tiếng giọng nói (Vocal Isolation),
    bằng mô hình AI GPU Native Demucs CUDA + DeepFilterNet3 Ultra Denoising + Pitch Shift Lách Bản Quyền.
    """
    if not os.path.isfile(video_path):
        logger.error(f"[AudioFilter] Video file not found: {video_path}")
        return None

    output_dir = os.path.abspath(output_audio_dir)
    os.makedirs(output_dir, exist_ok=True)

    video_stem = os.path.splitext(os.path.basename(video_path))[0]
    safe_vocal_path = os.path.join(output_dir, f"copyright_safe_{video_stem}_vocal.wav")
    if os.path.isfile(safe_vocal_path) and os.path.getsize(safe_vocal_path) > 0:
        logger.info(f"[AudioFilter] Sử dụng file vocal AI Lách Bản Quyền đã tạo sẵn: {safe_vocal_path}")
        return safe_vocal_path

    df_clean_path = os.path.join(output_dir, f"ultra_clean_{video_stem}_vocal.wav")
    demucs_vocal_path = os.path.join(output_dir, "htdemucs", video_stem, "vocals.wav")

    # 0. Native PyTorch Demucs CUDA (GPU 100%, CPU < 5%)
    try:
        try:
            from local_whisper_captions import _prepend_nvidia_dll_dirs_to_path
            _prepend_nvidia_dll_dirs_to_path()
        except Exception:
            pass

        if not os.path.isfile(demucs_vocal_path):
            cmd_demucs = [
                sys.executable, "-m", "demucs.separate",
                "--two-stems=vocals",
                "-d", "cuda",
                "-o", output_dir,
                video_path
            ]
            logger.info(f"[AudioFilter] Đang chạy Native PyTorch Demucs CUDA GPU từ: {video_path}")
            subprocess.run(cmd_demucs, check=True)

        if os.path.isfile(demucs_vocal_path):
            logger.info(f"[AudioFilter] Tách vocal Demucs GPU thành công: {demucs_vocal_path}")
            # Áp dụng DeepFilterNet3 CUDA GPU Lọc Cực Hạn diệt 100% nhạc nền và tạp âm
            if not os.path.isfile(df_clean_path):
                logger.info(f"[AudioFilter] Đang áp dụng DeepFilterNet3 CUDA Lọc Cực Hạn 100% tạp âm...")
                apply_deepfilternet3_ultra_clean(demucs_vocal_path, df_clean_path)

            source_clean = df_clean_path if os.path.isfile(df_clean_path) else demucs_vocal_path
            # Áp dụng Lách Bản Quyền Vân Giọng (Pitch Shift + Formant)
            return apply_copyright_safe_pitch_shift(source_clean, safe_vocal_path)
    except Exception as demucs_err:
        logger.warning(f"[AudioFilter] Native Demucs CUDA GPU fallback: {demucs_err}")

    # 1. Fallback qua audio-separator neu installed
    try:
        from audio_separator.separator import Separator
        logger.info(f"[AudioFilter] Đang lọc âm giọng nói (AI MDX) từ video: {video_path}")
        models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models_cache")
        os.makedirs(models_dir, exist_ok=True)

        sep_input_path = video_path
        temp_wav_extracted = None
        ext = os.path.splitext(video_path)[1].lower()
        if ext in (".mp4", ".mov", ".mkv", ".avi", ".flv", ".webm", ".m4v"):
            temp_wav_extracted = os.path.join(output_dir, f"temp_input_{uuid.uuid4().hex[:8]}.wav")
            try:
                cmd_prep = ["ffmpeg", "-y", "-i", video_path, "-vn", "-ar", "44100", "-ac", "2", temp_wav_extracted]
                subprocess.run(cmd_prep, capture_output=True, text=True, check=True)
                if os.path.isfile(temp_wav_extracted):
                    sep_input_path = temp_wav_extracted
            except Exception as prep_err:
                logger.warning(f"[AudioFilter] Pre-extracting audio from video failed: {prep_err}")

        sep = Separator(
            output_dir=output_dir,
            output_format="wav",
            model_file_dir=models_dir,
            output_single_stem="Vocals"
        )
        try:
            sep.load_model("UVR-MDX-NET-Inst_HQ_3.onnx")
        except Exception:
            sep.load_model()
        output_files = sep.separate(sep_input_path)

        if temp_wav_extracted and os.path.isfile(temp_wav_extracted):
            try:
                os.remove(temp_wav_extracted)
            except Exception:
                pass

        if output_files and len(output_files) > 0:
            extracted_path = os.path.join(output_dir, output_files[0])
            if os.path.isfile(extracted_path):
                logger.info(f"[AudioFilter] Tách vocal AI thành công: {extracted_path}")
                return extracted_path
    except Exception as e:
        logger.info(f"[AudioFilter] audio-separator fallback: {e}")

    # 2. Hard fallback sang FFmpeg bandpass filter
    out_vocal_filename = f"filtered_vocal_{uuid.uuid4().hex[:8]}.wav"
    out_vocal_path = os.path.join(output_dir, out_vocal_filename)
    try:
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn",
            "-af", "highpass=f=200,lowpass=f=3400,afftdn=nr=25,equalizer=f=1000:t=q:w=1:g=-15",
            "-ar", "44100", "-ac", "2",
            out_vocal_path
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        if os.path.isfile(out_vocal_path) and os.path.getsize(out_vocal_path) > 0:
            logger.info(f"[AudioFilter] Tách/lọc âm thanh vocal qua FFmpeg bandpass thành công: {out_vocal_path}")
            return out_vocal_path
    except Exception as e:
        logger.error(f"[AudioFilter] Lỗi khi chạy FFmpeg filter: {e}")

    return None


def copy_wav_to_text_reading(wav_path: str, draft_path: str, filename: str) -> str:
    """Copy WAV file into textReading/ subfolder of draft and return the placeholder path."""
    text_reading_dir = os.path.join(draft_path, "textReading")
    os.makedirs(text_reading_dir, exist_ok=True)
    dest = os.path.join(text_reading_dir, filename)
    shutil.copy2(wav_path, dest)
    return dest


def patch_offline_tts_in_draft(
    draft_path: str,
    voice_name: str = "default",
    output_audio_dir: str = "output_audio",
    item_config: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Generate NGHI-TTS audio for all translated subtitles in the draft and patch
    the resulting audio tracks/materials directly into draft_content.json.

    Bypasses opening CapCut GUI & RPA image workflows.
    """
    json_paths = get_draft_json_paths(draft_path)
    if not json_paths:
        logger.error(f"No draft_content.json found in {draft_path}")
        return False

    patched_any = False

    # If item_config not provided, try loading pipeline_config.json from draft_path
    if not item_config:
        config_file = os.path.join(draft_path, "pipeline_config.json")
        if os.path.isfile(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as cfg:
                    item_config = json.load(cfg)
            except Exception:
                item_config = {}

    item_config = item_config or {}
    tts_speed = float(item_config.get("tts_speed", 1.0) or 1.0)
    filter_audio = bool(item_config.get("filter_audio") or item_config.get("filterAudio") or False)

    # Get draft_id for placeholder path — read once from root draft_meta_info.json
    draft_id = get_draft_id_from_meta(draft_path)
    if not draft_id:
        logger.warning("Không tìm thấy draft_id từ draft_meta_info.json — path placeholder sẽ dùng đường dẫn tuyệt đối")

    for json_path in json_paths:
        logger.info(f"Reading draft JSON: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        materials = data.setdefault("materials", {})
        texts_list = materials.setdefault("texts", [])
        audios_list = materials.setdefault("audios", [])
        speeds_list = materials.setdefault("speeds", [])

        # Process filter_audio: isolate vocal & mute original video audio if enabled
        if filter_audio:
            logger.info("[AudioFilter] Tùy chọn lọc âm thanh gốc (filter_audio) được BẬT. Tiến hành tắt tiếng video gốc...")
            # Mute all original video and audio tracks, segments, and clips
            for tr in data.get("tracks", []):
                tr_type = tr.get("type")
                tr_name = tr.get("name", "")
                if tr_type == "video" or (tr_type == "audio" and tr_name not in ("audio_tts", "audio_filtered_vocal")):
                    for seg in tr.get("segments", []):
                        seg["volume"] = 0.0
                        if isinstance(seg.get("clip"), dict):
                            seg["clip"]["volume"] = 0.0

            # Mute volume in video materials directly
            for v_mat in materials.get("videos", []):
                v_mat["volume"] = 0.0

            # Extract video source path
            video_src = item_config.get("video_path") or item_config.get("videoPath")
            if not video_src and isinstance(item_config.get("video_paths"), list) and len(item_config["video_paths"]) > 0:
                video_src = item_config["video_paths"][0]
            if not video_src:
                for v_mat in materials.get("videos", []):
                    v_path = v_mat.get("path")
                    if v_path and os.path.isfile(v_path):
                        video_src = v_path
                        break

            if video_src:
                filtered_vocal_wav = extract_filtered_vocal_audio(video_src, output_audio_dir=output_audio_dir)
                if filtered_vocal_wav and os.path.isfile(filtered_vocal_wav):
                    vocal_mat_id = str(uuid.uuid4()).upper()
                    vocal_seg_id = str(uuid.uuid4()).upper()
                    vocal_speed_id = str(uuid.uuid4()).upper()

                    vocal_filename = f"{vocal_mat_id}_filtered_vocal.wav"
                    dest_vocal = copy_wav_to_text_reading(filtered_vocal_wav, draft_path, vocal_filename)
                    vocal_path_abs = os.path.abspath(dest_vocal).replace("\\", "/")
                    vocal_dur_us = get_wav_duration_us(dest_vocal)

                    # Calculate video speed matching video adjustment
                    video_speed = float(item_config.get("speed") or item_config.get("video_speed") or 1.0)
                    target_dur_us = int(round(vocal_dur_us / video_speed)) if video_speed > 0 else vocal_dur_us

                    speeds_list.append({
                        "curve_speed": None,
                        "id": vocal_speed_id,
                        "mode": 0,
                        "speed": video_speed,
                        "type": "speed"
                    })

                    audios_list.append({
                        "duration": vocal_dur_us,
                        "id": vocal_mat_id,
                        "name": "Original_Filtered_Vocal",
                        "path": vocal_path_abs,
                        "type": "extract_music"
                    })

                    # Remove old filtered vocal track if exists
                    data["tracks"] = [tr for tr in data["tracks"] if not (tr.get("type") == "audio" and tr.get("name") == "audio_filtered_vocal")]

                    vocal_track = {
                        "attribute": 0,
                        "flag": 0,
                        "id": str(uuid.uuid4()).upper(),
                        "is_contain_material_segment": True,
                        "name": "audio_filtered_vocal",
                        "segments": [
                            {
                                "caption_info": None,
                                "clip": None,
                                "common_keyframes": [],
                                "enable_adjust": True,
                                "extra_material_refs": [],
                                "group_id": "",
                                "hdr_settings": None,
                                "id": vocal_seg_id,
                                "intensifies_audio_path": "",
                                "is_placeholder": False,
                                "is_tone_modify": False,
                                "keyframe_refs": [],
                                "last_oper_type": 0,
                                "material_id": vocal_mat_id,
                                "render_index": 0,
                                "responsive_layout": None,
                                "reverse": False,
                                "source_timerange": {
                                    "duration": vocal_dur_us,
                                    "start": 0
                                },
                                "speed_id": vocal_speed_id,
                                "target_timerange": {
                                    "duration": target_dur_us,
                                    "start": 0
                                },
                                "template_id": "",
                                "template_scene": "default",
                                "track_attribute": 0,
                                "track_render_index": 0,
                                "uniform_scale": None,
                                "visible": True,
                                "volume": 1.0
                            }
                        ],
                        "type": "audio"
                    }
                    data["tracks"].insert(0, vocal_track)
                    logger.info(f"[AudioFilter] Đã chèn track audio_filtered_vocal vào draft (Speed: {video_speed}x, Duration: {target_dur_us/1_000_000:.2f}s).")

            # Always save draft JSON after audio filter modifications
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            patched_any = True

        text_segments = extract_text_segments_from_draft(data)
        if not text_segments:
            logger.warning(f"Không có phụ đề nào trong bản nháp {json_path} để tạo giọng đọc offline.")
            continue

        logger.info(f"Found {len(text_segments)} subtitle segments. Generating NGHI-TTS audio (Voice: '{voice_name}', Speed: {tts_speed}x)...")

        # Clean up stale/old TTS audio tracks to prevent duplicates or out-of-order tracks
        tracks = data.setdefault("tracks", [])
        data["tracks"] = [tr for tr in tracks if not (tr.get("type") == "audio" and tr.get("name") in ("audio_tts", "TTS_Track", ""))]
        tracks = data["tracks"]

        tts_track = {
            "attribute": 0,
            "flag": 0,
            "id": str(uuid.uuid4()).upper(),
            "is_contain_material_segment": True,
            "name": "audio_tts",
            "segments": [],
            "type": "audio"
        }
        tracks.append(tts_track)

        added_count = 0

        # Extract tts speed from item_config
        tts_speed = float((item_config or {}).get("tts_speed", 1.0) or 1.0)

        for seg in text_segments:
            text = seg["text"]
            start_us = seg["start_us"]

            try:
                # 1. Generate audio WAV via NGHI-TTS with configured speed
                wav_path = generate_nghitts(text, voice_name=voice_name, speed=tts_speed)
                audio_dur_us = get_wav_duration_us(wav_path)

                audio_mat_id = str(uuid.uuid4()).upper()
                audio_seg_id = str(uuid.uuid4()).upper()
                speed_id = str(uuid.uuid4()).upper()

                # 2. Copy WAV into draft textReading/ folder and use absolute forward-slash path
                wav_filename = f"{audio_mat_id}.wav"
                dest_wav = copy_wav_to_text_reading(wav_path, draft_path, wav_filename)
                audio_path = os.path.abspath(dest_wav).replace("\\", "/")

                # 3. Add Audio Material matching CapCut Native text_to_audio schema
                text_mat_id = seg.get("text_material_id", "")
                text_prefix = text[:10] if len(text) > 10 else text
                audio_material = {
                    "ai_music_enter_from": "",
                    "ai_music_generate_scene": 0,
                    "ai_music_type": 0,
                    "aigc_history_id": "",
                    "aigc_item_id": "",
                    "app_id": 0,
                    "category_id": "",
                    "category_name": "",
                    "check_flag": 1,
                    "cloned_model_type": "",
                    "copyright_limit_type": "none",
                    "duration": audio_dur_us,
                    "effect_id": "",
                    "formula_id": "",
                    "id": audio_mat_id,
                    "intensifies_path": "",
                    "is_ai_clone_tone": False,
                    "is_ai_clone_tone_post": False,
                    "is_text_edit_overdub": False,
                    "is_ugc": False,
                    "local_material_id": "",
                    "lyric_type": 0,
                    "mock_tone_speaker": ",".join([voice_name] * 85),
                    "moyin_emotion": "",
                    "music_id": "",
                    "music_source": "",
                    "name": text_prefix + ("..." if len(text) > 10 else ""),
                    "path": audio_path,
                    "pgc_id": "",
                    "pgc_name": "",
                    "query": "",
                    "request_id": "",
                    "resource_id": "",
                    "search_id": "",
                    "similiar_music_info": {"original_song_id": "", "original_song_name": ""},
                    "sound_separate_type": "",
                    "source_from": "",
                    "source_platform": 0,
                    "team_id": "",
                    "text_id": text_mat_id,
                    "third_resource_id": "",
                    "tone_category_id": "",
                    "tone_category_name": "",
                    "tone_effect_id": "",
                    "tone_effect_name": voice_name,
                    "tone_emotion_name_key": "",
                    "tone_emotion_role": "",
                    "tone_emotion_scale": 0.0,
                    "tone_emotion_selection": "",
                    "tone_emotion_style": "",
                    "tone_platform": "sami",
                    "tone_second_category_id": "",
                    "tone_second_category_name": "",
                    "tone_speaker": voice_name,
                    "tone_type": voice_name,
                    "tts_benefit_info": {
                        "benefit_amount": -1,
                        "benefit_log_extra": "",
                        "benefit_log_id": "",
                        "benefit_type": "none"
                    },
                    "tts_generate_scene": "audio_panel",
                    "tts_task_id": "",
                    "type": "text_to_audio",
                    "unique_id": "",
                    "video_id": "",
                    "wave_points": []
                }
                audios_list.append(audio_material)

                # Link text_to_speech_info in materials.texts
                if text_mat_id:
                    for t in texts_list:
                        if t.get("id") == text_mat_id:
                            t["text_to_speech_info"] = {
                                "audio_id": audio_mat_id,
                                "speaker_id": voice_name,
                                "speaker_name": voice_name
                            }

                # 3. Add Speed Material
                speed_mat = {
                    "curve_speed": None,
                    "id": speed_id,
                    "mode": 0,
                    "speed": 1.0,
                    "type": "speed"
                }
                speeds_list.append(speed_mat)

                # 4. Add Segment to Audio Track matching CapCut PyJianYingDraft schema
                audio_segment = {
                    "caption_info": None,
                    "clip": None,
                    "common_keyframes": [],
                    "enable_adjust": True,
                    "enable_color_curves": True,
                    "enable_color_wheels": True,
                    "enable_lut": True,
                    "enable_smart_color_adjust": False,
                    "extra_material_refs": [],
                    "group_id": "",
                    "hdr_settings": None,
                    "id": audio_seg_id,
                    "intensifies_audio_path": "",
                    "is_placeholder": False,
                    "is_tone_modify": False,
                    "keyframe_refs": [],
                    "last_oper_type": 0,
                    "material_id": audio_mat_id,
                    "render_index": 0,
                    "responsive_layout": None,
                    "reverse": False,
                    "source_timerange": {
                        "duration": audio_dur_us,
                        "start": 0
                    },
                    "speed_id": speed_id,
                    "target_timerange": {
                        "duration": audio_dur_us,
                        "start": start_us
                    },
                    "template_id": "",
                    "template_scene": "default",
                    "track_attribute": 0,
                    "track_render_index": 0,
                    "uniform_scale": None,
                    "visible": True,
                    "volume": 1.0
                }
                tts_track["segments"].append(audio_segment)
                added_count += 1

            except Exception as e:
                logger.error(f"Error generating TTS for segment '{text}': {e}")

        logger.info(f"Successfully generated and patched {added_count}/{len(text_segments)} audio segments into {json_path}")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        patched_any = True

    if patched_any:
        clear_mini_draft_cache(draft_path)

    return patched_any


def clear_mini_draft_cache(draft_path: str):
    """Remove mini_draft.json and patch cache files so CapCut rebuilds timeline cleanly from draft_content.json."""
    for root, dirs, files in os.walk(draft_path):
        for file in files:
            if file in ("mini_draft.json", "mini_draft.json.bak", "patch.json"):
                p = os.path.join(root, file)
                try:
                    os.remove(p)
                    logger.info(f"Cleared mini_draft cache file: {p}")
                except Exception as e:
                    logger.warning(f"Could not remove {p}: {e}")

if __name__ == "__main__":
    print("Offline TTS Patcher loaded.")
