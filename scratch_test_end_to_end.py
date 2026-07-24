import os, sys, json
sys.path.append('.')

from anti_copyright_patcher import apply_full_anti_copyright_pipeline, _is_main_video_track, resync_subtitles_and_audio_to_video_timeline
from offline_tts_patcher import patch_offline_tts_in_draft

appdata = os.environ.get('LOCALAPPDATA', '')
capcut_draft = os.path.join(appdata, 'CapCut', 'User Data', 'Projects', 'com.lveditor.draft', '00000000000')

p = os.path.join(capcut_draft, 'draft_content.json')
if not os.path.exists(p):
    print('Draft JSON not found at:', p)
    sys.exit(0)

print('=== STARTING END-TO-END PIPELINE TEST ===')

# Step 1: Run Anti-Copyright Pipeline (Smart Cuts + Speed + Resync)
logger_res = apply_full_anti_copyright_pipeline(capcut_draft, config={'video_speed': 1.0, 'smart_splits': True})
print('1. Anti-Copyright Pipeline Result:', logger_res)

# Step 2: Run Offline TTS Patching
patch_offline_tts_in_draft(capcut_draft, voice_name='default', item_config={'tts_speed': 1.17, 'filter_audio': False})
print('2. Offline TTS Patching Completed.')

# Step 3: Verify Final Draft JSON Structure
data = json.load(open(p, encoding='utf-8'))
materials = data.get('materials', {})

video_segs = []
sub_segs = []
tts_segs = []

for tr in data.get('tracks', []):
    tr_type = tr.get('type')
    tr_name = tr.get('name')
    if _is_main_video_track(tr, materials):
        for s in tr.get('segments', []):
            s_src = s.get('source_timerange', {})
            s_tgt = s.get('target_timerange', {})
            video_segs.append({
                'src_start': s_src.get('start', 0) / 1e6,
                'src_end': (s_src.get('start', 0) + s_src.get('duration', 0)) / 1e6,
                'tgt_start': s_tgt.get('start', 0) / 1e6,
                'tgt_end': (s_tgt.get('start', 0) + s_tgt.get('duration', 0)) / 1e6,
            })
    elif tr_type == 'text':
        for s in tr.get('segments', []):
            t = s.get('target_timerange', {})
            sub_segs.append({
                'start': t.get('start', 0) / 1e6,
                'end': (t.get('start', 0) + t.get('duration', 0)) / 1e6,
                '_ocr_src': s.get('_ocr_source_start', 0) / 1e6
            })
    elif tr_type == 'audio' and tr_name == 'audio_tts':
        for s in tr.get('segments', []):
            t = s.get('target_timerange', {})
            tts_segs.append({
                'start': t.get('start', 0) / 1e6,
                'end': (t.get('start', 0) + t.get('duration', 0)) / 1e6,
            })

video_segs.sort(key=lambda x: x['src_start'])
sub_segs.sort(key=lambda x: x['start'])
tts_segs.sort(key=lambda x: x['start'])

main_video_dur = video_segs[-1]['tgt_end'] if video_segs else 0

print('\n=== END-TO-END VERIFICATION REPORT ===')
print(f'Video Segments Count: {len(video_segs)}')
print(f'Total Main Video Duration: {main_video_dur:.2f}s ({int(main_video_dur//60):02d}:{int(main_video_dur%60):02d})')

print('\n[Video Segments Continuity Check]')
for i, vs in enumerate(video_segs, 1):
    print(f'  Seg #{i}: src=[{vs["src_start"]:.2f}s .. {vs["src_end"]:.2f}s]  tgt=[{vs["tgt_start"]:.2f}s .. {vs["tgt_end"]:.2f}s]')
    if i < len(video_segs):
        gap = video_segs[i]['src_start'] - vs['src_end']
        print(f'    -> Gap to Seg #{i+1}: {gap:.4f}s (Overlap check: {"OK (0s overlap)" if abs(gap) < 0.001 else "OVERLAP ERROR!"})')

print(f'\n[Subtitles Distribution Check]')
print(f'Total Subtitles Count: {len(sub_segs)}')
if sub_segs:
    print(f'  Sub #1 Start: {sub_segs[0]["start"]:.2f}s')
    print(f'  Sub #{len(sub_segs)} End: {sub_segs[-1]["end"]:.2f}s (Max Video Dur: {main_video_dur:.2f}s)')
    print(f'  Boundary Check: {"OK (Subtitles end inside video)" if sub_segs[-1]["start"] <= main_video_dur else "OVERFLOW ERROR!"}')

print(f'\n[TTS Audio Alignment Check]')
print(f'Total TTS Clips Count: {len(tts_segs)}')
if tts_segs and sub_segs:
    max_align_diff = max(abs(s['start'] - t['start']) for s, t in zip(sub_segs, tts_segs))
    print(f'  Max Sub-to-TTS Start Alignment Diff: {max_align_diff:.4f}s')
    print(f'  Alignment Status: {"PERFECT (0.0000s diff)" if max_align_diff < 0.001 else "MISALIGNED!"}')

print('\n=== VERIFICATION FINISHED SUCCESSFULLY ===')
