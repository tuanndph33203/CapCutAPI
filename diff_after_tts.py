import json, os, sys, re
sys.stdout.reconfigure(encoding='utf-8')

DRAFT = r"C:\Users\nguye\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\00000000000"
SNAP  = r"C:\Users\nguye\Projects\CapCutAPI\.gemini\draft_before_tts.json"

snap = json.load(open(SNAP, encoding="utf-8"))
old_ids = set(snap["audio_mat_ids"])

# Check ALL Timelines subfolders
tl_root = os.path.join(DRAFT, "Timelines")
for d_name in os.listdir(tl_root):
    tl_json = os.path.join(tl_root, d_name, "draft_content.json")
    if not os.path.exists(tl_json):
        continue
    d2 = json.load(open(tl_json, encoding="utf-8"))
    new_a = [a for a in d2.get("materials", {}).get("audios", []) if a["id"] not in old_ids]
    new_t = [t for t in d2.get("tracks", []) if t.get("type") == "audio"]
    print(f"\n=== TIMELINE: {d_name} ===")
    print(f"  draft_content id: {d2.get('id')}")
    print(f"  Total audios: {len(d2.get('materials',{}).get('audios',[]))}, NEW: {len(new_a)}")
    print(f"  Audio tracks: {len(new_t)}")
    for a in new_a:
        print(f"\n  --- NEW AUDIO MATERIAL ---")
        print(json.dumps(a, ensure_ascii=False, indent=4))
    for t in new_t:
        segs = t.get("segments", [])
        print(f"\n  --- AUDIO TRACK: name={t.get('name')} segments={len(segs)} ---")
        if segs:
            print(json.dumps(segs[0], ensure_ascii=False, indent=4))
