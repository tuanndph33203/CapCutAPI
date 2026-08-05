import os
import sys
import json
import shutil
import uuid

# Ensure UTF-8 output encoding for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from offline_tts_patcher import patch_offline_tts_in_draft

def test_pipeline_patcher():
    print("=" * 60)
    print("🧪 TESTING OFFLINE TTS PATCHER IN DRAFT PIPELINE")
    print("=" * 60)

    test_draft_dir = os.path.join(os.path.dirname(__file__), "scratch", "test_mock_draft")
    os.makedirs(test_draft_dir, exist_ok=True)
    json_path = os.path.join(test_draft_dir, "draft_content.json")

    # Create mock draft_content.json with translated text materials and text track
    mat_id1 = str(uuid.uuid4()).upper()
    mat_id2 = str(uuid.uuid4()).upper()
    seg_id1 = str(uuid.uuid4()).upper()
    seg_id2 = str(uuid.uuid4()).upper()
    text_track_id = str(uuid.uuid4()).upper()

    mock_data = {
        "canvas_config": {"ratio": "16:9", "width": 1920, "height": 1080},
        "materials": {
            "audios": [],
            "speeds": [],
            "texts": [
                {
                    "id": mat_id1,
                    "type": "text",
                    "content": json.dumps({"text": "Xin chào, đây là câu phụ đề thứ nhất được ghép nối tự động."})
                },
                {
                    "id": mat_id2,
                    "type": "text",
                    "content": json.dumps({"text": "Đây là câu phụ đề thứ hai tạo giọng đọc offline qua NGHI-TTS."})
                }
            ]
        },
        "tracks": [
            {
                "id": text_track_id,
                "type": "text",
                "name": "text_subtitles",
                "segments": [
                    {
                        "id": seg_id1,
                        "material_id": mat_id1,
                        "target_timerange": {"start": 0, "duration": 2000000}
                    },
                    {
                        "id": seg_id2,
                        "material_id": mat_id2,
                        "target_timerange": {"start": 2500000, "duration": 3000000}
                    }
                ]
            }
        ]
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(mock_data, f, ensure_ascii=False, indent=4)

    print(f"📝 Created mock draft at: {test_draft_dir}")

    # Run patch_offline_tts_in_draft
    success = patch_offline_tts_in_draft(test_draft_dir, voice_name="Ngọc Huyền (mới)")
    assert success, "patch_offline_tts_in_draft returned False"

    # Verify patched draft_content.json
    with open(json_path, "r", encoding="utf-8") as f:
        patched_data = json.load(f)

    audios = patched_data["materials"]["audios"]
    tracks = patched_data["tracks"]
    audio_tracks = [t for t in tracks if t.get("type") == "audio"]

    print(f"\n📊 VERIFICATION RESULTS:")
    print(f"   Audio materials created : {len(audios)}")
    print(f"   Audio tracks present    : {len(audio_tracks)}")
    
    assert len(audios) == 2, f"Expected 2 audio materials, got {len(audios)}"
    assert len(audio_tracks) >= 1, "No audio track created"
    
    tts_segments = audio_tracks[0]["segments"]
    print(f"   TTS Audio segments count: {len(tts_segments)}")
    assert len(tts_segments) == 2, f"Expected 2 audio segments, got {len(tts_segments)}"

    for idx, seg in enumerate(tts_segments, 1):
        mat_id = seg["material_id"]
        mat = next((a for a in audios if a["id"] == mat_id), None)
        assert mat is not None, f"Material {mat_id} not found"
        wav_file = mat["path"]
        print(f"   Segment {idx}: Start={seg['target_timerange']['start']/1e6}s, Duration={seg['target_timerange']['duration']/1e6}s")
        print(f"              WAV={wav_file} ({os.path.getsize(wav_file):,} bytes)")
        assert os.path.exists(wav_file)
        assert os.path.getsize(wav_file) > 0

    print("\n" + "=" * 60)
    print("🎉 ALL PIPELINE TTS PATCHER TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_pipeline_patcher()
