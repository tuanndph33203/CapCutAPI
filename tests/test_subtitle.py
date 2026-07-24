import unittest
from timeline.models import VideoSegment, SubtitleSegment
from subtitle.compiler import compile_subtitles

class TestSubtitle(unittest.TestCase):
    def test_compile_subtitles(self):
        segs = [
            VideoSegment(
                id="v1",
                material_id="mat1",
                src_start=0,
                src_duration=500000,
                trim_left=0,
                trim_right=0,
                speed=2.0,
                target_start=0,
                target_duration=250000
            )
        ]
        subs = [
            SubtitleSegment(
                id="s1",
                ocr_source_start=100000,
                ocr_source_duration=100000,
                target_start=0,
                target_duration=0
            )
        ]
        compile_subtitles(subs, segs)
        self.assertEqual(subs[0].target_start, 50000)
        self.assertEqual(subs[0].target_duration, 50000)

if __name__ == "__main__":
    unittest.main()
