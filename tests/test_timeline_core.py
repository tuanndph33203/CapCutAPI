import unittest
from timeline.models import VideoSegment, SubtitleSegment, AudioSegment
from timeline.compiler import compile_timeline
from timeline.mapper import map_source_to_target, map_target_to_source
from operations.split import split_video_segments
from operations.speed import apply_speed_dynamic
from operations.mirror import apply_mirror
from operations.crop import apply_scale_crop_dynamic
from operations.color import apply_color_adjustments_dynamic

class TestTimelineCore(unittest.TestCase):
    def test_models_and_compiler(self):
        # 1. Create a segment
        seg = VideoSegment(
            id="v1",
            material_id="mat1",
            src_start=1000000,
            src_duration=5000000,
            trim_left=100000,
            trim_right=200000,
            speed=2.0
        )
        
        # 2. Compile segment
        compile_timeline([seg])
        
        # effective_source = 5000000 - 100000 - 200000 = 4700000
        # effective_target = 4700000 / 2.0 = 2350000
        self.assertEqual(seg.target_start, 0)
        self.assertEqual(seg.target_duration, 2350000)

    def test_operations(self):
        seg = VideoSegment(
            id="v1",
            material_id="mat1",
            src_start=0,
            src_duration=10000000,
            trim_left=0,
            trim_right=0,
            speed=1.0
        )
        
        # Test split operation
        split_segs = split_video_segments([seg], cut_points=[4000000], micro_trim_us=200000)
        self.assertEqual(len(split_segs), 2)
        
        self.assertEqual(split_segs[0].src_start, 0)
        self.assertEqual(split_segs[0].src_duration, 4000000)
        self.assertEqual(split_segs[0].trim_right, 200000)
        
        self.assertEqual(split_segs[1].src_start, 4000000)
        self.assertEqual(split_segs[1].src_duration, 6000000)
        self.assertEqual(split_segs[1].trim_right, 0)

    def test_mapper(self):
        segs = [
            VideoSegment(
                id="v1",
                material_id="mat1",
                src_start=0,
                src_duration=5000000,
                trim_left=0,
                trim_right=1000000, # plays 0 -> 4000000
                speed=1.0,
                target_start=0,
                target_duration=4000000
            ),
            VideoSegment(
                id="v2",
                material_id="mat1",
                src_start=5000000,
                src_duration=5000000,
                trim_left=1000000, # plays 6000000 -> 10000000
                trim_right=0,
                speed=2.0,
                target_start=4000000,
                target_duration=2000000 # plays in target 4000000 -> 6000000
            )
        ]
        
        # Test mapping source to target within seg 1
        mapped_tgt = map_source_to_target(2000000, segs)
        self.assertEqual(mapped_tgt.target, 2000000)
        self.assertEqual(mapped_tgt.ratio, 1.0)
        
        # Test mapping source in trimmed gap (should map to start of next segment)
        mapped_tgt = map_source_to_target(4500000, segs)
        self.assertEqual(mapped_tgt.target, 4000000)
        
        # Test mapping source inside seg 2
        # source = 7000000 (which is start + trim_left + 1000000 offset)
        # target should be target_start + 1000000 / 2.0 = 4500000
        mapped_tgt = map_source_to_target(7000000, segs)
        self.assertEqual(mapped_tgt.target, 4500000)
        self.assertEqual(mapped_tgt.ratio, 0.5)

        # Test reverse mapping
        mapped_src = map_target_to_source(4500000, segs)
        self.assertEqual(mapped_src.source, 7000000)
        self.assertEqual(mapped_src.ratio, 2.0)

    def test_pipeline_phases_6_10(self):
        draft_mock = {
            "materials": {
                "speeds": [
                    {"id": "speed_v1", "speed": 1.0, "type": "speed"}
                ],
                "videos": [
                    {"id": "video_mat", "path": "test.mp4"}
                ]
            },
            "tracks": [
                {
                    "type": "video",
                    "name": "video",
                    "segments": [
                        {
                            "id": "v1",
                            "material_id": "video_mat",
                            "source_timerange": {"start": 0, "duration": 10000000},
                            "target_timerange": {"start": 0, "duration": 10000000},
                            "extra_material_refs": ["speed_v1"],
                            "speed": 1.0
                        }
                    ]
                },
                {
                    "type": "text",
                    "name": "sub",
                    "segments": [
                        {
                            "id": "s1",
                            "target_timerange": {"start": 1000000, "duration": 2000000},
                            "_ocr_source_start": 1000000,
                            "_ocr_source_duration": 2000000
                        }
                    ]
                }
            ]
        }
        
        # 1. Parse draft (Phase 2)
        from timeline.parser import parse_draft
        video_segs, subtitle_segs, audio_segs = parse_draft(draft_mock)
        
        # 2. Compile video timeline (Phase 4)
        from timeline.compiler import compile_timeline
        compile_timeline(video_segs)
        
        # 3. Compile subtitles (Phase 6)
        from subtitle.compiler import compile_subtitles
        compile_subtitles(subtitle_segs, video_segs)
        
        # 4. Compile audio (Phase 7)
        from audio.compiler import compile_audio
        compile_audio(audio_segs, video_segs)
        
        # 5. Validate (Phase 9)
        from timeline.validator import validate_timeline
        validate_timeline(video_segs, subtitle_segs, audio_segs)
        
        # 6. Exporter (Phase 8)
        from timeline.exporter import export_draft
        export_draft(draft_mock, video_segs, subtitle_segs, audio_segs)
        
        # 7. Debug Dump (Phase 10)
        from debug.timeline_dump import dump_stage_timeline, dump_subtitle_debug, dump_audio_debug
        dump_stage_timeline("test_dump.json", video_segs)
        dump_subtitle_debug("test_sub_dump.json", subtitle_segs)
        dump_audio_debug("test_aud_dump.json", audio_segs)

if __name__ == '__main__':
    unittest.main()
