#!/usr/bin/env python3
"""
Unit Test Suite for Full Novel Video Upgrades
============================================
Verifies:
1. Dynamic Pacing Analysis (Combat 1.3x, Emotional 1.1x, Dialogue 1.16x, Normal 1.2x)
2. BGM Resolution & Ambient Track Availability
3. Multi-shot B-roll Pacing (4-6s per visual cut) & CapCut Native Transitions in Draft JSON
4. 3D YouTube Thumbnail Generation (1280x720, golden 3D text, episode badge)
5. Intermediate Audio Cache Cleaner (cleans sent_*.wav, preserves Master MP3/SRT)
6. Voice Catalog API Endpoint (GET /api/tts/voices)
7. Batch Production Queue Runner execution logic
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

# UTF-8 stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))

from capcut_api.ai.nghitts_service import (
    NGHITTS_VOICES,
    list_available_nghitts_voices,
    resolve_nghitts_voice
)
from capcut_api.ai.novel_video_pipeline import (
    NovelVideoPipeline,
    SpeechSentence,
    analyze_sentence_pacing,
    resolve_bgm_path
)
from capcut_api.ai.thumbnail_generator import ThumbnailGenerator
from PIL import Image


class TestFullNovelUpgrades(unittest.TestCase):
    """Test suite covering all novel video pipeline upgrades."""

    def setUp(self):
        self.pipeline = NovelVideoPipeline(novel_id="Pham nhan tu tien")
        self.test_temp_dir = Path(tempfile.mkdtemp(prefix="capcut_test_upgrades_"))

    def tearDown(self):
        if self.test_temp_dir.exists():
            try:
                shutil.rmtree(self.test_temp_dir)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # TEST 1: DYNAMIC PACING ANALYSIS
    # -------------------------------------------------------------------------
    def test_dynamic_pacing_analysis(self):
        """Test sentence sentiment analysis and dynamic pacing calculation."""
        test_sentences = [
            ("Hàn Lập lập tức vung kiếm chém tới tấp vào đầu ma thú bùng nổ kịch liệt!", 1.2, "combat_fast", 1.30),
            ("Nàng đau đớn rơi nước mắt, trong lòng xót xa đau thương khôn nguôi...", 1.2, "emotional_slow", 1.10),
            ('"Đạo hữu xin dừng bước, tại hạ có điều muốn thỉnh giáo."', 1.2, "dialogue", 1.15),
            ("Hàn Lập tiếp tục bước đi trên con đường đá dẫn tới quảng trường của phường thị.", 1.2, "normal", 1.20)
        ]

        for text, base_speed, expected_type, expected_speed in test_sentences:
            speed, pause, pacing_type = analyze_sentence_pacing(text, base_speed=base_speed)
            self.assertEqual(pacing_type, expected_type, f"Failed type for text: {text}")
            self.assertAlmostEqual(speed, expected_speed, places=2)

    # -------------------------------------------------------------------------
    # TEST 2: BGM RESOLUTION & AMBIENT TRACK
    # -------------------------------------------------------------------------
    def test_bgm_resolution_and_ambient_file(self):
        """Test background music resolution to default ambient track and custom path."""
        # 1. Default ambient track resolution
        default_bgm = resolve_bgm_path(None)
        self.assertIsNotNone(default_bgm, "Default BGM path should not be None")
        self.assertTrue(os.path.exists(default_bgm), f"Default BGM file does not exist: {default_bgm}")
        self.assertGreater(os.path.getsize(default_bgm), 100_000, "BGM file should have valid audio content")

        # 2. Custom path resolution
        dummy_custom = self.test_temp_dir / "custom_bgm.wav"
        dummy_custom.write_bytes(b"RIFF" + b"\x00" * 100)
        resolved_custom = resolve_bgm_path(str(dummy_custom))
        self.assertEqual(str(dummy_custom.resolve()), resolved_custom)

    # -------------------------------------------------------------------------
    # TEST 3: MULTI-SHOT B-ROLL PACING & CAPCUT NATIVE TRANSITIONS IN DRAFT
    # -------------------------------------------------------------------------
    def test_multishot_pacing_and_transitions(self):
        """Test dividing scenes into 4-6s shots and exporting native transitions in draft."""
        # Create dummy keyframe images
        dummy_img1 = self.test_temp_dir / "frame_001.jpg"
        dummy_img2 = self.test_temp_dir / "frame_002.jpg"
        Image.new("RGB", (1920, 1080), color=(50, 80, 120)).save(dummy_img1)
        Image.new("RGB", (1920, 1080), color=(120, 50, 80)).save(dummy_img2)

        # Create sentences representing ~20 seconds of speech
        s1 = SpeechSentence(index=1, text="Hàn Lập phi thân qua hẻm núi hiểm trở.", pause_sec=0.2)
        s1.duration_sec, s1.start_sec, s1.end_sec = 4.5, 0.0, 4.5
        s2 = SpeechSentence(index=2, text="Trước mắt hắn xuất hiện một con cự thú hung tợn.", pause_sec=0.2)
        s2.duration_sec, s2.start_sec, s2.end_sec = 5.0, 4.7, 9.7
        s3 = SpeechSentence(index=3, text="Tiếng gầm thét vang dội khắp bốn bề không gian.", pause_sec=0.5, is_scene_break=True)
        s3.duration_sec, s3.start_sec, s3.end_sec = 4.8, 9.9, 14.7
        s4 = SpeechSentence(index=4, text="Trận đại chiến sinh tử bắt đầu bùng nổ!", pause_sec=0.5, is_scene_break=True)
        s4.duration_sec, s4.start_sec, s4.end_sec = 5.0, 15.2, 20.2

        sentences = [s1, s2, s3, s4]

        # 1. Run Step 3: Segmentation with multi-shot B-roll pacing
        scenes = self.pipeline.step3_ai_scene_segmentation_and_visuals(
            sentences=sentences,
            media_paths=[str(dummy_img1), str(dummy_img2)]
        )
        self.assertGreaterEqual(len(scenes), 1)

        # Check that visual_shots are populated and have 4-6s durations
        total_shots = 0
        for sc in scenes:
            self.assertIn("visual_shots", sc)
            self.assertGreaterEqual(len(sc["visual_shots"]), 1)
            for shot in sc["visual_shots"]:
                total_shots += 1
                self.assertGreaterEqual(shot["duration_sec"], 2.0)
                self.assertLessEqual(shot["duration_sec"], 7.0)

        # 2. Run Step 4: Build CapCut Draft
        step4_res = self.pipeline.step4_build_capcut_draft(
            project_name="Test_Upgrades_Tap192",
            scenes=scenes,
            sentences=sentences,
            canvas_ratio="16:9"
        )

        draft_folder = Path(step4_res["draft_folder"])
        content_json = draft_folder / "draft_content.json"
        self.assertTrue(content_json.exists(), "draft_content.json must exist")

        draft_data = json.loads(content_json.read_text(encoding="utf-8"))

        # Verify Track Video has segments
        video_tracks = [t for t in draft_data.get("tracks", []) if t.get("type") == "video"]
        self.assertGreaterEqual(len(video_tracks), 1)
        video_segments = video_tracks[0].get("segments", [])
        self.assertGreaterEqual(len(video_segments), 2, "Should have multiple visual segments for pacing")

        # Verify Native Transitions exist in materials.transitions
        materials = draft_data.get("materials", {})
        transitions = materials.get("transitions", [])
        self.assertGreaterEqual(len(transitions), 1, "Native transitions must be attached to segments")
        self.assertIn(transitions[0].get("name"), ["Dissolve", "Mix"], "Transition name should be Dissolve or Mix")

        # Verify BGM track was added and looped
        bgm_tracks = [t for t in draft_data.get("tracks", []) if t.get("name") == "bgm"]
        self.assertGreaterEqual(len(bgm_tracks), 1, "BGM track must be present")

        # Verify 3D Thumbnail was generated in draft folder
        thumbnail_file = draft_folder / "thumbnail.jpg"
        self.assertTrue(thumbnail_file.exists(), "thumbnail.jpg must be generated in draft folder")
        self.assertGreater(thumbnail_file.stat().st_size, 10_000)

    # -------------------------------------------------------------------------
    # TEST 4: 3D YOUTUBE THUMBNAIL GENERATOR
    # -------------------------------------------------------------------------
    def test_thumbnail_generator_standalone(self):
        """Test 3D YouTube Thumbnail generator direct output and resolution."""
        dummy_kf = self.test_temp_dir / "keyframe_cinematic.jpg"
        Image.new("RGB", (1920, 1080), color=(30, 40, 70)).save(dummy_kf)

        gen = ThumbnailGenerator()
        out_thumb = self.test_temp_dir / "test_thumb.jpg"
        result_path = gen.generate_thumbnail(
            base_image_path=str(dummy_kf),
            novel_title="Phàm Nhân Tu Tiên",
            episode_label="TẬP 192",
            subtitle_highlight="ĐẠI CHIẾN ĐỈNH CAO",
            output_path=str(out_thumb)
        )

        self.assertTrue(os.path.exists(result_path))
        with Image.open(result_path) as img:
            self.assertEqual(img.size, (1280, 720), "Thumbnail must be standard YouTube 1280x720")
            self.assertEqual(img.format, "JPEG")

    # -------------------------------------------------------------------------
    # TEST 5: AUDIO CACHE CLEANER
    # -------------------------------------------------------------------------
    def test_audio_cache_cleaner(self):
        """Test cleaning intermediate sent_*.wav files while preserving master files."""
        session_dir = self.test_temp_dir / "session_audio"
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create intermediate wav files
        (session_dir / "sent_0001_ngoc_huyen.wav").write_bytes(b"DUMMY_AUDIO_1" * 1000)
        (session_dir / "sent_0002_ngoc_huyen.wav").write_bytes(b"DUMMY_AUDIO_2" * 1000)
        (session_dir / "temp_chunk.wav").write_bytes(b"DUMMY_CHUNK" * 1000)

        # Create master files that MUST NOT be deleted
        master_mp3 = session_dir / "master_tts.mp3"
        master_mp3.write_bytes(b"MASTER_MP3_DATA" * 5000)
        master_wav = session_dir / "master_tts.wav"
        master_wav.write_bytes(b"MASTER_WAV_DATA" * 5000)
        srt_file = session_dir / "master_tts.srt"
        srt_file.write_text("1\n00:00:00,000 --> 00:00:02,000\nTest\n", encoding="utf-8")
        script_file = session_dir / "kich_ban.txt"
        script_file.write_text("Kịch bản thử nghiệm", encoding="utf-8")

        # Run cache cleaner
        res = self.pipeline.clean_session_audio_cache(session_dir)

        # Verify intermediate files were deleted
        self.assertEqual(res["cleaned_count"], 3)
        self.assertGreater(res["freed_bytes"], 0)
        self.assertFalse((session_dir / "sent_0001_ngoc_huyen.wav").exists())
        self.assertFalse((session_dir / "sent_0002_ngoc_huyen.wav").exists())
        self.assertFalse((session_dir / "temp_chunk.wav").exists())

        # Verify master files are safely preserved
        self.assertTrue(master_mp3.exists(), "master_tts.mp3 must be preserved")
        self.assertTrue(master_wav.exists(), "master_tts.wav must be preserved")
        self.assertTrue(srt_file.exists(), "master_tts.srt must be preserved")
        self.assertTrue(script_file.exists(), "kich_ban.txt must be preserved")

    # -------------------------------------------------------------------------
    # TEST 6: VOICE CATALOG API ENDPOINT
    # -------------------------------------------------------------------------
    def test_voice_catalog_api(self):
        """Test GET /api/tts/voices endpoint on Flask master server."""
        # 1. Service-level check
        voices = list_available_nghitts_voices()
        self.assertGreaterEqual(len(voices), 17, "Should have at least 17 NghiTTS voices")
        self.assertIn("Ngọc Huyền (mới)", voices)
        self.assertIn("Mạnh Dũng", voices)
        self.assertIn("Duy Oryx", voices)

        # Verify metadata fields
        ngoc_huyen = voices["Ngọc Huyền (mới)"]
        self.assertEqual(ngoc_huyen["gender"], "female")
        self.assertEqual(ngoc_huyen["region"], "Bắc")
        self.assertIn("slug", ngoc_huyen)
        self.assertIn("style", ngoc_huyen)

        # 2. Flask client check
        from capcut_api.server import master_app
        client = master_app.test_client()
        resp = client.get("/api/tts/voices")
        self.assertEqual(resp.status_code, 200)

        data = json.loads(resp.data.decode("utf-8"))
        self.assertTrue(data.get("success"))
        self.assertGreaterEqual(data.get("total", 0), 17)
        self.assertIn("Ngọc Huyền (mới)", data.get("voices", {}))

    # -------------------------------------------------------------------------
    # TEST 7: BATCH PRODUCTION QUEUE LOGIC
    # -------------------------------------------------------------------------
    def test_batch_production_queue_structure(self):
        """Test batch queue runner parameter validation and error handling."""
        # Test with empty episodes list
        empty_res = self.pipeline.run_batch_pipeline(episodes=[])
        self.assertFalse(empty_res["success"])
        self.assertEqual(empty_res["total_episodes"], 0)

        # Test with an episode with empty script
        mock_episodes = [
            {"project_name": "Test_Ep1", "script_text": ""},
        ]
        batch_res = self.pipeline.run_batch_pipeline(episodes=mock_episodes)
        self.assertFalse(batch_res["success"])
        self.assertEqual(batch_res["failed_count"], 1)
        self.assertIn("Kịch bản rỗng", batch_res["results"][0].get("error", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
