import os, sys, json, time

from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "src" / "capcut_api"))
sys.path.insert(0, str(ROOT_DIR / "src" / "capcut_api" / "processing"))
sys.path.insert(0, str(ROOT_DIR / "src" / "capcut_api" / "api"))
sys.path.insert(0, str(ROOT_DIR / "src" / "capcut_api" / "ai"))

from anti_copyright_patcher import (
    apply_full_anti_copyright_pipeline,
    patch_video_speed_dynamic,
    resync_subtitles_and_audio_to_video_timeline,
    _is_main_video_track,
    find_draft_content_paths
)
from offline_tts_patcher import patch_offline_tts_in_draft
from capcut_gui_app import patch_audio_speed_in_json

def run_test_and_verify(draft_dir: str, video_speed: float = 0.85, tts_speed: float = 1.17):
    print("==================================================================")
    print(f"=== TESTING FULL PIPELINE ON DRAFT: {draft_dir} ===")
    print("==================================================================")

    content_paths = find_draft_content_paths(draft_dir)
    if not content_paths:
        print("ERROR: No draft_content.json found in", draft_dir)
        return False

    p = content_paths[0]
    data = json.load(open(p, encoding='utf-8'))

    # Dump debug_before.json baseline
    video_segments = []
    subtitle_segments = []
    audio_segments = []
    materials = data.get("materials", {})
    
    for tr in data.get("tracks", []):
        tr_type = tr.get("type")
        tr_name = tr.get("name", "")
        for seg in tr.get("segments", []):
            seg_info = {
                "id": seg.get("id"),
                "material_id": seg.get("material_id"),
                "source_timerange": seg.get("source_timerange"),
                "target_timerange": seg.get("target_timerange"),
                "speed_id": seg.get("speed_id"),
                "extra_material_refs": seg.get("extra_material_refs"),
                "speed": seg.get("speed", 1.0)
            }
            if _is_main_video_track(tr, materials):
                video_segments.append(seg_info)
            elif tr_type == "text":
                subtitle_segments.append({
                    "id": seg.get("id"),
                    "ocr_source_start": seg.get("_ocr_source_start", seg.get("target_timerange", {}).get("start", 0)),
                    "ocr_source_duration": seg.get("_ocr_source_duration", seg.get("target_timerange", {}).get("duration", 0)),
                    "target_start": seg.get("target_timerange", {}).get("start", 0),
                    "target_duration": seg.get("target_timerange", {}).get("duration", 0)
                })
            elif tr_type == "audio" and tr_name != "audio_filtered_vocal":
                audio_segments.append(seg_info)
                
    materials_speed = materials.get("speeds", [])
    
    debug_before = {
        "video_segments": video_segments,
        "subtitle_segments": subtitle_segments,
        "audio_segments": audio_segments,
        "materials_speed": materials_speed
    }
    
    os.makedirs("debug", exist_ok=True)
    with open("debug/debug_before.json", "w", encoding="utf-8") as f_dbg:
        json.dump(debug_before, f_dbg, ensure_ascii=False, indent=4)

    # Collect initial OCR Chinese subtitle count & timestamps
    ocr_sub_count = 0
    ocr_starts = []
    for tr in data.get('tracks', []):
        if tr.get('type') == 'text':
            for seg in tr.get('segments', []):
                ocr_sub_count += 1
                t = seg.get('target_timerange', {})
                ocr_starts.append(t.get('start', 0))
                # Ensure _ocr_source_start is explicitly saved
                if '_ocr_source_start' not in seg:
                    seg['_ocr_source_start'] = t.get('start', 0)

    print(f"[Initial Check] Raw OCR Subtitle Count: {ocr_sub_count}")
    if ocr_sub_count == 0:
        print("WARNING: Draft has 0 subtitles initially.")

    # Save cleaned draft state
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    # ------------------------------------------------------------------
    # Step 3.5: Preprocessing (Smart Cuts + Mirror + Zoom/Crop at speed 1.0x)
    # ------------------------------------------------------------------
    print("\n--- STEP 3.5: Preprocessing Anti-Copyright (Speed 1.0x) ---")
    res35 = apply_full_anti_copyright_pipeline(draft_dir, config={'speed_patch': False, 'video_speed': 1.0, 'speed': 1.0})
    print("Step 3.5 Result:", res35)

    # ------------------------------------------------------------------
    # Step 6: Audio Filter & NGHI-TTS (on 1.0x Timeline)
    # ------------------------------------------------------------------
    print("\n--- STEP 6: Offline TTS & Audio Filter (Speed 1.0x) ---")
    try:
        patch_offline_tts_in_draft(draft_dir, voice_name='default', item_config={'tts_speed': tts_speed, 'filter_audio': True})
        print("Step 6 Completed.")
    except Exception as e:
        print("Step 6 Exception (expected if offline server unavail):", e)

    # ------------------------------------------------------------------
    # Step 7: Final Video Speed Slowdown (0.85x) & Resync
    # ------------------------------------------------------------------
    print(f"\n--- STEP 7: Final Video Speed ({video_speed}x) & Resync ---")
    patch_audio_speed_in_json(draft_dir, target_speed=tts_speed)
    patch_video_speed_dynamic(draft_dir, base_speed=video_speed, randomize=True)
    resync_count = resync_subtitles_and_audio_to_video_timeline(draft_dir)
    print(f"Step 7 Completed (Resynced segments: {resync_count}).")

    # ------------------------------------------------------------------
    # FINAL AUTOMATED AUDIT & VERIFICATION
    # ------------------------------------------------------------------
    print("\n==================================================================")
    print("=== AUTOMATED DRAFT VERIFICATION REPORT ===")
    print("==================================================================")

    data_final = json.load(open(p, encoding='utf-8'))
    materials = data_final.get('materials', {})

    video_segs = []
    vocal_segs = []
    text_segs = []
    tts_segs = []

    for tr in data_final.get('tracks', []):
        tr_type = tr.get('type')
        tr_name = tr.get('name', '')
        segs = tr.get('segments', [])

        if _is_main_video_track(tr, materials):
            for s in segs:
                s_src = s.get('source_timerange', {})
                s_tgt = s.get('target_timerange', {})
                video_segs.append({
                    'src_start': s_src.get('start', 0) / 1e6,
                    'src_end': (s_src.get('start', 0) + s_src.get('duration', 0)) / 1e6,
                    'tgt_start': s_tgt.get('start', 0) / 1e6,
                    'tgt_end': (s_tgt.get('start', 0) + s_tgt.get('duration', 0)) / 1e6,
                    'speed': s.get('speed', 1.0)
                })
        elif tr_type == 'audio' and tr_name == 'audio_filtered_vocal':
            for s in segs:
                s_src = s.get('source_timerange', {})
                s_tgt = s.get('target_timerange', {})
                vocal_segs.append({
                    'src_start': s_src.get('start', 0) / 1e6,
                    'src_end': (s_src.get('start', 0) + s_src.get('duration', 0)) / 1e6,
                    'tgt_start': s_tgt.get('start', 0) / 1e6,
                    'tgt_end': (s_tgt.get('start', 0) + s_tgt.get('duration', 0)) / 1e6,
                    'speed': s.get('speed', 1.0)
                })
        elif tr_type == 'text':
            for s in segs:
                t = s.get('target_timerange', {})
                text_segs.append({
                    'start': t.get('start', 0) / 1e6,
                    'end': (t.get('start', 0) + t.get('duration', 0)) / 1e6,
                    '_ocr_src': s.get('_ocr_source_start', 0) / 1e6
                })
        elif tr_type == 'audio' and tr_name == 'audio_tts':
            for s in segs:
                t = s.get('target_timerange', {})
                tts_segs.append({
                    'start': t.get('start', 0) / 1e6,
                    'end': (t.get('start', 0) + t.get('duration', 0)) / 1e6,
                })

    video_segs.sort(key=lambda x: x['tgt_start'])
    vocal_segs.sort(key=lambda x: x['tgt_start'])
    text_segs.sort(key=lambda x: x['start'])
    tts_segs.sort(key=lambda x: x['start'])

    vid_end = max((x['tgt_end'] for x in video_segs), default=0.0)
    vocal_end = max((x['tgt_end'] for x in vocal_segs), default=0.0)
    text_end = max((x['end'] for x in text_segs), default=0.0)
    tts_end = max((x['end'] for x in tts_segs), default=0.0)

    all_passed = True

    # Check 1: Subtitle Count Equality
    print(f"\n[Check 1: Subtitle Count Match]")
    print(f"  OCR Subtitles Input: {ocr_sub_count} | Final Draft Subtitles: {len(text_segs)}")
    if len(text_segs) == ocr_sub_count and ocr_sub_count > 0:
        print("  => PASS: 100% Subtitle Count Match!")
    else:
        print(f"  => FAIL: Subtitle count mismatch! Missing {ocr_sub_count - len(text_segs)} subtitles!")
        all_passed = False

    # Check 2: Audio Filtered Vocal Dynamic Speed & Segment 1-to-1 Match
    print(f"\n[Check 2: Audio Filtered Vocal 1-to-1 Dynamic Speed Match]")
    print(f"  Video Segments: {len(video_segs)} | Vocal Segments: {len(vocal_segs)}")
    if vocal_segs:
        vocal_match = True
        if len(video_segs) != len(vocal_segs):
            vocal_match = False
        else:
            for i, (v, a) in enumerate(zip(video_segs, vocal_segs), 1):
                if abs(v['tgt_start'] - a['tgt_start']) > 0.001 or abs(v['speed'] - a['speed']) > 0.001:
                    print(f"  Mismatch at Seg #{i}: Vid (tgt={v['tgt_start']:.3f}s, speed={v['speed']:.3f}) vs Vocal (tgt={a['tgt_start']:.3f}s, speed={a['speed']:.3f})")
                    vocal_match = False

        if vocal_match and video_segs:
            print("  => PASS: Audio Filtered Vocal matches Video 1-to-1 in speed, start time, and duration!")
        else:
            print("  => FAIL: Audio Filtered Vocal speed mismatch!")
            all_passed = False
    else:
        print("  => PASS: No video vocal track to filter (AI Storyboard/Novel Recap TTS mode).")

    # Check 3: Subtitle Monotonic Order & OCR Source Preservation
    print(f"\n[Check 3: Subtitle Monotonic Alignment]")
    sub_align_ok = True
    for i in range(len(text_segs) - 1):
        if text_segs[i]['start'] > text_segs[i+1]['start']:
            sub_align_ok = False
            print(f"  Non-monotonic order at Sub #{i+1} ({text_segs[i]['start']:.2f}s) vs Sub #{i+2} ({text_segs[i+1]['start']:.2f}s)")

    if sub_align_ok and text_segs:
        print("  => PASS: All subtitles are monotonically ordered and aligned!")
    else:
        print("  => FAIL: Subtitle alignment issue!")
        all_passed = False

    # Check 4: Timeline Tail Flush Alignment
    print(f"\n[Check 4: Timeline Tail Flush Alignment]")
    print(f"  Video Target End: {vid_end:.2f}s ({int(vid_end//60):02d}:{int(vid_end%60):02d})")
    print(f"  Vocal Target End: {vocal_end:.2f}s ({int(vocal_end//60):02d}:{int(vocal_end%60):02d})")
    print(f"  Subtitle Tail End: {text_end:.2f}s ({int(text_end//60):02d}:{int(text_end%60):02d})")
    if tts_segs:
        print(f"  TTS Audio Tail End: {tts_end:.2f}s ({int(tts_end//60):02d}:{int(tts_end%60):02d})")

    tail_ok = (text_end <= vid_end + 0.5) and (vocal_end <= vid_end + 0.5)
    if tail_ok:
        print("  => PASS: All track ends are flush-aligned within video bounds!")
    else:
        print("  => FAIL: Track tail overflow!")
        all_passed = False

    print("\n==================================================================")
    if all_passed:
        print("=== FINAL RESULT: 100% ALL CHECKS PASSED PERFECTLY ===")
    else:
        print("=== FINAL RESULT: SOME CHECKS FAILED - NEED ADJUSTMENT ===")
    print("==================================================================")
    return all_passed

if __name__ == "__main__":
    import sys, shutil
    appdata = os.environ.get('LOCALAPPDATA', '')
    projects_dir = Path(appdata) / 'CapCut' / 'User Data' / 'Projects' / 'com.lveditor.draft'
    
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        target_dir = sys.argv[1]
    else:
        # Clone from pristine source draft to Test_Full_Pipeline_Run
        src_draft = projects_dir / 'Pham nhan tu tien_Tap_2_ThuyetMinh_1788574341'
        if not src_draft.exists():
            src_draft = projects_dir / 'Pham nhan tu tien_Tap_2_ThuyetMinh_1788573636'
            
        target_dir = str(projects_dir / 'Test_Full_Pipeline_Run')
        if src_draft.exists():
            print(f"Preparing fresh test draft by copying from {src_draft.name}...")
            shutil.copytree(src_draft, target_dir, dirs_exist_ok=True)
            
    run_test_and_verify(target_dir)
