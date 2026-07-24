import os, sys, json
sys.path.append('.')

draft_root = os.path.expanduser('~') + r'\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft'
for root, dirs, files in os.walk(draft_root):
    for f in files:
        if f == 'draft_content.json':
            full_p = os.path.join(root, f)
            print('\n=== FOUND DRAFT JSON:', full_p, '===')
            try:
                data = json.load(open(full_p, encoding='utf-8'))
                for tr in data.get('tracks', []):
                    t_type = tr.get('type')
                    t_name = tr.get('name')
                    segs = tr.get('segments', [])
                    print(f'Track type={t_type}, name="{t_name}", segs={len(segs)}')
                    if t_type == 'text':
                        for i, s in enumerate(segs[:5], 1):
                            t = s.get('target_timerange', {})
                            print(f'  Sub #{i}: start={t.get("start",0)/1e6:.2f}s, dur={t.get("duration",0)/1e6:.2f}s, _ocr_src={s.get("_ocr_source_start",0)/1e6:.2f}s')
            except Exception as e:
                print('Error reading:', e)
