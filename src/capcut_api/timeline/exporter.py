from typing import List
from timeline.models import VideoSegment, SubtitleSegment, AudioSegment
from timeline.parser import _is_main_video_track

def export_draft(
    data: dict,
    video_segs: List[VideoSegment],
    subtitle_segs: List[SubtitleSegment],
    audio_segs: List[AudioSegment],
    sync_video: bool = True,
    sync_audio: bool = True,
    sync_subtitles: bool = True
) -> dict:
    """
    Exports the compiled Timeline Element dataclasses back to the raw CapCut Draft JSON format.
    Does not compute timeline coordinates; only writes the pre-compiled values.
    """
    materials = data.setdefault("materials", {})
    speeds = materials.setdefault("speeds", [])
    speed_map = {s.get("id"): s for s in speeds if isinstance(s, dict)}

    # Index segments by ID for O(1) matching
    video_map = {vs.id: vs for vs in video_segs}
    sub_map = {ss.id: ss for ss in subtitle_segs}
    aud_map = {as_val.id: as_val for as_val in audio_segs}

    main_video_segments_dict = []

    for track in data.get("tracks", []):
        tr_type = track.get("type")
        tr_name = track.get("name", "")
        
        if _is_main_video_track(track, materials):
            if not sync_video:
                continue
            import copy
            new_segs = []
            for v_model in video_segs:
                seg_dict = copy.deepcopy(v_model.raw_dict) if v_model.raw_dict else {}
                seg_dict["id"] = v_model.id
                seg_dict["source_timerange"] = {
                    "start": v_model.src_start,
                    "duration": v_model.src_duration
                }
                seg_dict["target_timerange"] = {
                    "start": v_model.target_start,
                    "duration": v_model.target_duration
                }
                seg_dict["speed"] = v_model.speed
                
                clip = seg_dict.setdefault("clip", {})
                clip["flip"] = {
                    "horizontal": v_model.flip_horizontal,
                    "vertical": v_model.flip_vertical
                }
                clip["scale"] = {
                    "x": v_model.scale_x,
                    "y": v_model.scale_y
                }
                
                seg_dict["color_adjustments"] = v_model.color_adjustments
                
                for ref in v_model.extra_material_refs:
                    if ref in speed_map:
                        speed_map[ref]["speed"] = v_model.speed
                if v_model.speed_id and v_model.speed_id in speed_map:
                    speed_map[v_model.speed_id]["speed"] = v_model.speed
                    
                new_segs.append(seg_dict)
            track["segments"] = new_segs
            main_video_segments_dict = new_segs
            
        elif tr_type == "text":
            if not sync_subtitles:
                continue
            new_segs = []
            for seg in track.get("segments", []):
                seg_id = seg.get("id")
                if seg_id in sub_map:
                    s_model = sub_map[seg_id]
                    seg["target_timerange"] = {
                        "start": s_model.target_start,
                        "duration": s_model.target_duration
                    }
                    seg["_ocr_source_start"] = s_model.ocr_source_start
                    seg["_ocr_source_duration"] = s_model.ocr_source_duration
                    new_segs.append(seg)
            track["segments"] = new_segs
            
        elif tr_type == "audio" and tr_name != "audio_filtered_vocal":
            if not sync_audio:
                continue
            new_segs = []
            for seg in track.get("segments", []):
                seg_id = seg.get("id")
                if seg_id in aud_map:
                    a_model = aud_map[seg_id]
                    seg["source_timerange"] = {
                        "start": a_model.src_start,
                        "duration": a_model.src_duration
                    }
                    seg["target_timerange"] = {
                        "start": a_model.target_start,
                        "duration": a_model.target_duration
                    }
                    seg["speed"] = a_model.speed
                    if a_model.ocr_source_start is not None:
                        seg["_ocr_source_start"] = a_model.ocr_source_start
                    
                    for ref in a_model.extra_material_refs:
                        if ref in speed_map:
                            speed_map[ref]["speed"] = a_model.speed
                    if a_model.speed_id and a_model.speed_id in speed_map:
                        speed_map[a_model.speed_id]["speed"] = a_model.speed
                        
                    new_segs.append(seg)
            track["segments"] = new_segs

    # Sync audio_filtered_vocal segments 1-to-1 with compiled main video segments
    if sync_video and main_video_segments_dict:
        for track in data.get("tracks", []):
            if track.get("type") == "audio" and track.get("name") == "audio_filtered_vocal":
                a_segs = track.get("segments", [])
                for seg_idx, v_seg in enumerate(main_video_segments_dict):
                    if seg_idx < len(a_segs):
                        a_seg = a_segs[seg_idx]
                        v_src = v_seg.get("source_timerange", {})
                        v_tgt = v_seg.get("target_timerange", {})
                        
                        a_seg["source_timerange"] = {
                            "start": v_src.get("start", 0),
                            "duration": v_src.get("duration", 0)
                        }
                        a_seg["target_timerange"] = {
                            "start": v_tgt.get("start", 0),
                            "duration": v_tgt.get("duration", 0)
                        }
                        
                        v_spd = v_seg.get("speed", 1.0)
                        a_seg["speed"] = v_spd
                        for ref in a_seg.get("extra_material_refs", []):
                            if ref in speed_map:
                                speed_map[ref]["speed"] = v_spd
                        speed_id = a_seg.get("speed_id")
                        if speed_id and speed_id in speed_map:
                            speed_map[speed_id]["speed"] = v_spd

    if sync_video:
        # Update logo stickers (GIF/PNG overlay) matching the video timeline end bounds
        main_video_target_dur = max(
            vs.target_start + vs.target_duration
            for vs in video_segs
        ) if video_segs else 0

        if main_video_target_dur > 0:
            for track in data.get("tracks", []):
                if track.get("type") == "video" and not _is_main_video_track(track, materials):
                    for seg in track.get("segments", []):
                        s_tgt = seg.setdefault("target_timerange", {})
                        s_tgt["start"] = 0
                        s_tgt["duration"] = main_video_target_dur

    return data
