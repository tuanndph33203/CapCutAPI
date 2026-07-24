import unittest
from timeline.models import VideoSegment, AudioSegment
from audio.compiler import compile_audio

class TestAudio(unittest.TestCase):
    def test_compile_audio(self):
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
        auds = [
            AudioSegment(
                id="a1",
                material_id="mat2",
                src_start=100000,
                src_duration=100000,
                target_start=0,
                target_duration=0
            )
        ]
        compile_audio(auds, segs)
        self.assertEqual(auds[0].target_start, 50000)
        self.assertEqual(auds[0].target_duration, 50000)

if __name__ == "__main__":
    unittest.main()
