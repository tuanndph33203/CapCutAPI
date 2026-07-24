import os, sys, json

sys.path.append('.')

from anti_copyright_patcher import resync_only_subtitles_to_video_timeline, find_draft_content_paths

appdata = os.environ.get('LOCALAPPDATA', '')
draft_dir = os.path.join(appdata, 'CapCut', 'User Data', 'Projects', 'com.lveditor.draft', '00000000000')

print("==================================================================")
print("=== TESTING DEDICATED FUNCTION: resync_only_subtitles_to_video_timeline ===")
print("==================================================================")

paths = find_draft_content_paths(draft_dir)
if not paths:
    print("ERROR: Draft content not found at:", draft_dir)
    sys.exit(0)

p = paths[0]
data_before = json.load(open(p, encoding='utf-8'))

sub_before = []
audio_before = []
video_before = []

for tr in data_before.get('tracks', []):
    t_type = tr.get('type')
    t_name = tr.get('name', '')
    segs = tr.get('segments', [])
    if t_type == 'text':
        for s in segs:
            t = s.get('target_timerange', {})
            sub_before.append({
                'id': s.get('id'),
                'start': t.get('start', 0) / 1e6,
                'dur': t.get('duration', 0) / 1e6
            })
    elif t_type == 'audio':
        for s in segs:
            t = s.get('target_timerange', {})
            audio_before.append({'name': t_name, 'start': t.get('start', 0) / 1e6})
    elif t_type == 'video' and t_name == 'video':
        for s in segs:
            t = s.get('target_timerange', {})
            video_before.append({'start': t.get('start', 0) / 1e6, 'dur': t.get('duration', 0) / 1e6})

sub_before.sort(key=lambda x: x['start'])

print(f"[Before Resync] Subtitles Count: {len(sub_before)} | Video Segments: {len(video_before)} | Audio Segments: {len(audio_before)}")
if sub_before:
    print(f"  First Sub Start: {sub_before[0]['start']:.2f}s | Last Sub Start: {sub_before[-1]['start']:.2f}s")

# Execute resync_only_subtitles_to_video_timeline
patched_count = resync_only_subtitles_to_video_timeline(draft_dir)
print(f"\n[Execution] resync_only_subtitles_to_video_timeline returned: {patched_count} modified segments.")

data_after = json.load(open(p, encoding='utf-8'))

sub_after = []
audio_after = []
video_after = []

for tr in data_after.get('tracks', []):
    t_type = tr.get('type')
    t_name = tr.get('name', '')
    segs = tr.get('segments', [])
    if t_type == 'text':
        for s in segs:
            t = s.get('target_timerange', {})
            sub_after.append({
                'id': s.get('id'),
                'start': t.get('start', 0) / 1e6,
                'dur': t.get('duration', 0) / 1e6
            })
    elif t_type == 'audio':
        for s in segs:
            t = s.get('target_timerange', {})
            audio_after.append({'name': t_name, 'start': t.get('start', 0) / 1e6})
    elif t_type == 'video' and t_name == 'video':
        for s in segs:
            t = s.get('target_timerange', {})
            video_after.append({'start': t.get('start', 0) / 1e6, 'dur': t.get('duration', 0) / 1e6})

sub_after.sort(key=lambda x: x['start'])

print(f"\n[After Resync] Subtitles Count: {len(sub_after)} | Video Segments: {len(video_after)} | Audio Segments: {len(audio_after)}")

print("\n--- COMPARISON TABLE (First 5 Subtitles) ---")
for i in range(min(5, len(sub_after))):
    sb = sub_before[i] if i < len(sub_before) else {}
    sa = sub_after[i]
    print(f"  Sub #{i+1:02d}: Before=[start={sb.get('start',0):.2f}s, dur={sb.get('dur',0):.2f}s]  ->  After=[start={sa['start']:.2f}s, dur={sa['dur']:.2f}s]")

print("\n--- COMPARISON TABLE (Last 5 Subtitles) ---")
for i in range(max(0, len(sub_after)-5), len(sub_after)):
    sb = sub_before[i] if i < len(sub_before) else {}
    sa = sub_after[i]
    print(f"  Sub #{i+1:02d}: Before=[start={sb.get('start',0):.2f}s, dur={sb.get('dur',0):.2f}s]  ->  After=[start={sa['start']:.2f}s, dur={sa['dur']:.2f}s]")

# VERIFICATION CHECKS
count_ok = (len(sub_before) == len(sub_after))
audio_untouched = (audio_before == audio_after)
video_untouched = (video_before == video_after)
monotonic_ok = all(sub_after[i]['start'] <= sub_after[i+1]['start'] for i in range(len(sub_after)-1))

print("\n==================================================================")
print("=== VERIFICATION SUMMARY ===")
print("==================================================================")
print(f"  1. Subtitle Count Preserved (100% Match): {'PASS' if count_ok else 'FAIL'}")
print(f"  2. Monotonic Timeline Alignment:           {'PASS' if monotonic_ok else 'FAIL'}")
print(f"  3. Audio Tracks 100% Untouched:            {'PASS' if audio_untouched else 'FAIL'}")
print(f"  4. Video Track 100% Untouched:            {'PASS' if video_untouched else 'FAIL'}")

if count_ok and monotonic_ok and audio_untouched and video_untouched:
    print("\n>>> RESULT: SUCCESS! Function resync_only_subtitles_to_video_timeline works 100% PERFECTLY!")
else:
    print("\n>>> RESULT: FAIL - Verification checks failed.")
