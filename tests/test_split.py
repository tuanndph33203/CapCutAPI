import unittest
from timeline.models import VideoSegment
from operations.split import split_video_segments

class TestSplit(unittest.TestCase):
    def test_split_video_segments(self):
        seg = VideoSegment(
            id="v1",
            material_id="mat1",
            src_start=0,
            src_duration=10000,
            trim_left=0,
            trim_right=0,
            speed=1.0
        )
        splits = split_video_segments([seg], [3000], micro_trim_us=200)
        self.assertEqual(len(splits), 2)
        self.assertEqual(splits[0].src_duration, 3000)
        self.assertEqual(splits[0].trim_right, 200)
        self.assertEqual(splits[1].src_start, 3000)
        self.assertEqual(splits[1].src_duration, 7000)

if __name__ == "__main__":
    unittest.main()
