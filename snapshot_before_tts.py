"""
Bước 1: Chạy script này TRƯỚC khi tạo TTS trong CapCut để snapshot.
"""
import json, os, sys, shutil
sys.stdout.reconfigure(encoding='utf-8')

DRAFT = r"C:\Users\nguye\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\00000000000"
SNAP  = r"C:\Users\nguye\Projects\CapCutAPI\.gemini\draft_before_tts.json"

d = json.load(open(os.path.join(DRAFT, "draft_content.json"), encoding="utf-8"))

# Lưu danh sách ID audio materials + tracks hiện tại
before = {
    "audio_mat_ids": [a["id"] for a in d.get("materials", {}).get("audios", [])],
    "audio_track_ids": [t["id"] for t in d.get("tracks", []) if t.get("type") == "audio"],
    "full": d
}
with open(SNAP, "w", encoding="utf-8") as f:
    json.dump(before, f, ensure_ascii=False, indent=2)

print(f"OK: snapshot saved -> {SNAP}")
print(f"  Audio materials truoc: {len(before['audio_mat_ids'])}")
print(f"  Audio tracks truoc:    {len(before['audio_track_ids'])}")
print()
print("Gio ban mo CapCut, vao du an 00000000000.")
print("Chon 1 subtitle, nhan Text -> Text to speech -> chon giong -> Apply.")
print("Sau do DONG CapCut lai va chay script diff_after_tts.py")
