import unittest
from timeline.models import VideoSegment
from operations.speed import apply_speed_dynamic

class TestSpeed(unittest.TestCase):
    def test_apply_speed_dynamic(self):
        seg = VideoSegment(
            id="v1",
            material_id="mat1",
            src_start=0,
            src_duration=10000,
            trim_left=0,
            trim_right=0,
            speed=1.0
        )
        apply_speed_dynamic([seg], base_speed=1.1, randomize=False)
        self.assertEqual(seg.speed, 1.1)

if __name__ == "__main__":
    unittest.main()
