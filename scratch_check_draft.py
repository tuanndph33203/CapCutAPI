import os, sys, json
sys.path.append('.')

appdata = os.environ.get('LOCALAPPDATA', '')
capcut_draft = os.path.join(appdata, 'CapCut', 'User Data', 'Projects', 'com.lveditor.draft', '00000000000')

p = os.path.join(capcut_draft, 'draft_content.json')
if not os.path.exists(p):
    print('Draft JSON not found at:', p)
    sys.exit(0)

data = json.load(open(p, encoding='utf-8'))
materials = data.get('materials', {})

print('=== DRAFT DETAILED ANALYSIS ===')
print('Draft Path:', p)
print('Tracks Count:', len(data.get('tracks', [])))

for tr_idx, tr in enumerate(data.get('tracks', []), 1):
    tr_type = tr.get('type')
    tr_name = tr.get('name')
    segs = tr.get('segments', [])
    print(f'\nTrack #{tr_idx}: type={tr_type}, name="{tr_name}", segments={len(segs)}')
    
    if tr_type == 'video' and 'sticker' not in str(tr_name).lower() and 'gif' not in str(tr_name).lower():
        for i, s in enumerate(segs, 1):
            src = s.get('source_timerange', {})
            tgt = s.get('target_timerange', {})
            print(f'  Vid Seg #{i}: src=[{src.get("start",0)/1e6:.2f}s .. {(src.get("start",0)+src.get("duration",0))/1e6:.2f}s]  tgt=[{tgt.get("start",0)/1e6:.2f}s .. {(tgt.get("start",0)+tgt.get("duration",0))/1e6:.2f}s]')
            
    elif tr_type == 'text':
        print(f'  Total Subtitles: {len(segs)}')
        if segs:
            s_first = segs[0].get('target_timerange', {})
            s_last = segs[-1].get('target_timerange', {})
            print(f'  Sub #1: start={s_first.get("start",0)/1e6:.2f}s, dur={s_first.get("duration",0)/1e6:.2f}s, _ocr_src={segs[0].get("_ocr_source_start", 0)/1e6:.2f}s')
            print(f'  Sub #{len(segs)}: start={s_last.get("start",0)/1e6:.2f}s, dur={s_last.get("duration",0)/1e6:.2f}s, _ocr_src={segs[-1].get("_ocr_source_start", 0)/1e6:.2f}s')

    elif tr_type == 'audio' and tr_name == 'audio_tts':
        print(f'  Total TTS Clips: {len(segs)}')
        if segs:
            t_first = segs[0].get('target_timerange', {})
            t_last = segs[-1].get('target_timerange', {})
            print(f'  TTS Clip #1: start={t_first.get("start",0)/1e6:.2f}s, dur={t_first.get("duration",0)/1e6:.2f}s, _ocr_src={segs[0].get("_ocr_source_start", 0)/1e6:.2f}s')
            print(f'  TTS Clip #{len(segs)}: start={t_last.get("start",0)/1e6:.2f}s, dur={t_last.get("duration",0)/1e6:.2f}s, _ocr_src={segs[-1].get("_ocr_source_start", 0)/1e6:.2f}s')

    elif tr_type == 'audio' and tr_name == 'audio_filtered_vocal':
        print(f'  Total Filtered Vocal Segments: {len(segs)}')
        if segs:
            v_last = segs[-1].get('target_timerange', {})
            print(f'  Vocal End: {(v_last.get("start",0)+v_last.get("duration",0))/1e6:.2f}s')
