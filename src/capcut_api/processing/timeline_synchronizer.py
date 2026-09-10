# -*- coding: utf-8 -*-
import os
import json
import uuid
import time
import re
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any

FFMPEG_EXE = r"C:\Users\admin.TRANANH\AppData\Local\Programs\Python\Python311\Scripts\ffmpeg.EXE"

class TimelineSynchronizer:
    """
    Đồng bộ hóa hoàn hảo tất cả các Track trong CapCut Draft:
    - Track Video/Ảnh: Co giãn thông minh để tổng thời lượng khớp 100% với Master Audio.
    - Track Audio: Chỉ giữ 1 track thuyết minh master duy nhất, loại bỏ track rác/lệch pha.
    - Track Subtitle: Căn chỉnh theo giọng đọc, ngắt nhịp rời rạc (0.06s), kết thúc khớp cùng audio.
    """

    @staticmethod
    def get_audio_duration_sec(audio_path: str) -> float:
        """Đo thời lượng chính xác tuyệt đối bằng ffmpeg hoặc ffprobe."""
        if os.path.exists(FFMPEG_EXE) and os.path.exists(audio_path):
            cmd = [FFMPEG_EXE, "-i", audio_path]
            res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            m = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', res.stderr)
            if m:
                h, mi, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
                return h * 3600 + mi * 60 + s
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            pass
        return os.path.getsize(audio_path) / 16000.0

    @classmethod
    def synchronize_draft(
        cls,
        draft_dir: str,
        master_audio_path: str,
        subtitles: Optional[List[Dict[str, Any]]] = None,
        disable_flip: bool = True,
        font_size: float = 5.5,
        transform_y: float = -0.78
    ) -> Dict[str, Any]:
        content_path = os.path.join(draft_dir, "draft_content.json")
        info_path = os.path.join(draft_dir, "draft_info.json")

        if not os.path.exists(content_path):
            raise FileNotFoundError(f"Draft content not found: {content_path}")

        master_dur_sec = cls.get_audio_duration_sec(master_audio_path)
        master_dur_us = int(round(master_dur_sec * 1e6))

        # Đảm bảo copy audio vào thư mục draft để CapCut không bị Media lost
        draft_audio_dir = os.path.join(draft_dir, "audio")
        os.makedirs(draft_audio_dir, exist_ok=True)
        target_audio_path = os.path.join(draft_audio_dir, Path(master_audio_path).name)
        import shutil
        if os.path.abspath(master_audio_path) != os.path.abspath(target_audio_path):
            shutil.copy2(master_audio_path, target_audio_path)
        abs_audio_path = os.path.abspath(target_audio_path).replace("/", "\\")

        with open(content_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        materials = data.setdefault("materials", {})

        # 1. ĐỒNG BỘ TRACK AUDIO
        audio_mat_id = str(uuid.uuid4()).replace("-", "")
        audio_seg_id = str(uuid.uuid4()).replace("-", "")

        audio_mat = {
            "app_id": 0,
            "category_id": "",
            "category_name": "local",
            "check_flag": 1,
            "duration": master_dur_us,
            "extra_info": "",
            "file_Path": abs_audio_path,
            "id": audio_mat_id,
            "name": Path(abs_audio_path).name,
            "path": abs_audio_path,
            "type": "extract_music"
        }
        materials["audios"] = [audio_mat]

        audio_segment = {
            "clip": {"alpha": 1.0, "flip": {"horizontal": False, "vertical": False}, "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0}, "transform": {"x": 0.0, "y": 0.0}},
            "id": audio_seg_id,
            "material_id": audio_mat_id,
            "render_timerange": {"duration": master_dur_us, "start": 0},
            "source_timerange": {"duration": master_dur_us, "start": 0},
            "speed": 1.0,
            "target_timerange": {"duration": master_dur_us, "start": 0},
            "volume": 1.0,
            "visible": True
        }
        audio_track = {
            "id": str(uuid.uuid4()).replace("-", ""),
            "type": "audio",
            "name": "voiceover",
            "segments": [audio_segment]
        }

        # 2. ĐỒNG BỘ TRACK VIDEO/ẢNH
        old_v_tracks = [tr for tr in data.get("tracks", []) if tr.get("type") == "video"]
        if not old_v_tracks or not old_v_tracks[0].get("segments"):
            raise ValueError("Không tìm thấy video track có segment hợp lệ!")

        video_track = old_v_tracks[0]
        v_segs = video_track["segments"]
        n_segs = len(v_segs)
        old_v_total_us = sum(s["target_timerange"]["duration"] for s in v_segs)

        scale = master_dur_us / max(1, old_v_total_us)
        curr_v_start = 0

        for i, s in enumerate(v_segs):
            if i == n_segs - 1:
                s_dur = master_dur_us - curr_v_start
            else:
                s_dur = int(round(s["target_timerange"]["duration"] * scale))
            s_dur = max(100000, s_dur)

            s["target_timerange"] = {"start": curr_v_start, "duration": s_dur}
            s["render_timerange"] = {"start": 0, "duration": s_dur}

            src_dur = s["source_timerange"].get("duration", 0)
            if src_dur == s["target_timerange"]["duration"] or src_dur > 10000000:
                s["source_timerange"]["duration"] = s_dur

            # Khắc phục triệt để lật ngược ảnh nếu người dùng chọn không lật
            if disable_flip:
                clip_obj = s.setdefault("clip", {})
                flip_obj = clip_obj.setdefault("flip", {})
                flip_obj["horizontal"] = False
                flip_obj["vertical"] = False

            curr_v_start += s_dur

        video_track["segments"] = v_segs

        # 3. ĐỒNG BỘ TRACK SUBTITLE (ĐẢM BẢO 100% ZERO OVERLAP - KHÔNG BAO GIỜ ĐÈ CHỮ)
        new_tracks = [video_track, audio_track]

        if subtitles:
            font_path = "C:/Users/admin.TRANANH/AppData/Local/CapCut/Apps/9.4.0.4015/Resources/Font/SystemFont/en.ttf"
            new_texts = []
            new_text_segs = []

            # Áp dụng thuật toán triệt tiêu va chạm timeline:
            MIN_GAP = 0.05
            sorted_subs = sorted(subtitles, key=lambda x: x["start"])
            for i in range(len(sorted_subs) - 1):
                c_start = sorted_subs[i]["start"]
                n_start = sorted_subs[i+1]["start"]
                if n_start < c_start + 0.25:
                    sorted_subs[i+1]["start"] = c_start + 0.25 + MIN_GAP
                    n_start = sorted_subs[i+1]["start"]
                max_allowed = max(0.15, n_start - MIN_GAP - c_start)
                sorted_subs[i]["duration"] = min(sorted_subs[i]["duration"], max_allowed)

            for sub in sorted_subs:
                mat_id = str(uuid.uuid4()).replace("-", "")
                seg_id = str(uuid.uuid4()).replace("-", "")
                txt = sub["text"]

                s_sec = min(sub["start"], max(0.0, master_dur_sec - 0.25))
                dur_sec = sub["duration"]
                if s_sec + dur_sec > master_dur_sec:
                    dur_sec = max(0.15, master_dur_sec - s_sec - 0.02)

                start_us = int(round(s_sec * 1e6))
                dur_us = max(100000, int(round(dur_sec * 1e6)))

                content_obj = {
                    "styles": [
                        {
                            "fill": {
                                "alpha": 1.0,
                                "content": {
                                    "render_type": "solid",
                                    "solid": {
                                        "alpha": 1.0,
                                        "color": [1.0, 0.92, 0.15]
                                    }
                                }
                            },
                            "range": [0, len(txt)],
                            "size": font_size
                        }
                    ],
                    "text": txt
                }

                mat_item = {
                    "id": mat_id,
                    "type": "text",
                    "content": json.dumps(content_obj, ensure_ascii=False),
                    "font_size": font_size,
                    "font_path": font_path,
                    "border_alpha": 1.0,
                    "border_color": "#000000",
                    "border_width": 0.08,
                    "border_mode": 0,
                    "alignment": 1,
                    "line_spacing": 0.02,
                    "line_max_width": 0.70,
                    "fixed_width": 1344.0,
                    "fixed_height": -1.0,
                    "global_alpha": 1.0,
                    "text_alpha": 1.0,
                    "text_color": "#FFE81F",
                    "has_shadow": False,
                    "words": {"start_time": [], "end_time": [], "text": []},
                    "current_words": {"start_time": [], "end_time": [], "text": []},
                    "typesetting": 0,
                    "line_feed": 1,
                    "check_flag": 15,
                    "text_size": 30,
                    "sub_type": 0,
                    "add_type": 0,
                    "recognize_type": 0
                }
                new_texts.append(mat_item)

                seg_item = {
                    "id": seg_id,
                    "material_id": mat_id,
                    "source_timerange": {"start": 0, "duration": dur_us},
                    "target_timerange": {"start": start_us, "duration": dur_us},
                    "render_timerange": {"start": 0, "duration": dur_us},
                    "clip": {
                        "alpha": 1.0,
                        "flip": {"horizontal": False, "vertical": False},
                        "rotation": 0.0,
                        "scale": {"x": 1.0, "y": 1.0},
                        "transform": {"x": 0.0, "y": transform_y}
                    },
                    "speed": 1.0,
                    "volume": 1.0,
                    "state": 0,
                    "visible": True,
                    "uniform_scale": None,
                    "extra_material_refs": []
                }
                new_text_segs.append(seg_item)

            materials["texts"] = new_texts
            text_track = {
                "id": str(uuid.uuid4()).replace("-", ""),
                "type": "text",
                "name": "subtitles",
                "segments": new_text_segs
            }
            new_tracks.append(text_track)

        # 4. GHI NHẬN CÁC TRACK ĐÃ ĐỒNG BỘ
        data["tracks"] = new_tracks
        data["duration"] = master_dur_us

        with open(content_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if os.path.exists(info_path):
            with open(info_path, 'r', encoding='utf-8') as f:
                d_info = json.load(f)
            d_info["tm_duration"] = master_dur_us
            d_info["tm_draft_modified"] = int(time.time() * 1e6)
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(d_info, f, ensure_ascii=False, indent=2)

        mini_p = os.path.join(draft_dir, "mini_draft.json")
        if os.path.exists(mini_p):
            try:
                os.remove(mini_p)
            except Exception:
                pass

        return {
            "master_duration_sec": master_dur_sec,
            "video_end_sec": curr_v_start / 1e6,
            "audio_end_sec": master_dur_sec,
            "subtitle_clips": len(subtitles) if subtitles else 0
        }
