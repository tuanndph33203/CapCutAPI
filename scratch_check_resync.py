import os, sys, json
sys.path.append('.')
from anti_copyright_patcher import resync_subtitles_and_audio_to_video_timeline, _is_main_video_track

appdata = os.environ.get('LOCALAPPDATA', '')
capcut_draft = os.path.join(appdata, 'CapCut', 'User Data', 'Projects', 'com.lveditor.draft', '00000000000')

p = os.path.join(capcut_draft, 'draft_content.json')
data = json.load(open(p, encoding='utf-8'))

# Clear all _resynced markers and _resync_version so we can do a fresh test
cleared = 0
for tr in data.get('tracks', []):
    for seg in tr.get('segments', []):
        if '_resynced' in seg:
            del seg['_resynced']
            cleared += 1
if '_resync_version' in data:
    del data['_resync_version']
print(f'Cleared {cleared} _resynced markers')

# Restore sub timestamps from VIDEO source_timerange space (simulate fresh OCR state)
# The raw OCR sub timestamps should be from source video time, not target time.
# Current state: subs are already at wrong "accumulated" target times from previous bad resync.
# We cannot restore original OCR timestamps without a fresh OCR run.
# Instead, let's just check what the current sub starts look like vs video src/tgt:
materials = data.get('materials', {})
print('\n=== VIDEO SEGMENTS ===')
for tr in data.get('tracks', []):
    if _is_main_video_track(tr, materials):
        for i, s in enumerate(tr.get('segments', []), 1):
            src = s.get('source_timerange', {})
            tgt = s.get('target_timerange', {})
            print(f'  Vid {i}: src=[{src.get("start",0)/1e6:.2f}s..{(src.get("start",0)+src.get("duration",0))/1e6:.2f}s]  tgt=[{tgt.get("start",0)/1e6:.2f}s..{(tgt.get("start",0)+tgt.get("duration",0))/1e6:.2f}s]')

sub_starts = []
for tr in data.get('tracks', []):
    if tr.get('type') == 'text':
        for seg in tr.get('segments', []):
            t = seg.get('target_timerange', {})
            sub_starts.append(t.get('start', 0) / 1_000_000)
sub_starts.sort()
print(f'\n=== Current sub starts (count={len(sub_starts)}): ===')
print([f'{v:.2f}s' for v in sub_starts])

with open(p, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)
print('\nCleared markers and saved. Now running resync...')

count = resync_subtitles_and_audio_to_video_timeline(capcut_draft)
print(f'Resynced {count} segments')

data2 = json.load(open(p, encoding='utf-8'))
sub_after = []
for tr in data2.get('tracks', []):
    if tr.get('type') == 'text':
        for seg in tr.get('segments', []):
            t = seg.get('target_timerange', {})
            sub_after.append(t.get('start', 0) / 1_000_000)
sub_after.sort()
print(f'\n=== Sub starts AFTER resync (count={len(sub_after)}): ===')
print([f'{v:.2f}s' for v in sub_after])
