import os, json, sys
sys.stdout.reconfigure(encoding='utf-8')

appdata = os.environ.get('LOCALAPPDATA', '')
draft_dir = os.path.join(appdata, 'CapCut', 'User Data', 'Projects', 'com.lveditor.draft', '00000000000')

paths = []
for root, _, files in os.walk(draft_dir):
    for f in files:
        if f == 'draft_content.json':
            paths.append(os.path.join(root, f))

if not paths:
    print("No draft_content.json found")
    sys.exit(1)

p = paths[0]
d = json.load(open(p, encoding='utf-8'))
materials = d.get('materials', {})
texts_map = {t.get('id'): t.get('recognize_text') or t.get('text') or '' for t in materials.get('texts', [])}

text_segs = []
for tr in d.get('tracks', []):
    if tr.get('type') == 'text':
        for s in tr.get('segments', []):
            st = s.get('target_timerange', {}).get('start', 0)
            dur = s.get('target_timerange', {}).get('duration', 0)
            txt = texts_map.get(s.get('material_id'), '')
            text_segs.append((st, dur, txt))

text_segs.sort(key=lambda x: x[0])

def to_ts(us):
    s = us / 1e6
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    ms = int(round((s - int(s)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"

srt_lines = []
for idx, (st, dur, txt) in enumerate(text_segs, 1):
    srt_lines.append(f"{idx}\n{to_ts(st)} --> {to_ts(st+dur)}\n{txt}\n")

srt_content = "\n".join(srt_lines)

out_workspace = os.path.abspath("capcut_draft_subtitles.srt")
with open(out_workspace, "w", encoding="utf-8") as f:
    f.write(srt_content)

out_draft = os.path.join(draft_dir, "capcut_draft_subtitles.srt")
with open(out_draft, "w", encoding="utf-8") as f:
    f.write(srt_content)

print(f"✅ Đã xuất tệp SRT mới nhất thành công!")
print(f"📍 File local workspace: {out_workspace}")
print(f"📊 Tổng số câu phụ đề: {len(text_segs)}")
